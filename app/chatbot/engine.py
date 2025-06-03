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
from app.chatbot.simple_memory import SimpleChatbotMemory
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

    # ========================== SIMPLIFIED MEMORY PROCESSING ==========================
    
    def process_message_simple_memory(self, api_key: str, user_message: str, user_identifier: str, 
                                    platform: str = "web", max_context: int = 20) -> Dict[str, Any]:
        """
        Process message with simple conversation memory - no cross-platform complexity
        """
        # Get tenant from API key
        tenant = self._get_tenant_by_api_key(api_key)
        if not tenant:
            logger.error(f"Invalid API key: {api_key[:5]}...")
            return {"error": "Invalid API key", "success": False}
        
        # Initialize simple memory manager
        memory = SimpleChatbotMemory(self.db, tenant.id)
        
        # Get or create session
        session_id, is_new_session = memory.get_or_create_session(user_identifier, platform)
        
        # Get conversation history for context
        conversation_history = memory.get_conversation_history(user_identifier, max_context)
        
        logger.info(f"Processing message for {user_identifier} - {len(conversation_history)} previous messages")
        
        # Store user message
        if not memory.store_message(session_id, user_message, True):
            return {"error": "Failed to store user message", "success": False}
        
        # Initialize or get chatbot chain
        if session_id not in self.active_sessions:
            logger.info(f"Initializing chatbot chain for session {session_id}")
            chain = self._initialize_chatbot_chain(tenant.id)
            if not chain:
                logger.error(f"Failed to initialize chatbot chain for tenant {tenant.id}")
                return {"error": "Failed to initialize chatbot", "success": False}
            self.active_sessions[session_id] = chain
        else:
            logger.info(f"Using existing chatbot chain for session {session_id}")
            chain = self.active_sessions[session_id]
        
        # Build prompt with conversation context
        system_prompt = None
        if hasattr(tenant, 'system_prompt') and tenant.system_prompt:
            system_prompt = tenant.system_prompt.replace("$company_name", tenant.name)
        
        # Create enhanced prompt with conversation history
        if conversation_history:
            enhanced_prompt = memory.build_context_prompt(user_message, conversation_history, system_prompt)
        else:
            enhanced_prompt = user_message
        
        # Generate response
        try:
            logger.info(f"Generating response for: '{user_message}' (with {len(conversation_history)} context messages)")
            
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
            
            # Store bot response
            if not memory.store_message(session_id, bot_response, False):
                logger.warning("Failed to store bot response")
            
            return {
                "session_id": session_id,
                "response": bot_response,
                "success": True,
                "is_new_session": is_new_session,
                "context_messages": len(conversation_history),
                "platform": platform
            }
            
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}", exc_info=True)
            return {"error": f"Error generating response: {str(e)}", "success": False}
    
    def process_discord_message_simple(self, api_key: str, user_message: str, discord_user_id: str, 
                                     channel_id: str, guild_id: str, max_context: int = 20) -> Dict[str, Any]:
        """
        Simplified Discord message processing with basic memory
        """
        user_identifier = f"discord:{discord_user_id}"
        
        result = self.process_message_simple_memory(
            api_key=api_key,
            user_message=user_message,
            user_identifier=user_identifier,
            platform="discord",
            max_context=max_context
        )
        
        # Add Discord-specific info to result
        if result.get("success"):
            result["discord_info"] = {
                "user_id": discord_user_id,
                "channel_id": channel_id,
                "guild_id": guild_id
            }
        
        return result
    
    def get_user_memory_stats(self, api_key: str, user_identifier: str) -> Dict[str, Any]:
        """
        Get memory statistics for a user - useful for debugging
        """
        tenant = self._get_tenant_by_api_key(api_key)
        if not tenant:
            return {"error": "Invalid API key", "success": False}
        
        memory = SimpleChatbotMemory(self.db, tenant.id)
        stats = memory.get_session_stats(user_identifier)
        
        return {
            "success": True,
            "user_identifier": user_identifier,
            "stats": stats
        }

    # ========================== HANDOFF DETECTION ==========================
    
    def process_message_with_handoff_detection(self, api_key: str, user_message: str, 
                                            user_identifier: str) -> Dict[str, Any]:
        """
        Enhanced message processing with automatic handoff detection for live chat
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
                platform="web",  # Default platform - can be enhanced to detect platform
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



    # ========================== DISCORD MEMORY WITH DELAY ==========================
    
    async def process_discord_message_simple_with_delay(self, api_key: str, user_message: str, discord_user_id: str, 
                                                      channel_id: str, guild_id: str, max_context: int = 20) -> Dict[str, Any]:
        """
        Discord message processing with both simple memory AND delay simulation
        """
        # Get tenant from API key
        tenant = self._get_tenant_by_api_key(api_key)
        if not tenant:
            logger.error(f"Invalid API key: {api_key[:5]}...")
            return {"error": "Invalid API key", "success": False}
        
        # Record start time for delay calculation
        start_time = time.time()
        
        user_identifier = f"discord:{discord_user_id}"
        
        # Initialize simple memory manager
        from app.chatbot.simple_memory import SimpleChatbotMemory
        memory = SimpleChatbotMemory(self.db, tenant.id)
        
        # Get or create session
        session_id, is_new_session = memory.get_or_create_session(user_identifier, "discord")
        
        # Get conversation history for context
        conversation_history = memory.get_conversation_history(user_identifier, max_context)
        
        logger.info(f"Processing Discord message with delay for {user_identifier} - {len(conversation_history)} previous messages")
        
        # Store user message
        if not memory.store_message(session_id, user_message, True):
            return {"error": "Failed to store user message", "success": False}
        
        # Initialize or get chatbot chain
        if session_id not in self.active_sessions:
            logger.info(f"Initializing chatbot chain for session {session_id}")
            chain = self._initialize_chatbot_chain(tenant.id)
            if not chain:
                logger.error(f"Failed to initialize chatbot chain for tenant {tenant.id}")
                return {"error": "Failed to initialize chatbot", "success": False}
            self.active_sessions[session_id] = chain
        else:
            logger.info(f"Using existing chatbot chain for session {session_id}")
            chain = self.active_sessions[session_id]
        
        # Build prompt with conversation context
        system_prompt = None
        if hasattr(tenant, 'system_prompt') and tenant.system_prompt:
            system_prompt = tenant.system_prompt.replace("$company_name", tenant.name)
        
        # Create enhanced prompt with conversation history
        if conversation_history:
            enhanced_prompt = memory.build_context_prompt(user_message, conversation_history, system_prompt)
        else:
            enhanced_prompt = user_message
        
        # Generate response
        try:
            logger.info(f"Generating response with delay for: '{user_message}' (with {len(conversation_history)} context messages)")
            
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
            
            # Calculate human-like delay based on question and response
            response_delay = 0
            if self.delay_simulator:
                response_delay = self.delay_simulator.calculate_response_delay(user_message, bot_response)
                
                # Wait for the calculated delay
                logger.info(f"Simulating human thinking/typing time: {response_delay:.2f} seconds")
                await asyncio.sleep(response_delay)
            
            # Store bot response
            if not memory.store_message(session_id, bot_response, False):
                logger.warning("Failed to store bot response")
            
            # Calculate total processing time
            total_time = time.time() - start_time
            
            return {
                "session_id": session_id,
                "response": bot_response,
                "success": True,
                "is_new_session": is_new_session,
                "context_messages": len(conversation_history),
                "platform": "discord",
                "discord_info": {
                    "user_id": discord_user_id,
                    "channel_id": channel_id,
                    "guild_id": guild_id
                },
                "response_delay": response_delay,
                "total_processing_time": total_time
            }
            
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}", exc_info=True)
            return {"error": f"Error generating response: {str(e)}", "success": False}
        

    # ========================== SMART FEEDBACK SYSTEM ==========================
    
    def process_message_with_smart_feedback(self, api_key: str, user_message: str, user_identifier: str, 
                                        platform: str = "web", max_context: int = 20) -> Dict[str, Any]:
        """
        Process message with smart feedback system that:
        1. Asks for email on new conversations
        2. Detects inadequate responses
        3. Triggers tenant feedback loop
        """
        from app.chatbot.smart_feedback import SmartFeedbackManager
        
        # Get tenant from API key
        tenant = self._get_tenant_by_api_key(api_key)
        if not tenant:
            logger.error(f"Invalid API key: {api_key[:5]}...")
            return {"error": "Invalid API key", "success": False}
        
        # Initialize managers
        from app.chatbot.simple_memory import SimpleChatbotMemory
        memory = SimpleChatbotMemory(self.db, tenant.id)
        feedback_manager = SmartFeedbackManager(self.db, tenant.id)
        
        # Get or create session
        session_id, is_new_session = memory.get_or_create_session(user_identifier, platform)
        
        # Check if we should ask for email (new conversations)
        if feedback_manager.should_request_email(session_id, user_identifier):
            email_request = feedback_manager.generate_email_request_message(tenant.name)
            
            # Store the email request as bot message
            memory.store_message(session_id, email_request, False)
            
            return {
                "session_id": session_id,
                "response": email_request,
                "success": True,
                "is_new_session": is_new_session,
                "email_requested": True,
                "platform": platform
            }
        
        # Check if user is providing email
        extracted_email = feedback_manager.extract_email_from_message(user_message)
        if extracted_email:
            # Store email and acknowledge
            if feedback_manager.store_user_email(session_id, extracted_email):
                acknowledgment = f"Thank you! I've noted your email as {extracted_email}. How can I help you today?"
                
                # Store both user message and bot response
                memory.store_message(session_id, user_message, True)
                memory.store_message(session_id, acknowledgment, False)
                
                return {
                    "session_id": session_id,
                    "response": acknowledgment,
                    "success": True,
                    "is_new_session": is_new_session,
                    "email_captured": True,
                    "user_email": extracted_email,
                    "platform": platform
                }
        
        # Process message normally with memory
        result = self.process_message_simple_memory(
            api_key=api_key,
            user_message=user_message,
            user_identifier=user_identifier,
            platform=platform,
            max_context=max_context
        )
        
        if not result.get("success"):
            return result
        
        bot_response = result["response"]
        
        # 🔔 FIXED: Add proper feedback detection with logging
        logger.info(f"🔍 Checking bot response for inadequate patterns: '{bot_response[:100]}...'")
        
        try:
            is_inadequate = feedback_manager.detect_inadequate_response(bot_response)
            logger.info(f"🔍 Inadequate response detection result: {is_inadequate}")
            
            if is_inadequate:
                logger.info(f"🔔 Detected inadequate response, triggering feedback system")
                
                # Get conversation context
                conversation_history = memory.get_conversation_history(user_identifier, 10)
                
                # Create feedback request (this sends email to tenant)
                feedback_id = feedback_manager.create_feedback_request(
                    session_id=session_id,
                    user_question=user_message,
                    bot_response=bot_response,
                    conversation_context=conversation_history
                )
                
                if feedback_id:
                    logger.info(f"✅ Created feedback request {feedback_id} for inadequate response")
                    result["feedback_triggered"] = True
                    result["feedback_id"] = feedback_id
                else:
                    logger.error(f"❌ Failed to create feedback request")
            else:
                logger.info(f"✅ Response appears adequate, no feedback needed")
                
        except Exception as e:
            logger.error(f"💥 Error in feedback detection: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        return result
    
    def process_web_message_with_feedback(self, api_key: str, user_message: str, user_identifier: str, 
                                        max_context: int = 20) -> Dict[str, Any]:
        """
        Web-specific message processing with smart feedback system
        """
        if not user_identifier.startswith("web:"):
            user_identifier = f"web:{user_identifier}"
        
        return self.process_message_with_smart_feedback(
            api_key=api_key,
            user_message=user_message,
            user_identifier=user_identifier,
            platform="web",
            max_context=max_context
        )
    
    def handle_tenant_feedback_response(self, api_key: str, feedback_id: str, tenant_response: str) -> Dict[str, Any]:
        """
        Handle tenant's email response to feedback request
        """
        from app.chatbot.smart_feedback import SmartFeedbackManager
        
        # Get tenant from API key
        tenant = self._get_tenant_by_api_key(api_key)
        if not tenant:
            return {"error": "Invalid API key", "success": False}
        
        feedback_manager = SmartFeedbackManager(self.db, tenant.id)
        
        success = feedback_manager.process_tenant_response(feedback_id, tenant_response)
        
        return {
            "success": success,
            "feedback_id": feedback_id,
            "message": "Tenant response processed and user notified" if success else "Failed to process response"
        }
    
    def get_feedback_stats(self, api_key: str) -> Dict[str, Any]:
        """
        Get feedback system statistics for tenant
        """
        from app.chatbot.smart_feedback import SmartFeedbackManager
        
        tenant = self._get_tenant_by_api_key(api_key)
        if not tenant:
            return {"error": "Invalid API key", "success": False}
        
        feedback_manager = SmartFeedbackManager(self.db, tenant.id)
        stats = feedback_manager.get_pending_feedback_stats()
        
        return {
            "success": True,
            "tenant_id": tenant.id,
            "stats": stats
        }
    

    def process_slack_message_simple(self, api_key: str, user_message: str, slack_user_id: str, 
                               channel_id: str, team_id: str = None, max_context: int = 20) -> Dict[str, Any]:
        """
        Simplified Slack message processing with basic memory
        """
        user_identifier = f"slack:{slack_user_id}"
        
        result = self.process_message_simple_memory(
            api_key=api_key,
            user_message=user_message,
            user_identifier=user_identifier,
            platform="slack",
            max_context=max_context
        )
        
        # Add Slack-specific info to result
        if result.get("success"):
            result["slack_info"] = {
                "user_id": slack_user_id,
                "channel_id": channel_id,
                "team_id": team_id
            }
        
        return result
    

    async def process_slack_message_simple_with_delay(self, api_key: str, user_message: str, slack_user_id: str, 
                                                    channel_id: str, team_id: str = None, max_context: int = 20) -> Dict[str, Any]:
        """
        Slack message processing with both simple memory AND delay simulation
        """
        import time
        import asyncio
        
        # Get tenant from API key
        tenant = self._get_tenant_by_api_key(api_key)
        if not tenant:
            logger.error(f"Invalid API key: {api_key[:5]}...")
            return {"error": "Invalid API key", "success": False}
        
        # Record start time for delay calculation
        start_time = time.time()
        
        user_identifier = f"slack:{slack_user_id}"
        
        # Initialize simple memory manager
        from app.chatbot.simple_memory import SimpleChatbotMemory
        memory = SimpleChatbotMemory(self.db, tenant.id)
        
        # Get or create session
        session_id, is_new_session = memory.get_or_create_session(user_identifier, "slack")
        
        # Get conversation history for context
        conversation_history = memory.get_conversation_history(user_identifier, max_context)
        
        logger.info(f"Processing Slack message with delay for {user_identifier} - {len(conversation_history)} previous messages")
        
        # Store user message
        if not memory.store_message(session_id, user_message, True):
            return {"error": "Failed to store user message", "success": False}
        
        # Initialize or get chatbot chain
        if session_id not in self.active_sessions:
            logger.info(f"Initializing chatbot chain for session {session_id}")
            chain = self._initialize_chatbot_chain(tenant.id)
            if not chain:
                logger.error(f"Failed to initialize chatbot chain for tenant {tenant.id}")
                return {"error": "Failed to initialize chatbot", "success": False}
            self.active_sessions[session_id] = chain
        else:
            logger.info(f"Using existing chatbot chain for session {session_id}")
            chain = self.active_sessions[session_id]
        
        # Build prompt with conversation context
        system_prompt = None
        if hasattr(tenant, 'system_prompt') and tenant.system_prompt:
            system_prompt = tenant.system_prompt.replace("$company_name", tenant.name)
        
        # Create enhanced prompt with conversation history
        if conversation_history:
            enhanced_prompt = memory.build_context_prompt(user_message, conversation_history, system_prompt)
        else:
            enhanced_prompt = user_message
        
        # Generate response
        try:
            logger.info(f"Generating response with delay for: '{user_message}' (with {len(conversation_history)} context messages)")
            
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
            
            # Calculate human-like delay based on question and response
            response_delay = 0
            if self.delay_simulator:
                response_delay = self.delay_simulator.calculate_response_delay(user_message, bot_response)
                
                # Wait for the calculated delay
                logger.info(f"Simulating human thinking/typing time: {response_delay:.2f} seconds")
                await asyncio.sleep(response_delay)
            
            # Store bot response
            if not memory.store_message(session_id, bot_response, False):
                logger.warning("Failed to store bot response")
            
            # Calculate total processing time
            total_time = time.time() - start_time
            
            return {
                "session_id": session_id,
                "response": bot_response,
                "success": True,
                "is_new_session": is_new_session,
                "context_messages": len(conversation_history),
                "platform": "slack",
                "slack_info": {
                    "user_id": slack_user_id,
                    "channel_id": channel_id,
                    "team_id": team_id
                },
                "response_delay": response_delay,
                "total_processing_time": total_time
            }
            
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}", exc_info=True)
            return {"error": f"Error generating response: {str(e)}", "success": False}
        


    

    