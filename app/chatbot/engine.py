# import uuid
# from typing import Dict, List, Any, Optional, Tuple
# from sqlalchemy.orm import Session
# from app.knowledge_base.processor import DocumentProcessor
# from app.chatbot.chains import create_chatbot_chain
# from app.tenants.models import Tenant
# from app.knowledge_base.models import KnowledgeBase, FAQ
# from app.chatbot.models import ChatSession, ChatMessage

# class ChatbotEngine:
#     """The main chatbot engine that handles conversations"""
    
#     def __init__(self, db: Session):
#         self.db = db
#         self.active_sessions = {}  # In-memory storage of active chat sessions
    
#     def _get_tenant(self, tenant_id: int) -> Optional[Tenant]:
#         """Get tenant information"""
#         return self.db.query(Tenant).filter(Tenant.id == tenant_id, Tenant.is_active == True).first()
    
#     def _get_tenant_by_api_key(self, api_key: str) -> Optional[Tenant]:
#         """Get tenant information by API key"""
#         return self.db.query(Tenant).filter(Tenant.api_key == api_key, Tenant.is_active == True).first()
    
#     def _get_knowledge_bases(self, tenant_id: int) -> List[KnowledgeBase]:
#         """Get all knowledge bases for a tenant"""
#         return self.db.query(KnowledgeBase).filter(KnowledgeBase.tenant_id == tenant_id).all()
    
#     def _get_faqs(self, tenant_id: int) -> List[Dict[str, str]]:
#         """Get all FAQs for a tenant"""
#         faqs = self.db.query(FAQ).filter(FAQ.tenant_id == tenant_id).all()
#         return [{"question": faq.question, "answer": faq.answer} for faq in faqs]
    
#     def _get_or_create_session(self, tenant_id: int, user_identifier: str) -> Tuple[str, bool]:
#         """Get existing or create new chat session"""
#         # Check for existing session
#         session = self.db.query(ChatSession).filter(
#             ChatSession.tenant_id == tenant_id,
#             ChatSession.user_identifier == user_identifier,
#             ChatSession.is_active == True
#         ).first()
        
#         created = False
#         if not session:
#             # Create new session
#             session_id = str(uuid.uuid4())
#             session = ChatSession(
#                 session_id=session_id,
#                 tenant_id=tenant_id,
#                 user_identifier=user_identifier
#             )
#             self.db.add(session)
#             self.db.commit()
#             self.db.refresh(session)
#             created = True
        
#         return session.session_id, created
    
#     def _initialize_chatbot_chain(self, tenant_id: int) -> Optional[Any]:
#         """Initialize the chatbot chain for a tenant"""
#         tenant = self._get_tenant(tenant_id)
#         if not tenant:
#             return None
        
#         # Get knowledge bases
#         knowledge_bases = self._get_knowledge_bases(tenant_id)
        
#         # Get FAQs
#         faqs = self._get_faqs(tenant_id)
        
#         # If we have knowledge bases, use retrieval chain
#         if knowledge_bases:
#             # Use the first knowledge base for now (can be extended to combine multiple)
#             kb = knowledge_bases[0]
        
#         # Initialize document processor and get vector store
#         processor = DocumentProcessor(tenant_id)
#         try:
#             vector_store = processor.get_vector_store(kb.vector_store_id)
            
#             # Create chatbot chain
#             chain = create_chatbot_chain(vector_store, tenant.name, faqs)
#             return chain
#         except Exception as e:
#             print(f"Error initializing vector store: {str(e)}")
#             return None
    
#     # If we don't have knowledge bases but have FAQs, create a simple chain
#     elif faqs:
#         from langchain_community.chat_models import ChatOpenAI
#         from langchain.chains import ConversationChain
#         from langchain.memory import ConversationBufferMemory
#         from app.config import settings
#         from app.chatbot.prompts import SYSTEM_PROMPT_TEMPLATE
        
