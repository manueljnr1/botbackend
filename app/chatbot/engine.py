import uuid
from typing import Dict, List, Any, Optional, Tuple
from sqlalchemy.orm import Session
from app.knowledge_base.processor import DocumentProcessor
from app.chatbot.chains import create_chatbot_chain
from app.tenants.models import Tenant
from app.knowledge_base.models import KnowledgeBase, FAQ
from app.chatbot.models import ChatSession, ChatMessage

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
        if not knowledge_bases:
            return None
        
        # Use the first knowledge base for now (can be extended to combine multiple)
        kb = knowledge_bases[0]
        
        # Get FAQs
        faqs = self._get_faqs(tenant_id)
        
        # Initialize document processor and get vector store
        processor = DocumentProcessor(tenant_id)
        vector_store = processor.get_vector_store(kb.vector_store_id)
        
        # Create chatbot chain
        chain = create_chatbot_chain(vector_store, tenant.name, faqs)
        
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
                return {
                    "error": "Failed to initialize chatbot",
                    "success": False
                }
            self.active_sessions[session_id] = chain
        else:
            chain = self.active_sessions[session_id]
        
        # Generate response
        try:
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
    

