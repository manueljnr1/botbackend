import uuid
import logging
from typing import Dict, List, Any, Optional, Tuple
from sqlalchemy.orm import Session
from app.knowledge_base.processor import DocumentProcessor
from app.chatbot.chains import create_chatbot_chain
from app.tenants.models import Tenant
from app.knowledge_base.models import KnowledgeBase, FAQ
from app.chatbot.models import ChatSession, ChatMessage
from app.config import settings

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ChatbotEngine:
    """The main chatbot engine that handles conversations"""
    
    def __init__(self, db: Session):
        self.db = db
        self.active_sessions = {}  # In-memory storage of active chat sessions
    
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
                user_identifier=user_identifier
            )
            self.db.add(session)
            self.db.commit()
            self.db.refresh(session)
            created = True
            logger.info(f"Created new chat session: {session_id}")
        else:
            logger.info(f"Using existing chat session: {session.session_id}")
        
        return session.session_id, created
    
    def _create_simple_chain(self, tenant, faq_info):
        """Helper method to create a simple conversation chain"""
        # Import required modules
        from app.chatbot.prompts import SYSTEM_PROMPT_TEMPLATE
        from langchain_openai import ChatOpenAI
        from langchain.chains import ConversationChain
        from langchain.memory import ConversationBufferMemory
        
        logger.info("Creating simple conversation chain without knowledge base")
        
        # Check if tenant has custom system prompt
        if hasattr(tenant, 'system_prompt') and tenant.system_prompt:
            # Replace placeholders in custom prompt
            system_prompt = tenant.system_prompt
            system_prompt = system_prompt.replace("{company_name}", tenant.name)
            system_prompt = system_prompt.replace("{faq_info}", faq_info)
            system_prompt = system_prompt.replace("{knowledge_base_info}", "No knowledge base available yet.")
        else:
            # Format default system prompt
            system_prompt = SYSTEM_PROMPT_TEMPLATE.substitute(
                company_name=tenant.name,
                knowledge_base_info="No knowledge base available yet.",
                faq_info=faq_info
            )
        
        # Create a direct LLM chain
        llm = ChatOpenAI(
            model_name="gpt-3.5-turbo",
            temperature=0.7,
            openai_api_key=settings.OPENAI_API_KEY
        )
        
        memory = ConversationBufferMemory(return_messages=True)
        chain = ConversationChain(
            llm=llm,
            memory=memory,
            verbose=True
        )
        
        # Store the system prompt in a way the chain can use it
        chain.prompt.template = system_prompt + "\n\nHuman: {input}\nAI: "
        
        return chain
    
    def _initialize_chatbot_chain(self, tenant_id: int) -> Optional[Any]:
        """Initialize the chatbot chain for a tenant"""
        tenant = self._get_tenant(tenant_id)
        if not tenant:
            logger.error(f"Tenant not found for ID: {tenant_id}")
            return None
        
        # Get knowledge bases
        knowledge_bases = self._get_knowledge_bases(tenant_id)
        
        # Get FAQs
        faqs = self._get_faqs(tenant_id)
        logger.info(f"Found {len(faqs)} FAQs for tenant")

        faq_info = "\n".join([f"Q: {faq['question']}\nA: {faq['answer']}" for faq in faqs]) if faqs else "No FAQs available yet."
        
        # Import required modules
        from app.chatbot.prompts import SYSTEM_PROMPT_TEMPLATE
        from langchain_openai import ChatOpenAI
        from langchain.chains import ConversationalRetrievalChain
        from langchain.memory import ConversationBufferMemory
        from langchain.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
        
        # If we have knowledge bases, use retrieval chain
        if knowledge_bases:
            # Use the first knowledge base for now (can be extended to combine multiple)
            kb = knowledge_bases[0]
            logger.info(f"Using knowledge base: {kb.name} (ID: {kb.id}, Vector Store: {kb.vector_store_id})")
            
            # Initialize document processor and get vector store
            processor = DocumentProcessor(tenant_id)
            try:
                vector_store = processor.get_vector_store(kb.vector_store_id)
                if vector_store is None:
                    logger.error(f"Failed to load vector store: {kb.vector_store_id}")
                    # Fall back to simple conversation
                    return self._create_simple_chain(tenant, faq_info)
                logger.info(f"Successfully loaded vector store")
            except Exception as e:
                logger.error(f"Error loading vector store: {e}")
                # Fall back to simple conversation
                return self._create_simple_chain(tenant, faq_info)
            
            try:
                # Check if tenant has custom system prompt
                system_prompt = ""
                if hasattr(tenant, 'system_prompt') and tenant.system_prompt:
                    # Replace placeholders in custom prompt
                    system_prompt = tenant.system_prompt
                    system_prompt = system_prompt.replace("{company_name}", tenant.name)
                    system_prompt = system_prompt.replace("{faq_info}", faq_info)
                    system_prompt = system_prompt.replace("{knowledge_base_info}", f"Knowledge from {kb.name}")
                else:
                    # Use default system prompt
                    system_prompt = SYSTEM_PROMPT_TEMPLATE.substitute(
                        company_name=tenant.name,
                        knowledge_base_info=f"Knowledge from {kb.name}",
                        faq_info=faq_info
                    )
                
                # Initialize the LLM
                llm = ChatOpenAI(
                    model_name="gpt-3.5-turbo",
                    temperature=0.7,
                    openai_api_key=settings.OPENAI_API_KEY
                )
                
                # Create conversation memory
                memory = ConversationBufferMemory(
                    memory_key="chat_history",
                    return_messages=True
                )
                
                # Create system and human message prompts
                system_message_prompt = SystemMessagePromptTemplate.from_template(system_prompt)
                human_message_prompt = HumanMessagePromptTemplate.from_template("{question}")
                chat_prompt = ChatPromptTemplate.from_messages([system_message_prompt, human_message_prompt])
                
                # Create the chain with the prompt template
                logger.info("Creating ConversationalRetrievalChain with vector store...")
                
                chain = ConversationalRetrievalChain.from_llm(
                    llm=llm,
                    retriever=vector_store.as_retriever(search_kwargs={"k": 5}),
                    memory=memory,
                    verbose=True,
                     combine_docs_chain_kwargs={"prompt": chat_prompt}
                )

               
                logger.info(f"Successfully created chatbot chain for tenant: {tenant.name}")
                return chain
            except Exception as e:
                logger.error(f"Error creating chatbot chain: {e}", exc_info=True)
                # Fall back to simple conversation
                return self._create_simple_chain(tenant, faq_info)
        else:
            # No knowledge bases, create a simple chain
            return self._create_simple_chain(tenant, faq_info)
    
    def process_message(
        self, api_key: str, user_message: str, user_identifier: str
    ) -> Dict[str, Any]:
        """Process an incoming message and return a response"""
        # Get tenant from API key
        tenant = self._get_tenant_by_api_key(api_key)
        if not tenant:
            logger.error(f"Invalid API key: {api_key[:5]}...")
            return {
                "error": "Invalid API key",
                "success": False
            }
        
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
                return {
                    "error": "Failed to initialize chatbot",
                    "success": False
                }
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
            return {
                "error": f"Error generating response: {str(e)}",
                "success": False
            }
    
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