#         # Format system prompt
#         system_prompt = SYSTEM_PROMPT_TEMPLATE.substitute(
#             company_name=tenant.name,
#             knowledge_base_info="No knowledge base available yet.",
#             faq_info="\n".join([f"Q: {faq['question']}\nA: {faq['answer']}" for faq in faqs])
#         )
        
#         # Create a direct LLM chain
#         llm = ChatOpenAI(
#             model_name="gpt-4",
#             temperature=0.7,
#             openai_api_key=settings.OPENAI_API_KEY
#         )
        
#         memory = ConversationBufferMemory(return_messages=True)
#         chain = ConversationChain(
#             llm=llm,
#             memory=memory,
#             verbose=True
#         )
        
#         # Store the system prompt in a way the chain can use it
#         chain.prompt.template = system_prompt + "\n\nHuman: {input}\nAI: "
        
#         return chain
    
#     # If we have nothing, still create a generic chain
#     else:
#         from langchain_community.chat_models import ChatOpenAI
#         from langchain.chains import ConversationChain
#         from langchain.memory import ConversationBufferMemory
#         from app.config import settings
#         from app.chatbot.
    
#     def process_message(
#         self, api_key: str, user_message: str, user_identifier: str
#     ) -> Dict[str, Any]:
#         """Process an incoming message and return a response"""
#         # Get tenant from API key
#         tenant = self._get_tenant_by_api_key(api_key)
#         if not tenant:
#             return {
#                 "error": "Invalid API key",
#                 "success": False
#             }
        
#         # Get or create session
#         session_id, is_new_session = self._get_or_create_session(tenant.id, user_identifier)
        
#         # Store user message
#         session = self.db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
#         user_msg = ChatMessage(
#             session_id=session.id,
#             content=user_message,
#             is_from_user=True
#         )
#         self.db.add(user_msg)
#         self.db.commit()
        
#         # Initialize or get chatbot chain
#         if session_id not in self.active_sessions:
#             chain = self._initialize_chatbot_chain(tenant.id)
#             if not chain:
#                 return {
#                     "error": "Failed to initialize chatbot",
#                     "success": False
#                 }
#             self.active_sessions[session_id] = chain
#         else:
#             chain = self.active_sessions[session_id]
        
#         # Generate response
#         try:
#             response = chain({"question": user_message})
#             bot_response = response.get("answer", "I'm sorry, I couldn't generate a response.")
            
#             # Store bot response
#             bot_msg = ChatMessage(
#                 session_id=session.id,
#                 content=bot_response,
#                 is_from_user=False
#             )
#             self.db.add(bot_msg)
#             self.db.commit()
            
#             return {
#                 "session_id": session_id,
#                 "response": bot_response,
#                 "success": True,
#                 "is_new_session": is_new_session
#             }
#         except Exception as e:
#             return {
#                 "error": f"Error generating response: {str(e)}",
#                 "success": False
#             }
    
#     def end_session(self, session_id: str) -> bool:
#         """End a chat session"""
#         session = self.db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
#         if not session:
#             return False
        
#         # Mark session as inactive
#         session.is_active = False
#         self.db.commit()
        
#         # Remove from active sessions
#         if session_id in self.active_sessions:
#             del self.active_sessions[session_id]
        
#         return True
    

# def process_message(
#     self, api_key: str, user_message: str, user_identifier: str
# ) -> Dict[str, Any]:
#     """Process an incoming message and return a response"""
#     # Get tenant from API key
#     tenant = self._get_tenant_by_api_key(api_key)
#     if not tenant:
#         return {
#             "error": "Invalid API key",
#             "success": False
#         }
    
#     # Get or create session
#     session_id, is_new_session = self._get_or_create_session(tenant.id, user_identifier)
    
#     # Store user message
#     session = self.db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
#     user_msg = ChatMessage(
#         session_id=session.id,
#         content=user_message,
#         is_from_user=True
#     )
#     self.db.add(user_msg)
#     self.db.commit()
    
