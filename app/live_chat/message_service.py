from datetime import datetime
from sqlalchemy.orm import Session
from app.live_chat.models import Conversation, Message, MessageType
from app.live_chat.state_manager import ChatStateManager
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)

class MessageService:
    """Handle message sending and persistence"""
    
    def __init__(self, db: Session, state_manager: ChatStateManager):
        self.db = db
        self.state = state_manager
    
    def send_message(self, session_id: str, content: str, from_agent: bool = False,
                    agent_id: int = None, sender_name: str = None) -> Dict:
        """Send a message in conversation"""
        
        # Get conversation
        conversation = self.db.query(Conversation).filter(
            Conversation.session_id == session_id
        ).first()
        
        if not conversation:
            raise ValueError(f"Conversation {session_id} not found")
        
        # Create message
        message = Message(
            conversation_id=conversation.id,
            content=content,
            from_agent=from_agent,
            agent_id=agent_id,
            sender_name=sender_name or ("Agent" if from_agent else "Customer")
        )
        
        self.db.add(message)
        
        # Update first response time if this is agent's first message
        if from_agent and not conversation.first_response_time_seconds and conversation.assigned_at:
            response_time = (datetime.utcnow() - conversation.assigned_at).total_seconds()
            conversation.first_response_time_seconds = int(response_time)
        
        self.db.commit()
        self.db.refresh(message)
        
        # Update conversation state activity
        self.state.update_conversation_state(session_id, {
            "last_message_at": datetime.utcnow().isoformat(),
            "last_message_from_agent": from_agent
        })
        
        return {
            "message_id": message.id,
            "content": message.content,
            "from_agent": message.from_agent,
            "sender_name": message.sender_name,
            "timestamp": message.created_at.isoformat()
        }
    
    def get_conversation_messages(self, session_id: str, limit: int = 50) -> List[Dict]:
        """Get messages for a conversation"""
        conversation = self.db.query(Conversation).filter(
            Conversation.session_id == session_id
        ).first()
        
        if not conversation:
            return []
        
        messages = self.db.query(Message).filter(
            Message.conversation_id == conversation.id
        ).order_by(Message.created_at.desc()).limit(limit).all()
        
        return [
            {
                "message_id": msg.id,
                "content": msg.content,
                "from_agent": msg.from_agent,
                "sender_name": msg.sender_name,
                "timestamp": msg.created_at.isoformat()
            }
            for msg in reversed(messages)
        ]