import re
import uuid
import logging
import asyncio 
from typing import Dict, List, Any, Optional, Tuple
import time
from sqlalchemy.orm import Session
from app.knowledge_base.processor import DocumentProcessor
from app.chatbot.chains import create_chatbot_chain
from app.tenants.models import Tenant
from app.knowledge_base.models import KnowledgeBase, FAQ, ProcessingStatus
from app.chatbot.models import ChatSession, ChatMessage
from app.config import settings
from app.utils.language_service import language_service
from app.chatbot.response_simulator import SimpleHumanDelaySimulator
from app.chatbot.simple_memory import SimpleChatbotMemory
from datetime import datetime
from app.chatbot.security import build_secure_chatbot_prompt, check_message_security

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ChatbotEngine:
    """The main chatbot engine that handles conversations with FAQ quality filtering and KB integration"""
    
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

    # ========================== FAQ QUALITY AND MATCHING ==========================
    
    def _check_faq_with_llm(self, user_message: str, faqs: List[Dict[str, str]]) -> Optional[str]:
        """Use LLM to intelligently match user questions to FAQs"""
        if not faqs:
            return None
        
        from langchain_openai import ChatOpenAI
        from langchain.prompts import PromptTemplate
        
        # Format FAQs for the LLM
        faq_list = ""
        for i, faq in enumerate(faqs):
            faq_list += f"{i+1}. Q: {faq['question']}\n   A: {faq['answer']}\n\n"
        
        prompt = PromptTemplate(
            input_variables=["user_question", "faq_list"],
            template="""You are an FAQ matching assistant. Given a user question and a list of FAQs, determine if any FAQ answers the user's question.

    User Question: "{user_question}"

    Available FAQs:
    {faq_list}

    Instructions:
    1. If an FAQ directly answers the user's question, respond with: "MATCH: [FAQ_NUMBER]"
    2. If no FAQ matches, respond with: "NO_MATCH"
    3. Consider variations in wording (e.g., "business hours" matches "what time are you open")
    4. Look for semantic similarity, not just exact words
    5. If someone ask you what what you do, you should not answer with a FAQ or list out your FAQs, but rather with a general description of the company and its services.

    Response:"""
        )
        
        try:
            llm = ChatOpenAI(model_name="gpt-3.5-turbo", temperature=0.1, openai_api_key=settings.OPENAI_API_KEY)
            
            # FIX: Use invoke() instead of direct call
            result = llm.invoke(prompt.format(
                user_question=user_message,
                faq_list=faq_list
            ))
            
            # FIX: Handle both string and message object responses
            if hasattr(result, 'content'):
                result_text = result.content.strip()
            else:
                result_text = str(result).strip()
            
            logger.info(f"🤖 LLM FAQ matching result: {result_text}")
            
            # Parse the result
            if result_text.startswith("MATCH:"):
                try:
                    faq_number = int(result_text.split(":")[1].strip()) - 1
                    if 0 <= faq_number < len(faqs):
                        matched_faq = faqs[faq_number]
                        
                        # Check if answer is adequate
                        if self._is_faq_answer_adequate(matched_faq['answer']):
                            logger.info(f"🤖 LLM FAQ match found with good answer: {matched_faq['question']}")
                            return self._make_faq_conversational(matched_faq['answer'])
                        else:
                            logger.info(f"🤖 LLM found FAQ match but answer inadequate")
                            return None
                except (ValueError, IndexError) as e:
                    logger.warning(f"Could not parse LLM FAQ result: {result_text}, error: {e}")
            
            logger.info(f"🤖 LLM found no FAQ match for: {user_message}")
            return None
            
        except Exception as e:
            logger.error(f"Error in LLM FAQ matching: {e}")
            return None

    def _is_faq_answer_adequate(self, faq_answer: str) -> bool:
        """
        Check if FAQ answer is detailed enough or just a redirect
        """
        faq_lower = faq_answer.lower()
        
        # Inadequate patterns that indicate redirects rather than answers
        inadequate_patterns = [
            r'check.*youtube',
            r'check.*google',
            r'search.*online',
            r'look.*up',
            r'see.*documentation',
            r'visit.*website',
            r'contact.*support',
            r'email.*us',
            r'google.*it',
            r'youtube.*tutorial',
            r'find.*online'
        ]
        
        # If it matches redirect patterns, it's inadequate
        for pattern in inadequate_patterns:
            if re.search(pattern, faq_lower):
                logger.info(f"🔍 FAQ answer contains redirect pattern: {pattern}")
                return False
        
        # If it's too short (less than 50 characters), probably inadequate
        if len(faq_answer.strip()) < 50:
            logger.info(f"🔍 FAQ answer too short: {len(faq_answer)} chars")
            return False
        
        # Otherwise, it's probably adequate
        return True

    def _make_faq_conversational(self, faq_answer: str) -> str:
        """
        Convert robotic FAQ answer to conversational tone
        """
        import random
        
        # Conversational starters
        starters = [
            "Great question! ",
            "Happy to help with that! ",
            "Sure thing! ",
            "Absolutely! ",
            "Here's what you need to do: ",
            "No problem! ",
            "Perfect timing for this question! "
        ]
        
        # Conversational endings
        enders = [
            " Let me know if you need any clarification!",
            " Feel free to reach out if you have more questions!",
            " Hope that helps! Anything else I can assist with?",
            " Does that make sense? Happy to explain further!",
            " Let me know how it goes!",
            " That should get you sorted! 😊"
        ]
        
        # Add random starter and ender
        starter = random.choice(starters)
        ender = random.choice(enders)
        
        # Clean up the FAQ answer (remove overly formal language)
        conversational_answer = faq_answer
        
        # Replace formal phrases with casual ones
        replacements = {
            "Please follow these steps:": "Here's how to do it:",
            "Navigate to": "Go to",
            "Click on": "Click",
            "You will see": "You'll see",
            "In order to": "To",
            "Please note": "Just so you know",
            "It is recommended": "I'd suggest",
            "You should": "You can",
            "Please contact": "Feel free to contact"
        }
        
        for formal, casual in replacements.items():
            conversational_answer = conversational_answer.replace(formal, casual)
        
        return f"{starter}{conversational_answer}{ender}"

    def _get_kb_answer(self, user_message: str, tenant_id: int) -> Optional[str]:
        """
        Get answer from knowledge base using the chatbot chain
        """
        try:
            # Get a temporary session for KB lookup
            temp_session_id = f"temp_kb_{uuid.uuid4()}"
            
            # Initialize chatbot chain for this tenant
            chain = self._initialize_chatbot_chain(tenant_id)
            if not chain:
                logger.warning(f"No KB chain available for tenant {tenant_id}")
                return None
            
            # Generate response using KB
            if hasattr(chain, '__call__'):
                response = chain({"question": user_message})
                kb_response = response.get("answer", None)
            elif hasattr(chain, 'run'):
                kb_response = chain.run(user_message)
            else:
                logger.error(f"Unexpected chain type: {type(chain)}")
                return None
            
            logger.info(f"📚 KB answer retrieved: {kb_response[:100]}...")
            return kb_response
            
        except Exception as e:
            logger.error(f"Error getting KB answer: {e}")
            return None

    def _answers_are_compatible(self, faq_answer: str, kb_answer: str) -> bool:
        """
        Check if FAQ and KB answers are compatible (not contradictory)
        """
        if not faq_answer or not kb_answer:
            return True
        
        # Simple compatibility check - look for obvious contradictions
        faq_lower = faq_answer.lower()
        kb_lower = kb_answer.lower()
        
        # Check for contradictory words
        contradictions = [
            ("yes", "no"),
            ("true", "false"),
            ("can", "cannot"),
            ("will", "will not"),
            ("is", "is not"),
            ("available", "unavailable"),
            ("possible", "impossible")
        ]
        
        for word1, word2 in contradictions:
            if word1 in faq_lower and word2 in kb_lower:
                logger.warning(f"Potential contradiction detected: '{word1}' in FAQ vs '{word2}' in KB")
                return False
            if word2 in faq_lower and word1 in kb_lower:
                logger.warning(f"Potential contradiction detected: '{word2}' in FAQ vs '{word1}' in KB")
                return False
        
        return True

    def _get_harmonized_answer(self, user_message: str, tenant_id: int) -> Dict[str, Any]:
        """
        Get harmonized answer using hierarchical approach:
        1. FAQ (authoritative, current) - with quality filter
        2. KB (detailed context)
        3. Combined (if both exist and compatible)
        """
        faqs = self._get_faqs(tenant_id)
        
        # Step 1: Check FAQ first (with quality filter)
        faq_answer = self._check_faq_with_llm(user_message, faqs)
        
        # Step 2: Get KB context if FAQ is inadequate or missing
        kb_answer = None
        if not faq_answer:
            kb_answer = self._get_kb_answer(user_message, tenant_id)
        
        # Step 3: Decide how to combine
        if faq_answer and kb_answer:
            # Both exist - check for harmony
            if self._answers_are_compatible(faq_answer, kb_answer):
                # Combine: FAQ as primary, KB as additional detail
                final_answer = f"{faq_answer}\n\n💡 Additional information: {kb_answer}"
                source = "FAQ+KB"
            else:
                # Conflict detected - FAQ wins, log the issue
                logger.warning(f"⚠️ FAQ/KB conflict detected for: {user_message}")
                final_answer = faq_answer + "\n\n(Note: Please contact support if you need more specific details)"
                source = "FAQ_OVERRIDE"
        elif faq_answer:
            final_answer = faq_answer
            source = "FAQ"
        elif kb_answer:
            final_answer = kb_answer
            source = "KB"
        else:
            final_answer = None
            source = "NONE"
        
        return {
            "answer": final_answer,
            "source": source,
            "faq_content": faq_answer,
            "kb_content": kb_answer
        }

    # ========================== SECURITY METHODS ==========================
    
    def _check_message_security(self, user_message: str, tenant_name: str) -> tuple[bool, str]:
        """Check message security before processing (legacy method)"""
        return check_message_security(user_message, tenant_name)

    def _check_message_security_with_context(self, user_message: str, tenant_name: str, 
                                           faq_info: str = "", knowledge_base_context: str = "") -> Tuple[bool, str, bool]:
        """
        Enhanced security check that considers available context
        
        Returns:
            (is_safe, security_response, context_override)
        """
        from app.chatbot.security import SecurityPromptManager
        
        is_safe, risk_type, context_has_answer = SecurityPromptManager.check_user_message_security_with_context(
            user_message, faq_info, knowledge_base_context
        )
        
        if not is_safe:
            security_response = SecurityPromptManager.get_security_decline_message(risk_type, tenant_name)
            return False, security_response, False
        elif context_has_answer:
            # Message was risky but context has legitimate answer
            logger.info(f"🔓 Allowing potentially risky question due to legitimate context available")
            return True, "", True
        else:
            return True, "", False

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
        from langchain_openai import ChatOpenAI
        from langchain.chains import ConversationChain
        from langchain.memory import ConversationBufferMemory
        from langchain.prompts import PromptTemplate
        
        logger.info("Creating simple conversation chain without knowledge base")
        
        # Use the new secure prompt builder
        secure_prompt = build_secure_chatbot_prompt(
            tenant_prompt=getattr(tenant, 'system_prompt', None),
            company_name=tenant.business_name,
            faq_info=faq_info,
            knowledge_base_info=""
        )
        
        # Create prompt template with security integrated
        prompt_template = f"""{secure_prompt}

    Conversation History:
    {{history}}

    User: {{input}}

    AI Assistant:"""
        
        prompt = PromptTemplate(
            input_variables=["history", "input"],
            template=prompt_template
        )
        
        # Create LLM
        llm = ChatOpenAI(
            model_name="gpt-3.5-turbo",
            temperature=0.3,
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
        """Initialize the chatbot chain for a tenant with security integration"""
        tenant = self._get_tenant(tenant_id)
        if not tenant:
            logger.error(f"Tenant not found for ID: {tenant_id}")
            return None
        
        # Get knowledge bases and FAQs
        knowledge_bases = self._get_knowledge_bases(tenant_id)
        faqs = self._get_faqs(tenant_id)
        
        logger.info(f"Found {len(faqs)} FAQs for tenant")
        
        # Format FAQ info
        if faqs:
            faq_info = "\n\n".join([f"Question: {faq['question']}\nAnswer: {faq['answer']}" for faq in faqs])
            logger.info(f"FAQ info: {faq_info[:200]}...")
        else:
            faq_info = "No specific FAQs are available."
        
        from langchain_openai import ChatOpenAI
        from langchain.chains import ConversationalRetrievalChain
        from langchain.memory import ConversationBufferMemory
        from langchain.prompts import PromptTemplate
        
        completed_kbs = [kb for kb in knowledge_bases if kb.processing_status == ProcessingStatus.COMPLETED]

        if completed_kbs:
            processor = DocumentProcessor(tenant_id)
                
            for kb in completed_kbs:
                try:
                        logger.info(f"Attempting to load vector store for KB ID: {kb.id}, Vector Store ID: {kb.vector_store_id}")
                        vector_store = processor.get_vector_store(kb.vector_store_id)
                        
                        # Build secure prompt with security layer
                        secure_prompt_content = build_secure_chatbot_prompt(
                            tenant_prompt=getattr(tenant, 'system_prompt', None),
                            company_name=tenant.business_name,
                            faq_info=faq_info,
                            knowledge_base_info="Use this context: {context}"
                        )
                        
                        qa_prompt_template = f"""{secure_prompt_content}
            
CRITICAL: You have access to detailed documentation. You MUST use the provided context to give specific, step-by-step instructions. Do NOT refer users to external guides or say "refer to the guide" - you ARE the guide.

If the context contains setup instructions, provide them directly with numbered steps. Be helpful and detailed.

Context: {{context}}

User Question: {{question}}

Your detailed, step-by-step response:"""
                        
                        qa_prompt = PromptTemplate(
                            template=qa_prompt_template,
                            input_variables=["context", "question"]
                        )
                        
                        # Initialize LLM
                        llm = ChatOpenAI(
                            model_name="gpt-3.5-turbo",
                            temperature=0.3,
                            openai_api_key=settings.OPENAI_API_KEY
                        )
                        
                        # Create memory
                        memory = ConversationBufferMemory(
                            memory_key="chat_history",
                            return_messages=True,
                            output_key="answer"
                        )
                        
                        # Create the chain with secure prompt
                        chain = ConversationalRetrievalChain.from_llm(
                            llm=llm,
                            retriever=vector_store.as_retriever(search_kwargs={"k": 3}),
                            memory=memory,
                            # Corrected arguments for combining documents
                            combine_docs_chain_kwargs={"prompt": qa_prompt},
                            return_source_documents=False,
                            verbose=True
                        )
                                        
                        logger.info(f"Successfully created secure chatbot chain for tenant: {tenant.name} using KB ID: {kb.id}")
                        return chain # Return the successfully created chain
                
                except FileNotFoundError:
                    logger.warning(f"Vector store not found for KB ID: {kb.id}. Trying next available knowledge base.")
                    continue # Try the next knowledge base
                except Exception as e:
                    logger.error(f"Failed to load KB ID: {kb.id} due to an unexpected error: {e}", exc_info=True)
                    continue # Try the next knowledge base

        # If loop finishes without returning a chain, or if no completed_kbs, fall back
        logger.warning(f"No valid knowledge base could be loaded for tenant {tenant.id}. Falling back to simple chain.")
        return self._create_simple_chain(tenant, faq_info)

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

    # ========================== SMART FEEDBACK SYSTEM ==========================
    
    # def process_web_message_with_advanced_feedback(self, api_key: str, user_message: str, user_identifier: str, 
    #                                                 max_context: int = 20) -> Dict[str, Any]:
    #     """
    #     Enhanced with explicit FAQ quality filtering first, then KB fallback
    #     """
    #     from app.chatbot.smart_feedback import AdvancedSmartFeedbackManager
        
    #     # Get tenant from API key
    #     tenant = self._get_tenant_by_api_key(api_key)
    #     if not tenant:
    #         logger.error(f"Invalid API key: {api_key[:5]}...")
    #         return {"error": "Invalid API key", "success": False}
        
    #     # Initialize managers
    #     memory = SimpleChatbotMemory(self.db, tenant.id)
    #     feedback_manager = AdvancedSmartFeedbackManager(self.db, tenant.id)
        
    #     # Get or create session
    #     session_id, is_new_session = memory.get_or_create_session(user_identifier, "web")
        
    #     # FIRST: Check if user is providing email (BEFORE checking if we should request)
    #     extracted_email = feedback_manager.extract_email_from_message(user_message)
    #     if extracted_email:
    #         logger.info(f"📧 Extracted email from message: {extracted_email}")
            
    #         # Store email and acknowledge
    #         if feedback_manager.store_user_email(session_id, extracted_email):
    #             acknowledgment = f"Perfect! I've noted your email as {extracted_email}. How can I assist you today?"
                
    #             # Store both user message and bot response
    #             memory.store_message(session_id, user_message, True)
    #             memory.store_message(session_id, acknowledgment, False)
                
    #             logger.info(f"✅ Email captured and stored: {extracted_email}")
                
    #             return {
    #                 "session_id": session_id,
    #                 "response": acknowledgment,
    #                 "success": True,
    #                 "is_new_session": is_new_session,
    #                 "email_captured": True,
    #                 "user_email": extracted_email,
    #                 "platform": "web"
    #             }
        
    #     # SECOND: Check if we should ask for email (new conversations without email)
    #     if feedback_manager.should_request_email(session_id, user_identifier):
    #         email_request = feedback_manager.generate_email_request_message(tenant.name)
            
    #         # Store the email request as bot message
    #         memory.store_message(session_id, email_request, False)
            
    #         logger.info(f"📧 Requesting email for new conversation: {user_identifier}")
            
    #         return {
    #             "session_id": session_id,
    #             "response": email_request,
    #             "success": True,
    #             "is_new_session": is_new_session,
    #             "email_requested": True,
    #             "platform": "web"
    #         }
        
    #     # 🔍 ENHANCED: CHECK FAQS WITH QUALITY FILTER, THEN KB
    #     faqs = self._get_faqs(tenant.id)
    #     logger.info(f"🔍 Checking {len(faqs)} FAQs with quality filter before using knowledge base")
        
    #     # Try FAQ first with quality check
    #     faq_answer = self._check_faq_with_llm(user_message, faqs)
        
    #     if faq_answer:
    #         logger.info(f"✅ HIGH-QUALITY FAQ ANSWER FOUND - Using direct FAQ response")
            
    #         # Store messages
    #         memory.store_message(session_id, user_message, True)
    #         memory.store_message(session_id, faq_answer, False)
            
    #         return {
    #             "session_id": session_id,
    #             "response": faq_answer,
    #             "success": True,
    #             "is_new_session": is_new_session,
    #             "answered_by": "FAQ",
    #             "faq_matched": True,
    #             "platform": "web"
    #         }
        
    #     # If no adequate FAQ, proceed with KB (which has detailed content)
    #     logger.info(f"📚 No adequate FAQ found - using knowledge base for detailed answer")
        
    #     result = self.process_message_simple_memory(
    #         api_key=api_key,
    #         user_message=user_message,
    #         user_identifier=user_identifier,
    #         platform="web",
    #         max_context=max_context
    #     )
        
    #     if result.get("success"):
    #         result["answered_by"] = "KnowledgeBase"
    #         result["faq_matched"] = False
        
    #     if not result.get("success"):
    #         return result
        
    #     bot_response = result["response"]
        
    #     # Enhanced inadequate response detection with advanced scoring
    #     logger.info(f"🔍 Advanced feedback: Analyzing bot response for inadequate patterns")
        
    #     try:
    #         is_inadequate = feedback_manager.detect_inadequate_response(bot_response)
    #         logger.info(f"🔍 Advanced inadequate response detection result: {is_inadequate}")
            
    #         if is_inadequate:
    #             logger.info(f"🔔 Detected inadequate response, triggering advanced feedback system")
                
    #             # Get conversation context
    #             conversation_history = memory.get_conversation_history(user_identifier, 10)
                
    #             # Create advanced feedback request (sends professional email to tenant)
    #             feedback_id = feedback_manager.create_feedback_request(
    #                 session_id=session_id,
    #                 user_question=user_message,
    #                 bot_response=bot_response,
    #                 conversation_context=conversation_history
    #             )
                
    #             if feedback_id:
    #                 logger.info(f"✅ Created advanced feedback request {feedback_id} with real-time tracking")
    #                 result["feedback_triggered"] = True
    #                 result["feedback_id"] = feedback_id
    #                 result["feedback_system"] = "advanced"
    #             else:
    #                 logger.error(f"❌ Failed to create advanced feedback request")
    #         else:
    #             logger.info(f"✅ Response appears adequate, no feedback needed")
                
    #     except Exception as e:
    #         logger.error(f"💥 Error in advanced feedback detection: {e}")
    #         import traceback
    #         logger.error(traceback.format_exc())
        
    #     return result

    def handle_advanced_tenant_feedback_response(self, api_key: str, feedback_id: str, tenant_response: str) -> Dict[str, Any]:
        """
        Handle tenant's email response using advanced feedback system
        """
        from app.chatbot.smart_feedback import AdvancedSmartFeedbackManager
        
        # Get tenant from API key
        tenant = self._get_tenant_by_api_key(api_key)
        if not tenant:
            return {"error": "Invalid API key", "success": False}
        
        feedback_manager = AdvancedSmartFeedbackManager(self.db, tenant.id)
        
        success = feedback_manager.process_tenant_response(feedback_id, tenant_response)
        
        return {
            "success": success,
            "feedback_id": feedback_id,
            "system": "advanced",
            "message": "Advanced tenant response processed and customer notified with professional follow-up" if success else "Failed to process response"
        }

    def get_advanced_feedback_stats(self, api_key: str) -> Dict[str, Any]:
        """
        Get advanced feedback system statistics with real-time data
        """
        from app.chatbot.smart_feedback import AdvancedSmartFeedbackManager
        
        tenant = self._get_tenant_by_api_key(api_key)
        if not tenant:
            return {"error": "Invalid API key", "success": False}
        
        feedback_manager = AdvancedSmartFeedbackManager(self.db, tenant.id)
        analytics = feedback_manager.get_feedback_analytics()
        
        return {
            "success": True,
            "tenant_id": tenant.id,
            "tenant_name": tenant.name,
            "system": "advanced",
            "analytics": analytics
        }

    # ========================== PLATFORM-SPECIFIC METHODS ==========================
    
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

    # ========================== DELAY PROCESSING ==========================
    
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

    async def process_slack_message_simple_with_delay(self, api_key: str, user_message: str, slack_user_id: str, 
                                                    channel_id: str, team_id: str = None, max_context: int = 20) -> Dict[str, Any]:
        """
        Slack message processing with both simple memory AND delay simulation
        """
        # Get tenant from API key
        tenant = self._get_tenant_by_api_key(api_key)
        if not tenant:
            logger.error(f"Invalid API key: {api_key[:5]}...")
            return {"error": "Invalid API key", "success": False}
        
        # Record start time for delay calculation
        start_time = time.time()
        
        user_identifier = f"slack:{slack_user_id}"
        
        # Initialize simple memory manager
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

    # ========================== UTILITY METHODS ==========================
    
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

    # ========================== LEGACY METHODS (For Backward Compatibility) ==========================
    
    def process_message(self, api_key: str, user_message: str, user_identifier: str) -> Dict[str, Any]:
        """Legacy method - redirects to simple memory processing"""
        logger.info(f"Using legacy process_message method - redirecting to simple memory processing")
        return self.process_message_simple_memory(api_key, user_message, user_identifier)

    def process_message_with_context_security(self, api_key: str, user_message: str, user_identifier: str) -> Dict[str, Any]:
        """Legacy method with context-aware security checking"""
        
        # Get tenant from API key
        tenant = self._get_tenant_by_api_key(api_key)
        if not tenant:
            logger.error(f"Invalid API key: {api_key[:5]}...")
            return {"error": "Invalid API key", "success": False}
        
        # Get context for security checking
        faqs = self._get_faqs(tenant.id)
        faq_info = "\n\n".join([f"Question: {faq['question']}\nAnswer: {faq['answer']}" for faq in faqs]) if faqs else ""
        
        # Get knowledge base context (simplified)
        knowledge_bases = self._get_knowledge_bases(tenant.id)
        kb_context = ""
        if knowledge_bases:
            kb_context = "Knowledge base available with company information"
        
        # 🔒 ENHANCED SECURITY CHECK with context awareness
        is_safe, security_response, context_override = self._check_message_security_with_context(
            user_message, tenant.name, faq_info, kb_context
        )
        
        if not is_safe:
            logger.warning(f"Security risk detected and blocked: {user_message[:50]}...")
            
            # Store the security incident
            session_id, _ = self._get_or_create_session(tenant.id, user_identifier)
            session = self.db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
            
            # Store user message (for audit trail)
            user_msg = ChatMessage(
                session_id=session.id,
                content=user_message,
                is_from_user=True
            )
            self.db.add(user_msg)
            
            # Store security response
            security_msg = ChatMessage(
                session_id=session.id,
                content=security_response,
                is_from_user=False
            )
            self.db.add(security_msg)
            self.db.commit()
            
            return {
                "session_id": session_id,
                "response": security_response,
                "success": True,
                "is_new_session": False,
                "security_declined": True,
                "context_available": bool(faq_info or kb_context)
            }
        
        # Log if security was overridden due to context
        if context_override:
            logger.info(f"🔓 Security pattern detected but allowing due to legitimate context: {user_message[:50]}...")
        
        # Continue with normal processing
        result = self.process_message_simple_memory(api_key, user_message, user_identifier)
        
        # Add context override info to result
        if result.get("success"):
            result["security_context_override"] = context_override
        
        return result
    


    def _check_faq_with_llm(self, user_message: str, faqs: List[Dict[str, str]]) -> Optional[str]:
        """
        Use LLM to intelligently match user questions to FAQs
        Much more flexible than string matching
        """
        if not faqs:
            return None
        
        from langchain_openai import ChatOpenAI
        from langchain.prompts import PromptTemplate
        
        # Format FAQs for the LLM
        faq_list = ""
        for i, faq in enumerate(faqs):
            faq_list += f"{i+1}. Q: {faq['question']}\n   A: {faq['answer']}\n\n"
        
        prompt = PromptTemplate(
            input_variables=["user_question", "faq_list"],
            template="""You are an FAQ matching assistant. Given a user question and a list of FAQs, determine if any FAQ answers the user's question.

    User Question: "{user_question}"

    Available FAQs:
    {faq_list}

    Instructions:
    1. If an FAQ directly answers the user's question, respond with: "MATCH: [FAQ_NUMBER]"
    2. If no FAQ matches, respond with: "NO_MATCH"
    3. Consider variations in wording (e.g., "business hours" matches "what time are you open")
    4. Look for semantic similarity, not just exact words

    Examples:
    - "what are your hours" matches "business hour"
    - "how to integrate slack" matches "How can i set up slack"
    - "when are you open" matches "business hour"

    Response:"""
        )
        
        try:
            llm = ChatOpenAI(model_name="gpt-3.5-turbo", temperature=0.1, openai_api_key=settings.OPENAI_API_KEY)
            
            result = llm(prompt.format(
                user_question=user_message,
                faq_list=faq_list
            )).strip()
            
            logger.info(f"🤖 LLM FAQ matching result: {result}")
            
            # Parse the result
            if result.startswith("MATCH:"):
                try:
                    faq_number = int(result.split(":")[1].strip()) - 1
                    if 0 <= faq_number < len(faqs):
                        matched_faq = faqs[faq_number]
                        
                        # Check if answer is adequate
                        if self._is_faq_answer_adequate(matched_faq['answer']):
                            logger.info(f"🤖 LLM FAQ match found with good answer: {matched_faq['question']}")
                            return self._make_faq_conversational(matched_faq['answer'])
                        else:
                            logger.info(f"🤖 LLM found FAQ match but answer inadequate: {matched_faq['answer'][:50]}...")
                            return None
                except (ValueError, IndexError) as e:
                    logger.warning(f"Could not parse LLM FAQ result: {result}, error: {e}")
            
            logger.info(f"🤖 LLM found no FAQ match for: {user_message}")
            return None
            
        except Exception as e:
            logger.error(f"Error in LLM FAQ matching: {e}")
            # Fallback to original method if LLM fails
            logger.info(f"Falling back to original FAQ matching method")
            return self._check_faq_first_with_quality_filter(user_message, faqs)

    def _get_smart_answer_with_llm(self, user_message: str, tenant_id: int) -> Dict[str, Any]:
        """Let LLM intelligently choose between FAQ and KB and format the response"""
        faqs = self._get_faqs(tenant_id)
        
        # Format FAQs for LLM
        faq_content = ""
        if faqs:
            for faq in faqs:
                faq_content += f"Q: {faq['question']}\nA: {faq['answer']}\n\n"
        
        # Get KB context if available
        kb_context = ""
        try:
            kb_answer = self._get_kb_answer(user_message, tenant_id)
            if kb_answer and len(kb_answer) > 100:
                kb_context = kb_answer[:1000]
        except Exception as e:
            logger.warning(f"Could not get KB context: {e}")
        
        from langchain_openai import ChatOpenAI
        from langchain.prompts import PromptTemplate
        
        prompt = PromptTemplate(
            input_variables=["user_question", "faq_content", "kb_context"],
            template="""You are a helpful customer service assistant. Answer the user's question using the best available information.

    User Question: {user_question}

    Available FAQs:
    {faq_content}

    Knowledge Base Context:
    {kb_context}

    Instructions:
    1. First check if any FAQ directly answers the question with a GOOD answer
    2. If FAQ answer is poor (like "check google", "look it up"), ignore it and use KB instead
    3. If you have detailed KB context, provide specific step-by-step instructions
    4. Be conversational, helpful, and detailed
    5. Don't refer users to external guides - provide the information directly
    6. If you don't have enough information, say so politely

    Your helpful response:"""
        )
        
        try:
            llm = ChatOpenAI(model_name="gpt-3.5-turbo", temperature=0.3, openai_api_key=settings.OPENAI_API_KEY)
            
            # FIX: Use invoke() and handle response properly
            result = llm.invoke(prompt.format(
                user_question=user_message,
                faq_content=faq_content if faq_content else "No FAQs available",
                kb_context=kb_context if kb_context else "No knowledge base context available"
            ))
            
            # FIX: Handle both string and message object responses
            if hasattr(result, 'content'):
                response = result.content.strip()
            else:
                response = str(result).strip()
            
            # Determine source
            source = "LLM_SMART"
            if any(faq['question'].lower() in response.lower() for faq in faqs):
                source = "FAQ_LLM"
            elif kb_context and len(kb_context) > 50:
                source = "KB_LLM"
            
            logger.info(f"🤖 Smart LLM response generated using source: {source}")
            
            return {
                "answer": response,
                "source": source,
                "faq_available": bool(faqs),
                "kb_available": bool(kb_context)
            }
            
        except Exception as e:
            logger.error(f"Error in smart LLM answer generation: {e}")
            return {
                "answer": None,
                "source": "ERROR",
                "error": str(e)
            }

   


    def process_web_message_with_advanced_feedback_llm(self, api_key: str, user_message: str, user_identifier: str, 
                                                max_context: int = 20, use_smart_llm: bool = False) -> Dict[str, Any]:
        """
        Enhanced with LLM-based FAQ matching and smart answer generation + context analysis + FEEDBACK DETECTION
        """
        from app.chatbot.smart_feedback import AdvancedSmartFeedbackManager
        
        # Get tenant from API key
        tenant = self._get_tenant_by_api_key(api_key)
        if not tenant:
            logger.error(f"Invalid API key: {api_key[:5]}...")
            return {"error": "Invalid API key", "success": False}
        
        # Initialize managers
        memory = SimpleChatbotMemory(self.db, tenant.id)
        feedback_manager = AdvancedSmartFeedbackManager(self.db, tenant.id)
        
        # Get or create session
        session_id, is_new_session = memory.get_or_create_session(user_identifier, "web")
        
        # NEW: Context analysis for topic changes
        if not is_new_session:
            conversation_history = memory.get_conversation_history(user_identifier, max_context)
            
            if conversation_history and len(conversation_history) > 1:
                context_analysis = self.analyze_conversation_context_llm(
                    user_message, 
                    conversation_history, 
                    tenant.name
                )
                
                # Handle topic changes
                if context_analysis.get('type') == 'TOPIC_CHANGE':
                    topic_response = self.handle_topic_change_response(
                        user_message,
                        context_analysis.get('previous_topic'),
                        context_analysis.get('suggested_approach'),
                        tenant.name
                    )
                    
                    if topic_response:
                        # Store the topic change response
                        memory.store_message(session_id, user_message, True)
                        memory.store_message(session_id, topic_response, False)
                        
                        return {
                            "session_id": session_id,
                            "response": topic_response,
                            "success": True,
                            "is_new_session": False,
                            "answered_by": "TOPIC_CHANGE_DETECTION",
                            "context_analysis": context_analysis,
                            "platform": "web"
                        }
        
        # Email handling (same as before)
        extracted_email = feedback_manager.extract_email_from_message(user_message)
        if extracted_email:
            logger.info(f"📧 Extracted email from message: {extracted_email}")
            
            if feedback_manager.store_user_email(session_id, extracted_email):
                acknowledgment = f"Perfect! I've noted your email as {extracted_email}. How can I assist you today?"
                
                memory.store_message(session_id, user_message, True)
                memory.store_message(session_id, acknowledgment, False)
                
                return {
                    "session_id": session_id,
                    "response": acknowledgment,
                    "success": True,
                    "is_new_session": is_new_session,
                    "email_captured": True,
                    "user_email": extracted_email,
                    "platform": "web"
                }
        
        if feedback_manager.should_request_email(session_id, user_identifier):
            email_request = feedback_manager.generate_email_request_message(tenant.name)
            memory.store_message(session_id, email_request, False)
            
            return {
                "session_id": session_id,
                "response": email_request,
                "success": True,
                "is_new_session": is_new_session,
                "email_requested": True,
                "platform": "web"
            }
        
        # 🤖 NEW: LLM-BASED SMART ANSWER GENERATION WITH FEEDBACK DETECTION
        if use_smart_llm:
            logger.info(f"🤖 Using smart LLM answer generation")
            
            smart_result = self._get_smart_answer_with_llm(user_message, tenant.id)
            
            if smart_result.get("answer"):
                logger.info(f"✅ SMART LLM ANSWER GENERATED - Source: {smart_result['source']}")
                
                # Store messages in memory
                memory.store_message(session_id, user_message, True)
                memory.store_message(session_id, smart_result["answer"], False)
                
                # 🔔 CRITICAL: ADD FEEDBACK DETECTION FOR SMART LLM RESPONSES
                result = {
                    "session_id": session_id,
                    "response": smart_result["answer"],
                    "success": True,
                    "is_new_session": is_new_session,
                    "answered_by": smart_result["source"],
                    "faq_available": smart_result.get("faq_available", False),
                    "kb_available": smart_result.get("kb_available", False),
                    "platform": "web"
                }
                
                # Detect inadequate responses and trigger feedback system
                try:
                    is_inadequate = feedback_manager.detect_inadequate_response(smart_result["answer"])
                    logger.info(f"🔍 Smart LLM inadequate response detection result: {is_inadequate}")
                    
                    if is_inadequate:
                        logger.info(f"🔔 Detected inadequate Smart LLM response, triggering feedback system")
                        
                        # Get conversation context
                        conversation_history = memory.get_conversation_history(user_identifier, 10)
                        
                        # Create feedback request
                        feedback_id = feedback_manager.create_feedback_request(
                            session_id=session_id,
                            user_question=user_message,
                            bot_response=smart_result["answer"],
                            conversation_context=conversation_history
                        )
                        
                        if feedback_id:
                            # Add feedback info to response
                            result["feedback_triggered"] = True
                            result["feedback_id"] = feedback_id
                            result["feedback_system"] = "advanced"
                            
                            # Optionally add feedback acknowledgment to response
                            feedback_msg = f"\n\nI've noticed this might not fully answer your question. I've sent this conversation to our team for review, and they'll follow up with you shortly with a better response."
                            result["response"] = smart_result["answer"] + feedback_msg
                            
                            logger.info(f"✅ Feedback request created for Smart LLM response: {feedback_id}")
                        else:
                            logger.error(f"❌ Failed to create feedback request for Smart LLM response")
                    else:
                        logger.info(f"✅ Smart LLM response appears adequate, no feedback needed")
                        
                except Exception as feedback_error:
                    logger.error(f"💥 Error in Smart LLM feedback detection: {feedback_error}")
                    # Continue with normal response if feedback system fails
                
                return result
        
        # 🤖 ENHANCED: LLM-BASED FAQ MATCHING (fallback or primary method)
        faqs = self._get_faqs(tenant.id)
        logger.info(f"🤖 Using LLM-based FAQ matching for {len(faqs)} FAQs")
        
        # Try LLM-based FAQ matching first
        faq_answer = self._check_faq_with_llm(user_message, faqs)
        
        if faq_answer:
            logger.info(f"✅ LLM FAQ MATCH FOUND - Using FAQ response")
            
            memory.store_message(session_id, user_message, True)
            memory.store_message(session_id, faq_answer, False)
            
            return {
                "session_id": session_id,
                "response": faq_answer,
                "success": True,
                "is_new_session": is_new_session,
                "answered_by": "FAQ_LLM",
                "faq_matched": True,
                "platform": "web"
            }
        
        # If no FAQ match, proceed with knowledge base
        logger.info(f"📚 No adequate FAQ found with LLM - using knowledge base")
        
        result = self.process_message_simple_memory(
            api_key=api_key,
            user_message=user_message,
            user_identifier=user_identifier,
            platform="web",
            max_context=max_context
        )
        
        if result.get("success"):
            result["answered_by"] = "KnowledgeBase"
            result["faq_matched"] = False
        
        # Continue with feedback detection for KB responses...
        if not result.get("success"):
            return result
        
        bot_response = result["response"]
        
        try:
            is_inadequate = feedback_manager.detect_inadequate_response(bot_response)
            
            if is_inadequate:
                logger.info(f"🔔 Detected inadequate KB response, triggering feedback system")
                
                conversation_history = memory.get_conversation_history(user_identifier, 10)
                
                feedback_id = feedback_manager.create_feedback_request(
                    session_id=session_id,
                    user_question=user_message,
                    bot_response=bot_response,
                    conversation_context=conversation_history
                )
                
                if feedback_id:
                    result["feedback_triggered"] = True
                    result["feedback_id"] = feedback_id
                    result["feedback_system"] = "advanced"
            
        except Exception as e:
            logger.error(f"💥 Error in KB feedback detection: {e}")
        
        return result






    def _check_faq_first_with_quality_filter(self, user_message: str, faqs: List[Dict[str, str]]) -> Optional[str]:
        """
        Check FAQs first but filter out low-quality answers
        Returns high-quality FAQ answer if match found, None otherwise
        """
        if not faqs:
            return None
        
        user_message_lower = user_message.lower().strip()
        
        for faq in faqs:
            faq_question_lower = faq['question'].lower().strip()
            
            # 1. Exact match
            if user_message_lower == faq_question_lower:
                # Check if FAQ answer is high quality
                if self._is_faq_answer_adequate(faq['answer']):
                    logger.info(f"📋 EXACT FAQ match found with good answer: {faq['question']}")
                    return self._make_faq_conversational(faq['answer'])
                else:
                    logger.info(f"📋 FAQ match found but answer is inadequate, will use KB instead")
                    return None
            
            # 2. High similarity match (90%+ for stricter matching)
            user_words = set(re.findall(r'\b\w{3,}\b', user_message_lower))
            faq_words = set(re.findall(r'\b\w{3,}\b', faq_question_lower))
            
            if user_words and faq_words:
                overlap = len(user_words.intersection(faq_words))
                user_word_ratio = overlap / len(user_words)
                faq_word_ratio = overlap / len(faq_words)
                
                # Much stricter: 90%+ match AND similar question length
                length_ratio = min(len(user_message), len(faq['question'])) / max(len(user_message), len(faq['question']))
                
                if user_word_ratio >= 0.9 and faq_word_ratio >= 0.9 and length_ratio >= 0.8:
                    if self._is_faq_answer_adequate(faq['answer']):
                        logger.info(f"📋 VERY HIGH SIMILARITY FAQ match found with good answer: {faq['question']}")
                        return self._make_faq_conversational(faq['answer'])
                    else:
                        logger.info(f"📋 High similarity FAQ found but answer inadequate, using KB instead")
                        return None
        
        logger.info(f"📋 No adequate FAQ match found for: {user_message}")
        return None
    

    def analyze_conversation_context_llm(self, current_message: str, conversation_history: List[Dict], 
                                    company_name: str) -> Dict[str, Any]:
        """Smart context analysis with time-aware greeting detection AND conversation questions"""
        
        user_msg_lower = current_message.lower().strip()
        greetings = ['hello', 'hi', 'hey', 'good morning', 'good afternoon', 'what\'s up']
        
        # NEW: Check for conversation history questions
        conversation_questions = [
            'what was our last conversation', 'what were we discussing', 'what did we talk about',
            'previous conversation', 'last discussion', 'what was the topic', 'earlier conversation',
            'before', 'what was our conversation about', 'remind me what we discussed'
        ]
        
        # Step 1: Check if it's a greeting
        is_greeting = any(greeting in user_msg_lower for greeting in greetings)
        
        # NEW: Check if it's asking about previous conversation
        is_conversation_question = any(phrase in user_msg_lower for phrase in conversation_questions)
        
        has_previous_conversation = len(conversation_history) > 2
        
        # Handle conversation questions
        if is_conversation_question and has_previous_conversation:
            logger.info(f"🔍 User asking about previous conversation: {current_message}")
            return self._analyze_previous_conversation_topic(conversation_history, current_message)
        
        # Handle greetings (existing logic)
        if not (is_greeting and has_previous_conversation):
            return {'type': 'CONTINUATION', 'reasoning': 'Not a greeting or no previous conversation'}
        
        # Step 2: Check time since last conversation (existing logic for greetings)
        try:
            # Get the last message timestamp
            last_message = conversation_history[-1] if conversation_history else None
            if last_message and 'timestamp' in last_message:
                from datetime import datetime, timedelta
                import pytz
                
                # Parse timestamp and handle timezone awareness
                timestamp_str = last_message['timestamp']
                
                # Remove 'Z' and handle different timestamp formats
                if timestamp_str.endswith('Z'):
                    timestamp_str = timestamp_str.replace('Z', '+00:00')
                
                # Parse the timestamp
                last_timestamp = datetime.fromisoformat(timestamp_str)
                
                # Make sure both datetimes are timezone-aware
                if last_timestamp.tzinfo is None:
                    # If naive, assume UTC
                    last_timestamp = last_timestamp.replace(tzinfo=pytz.UTC)
                
                # Current time in UTC
                current_time = datetime.now(pytz.UTC)
                
                time_since_last = current_time - last_timestamp
                hours_since_last = time_since_last.total_seconds() / 3600
                
                logger.info(f"⏰ Time since last conversation: {hours_since_last:.1f} hours")
                
                # If less than 12 hours, treat as continuation with warm greeting
                if hours_since_last < 12:
                    return {
                        'type': 'RECENT_GREETING',
                        'hours_since_last': hours_since_last,
                        'reasoning': f'Recent greeting ({hours_since_last:.1f}h ago) - warm acknowledgment'
                    }
                # If 12+ hours, treat as fresh start
                else:
                    return {
                        'type': 'FRESH_GREETING', 
                        'hours_since_last': hours_since_last,
                        'reasoning': f'Old conversation ({hours_since_last:.1f}h ago) - fresh start'
                    }
            
        except Exception as e:
            logger.error(f"Error checking conversation time: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            # Fall back to simple topic analysis without time checking
            logger.info("Falling back to simple greeting without time checking")
        
        # Step 3: If we can't determine time, just do a simple greeting
        logger.info(f"🧠 Simple greeting detected without time context")
        
        return {
            'type': 'SIMPLE_GREETING',
            'reasoning': 'Simple greeting without time context'
        }

    def _analyze_previous_conversation_topic(self, conversation_history: List[Dict], current_message: str) -> Dict[str, Any]:
        """Analyze what the previous conversation was about"""
        
        try:
            # Get last few messages to understand context
            recent_messages = []
            for msg in conversation_history[-10:]:  # More messages for better context
                role = "User" if msg.get("role") == "user" else "Assistant"
                content = msg.get("content", "")[:200]  # Limit length
                recent_messages.append(f"{role}: {content}")
            
            conversation_context = "\n".join(recent_messages)
            
            from langchain_openai import ChatOpenAI
            from langchain.prompts import PromptTemplate
            
            prompt = PromptTemplate(
                input_variables=["conversation", "question"],
                template="""Analyze this conversation history and provide a helpful summary of what was discussed.

    RECENT CONVERSATION:
    {conversation}

    USER QUESTION: "{question}"

    TASK: Provide a brief, helpful summary of what was mainly discussed in this conversation.

    Be specific and mention:
    1. The main topic(s) that were discussed
    2. Any specific issues or questions that came up
    3. What stage the conversation was at

    Keep it conversational and helpful, like: "We were discussing your Slack integration setup. You were working on configuring the bot token and we covered the OAuth permissions."

    Your helpful summary:"""
            )
            
            llm = ChatOpenAI(model_name="gpt-3.5-turbo", temperature=0.2, openai_api_key=settings.OPENAI_API_KEY)
            result = llm.invoke(prompt.format(conversation=conversation_context, question=current_message))
            
            response_text = result.content if hasattr(result, 'content') else str(result)
            
            logger.info(f"📝 Generated conversation summary: {response_text[:100]}...")
            
            return {
                'type': 'CONVERSATION_SUMMARY',
                'conversation_summary': response_text.strip(),
                'reasoning': 'User asked about previous conversation'
            }
            
        except Exception as e:
            logger.error(f"Error analyzing previous conversation: {e}")
            return {
                'type': 'CONVERSATION_SUMMARY_FALLBACK',
                'conversation_summary': "We were discussing various topics. Is there something specific you'd like to continue with?",
                'reasoning': f'Fallback due to error: {str(e)}'
            }

    def handle_topic_change_response(self, current_message: str, previous_topic: str, 
                                suggested_approach: str, company_name: str, 
                                context_analysis: Dict = None) -> Optional[str]:
        """Generate responses for greetings AND conversation history questions - HYBRID VERSION"""
        
        # Add debug logging
        logger.info(f"🔍 handle_topic_change_response called:")
        logger.info(f"   - current_message: {current_message}")
        logger.info(f"   - context_analysis: {context_analysis}")
        
        if not context_analysis:
            logger.warning("No context analysis provided to greeting handler")
            return None
        
        greeting_type = context_analysis.get('type', 'UNKNOWN')
        logger.info(f"🎯 Processing type: {greeting_type}")
        
        # Handle conversation summary requests with enhanced LLM
        if greeting_type in ['CONVERSATION_SUMMARY', 'CONVERSATION_SUMMARY_FALLBACK']:
            conversation_summary = context_analysis.get('conversation_summary', 'We discussed various topics.')
            
            # Use LLM to make the conversation summary more natural
            return self._enhance_conversation_summary_with_llm(
                current_message, conversation_summary, company_name
            )
        
        # For ALL OTHER types, use your existing LLM function with higher temperature for variety
        else:
            logger.info(f"🤖 Using your existing LLM function for type: {greeting_type}")
            return self._generate_llm_greeting_response_enhanced(
                current_message, previous_topic, suggested_approach, company_name, context_analysis
            )


    def _generate_llm_greeting_response_enhanced(self, current_message: str, previous_topic: str, 
                                            suggested_approach: str, company_name: str, 
                                            context_analysis: Dict) -> Optional[str]:
        """Enhanced version with natural LLM generation - no examples"""
        
        try:
            from langchain_openai import ChatOpenAI
            from langchain.prompts import PromptTemplate
            
            greeting_type = context_analysis.get('type', 'UNKNOWN')
            hours_since_last = context_analysis.get('hours_since_last', 0)
            
            # Clean prompt without contaminating examples
            prompt_template = """You are a helpful AI assistant for {company_name}. A customer just greeted you.

    CUSTOMER'S MESSAGE: "{current_message}"
    GREETING TYPE: {greeting_type}
    PREVIOUS TOPIC: {previous_topic}
    TIME SINCE LAST CHAT: {hours_since_last:.1f} hours ago

    TASK: Generate a friendly greeting that:
    1. Responds to their greeting warmly and naturally
    2. Varies your response style (don't always say the same thing)
    3. Asks how you can help them today
    4. Keep it brief and welcoming (under 30 words)
    5. For recent conversations, acknowledge continuity
    6. For fresh conversations, be welcoming but fresh
    7. If they ask about previous topics, summarize naturally and offer to continue or help with something new
    8. Try to avoid any general knowledge questions, just tell them you wouldnt be answering that politely. but answer if its within the scope of tenant business
    9. You must never sound robotic

    Your friendly, varied greeting response:"""

            prompt = PromptTemplate(
                input_variables=["current_message", "company_name", "greeting_type", "previous_topic", "hours_since_last"],
                template=prompt_template
            )
            
            llm = ChatOpenAI(
                model_name="gpt-3.5-turbo", 
                temperature=0.6,  # Increased for more variety
                openai_api_key=settings.OPENAI_API_KEY
            )
            
            result = llm.invoke(prompt.format(
                current_message=current_message,
                company_name=company_name,
                greeting_type=greeting_type,
                previous_topic=previous_topic or "none",
                hours_since_last=hours_since_last
            ))
            
            response_text = result.content if hasattr(result, 'content') else str(result)
            response_text = response_text.strip()
            
            # Validation
            if len(response_text) > 150:
                response_text = response_text[:150] + "..."
            
            if len(response_text) < 5:
                return "Hello! How can I help you today?"
            
            logger.info(f"🤖 Generated enhanced LLM greeting: {response_text[:40]}...")
            return response_text
            
        except Exception as e:
            logger.error(f"Error generating enhanced LLM greeting response: {e}")
            return "Hello! How can I help you today?"



    def _enhance_conversation_summary_with_llm(self, current_message: str, conversation_summary: str, company_name: str) -> str:
        """Make conversation summaries more natural and engaging"""
        
        try:
            from langchain_openai import ChatOpenAI
            from langchain.prompts import PromptTemplate
            
            prompt = PromptTemplate(
                input_variables=["current_message", "conversation_summary", "company_name"],
                template="""You are a helpful AI assistant for {company_name}. A customer is asking about your previous conversation.

    CUSTOMER ASKED: "{current_message}"
    WHAT YOU DISCUSSED: {conversation_summary}

    TASK: Create a natural, engaging response that:
    1. Summarizes what you discussed in a conversational way
    2. Offers to continue or help with something new
    3. Feels helpful and remembers the context
    4. Sounds natural, not robotic

    EXAMPLES:
    - "We were chatting about your Slack setup! You were working on the bot token. Want to continue with that, or need help with something else?"
    - "Earlier we discussed your billing questions. I remember you were asking about the pricing plans. How's that going?"

    Your natural conversation recap:"""
            )
            
            llm = ChatOpenAI(
                model_name="gpt-3.5-turbo", 
                temperature=0.5,
                openai_api_key=settings.OPENAI_API_KEY
            )
            
            result = llm.invoke(prompt.format(
                current_message=current_message,
                conversation_summary=conversation_summary,
                company_name=company_name
            ))
            
            response_text = result.content if hasattr(result, 'content') else str(result)
            return response_text.strip()
            
        except Exception as e:
            logger.error(f"Error enhancing conversation summary: {e}")
            return conversation_summary  # Fallback to original summary




    def _fallback_greeting_response(self, current_message: str, company_name: str, greeting_type: str = None) -> str:
        """Simple fallback greeting responses"""
        
        if greeting_type == 'RECENT_GREETING':
            return "Hello! I'm still here and ready to help. What can I assist you with today?"
        elif greeting_type == 'FRESH_GREETING':
            return f"Hello! How can I help you today?"
        else:
            return f"Hello! How can I help you today?"


    def _check_troubleshooting_triggers(self, user_message: str, tenant_id: int) -> Optional[Dict]:
        """
        Check if user message triggers any troubleshooting guide
        """
        try:
            # Get active troubleshooting guides
            troubleshooting_kbs = self.db.query(KnowledgeBase).filter(
                KnowledgeBase.tenant_id == tenant_id,
                KnowledgeBase.is_troubleshooting == True,
                KnowledgeBase.processing_status == ProcessingStatus.COMPLETED,
                KnowledgeBase.troubleshooting_flow.isnot(None)
            ).all()
            
            if not troubleshooting_kbs:
                return None
            
            user_msg_lower = user_message.lower()
            best_match = None
            best_score = 0
            
            for kb in troubleshooting_kbs:
                flow = kb.troubleshooting_flow
                if not flow:
                    continue
                
                # Check keywords
                keywords = flow.get("keywords", [])
                keyword_matches = sum(1 for kw in keywords if kw.lower() in user_msg_lower)
                
                # Check title/description similarity
                title_match = self._calculate_similarity(user_message, flow.get("title", ""))
                desc_match = self._calculate_similarity(user_message, flow.get("description", ""))
                
                # Calculate overall score
                score = (keyword_matches * 0.5) + (title_match * 0.3) + (desc_match * 0.2)
                
                if score > best_score and score > 0.3:  # Threshold
                    best_score = score
                    best_match = {
                        "kb_id": kb.id,
                        "flow": flow,
                        "score": score
                    }
            
            return best_match
            
        except Exception as e:
            logger.error(f"Error checking troubleshooting triggers: {e}")
            return None

    def _execute_troubleshooting_step(self, session_id: str, user_message: str, current_state: Dict) -> Dict[str, Any]:
        """
        Execute the current step in a troubleshooting flow
        """
        try:
            flow = current_state.get("flow", {})
            current_step_id = current_state.get("current_step", "step1")
            
            # Find current step
            current_step = None
            for step in flow.get("steps", []):
                if step.get("id") == current_step_id:
                    current_step = step
                    break
            
            if not current_step:
                return {
                    "success": False,
                    "response": "I'm having trouble with the troubleshooting guide. Let me help you another way.",
                    "end_troubleshooting": True
                }
            
            # Process user response and determine next step
            branches = current_step.get("branches", {})
            next_step_id = None
            branch_message = None
            
            # Match user response to branches
            user_msg_lower = user_message.lower()
            for branch_pattern, branch_data in branches.items():
                patterns = branch_pattern.split("|")
                if any(pattern in user_msg_lower for pattern in patterns):
                    next_step_id = branch_data.get("next")
                    branch_message = branch_data.get("message", "")
                    break
            
            # Default branch if no match
            if not next_step_id and "default" in branches:
                default_branch = branches["default"]
                next_step_id = default_branch.get("next")
                branch_message = default_branch.get("message", "I didn't understand that. Let me ask again.")
            
            # Find next step
            next_step = None
            for step in flow.get("steps", []):
                if step.get("id") == next_step_id:
                    next_step = step
                    break
            
            # Build response
            response_parts = []
            if branch_message:
                response_parts.append(branch_message)
            
            if next_step:
                response_parts.append(next_step.get("message", ""))
                
                # Update state
                current_state["current_step"] = next_step_id
                
                return {
                    "success": True,
                    "response": "\n\n".join(response_parts),
                    "continue_troubleshooting": True,
                    "wait_for_response": next_step.get("wait_for_response", True),
                    "updated_state": current_state
                }
            else:
                # End of flow
                success_msg = flow.get("success_message", "Great! The issue should be resolved now.")
                return {
                    "success": True,
                    "response": success_msg,
                    "end_troubleshooting": True
                }
            
        except Exception as e:
            logger.error(f"Error executing troubleshooting step: {e}")
            return {
                "success": False,
                "response": "I encountered an error in the troubleshooting guide. Let me help you another way.",
                "end_troubleshooting": True
            }

    # Modify the _get_harmonized_answer method to include troubleshooting
    def _get_harmonized_answer(self, user_message: str, tenant_id: int) -> Dict[str, Any]:
        """
        Get harmonized answer using hierarchical approach:
        1. FAQ (authoritative, current)
        2. Troubleshooting guides (NEW)
        3. KB (detailed context)
        4. Combined (if compatible)
        """
        # Check if there's an active troubleshooting session
        from app.chatbot.simple_memory import SimpleChatbotMemory
        memory = SimpleChatbotMemory(self.db, tenant_id)
        
        # This would need the session_id - you'd pass it from the main process_message method
        # For now, showing the structure:
        
        # Step 1: Check FAQ first (existing code)
        faqs = self._get_faqs(tenant_id)
        faq_answer = self._check_faq_with_llm(user_message, faqs)
        
        # Step 2: Check for troubleshooting triggers
        if not faq_answer:
            troubleshooting_match = self._check_troubleshooting_triggers(user_message, tenant_id)
            if troubleshooting_match:
                flow = troubleshooting_match["flow"]
                initial_msg = flow.get("initial_message", "I can help you with that. Let me guide you through the solution.")
                first_step = flow.get("steps", [{}])[0]
                
                return {
                    "answer": f"{initial_msg}\n\n{first_step.get('message', '')}",
                    "source": "TROUBLESHOOTING",
                    "troubleshooting_active": True,
                    "troubleshooting_state": {
                        "kb_id": troubleshooting_match["kb_id"],
                        "flow": flow,
                        "current_step": first_step.get("id", "step1")
                    }
                }
        
        # Step 3: Continue with KB search (existing code)
        kb_answer = None
        if not faq_answer:
            kb_answer = self._get_kb_answer(user_message, tenant_id)