#     # Initialize or get chatbot chain
#     if session_id not in self.active_sessions:
#         chain = self._initialize_chatbot_chain(tenant.id)
#         if not chain:
#             # Even if we don't have a knowledge base, create a simple LLM chain
#             from langchain_community.chat_models import ChatOpenAI
#             from langchain.chains import ConversationChain
#             from langchain.memory import ConversationBufferMemory
#             from app.config import settings
#             from app.chatbot.prompts import SYSTEM_PROMPT_TEMPLATE
            
#             # Get FAQs
#             faqs = self._get_faqs(tenant.id)
#             faq_info = "\n".join([f"Q: {faq['question']}\nA: {faq['answer']}" for faq in faqs]) if faqs else "No FAQs available yet."
            
#             # Format system prompt
#             system_prompt = SYSTEM_PROMPT_TEMPLATE.substitute(
#                 company_name=tenant.name,
#                 knowledge_base_info="No knowledge base available yet.",
#                 faq_info=faq_info
#             )
            
#             # Create a direct LLM chain
#             llm = ChatOpenAI(
#                 model_name="gpt-4",
#                 temperature=0.7,
#                 openai_api_key=settings.OPENAI_API_KEY
#             )
            
#             memory = ConversationBufferMemory(return_messages=True)
#             chain = ConversationChain(
#                 llm=llm,
#                 memory=memory,
#                 verbose=True
#             )
            
#             # Store the system prompt in a way the chain can use it
#             chain.prompt.template = system_prompt + "\n\nHuman: {input}\nAI: "
            
#             self.active_sessions[session_id] = chain
#         else:
#             self.active_sessions[session_id] = chain
#     else:
#         chain = self.active_sessions[session_id]
    
#     # Generate response
#     try:
#         # If it's a ConversationChain, use different input format
#         if hasattr(chain, 'prompt') and not hasattr(chain, 'retriever'):
#             response = chain.run(user_message)
#             bot_response = response
#         else:  # If it's a ConversationalRetrievalChain
#             response = chain({"question": user_message})
#             bot_response = response.get("answer", "I'm sorry, I couldn't generate a response.")
        
#         # Store bot response
#         bot_msg = ChatMessage(
#             session_id=session.id,
#             content=bot_response,
#             is_from_user=False
#         )
#         self.db.add(bot_msg)
#         self.db.commit()
        
#         return {
#             "session_id": session_id,
#             "response": bot_response,
#             "success": True,
#             "is_new_session": is_new_session
#         }
#     except Exception as e:
#         return {
#             "error": f"Error generating response: {str(e)}",
#             "success": False
#         }


