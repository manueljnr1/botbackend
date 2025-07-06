
"""
Simplified Memory System for Single-Platform Chatbot
Focuses on basic conversation memory within the same platform/session
"""

from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_
import logging
import uuid
from app.chatbot.models import ChatSession, ChatMessage

logger = logging.getLogger(__name__)

class SimpleChatbotMemory:
    """Simplified memory management for single-platform conversations"""
    
    def __init__(self, db: Session, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id
    
    def get_or_create_session(self, user_identifier: str, platform: str = "web") -> Tuple[str, bool]:
        """
        Get existing session or create new one - simplified version
        Returns: (session_id, is_new_session)
        """
        # Look for existing active session for this exact user identifier
        existing_session = self.db.query(ChatSession).filter(
            ChatSession.tenant_id == self.tenant_id,
            ChatSession.user_identifier == user_identifier,
            ChatSession.is_active == True
        ).first()
        
        if existing_session:
            logger.info(f"Found existing session {existing_session.session_id} for {user_identifier}")
            return existing_session.session_id, False
        
        # Create new session
        session_id = str(uuid.uuid4())
        new_session = ChatSession(
            session_id=session_id,
            tenant_id=self.tenant_id,
            user_identifier=user_identifier,
            platform=platform,
            is_active=True
        )
        
        self.db.add(new_session)
        self.db.commit()
        self.db.refresh(new_session)
        
        logger.info(f"Created new session {session_id} for {user_identifier}")
        return session_id, True
    
    def get_conversation_history(self, user_identifier: str, max_messages: int = 30) -> List[Dict]:
        """
        Get recent conversation history for the user - simplified
        Returns messages in chronological order (oldest first)
        """
        # Get the user's active session
        session = self.db.query(ChatSession).filter(
            ChatSession.tenant_id == self.tenant_id,
            ChatSession.user_identifier == user_identifier,
            ChatSession.is_active == True
        ).first()
        
        if not session:
            logger.info(f"No active session found for {user_identifier}")
            return []
        
        # Get recent messages from this session
        messages = self.db.query(ChatMessage).filter(
            ChatMessage.session_id == session.id
        ).order_by(ChatMessage.created_at.desc()).limit(max_messages).all()
        
        if not messages:
            return []
        
        # Convert to format expected by chatbot (chronological order)
        conversation = []
        for msg in reversed(messages):  # Reverse to get chronological order
            role = "user" if msg.is_from_user else "assistant"
            conversation.append({
                "role": role,
                "content": msg.content,
                "timestamp": msg.created_at.isoformat()
            })
        
        logger.info(f"Retrieved {len(conversation)} messages for {user_identifier}")
        return conversation
    
    def store_message(self, session_id: str, content: str, is_from_user: bool) -> bool:
        """
        Store a message in the conversation - simplified
        """
        try:
            # Get session by session_id
            session = self.db.query(ChatSession).filter(
                ChatSession.session_id == session_id
            ).first()
            
            if not session:
                logger.error(f"Session {session_id} not found")
                return False
            
            # Create and store message
            message = ChatMessage(
                session_id=session.id,
                content=content,
                is_from_user=is_from_user
            )
            
            self.db.add(message)
            self.db.commit()
            
            logger.info(f"Stored {'user' if is_from_user else 'bot'} message for session {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error storing message: {e}")
            self.db.rollback()
            return False
    
    def build_context_prompt(self, user_message: str, conversation_history: List[Dict], system_prompt: str = None) -> str:
        """
        Build a prompt with conversation context - simplified
        """
        prompt_parts = []
        
        # Add system prompt if provided
        if system_prompt:
            prompt_parts.append(system_prompt)
        
        # Add conversation history if available
        if conversation_history:
            prompt_parts.append("\nRecent conversation history:")
            
            # Only include recent messages to avoid token limits
            recent_messages = conversation_history[-10:]  # Last 10 messages
            
            for msg in recent_messages:
                role_label = "User" if msg["role"] == "user" else "Assistant"
                prompt_parts.append(f"{role_label}: {msg['content']}")
            
            prompt_parts.append("---")
        
        # Add current message
        prompt_parts.append(f"User: {user_message}")
        
        return "\n".join(prompt_parts)
    
    def cleanup_old_sessions(self, days_old: int = 30) -> int:
        """
        Clean up old inactive sessions - simplified and less aggressive
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        
        # Find sessions older than cutoff with no recent messages
        old_sessions = self.db.query(ChatSession).filter(
            and_(
                ChatSession.tenant_id == self.tenant_id,
                ChatSession.created_at < cutoff_date,
                ChatSession.is_active == True
            )
        ).all()
        
        deactivated_count = 0
        for session in old_sessions:
            # Check if session has any recent messages
            recent_message = self.db.query(ChatMessage).filter(
                and_(
                    ChatMessage.session_id == session.id,
                    ChatMessage.created_at > cutoff_date
                )
            ).first()
            
            # Only deactivate if no recent messages
            if not recent_message:
                session.is_active = False
                deactivated_count += 1
        
        self.db.commit()
        logger.info(f"Deactivated {deactivated_count} old sessions")
        return deactivated_count
    
    def get_session_stats(self, user_identifier: str) -> Dict:
        """
        Get basic stats for a user's session - for debugging
        """
        session = self.db.query(ChatSession).filter(
            ChatSession.tenant_id == self.tenant_id,
            ChatSession.user_identifier == user_identifier,
            ChatSession.is_active == True
        ).first()
        
        if not session:
            return {"session_exists": False}
        
        message_count = self.db.query(ChatMessage).filter(
            ChatMessage.session_id == session.id
        ).count()
        
        user_message_count = self.db.query(ChatMessage).filter(
            and_(
                ChatMessage.session_id == session.id,
                ChatMessage.is_from_user == True
            )
        ).count()
        
        return {
            "session_exists": True,
            "session_id": session.session_id,
            "total_messages": message_count,
            "user_messages": user_message_count,
            "bot_messages": message_count - user_message_count,
            "created_at": session.created_at.isoformat(),
            "platform": session.platform
        }
    

    def get_recent_messages(self, session_id: str, limit: int = 6) -> List[Dict[str, Any]]:
        """
        Get recent messages from conversation history for context analysis
        
        Args:
            session_id: The session ID string to get messages for
            limit: Maximum number of messages to return (default 6 for 3 exchanges)
        
        Returns:
            List of message dictionaries with keys: content, is_user, role, timestamp
        """
        try:
            # Get session by session_id (string)
            session = self.db.query(ChatSession).filter(
                ChatSession.session_id == session_id
            ).first()
            
            if not session:
                logger.warning(f"Session {session_id} not found for recent messages")
                return []
            
            # Get recent messages from this session
            messages = self.db.query(ChatMessage).filter(
                ChatMessage.session_id == session.id  # Use session.id (primary key)
            ).order_by(ChatMessage.created_at.desc()).limit(limit).all()
            
            if not messages:
                return []
            
            # Convert to format expected by context analyzer
            message_list = []
            for msg in reversed(messages):  # Reverse to get chronological order
                message_list.append({
                    "content": msg.content,
                    "is_user": msg.is_from_user,
                    "role": "user" if msg.is_from_user else "bot",
                    "timestamp": msg.created_at
                })
            
            logger.info(f"Retrieved {len(message_list)} recent messages for context analysis")
            return message_list
            
        except Exception as e:
            logger.error(f"Error getting recent messages for context analysis: {e}")
            return []