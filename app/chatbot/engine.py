import uuid
import logging
import asyncio 
from typing import Dict, List, Any, Optional, Tuple
import time
from sqlalchemy.orm import Session
from app.knowledge_base.processor import DocumentProcessor
from app.chatbot.chains import create_chatbot_chain
from app.tenants.models import Tenant
from app.knowledge_base.models import KnowledgeBase, FAQ
from app.chatbot.models import ChatSession, ChatMessage
from app.config import settings
from app.utils.language_service import language_service
from app.chatbot.response_simulator import SimpleHumanDelaySimulator
from app.chatbot.memory import EnhancedChatbotMemory
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ChatbotEngine:
    """The main chatbot engine that handles conversations"""
    
    def __init__(self, db: Session):
        self.db = db
        self.active_sessions = {}  # In-memory storage of active chat sessions
        
        # Initialize the delay simulator
        try:
            self.delay_simulator = SimpleHumanDelaySimulator()
        except ImportError:
            logger.warning("SimpleHumanDelaySimulator not available, delay features disabled")
            self.delay_simulator = None

    # ========================== TENANT METHODS ==========================
    
    def _get_tenant(self, tenant_id: int) -> Optional[Tenant]:
        """Get tenant information"""
        return self.db.query(Tenant).filter(Tenant.id == tenant_id, Tenant.is_active == True).first()
    
    def _get_tenant_by_api_key(self, api_key: str) -> Optional[Tenant]: 
        """Get tenant information by API key"""
        tenant = self.db.query(Tenant).filter(Tenant.api_key == api_key, Tenant.is_active == True).first()
        if tenant:
            logger.info(f"Found tenant: {tenant.name} (ID: {tenant.id})")
        else:
            logger.warning(f"No tenant found for API key: {api_key[:5]}...")
        return tenant

    # ========================== KNOWLEDGE BASE METHODS ==========================
    
    def _get_knowledge_bases(self, tenant_id: int) -> List[KnowledgeBase]:
        """Get all knowledge bases for a tenant"""
        kbs = self.db.query(KnowledgeBase).filter(KnowledgeBase.tenant_id == tenant_id).all()
        logger.info(f"Found {len(kbs)} knowledge bases for tenant {tenant_id}")
        return kbs
    
    def _get_faqs(self, tenant_id: int) -> List[Dict[str, str]]:
        """Get all FAQs for a tenant"""
        faqs = self.db.query(FAQ).filter(FAQ.tenant_id == tenant_id).all()
        logger.info(f"Found {len(faqs)} FAQs for tenant {tenant_id}")
        return [{"question": faq.question, "answer": faq.answer} for faq in faqs]

    def debug_faq_loading(self, tenant_id: int):
        """Debug method to check if FAQs are being loaded correctly"""
        faqs = self._get_faqs(tenant_id)
        logger.info(f"=== FAQ DEBUG for Tenant {tenant_id} ===")
        logger.info(f"Number of FAQs found: {len(faqs)}")
        
        for i, faq in enumerate(faqs):
            logger.info(f"FAQ {i+1}:")
            logger.info(f"  Question: {faq['question']}")
            logger.info(f"  Answer: {faq['answer']}")
        
        if not faqs:
            logger.warning("No FAQs found! Check if FAQs are properly saved in database.")
        
        return faqs

    # ========================== SESSION MANAGEMENT ==========================
    
    def _get_or_create_session(self, tenant_id: int, user_identifier: str) -> Tuple[str, bool]:
        """Get existing or create new chat session"""
        # Check for existing session
        session = self.db.query(ChatSession).filter(
            ChatSession.tenant_id == tenant_id,
            ChatSession.user_identifier == user_identifier,
            ChatSession.is_active == True
        ).first()
        
        created = False
        if not session:
            # Create new session
            session_id = str(uuid.uuid4())
            session = ChatSession(
                session_id=session_id,
                tenant_id=tenant_id,
                user_identifier=user_identifier,
                language_code="en"  # Default language is English
            )
            self.db.add(session)
            self.db.commit()
            self.db.refresh(session)
            created = True
            logger.info(f"Created new chat session: {session_id}")
        else:
            logger.info(f"Using existing chat session: {session.session_id}")
        
        return session.session_id, created

    def _get_or_create_session_with_memory(self, tenant_id: int, user_identifier: str, platform_data: Dict = None) -> Tuple[str, bool, Dict]:
        """Enhanced session creation with cross-platform memory"""
        memory_manager = EnhancedChatbotMemory(self.db, tenant_id)
        
        # Use the enhanced memory system to get or create session
        session_id, is_new_session, memory_context = memory_manager.get_or_create_session_with_memory(
            user_identifier, platform_data
        )
        
        return session_id, is_new_session, memory_context

    def end_session(self, session_id: str) -> bool:
        """End a chat session"""
        session = self.db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
        if not session:
            logger.warning(f"Session not found: {session_id}")
            return False
        
        # Mark session as inactive
        session.is_active = False
        self.db.commit()
        logger.info(f"Ended session: {session_id}")
        
        # Remove from active sessions
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
        
        return True

    # ========================== CHATBOT CHAIN METHODS ==========================
    
    def _create_simple_chain(self, tenant, faq_info):
        """Helper method to create a simple conversation chain when no KB is available"""
        from app.chatbot.prompts import SYSTEM_PROMPT_TEMPLATE
        from langchain_openai import ChatOpenAI
        from langchain.chains import ConversationChain
        from langchain.memory import ConversationBufferMemory
        from langchain.prompts import PromptTemplate
        
        logger.info("Creating simple conversation chain without knowledge base")
        
        # Check if tenant has custom system prompt
        if hasattr(tenant, 'system_prompt') and tenant.system_prompt:
            system_prompt = tenant.system_prompt
            system_prompt = system_prompt.replace("$company_name", tenant.name)
            system_prompt = system_prompt.replace("$faq_info", faq_info)
        else:
            # Format default system prompt
            system_prompt = SYSTEM_PROMPT_TEMPLATE.substitute(
                company_name=tenant.name,
                faq_info=faq_info
            )
        
        # Create custom prompt template that emphasizes FAQ checking
        prompt_template = f"""{system_prompt}

Since no additional knowledge base is available, please focus on using the FAQs above to answer user questions.

Conversation History:
{{history}}

User: {{input}}

Instructions:
1. Check if the user's question matches any FAQ above
2. If it matches, provide that answer naturally
3. If no FAQ matches, provide a helpful response based on general customer service principles
4. Never mention that you're checking FAQs or reference internal systems
5. Be friendly and professional

AI Assistant:"""
        
        prompt = PromptTemplate(
            input_variables=["history", "input"],
            template=prompt_template
        )
        
        # Create LLM
        llm = ChatOpenAI(
            model_name="gpt-3.5-turbo",
            temperature=0.3,  # Lower temperature for consistency
            openai_api_key=settings.OPENAI_API_KEY
        )
        
        memory = ConversationBufferMemory()
        
        chain = ConversationChain(
            llm=llm,
            memory=memory,
            prompt=prompt,
            verbose=True
        )
        
        return chain

    def _initialize_chatbot_chain(self, tenant_id: int) -> Optional[Any]:
        """Initialize the chatbot chain for a tenant"""
        tenant = self._get_tenant(tenant_id)
        if not tenant:
            logger.error(f"Tenant not found for ID: {tenant_id}")
            return None
        
        # Get knowledge bases and FAQs
        knowledge_bases = self._get_knowledge_bases(tenant_id)
        faqs = self._get_faqs(tenant_id)
        
        logger.info(f"Found {len(faqs)} FAQs for tenant")
        
        # Format FAQ info for better matching
        if faqs:
            faq_info = "\n\n".join([f"Question: {faq['question']}\nAnswer: {faq['answer']}" for faq in faqs])
            logger.info(f"FAQ info: {faq_info[:200]}...")  # Log first 200 chars for debugging
        else:
            faq_info = "No specific FAQs are available."
        
        from langchain_openai import ChatOpenAI
        from langchain.chains import ConversationalRetrievalChain
        from langchain.memory import ConversationBufferMemory
        from langchain.prompts import PromptTemplate
        
        if knowledge_bases:
            kb = knowledge_bases[0]
            processor = DocumentProcessor(tenant_id)
            
            try:
                vector_store = processor.get_vector_store(kb.vector_store_id)
                if vector_store is None:
                    return self._create_simple_chain(tenant, faq_info)
                
                # Create the system prompt with FAQs
                if hasattr(tenant, 'system_prompt') and tenant.system_prompt:
                    base_prompt = tenant.system_prompt
                else:
                    from app.chatbot.prompts import SYSTEM_PROMPT_TEMPLATE
                    base_prompt = SYSTEM_PROMPT_TEMPLATE.template
                
                # Replace placeholders
                system_prompt_content = base_prompt.replace("$company_name", tenant.name)
                system_prompt_content = system_prompt_content.replace("$faq_info", faq_info)
                
                # Create a better QA prompt that emphasizes FAQ checking and natural responses
                qa_prompt_template = f"""{system_prompt_content}

Here is additional context from our knowledge base that may help answer the question:
{{context}}

User Question: {{question}}

Instructions for your response:
1. First, check if this question is similar to any FAQ above
2. If an FAQ matches, use that answer (you can expand with knowledge base info if helpful)
3. If no FAQ matches, use the knowledge base context to provide a helpful answer
4. Respond naturally as a customer service representative - don't mention internal systems
5. If you cannot answer, politely say you don't have that information and offer to connect them with a specialist

Your response:"""
                
                qa_prompt = PromptTemplate(
                    template=qa_prompt_template,
                    input_variables=["context", "question"]
                )
                
                # Initialize LLM
                llm = ChatOpenAI(
                    model_name="gpt-3.5-turbo",
                    temperature=0.3,  # Lower temperature for more consistent responses
                    openai_api_key=settings.OPENAI_API_KEY
                )
                
                # Create memory
                memory = ConversationBufferMemory(
                    memory_key="chat_history",
                    return_messages=True,
                    output_key="answer"
                )
                
                # Create the chain with proper prompt
                chain = ConversationalRetrievalChain.from_llm(
                    llm=llm,
                    retriever=vector_store.as_retriever(search_kwargs={"k": 3}),  # Reduced to 3 for focus
                    memory=memory,
                    combine_docs_chain_kwargs={"prompt": qa_prompt},
                    return_source_documents=False,
                    verbose=True
                )
                
                logger.info(f"Successfully created chatbot chain for tenant: {tenant.name}")
                return chain
                
            except Exception as e:
                logger.error(f"Error creating chatbot chain: {e}", exc_info=True)
                return self._create_simple_chain(tenant, faq_info)
        else:
            return self._create_simple_chain(tenant, faq_info)

    # ========================== BASIC MESSAGE PROCESSING ==========================
    
    def process_message(self, api_key: str, user_message: str, user_identifier: str) -> Dict[str, Any]:
        """Process an incoming message and return a response"""
        # Get tenant from API key
        tenant = self._get_tenant_by_api_key(api_key)
        if not tenant:
            logger.error(f"Invalid API key: {api_key[:5]}...")
            return {"error": "Invalid API key", "success": False}
        
        # Get or create session
        session_id, is_new_session = self._get_or_create_session(tenant.id, user_identifier)
        
        # Store user message
        session = self.db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
        user_msg = ChatMessage(
            session_id=session.id,
            content=user_message,
            is_from_user=True
        )
        self.db.add(user_msg)
        self.db.commit()
        logger.info(f"Stored user message for session {session_id}")
        
        # Initialize or get chatbot chain
        if session_id not in self.active_sessions:
            logger.info(f"Initializing new chatbot chain for session {session_id}")
            chain = self._initialize_chatbot_chain(tenant.id)
            if not chain:
                logger.error(f"Failed to initialize chatbot chain for tenant {tenant.id}")
                return {"error": "Failed to initialize chatbot", "success": False}
            self.active_sessions[session_id] = chain
        else:
            logger.info(f"Using existing chatbot chain for session {session_id}")
            chain = self.active_sessions[session_id]
        
        # Generate response
        try:
            logger.info(f"Generating response for: '{user_message}'")
            if hasattr(chain, 'run'):
                # ConversationChain uses .run()
                bot_response = chain.run(user_message)
            elif hasattr(chain, '__call__'):
                # ConversationalRetrievalChain uses __call__
                response = chain({"question": user_message})
                bot_response = response.get("answer", "I'm sorry, I couldn't generate a response.")
            else:
                logger.error(f"Unexpected chain type: {type(chain)}")
                bot_response = "I'm sorry, I'm having trouble accessing my knowledge base."
                
            logger.info(f"Generated response: '{bot_response[:50]}...'")
            
            # Store bot response
            bot_msg = ChatMessage(
                session_id=session.id,
                content=bot_response,
                is_from_user=False
            )
            self.db.add(bot_msg)
            self.db.commit()
            
            return {
                "session_id": session_id,
                "response": bot_response,
                "success": True,
                "is_new_session": is_new_session
            }
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}", exc_info=True)
            return {"error": f"Error generating response: {str(e)}", "success": False}

    # ========================== LANGUAGE PROCESSING ==========================
    
    def process_message_with_language(self, api_key: str, user_message: str, user_identifier: str, 
                                    target_language: Optional[str] = None) -> Dict[str, Any]:
        """Process an incoming message with language detection and translation"""
        # Get tenant from API key
        tenant = self._get_tenant_by_api_key(api_key)
        if not tenant:
            logger.error(f"Invalid API key: {api_key[:5]}...")
            return {"error": "Invalid API key", "success": False}
        
        # Get or create session
        session_id, is_new_session = self._get_or_create_session(tenant.id, user_identifier)
        session = self.db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
        
        # Detect language if not specified
        detected_language = language_service.detect_language(user_message)
        source_language = detected_language or "en"
        
        # Update session language if detected
        if detected_language and not target_language:
            session.language_code = detected_language
            self.db.commit()
            logger.info(f"Updated session language to: {detected_language}")
        
        # If target language is specified, use it; otherwise use session language
        target_language = target_language or session.language_code or "en"
        
        # Store original message
        original_message = user_message
        was_translated = False
        
        # Translate message to English for processing if needed
        if source_language != "en":
            user_message, was_translated = language_service.translate(user_message, target_lang="en", source_lang=source_language)
            logger.info(f"Translated user message from {source_language} to English for processing")
        
        # Store user message
        user_msg = ChatMessage(
            session_id=session.id,
            content=original_message,  # Store original message
            translated_content=user_message if was_translated else None,  # Store translated message if any
            source_language=source_language,
            is_from_user=True
        )
        self.db.add(user_msg)
        self.db.commit()
        logger.info(f"Stored user message for session {session_id}")
        
        # Initialize or get chatbot chain
        if session_id not in self.active_sessions:
            logger.info(f"Initializing new chatbot chain for session {session_id}")
            chain = self._initialize_chatbot_chain(tenant.id)
            if not chain:
                logger.error(f"Failed to initialize chatbot chain for tenant {tenant.id}")
                return {"error": "Failed to initialize chatbot", "success": False}
            self.active_sessions[session_id] = chain
        else:
            logger.info(f"Using existing chatbot chain for session {session_id}")
            chain = self.active_sessions[session_id]
        
        # Generate response
        try:
            logger.info(f"Generating response for: '{user_message}'")
            
            # Use the chain to generate a response in English
            if hasattr(chain, '__call__'):
                # For LangChain conversation chains
                if hasattr(chain, 'run'):
                    # ConversationChain uses .run()
                    english_response = chain.run(input=user_message)
                else:
                    # ConversationalRetrievalChain uses __call__
                    response = chain({"question": user_message})
                    english_response = response.get("answer", "I'm sorry, I couldn't generate a response.")
            else:
                # Fallback for any other type of chain
                english_response = "I'm sorry, I'm having trouble accessing my knowledge base."
                logger.error(f"Unexpected chain type: {type(chain)}")
            
            logger.info(f"Generated English response: '{english_response[:50]}...'")
            
            # Translate response back to the target language if needed
            final_response = english_response
            was_bot_translated = False
            
            if target_language != "en":
                final_response, was_bot_translated = language_service.translate(
                    english_response, target_lang=target_language, source_lang="en"
                )
                logger.info(f"Translated bot response from English to {target_language}")
            
            # Store bot response
            bot_msg = ChatMessage(
                session_id=session.id,
                content=final_response,  # Store the final (possibly translated) response
                translated_content=english_response if was_bot_translated else None,  # Store original English response if translated
                source_language="en",  # Bot responses are generated in English
                target_language=target_language if was_bot_translated else None,
                is_from_user=False
            )
            self.db.add(bot_msg)
            self.db.commit()
            
            return {
                "session_id": session_id,
                "response": final_response,
                "detected_language": source_language,
                "language_name": language_service.get_language_name(source_language),
                "was_translated": was_translated or was_bot_translated,
                "success": True,
                "is_new_session": is_new_session
            }
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}", exc_info=True)
            return {"error": f"Error generating response: {str(e)}", "success": False}

    # ========================== DELAY PROCESSING ==========================
    
    async def process_message_with_delay(self, api_key: str, user_message: str, user_identifier: str,
                                       target_language: Optional[str] = None) -> Dict[str, Any]:
        """Process message with human-like delay"""
        
        # Get tenant from API key
        tenant = self._get_tenant_by_api_key(api_key)
        if not tenant:
            logger.error(f"Invalid API key: {api_key[:5]}...")
            return {"error": "Invalid API key", "success": False}
        
        # Record start time
        start_time = time.time()
        
        # Get or create session
        session_id, is_new_session = self._get_or_create_session(tenant.id, user_identifier)
        session = self.db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
        
        # Detect language if not specified
        detected_language = language_service.detect_language(user_message) if hasattr(self, 'language_service') else None
        source_language = detected_language or "en"
        target_language = target_language or session.language_code or "en"
        
        # Store original message
        original_message = user_message
        was_translated = False
        
        # Translate message to English for processing if needed
        if source_language != "en" and hasattr(self, 'language_service'):
            user_message, was_translated = language_service.translate(user_message, target_lang="en", source_lang=source_language)
            logger.info(f"Translated user message from {source_language} to English for processing")
        
        # Store user message
        user_msg = ChatMessage(
            session_id=session.id,
            content=original_message,
            translated_content=user_message if was_translated else None,
            source_language=source_language,
            is_from_user=True
        )
        self.db.add(user_msg)
        self.db.commit()
        logger.info(f"Stored user message for session {session_id}")
        
        # Initialize or get chatbot chain
        if session_id not in self.active_sessions:
            logger.info(f"Initializing new chatbot chain for session {session_id}")
            chain = self._initialize_chatbot_chain(tenant.id)
            if not chain:
                logger.error(f"Failed to initialize chatbot chain for tenant {tenant.id}")
                return {"error": "Failed to initialize chatbot", "success": False}
            self.active_sessions[session_id] = chain
        else:
            logger.info(f"Using existing chatbot chain for session {session_id}")
            chain = self.active_sessions[session_id]
        
        # Generate response first
        try:
            logger.info(f"Generating response for: '{user_message}'")
            
            # Use the chain to generate a response in English
            if hasattr(chain, '__call__'):
                if hasattr(chain, 'run'):
                    # ConversationChain uses .run()
                    english_response = chain.run(input=user_message)
                else:
                    # ConversationalRetrievalChain uses __call__
                    response = chain({"question": user_message})
                    english_response = response.get("answer", "I'm sorry, I couldn't generate a response.")
            else:
                english_response = "I'm sorry, I'm having trouble accessing my knowledge base."
                logger.error(f"Unexpected chain type: {type(chain)}")
            
            logger.info(f"Generated English response: '{english_response[:50]}...'")
            
            # Calculate human-like delay based on question and response
            if self.delay_simulator:
                response_delay = self.delay_simulator.calculate_response_delay(user_message, english_response)
                
                # Wait for the calculated delay
                logger.info(f"Simulating human thinking/typing time: {response_delay:.2f} seconds")
                await asyncio.sleep(response_delay)
            else:
                response_delay = 0
            
            # Translate response back to the target language if needed
            final_response = english_response
            was_bot_translated = False
            
            if target_language != "en" and hasattr(self, 'language_service'):
                final_response, was_bot_translated = language_service.translate(
                    english_response, target_lang=target_language, source_lang="en"
                )
                logger.info(f"Translated bot response from English to {target_language}")
            
            # Store bot response
            bot_msg = ChatMessage(
                session_id=session.id,
                content=final_response,
                translated_content=english_response if was_bot_translated else None,
                source_language="en",
                target_language=target_language if was_bot_translated else None,
                is_from_user=False
            )
            self.db.add(bot_msg)
            self.db.commit()
            
            # Calculate total processing time
            total_time = time.time() - start_time
            
            return {
                "session_id": session_id,
                "response": final_response,
                "detected_language": source_language,
                "language_name": language_service.get_language_name(source_language) if hasattr(self, 'language_service') else None,
                "was_translated": was_translated or was_bot_translated,
                "response_delay": response_delay,
                "total_processing_time": total_time,
                "success": True,
                "is_new_session": is_new_session
            }
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}", exc_info=True)
            return {"error": f"Error generating response: {str(e)}", "success": False}

                # ========================== ENHANCED MEMORY PROCESSING ==========================
    
    def _build_context_prompt(self, user_message: str, context: list, preferences: dict, system_prompt: str) -> str:
        """Build enhanced prompt with conversation context"""
        prompt_parts = []
        
        # System prompt
        if system_prompt:
            prompt_parts.append(f"System Instructions: {system_prompt}")
        
        # User preferences context
        if preferences["interaction_patterns"]["last_interaction"]:
            try:
                last_interaction = datetime.fromisoformat(preferences["interaction_patterns"]["last_interaction"].replace('Z', '+00:00'))
                time_since_last = datetime.now() - last_interaction.replace(tzinfo=None)
                
                if time_since_last.days > 7:
                    prompt_parts.append("Note: This user hasn't interacted in over a week. Provide a welcoming response.")
                elif time_since_last.total_seconds() < 300:  # 5 minutes
                    prompt_parts.append("Note: This is a continuing conversation from just a few minutes ago.")
            except:
                pass  # Skip if date parsing fails
        
        # Conversation context
        if context:
            prompt_parts.append("\nRecent conversation history:")
            for msg in context[-5:]:  # Last 5 messages
                role_label = "User" if msg["role"] == "user" else "Assistant"
                prompt_parts.append(f"{role_label}: {msg['content']}")
            prompt_parts.append("---")
        
        # Current message
        prompt_parts.append(f"Current User Message: {user_message}")
        
        return "\n".join(prompt_parts)

    def _build_memory_enhanced_prompt(self, user_message: str, conversation_context: List[Dict], 
                                    memory_context: Dict, user_preferences: Dict, tenant) -> str:
        """Build enhanced prompt with memory context and user preferences"""
        prompt_parts = []
        
        # System context with user preferences
        if hasattr(tenant, 'system_prompt') and tenant.system_prompt:
            prompt_parts.append(f"System Instructions: {tenant.system_prompt}")
        
        # User context from memory
        if memory_context['platforms_used']:
            platforms_str = ", ".join(memory_context['platforms_used'])
            prompt_parts.append(f"User Context: This user has previously communicated via {platforms_str}.")
        
        # Communication style preference
        comm_style = user_preferences.get('interaction_patterns', {}).get('most_active_platform')
        if comm_style:
            prompt_parts.append(f"Note: User is most active on {comm_style}.")
        
        # Previous conversation summary
        if memory_context['user_summary']['total_messages'] > 0:
            summary = memory_context['user_summary']
            prompt_parts.append(
                f"User History: {summary['total_messages']} previous messages, "
                f"communication style: {summary['communication_style']}, "
                f"topics discussed: {', '.join(summary['topics_discussed']) if summary['topics_discussed'] else 'general conversation'}"
            )
        
        # Recent conversation context (if available)
        if conversation_context:
            prompt_parts.append("\nRecent conversation:")
            for msg in conversation_context[-5:]:  # Last 5 messages
                role_label = "User" if msg["role"] == "user" else "Assistant"
                platform_info = f" [{msg.get('platform', 'web')}]" if msg.get('platform') else ""
                prompt_parts.append(f"{role_label}{platform_info}: {msg['content']}")
            prompt_parts.append("---")
        
        # Current message
        prompt_parts.append(f"Current User Message: {user_message}")
        
        # Instructions for continuity
        prompt_parts.append(
            "\nInstructions: Respond naturally, maintaining conversation continuity. "
            "Reference previous conversations when relevant, but don't explicitly mention "
            "that you're accessing memory or different platforms."
        )
        
        return "\n".join(prompt_parts)

    def process_message_with_memory(self, api_key: str, user_message: str, user_identifier: str, 
                                  use_context: bool = True, max_context: int = 5) -> Dict[str, Any]:
        """Enhanced message processing with conversation context/memory"""
        # Get tenant
        tenant = self._get_tenant_by_api_key(api_key)
        if not tenant:
            return {"success": False, "error": "Invalid API key"}
        
        # Initialize memory manager
        memory_manager = EnhancedChatbotMemory(self.db, tenant.id)
        
        # Build enhanced prompt with context if enabled
        if use_context:
            # Get conversation context
            context = memory_manager.get_conversation_context(user_identifier, max_context)
            
            # Get user preferences for personalization
            preferences = memory_manager.get_user_preferences(user_identifier)
            
            # Build enhanced prompt with context
            enhanced_prompt = self._build_context_prompt(
                user_message, 
                context, 
                preferences, 
                getattr(tenant, 'system_prompt', None)
            )
        else:
            # Use original prompt without context
            enhanced_prompt = user_message
        
        # Process with existing logic but with enhanced prompt
        try:
            # Get or create session
            session_id, is_new_session = self._get_or_create_session(tenant.id, user_identifier)
            session = self.db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
            
            # Store user message
            user_msg = ChatMessage(
                session_id=session.id,
                content=user_message,  # Store original user message
                is_from_user=True
            )
            self.db.add(user_msg)
            self.db.commit()
            
            # Initialize or get chatbot chain
            if session_id not in self.active_sessions:
                chain = self._initialize_chatbot_chain(tenant.id)
                if not chain:
                    return {"success": False, "error": "Failed to initialize chatbot"}
                self.active_sessions[session_id] = chain
            else:
                chain = self.active_sessions[session_id]
            
            # Generate response using enhanced prompt
            if hasattr(chain, 'run'):
                response_text = chain.run(enhanced_prompt)
            elif hasattr(chain, '__call__'):
                response = chain({"question": enhanced_prompt})
                response_text = response.get("answer", "I'm sorry, I couldn't generate a response.")
            else:
                response_text = "I'm sorry, I'm having trouble accessing my knowledge base."
            
            # Store bot response
            bot_msg = ChatMessage(
                session_id=session.id,
                content=response_text,
                is_from_user=False
            )
            self.db.add(bot_msg)
            self.db.commit()
            
            return {
                "success": True,
                "response": response_text,
                "session_id": session_id,
                "is_new_session": is_new_session,
                "context_used": use_context,
                "context_length": len(context) if use_context else 0
            }
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error in process_message_with_memory: {str(e)}")
            return {"success": False, "error": str(e)}

    def process_message_with_enhanced_memory(self, api_key: str, user_message: str, user_identifier: str,
                                           platform_data: Dict = None, target_language: Optional[str] = None) -> Dict[str, Any]:
        """Process message with enhanced cross-platform memory"""
        # Get tenant from API key
        tenant = self._get_tenant_by_api_key(api_key)
        if not tenant:
            logger.error(f"Invalid API key: {api_key[:5]}...")
            return {"error": "Invalid API key", "success": False}
        
        # Initialize memory manager
        memory_manager = EnhancedChatbotMemory(self.db, tenant.id)
        
        # Get or create session with memory context
        session_id, is_new_session, memory_context = self._get_or_create_session_with_memory(
            tenant.id, user_identifier, platform_data
        )
        
        # Get conversation context for this user across platforms
        conversation_context = memory_manager.get_conversation_context(user_identifier, max_messages=10)
        user_preferences = memory_manager.get_user_preferences(user_identifier)
        
        logger.info(f"Memory context: {len(memory_context['messages'])} cross-platform messages")
        logger.info(f"Conversation context: {len(conversation_context)} recent messages")
        logger.info(f"User used {len(user_preferences['platforms_used'])} platforms: {user_preferences['platforms_used']}")
        
        # Store user message with platform metadata
        success = memory_manager.store_message_with_context(
            session_id, user_message, True, platform_data
        )
        
        if not success:
            return {"error": "Failed to store message", "success": False}
        
        # Build enhanced prompt with memory
        enhanced_prompt = self._build_memory_enhanced_prompt(
            user_message, conversation_context, memory_context, user_preferences, tenant
        )
        
        # Initialize or get chatbot chain
        if session_id not in self.active_sessions:
            logger.info(f"Initializing new chatbot chain for session {session_id}")
            chain = self._initialize_chatbot_chain(tenant.id)
            if not chain:
                logger.error(f"Failed to initialize chatbot chain for tenant {tenant.id}")
                return {"error": "Failed to initialize chatbot", "success": False}
            self.active_sessions[session_id] = chain
        else:
            logger.info(f"Using existing chatbot chain for session {session_id}")
            chain = self.active_sessions[session_id]
        
        # Generate response using enhanced prompt
        try:
            logger.info(f"Generating response with memory context for: '{user_message}'")
            
            if hasattr(chain, 'run'):
                # ConversationChain uses .run()
                bot_response = chain.run(enhanced_prompt)
            elif hasattr(chain, '__call__'):
                # ConversationalRetrievalChain uses __call__
                response = chain({"question": enhanced_prompt})
                bot_response = response.get("answer", "I'm sorry, I couldn't generate a response.")
            else:
                logger.error(f"Unexpected chain type: {type(chain)}")
                bot_response = "I'm sorry, I'm having trouble accessing my knowledge base."
                
            logger.info(f"Generated response: '{bot_response[:50]}...'")
            
            # Store bot response with platform metadata
            memory_manager.store_message_with_context(
                session_id, bot_response, False, platform_data
            )
            
            return {
                "session_id": session_id,
                "response": bot_response,
                "success": True,
                "is_new_session": is_new_session,
                "memory_stats": {
                    "cross_platform_messages": len(memory_context['messages']),
                    "platforms_used": memory_context['platforms_used'],
                    "conversation_context_length": len(conversation_context),
                    "user_summary": memory_context['user_summary']
                }
            }
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}", exc_info=True)
            return {"error": f"Error generating response: {str(e)}", "success": False}

    # ========================== PLATFORM-SPECIFIC METHODS ==========================
    
    def process_discord_message(self, api_key: str, user_message: str, discord_user_id: str, 
                              channel_id: str, guild_id: str) -> Dict[str, Any]:
        """Process Discord message with platform-specific context"""
        user_identifier = f"discord:{discord_user_id}"
        platform_data = {
            "platform": "discord",
            "user_id": discord_user_id,
            "channel_id": channel_id,
            "guild_id": guild_id
        }
        
        return self.process_message_with_enhanced_memory(
            api_key, user_message, user_identifier, platform_data
        )

    def process_whatsapp_message(self, api_key: str, user_message: str, phone_number: str) -> Dict[str, Any]:
        """Process WhatsApp message with platform-specific context"""
        user_identifier = f"whatsapp:{phone_number}"
        platform_data = {
            "platform": "whatsapp",
            "phone_number": phone_number
        }
        
        return self.process_message_with_enhanced_memory(
            api_key, user_message, user_identifier, platform_data
        )

    def process_web_message(self, api_key: str, user_message: str, user_identifier: str, 
                           session_token: str = None) -> Dict[str, Any]:
        """Process web message with platform-specific context"""
        if not user_identifier.startswith("web:"):
            user_identifier = f"web:{user_identifier}"
        
        platform_data = {
            "platform": "web",
            "session_token": session_token,
            "user_agent": "web"  # You can capture this from request headers
        }
        
        return self.process_message_with_enhanced_memory(
            api_key, user_message, user_identifier, platform_data
        )
    def process_discord_message(self, api_key: str, user_message: str, discord_user_id: str, 
                          channel_id: str, guild_id: str) -> Dict[str, Any]:
        """
        Process Discord message with platform-specific context
        """
        user_identifier = f"discord:{discord_user_id}"
        platform_data = {
            "platform": "discord",
            "user_id": discord_user_id,
            "channel_id": channel_id,
            "guild_id": guild_id
        }
        
        return self.process_message_with_enhanced_memory(
            api_key, user_message, user_identifier, platform_data
        )
    
    
    def process_message_with_handoff_detection(self, api_key: str, user_message: str, 
                                            user_identifier: str) -> Dict[str, Any]:
        """
        Enhanced message processing with automatic handoff detection
        """
        # Import here to avoid circular imports
        from app.live_chat.manager import LiveChatManager
        
        # Get tenant
        tenant = self._get_tenant_by_api_key(api_key)
        if not tenant:
            return {"error": "Invalid API key", "success": False}
        
        # Check for handoff request
        chat_manager = LiveChatManager(self.db)
        is_handoff, reason, department = chat_manager.detect_handoff_request(user_message)
        
        if is_handoff:
            # Get or create session for context
            session_id, _ = self._get_or_create_session(tenant.id, user_identifier)
            
            # Initiate live chat
            live_chat = chat_manager.initiate_live_chat(
                tenant_id=tenant.id,
                user_identifier=user_identifier,
                chatbot_session_id=session_id,
                handoff_reason=reason,
                platform="web",  # Default platform
                department=department
            )
            
            return {
                "success": True,
                "handoff_initiated": True,
                "live_chat_session_id": live_chat.session_id,
                "response": "I'm connecting you with one of our support agents. Please wait a moment...",
                "handoff_reason": reason,
                "department": department
            }
        else:
            # Process normally with chatbot
            return self.process_message(api_key, user_message, user_identifier)