import uuid
from openai import OpenAI
from app.utils.env import get_openai_api_key
from typing import Dict, List, Any, Optional, Tuple
from sqlalchemy.orm import Session
from app.knowledge_base.processor import DocumentProcessor
from app.chatbot.chains import create_chatbot_chain
from app.tenants.models import Tenant
from app.knowledge_base.models import KnowledgeBase, FAQ
from app.chatbot.models import ChatSession, ChatMessage
import logging

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
        return self.db.query(Tenant).filter(Tenant.api_key == api_key, Tenant.is_active == True).first()
    
    def _get_knowledge_bases(self, tenant_id: int) -> List[KnowledgeBase]:
        """Get all knowledge bases for a tenant"""
        return self.db.query(KnowledgeBase).filter(KnowledgeBase.tenant_id == tenant_id).all()
    
    def _get_faqs(self, tenant_id: int) -> List[Dict[str, str]]:
        """Get all FAQs for a tenant"""
        faqs = self.db.query(FAQ).filter(FAQ.tenant_id == tenant_id).all()
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
        
        return session.session_id, created
    
    def _initialize_chatbot_chain(self, tenant_id: int) -> Optional[Any]:
        """Initialize the chatbot chain for a tenant"""
        tenant = self._get_tenant(tenant_id)
        if not tenant:
            return None
        
        # Get knowledge bases
        knowledge_bases = self._get_knowledge_bases(tenant_id)
        
        # Get FAQs
        faqs = self._get_faqs(tenant_id)
        
        # If we have knowledge bases, use retrieval chain
        if knowledge_bases:
            # Use the first knowledge base for now (can be extended to combine multiple)
            kb = knowledge_bases[0]
            
            # Initialize document processor and get vector store
            processor = DocumentProcessor(tenant_id)
            try:
                vector_store = processor.get_vector_store(kb.vector_store_id)
                
                # Create chatbot chain
                chain = create_chatbot_chain(vector_store, tenant.name, faqs)
                return chain
            except Exception as e:
                print(f"Error initializing vector store: {str(e)}")
                return None
        
        # If we don't have knowledge bases but have FAQs, create a simple chain
        elif faqs:
            from langchain_community.chat_models import ChatOpenAI
            from langchain.chains import ConversationChain
            from langchain.memory import ConversationBufferMemory
            from app.config import settings
            from app.chatbot.prompts import SYSTEM_PROMPT_TEMPLATE
            
            # Format system prompt
            system_prompt = SYSTEM_PROMPT_TEMPLATE.substitute(
                company_name=tenant.name,
                knowledge_base_info="No knowledge base available yet.",
                faq_info="\n".join([f"Q: {faq['question']}\nA: {faq['answer']}" for faq in faqs])
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
        
        # If we have nothing, still create a generic chain
        else:
            from langchain_community.chat_models import ChatOpenAI
            from langchain.chains import ConversationChain
            from langchain.memory import ConversationBufferMemory
            from app.config import settings
            from app.chatbot.prompts import SYSTEM_PROMPT_TEMPLATE
            
            # Format system prompt
            system_prompt = SYSTEM_PROMPT_TEMPLATE.substitute(
                company_name=tenant.name,
                knowledge_base_info="No knowledge base available yet.",
                faq_info="No FAQs available yet."
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
    
    def process_message(
        self, api_key: str, user_message: str, user_identifier: str
    ) -> Dict[str, Any]:
        """Process an incoming message and return a response"""
        # Get tenant from API key
        tenant = self._get_tenant_by_api_key(api_key)
        if not tenant:
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
        
        # Initialize or get chatbot chain
        if session_id not in self.active_sessions:
            chain = self._initialize_chatbot_chain(tenant.id)
            if not chain:
                # Even if we don't have a knowledge base, create a simple LLM chain
                from langchain_community.chat_models import ChatOpenAI
                from langchain.chains import ConversationChain
                from langchain.memory import ConversationBufferMemory
                from app.config import settings
                from app.chatbot.prompts import SYSTEM_PROMPT_TEMPLATE
                
                # Get FAQs
                faqs = self._get_faqs(tenant.id)
                faq_info = "\n".join([f"Q: {faq['question']}\nA: {faq['answer']}" for faq in faqs]) if faqs else "No FAQs available yet."
                
                # Format system prompt
                system_prompt = SYSTEM_PROMPT_TEMPLATE.substitute(
                    company_name=tenant.name,
                    knowledge_base_info="No knowledge base available yet.",
                    faq_info=faq_info
                )

                
                
                # Create a direct LLM chain
                llm = ChatOpenAI(
                    model_name="ggpt-3.5-turbo",
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
                
                self.active_sessions[session_id] = chain
            else:
                self.active_sessions[session_id] = chain
        else:
            chain = self.active_sessions[session_id]
        
        # Generate response
        try:
            # If it's a ConversationChain, use different input format
            if hasattr(chain, 'prompt') and not hasattr(chain, 'retriever'):
                response = chain.run(user_message)
                bot_response = response
            else:  # If it's a ConversationalRetrievalChain
                response = chain({"question": user_message})
                bot_response = response.get("answer", "I'm sorry, I couldn't generate a response.")
            
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
            return {
                "error": f"Error generating response: {str(e)}",
                "success": False
            }
    
    def end_session(self, session_id: str) -> bool:
        """End a chat session"""
        session = self.db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
        if not session:
            return False
        
        # Mark session as inactive
        session.is_active = False
        self.db.commit()
        
        # Remove from active sessions
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
        
        return True