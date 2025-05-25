# app/chatbot/memory.py
"""
Enhanced Memory System for Multi-Platform Chatbot with Cross-Platform Persistence
"""

from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
import json
import logging
import hashlib
from app.chatbot.models import ChatSession, ChatMessage

logger = logging.getLogger(__name__)

class EnhancedChatbotMemory:
    """Enhanced memory management for multi-platform chatbot with cross-platform persistence"""
    
    def __init__(self, db: Session, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id
    
    def normalize_user_identifier(self, user_identifier: str) -> Tuple[str, str]:
        """
        Normalize user identifier and extract platform info
        Returns: (normalized_id, platform)
        """
        user_id = user_identifier.lower().strip()
        
        # Extract platform and normalize ID
        if user_id.startswith("discord:"):
            platform = "discord"
            normalized_id = user_id.replace("discord:", "")
        elif user_id.startswith("whatsapp:"):
            platform = "whatsapp" 
            normalized_id = user_id.replace("whatsapp:", "")
        elif user_id.startswith("web:"):
            platform = "web"
            normalized_id = user_id.replace("web:", "")
        elif "@" in user_id:
            platform = "email"
            normalized_id = user_id
        elif user_id.startswith("+") or user_id.isdigit():
            platform = "phone"
            normalized_id = user_id
        else:
            platform = "web"
            normalized_id = user_id
            
        return normalized_id, platform
    
    def create_unified_user_hash(self, user_identifier: str) -> str:
        """
        Create a unified hash for the same user across platforms
        This helps link the same person using different platforms
        """
        normalized_id, platform = self.normalize_user_identifier(user_identifier)
        
        # For phone numbers and emails, use the normalized ID directly
        if platform in ["phone", "email"]:
            return hashlib.sha256(f"{self.tenant_id}:{normalized_id}".encode()).hexdigest()[:16]
        
        # For other platforms, use the normalized ID
        return hashlib.sha256(f"{self.tenant_id}:{platform}:{normalized_id}".encode()).hexdigest()[:16]
    
    def get_or_create_session_with_memory(self, user_identifier: str, platform_specific_data: Dict = None) -> Tuple[str, bool, Dict]:
        """
        Get or create session with cross-platform memory consideration
        Returns: (session_id, is_new_session, memory_context)
        """
        normalized_id, platform = self.normalize_user_identifier(user_identifier)
        
        # Check for existing active session for this exact identifier
        existing_session = self.db.query(ChatSession).filter(
            ChatSession.tenant_id == self.tenant_id,
            ChatSession.user_identifier == user_identifier,
            ChatSession.is_active == True
        ).first()
        
        if existing_session:
            logger.info(f"Found existing session {existing_session.session_id} for {user_identifier}")
            return existing_session.session_id, False, self.get_cross_platform_memory(user_identifier)
        
        # Create new session with platform-specific data
        import uuid
        session_id = str(uuid.uuid4())
        
        new_session = ChatSession(
            session_id=session_id,
            tenant_id=self.tenant_id,
            user_identifier=user_identifier,
            platform=platform
        )
        
        # Add platform-specific fields
        if platform_specific_data:
            if platform == "discord":
                new_session.discord_channel_id = platform_specific_data.get("channel_id")
                new_session.discord_user_id = platform_specific_data.get("user_id")
                new_session.discord_guild_id = platform_specific_data.get("guild_id")
        
        self.db.add(new_session)
        self.db.commit()
        self.db.refresh(new_session)
        
        logger.info(f"Created new session {session_id} for {user_identifier} on {platform}")
        
        # Get cross-platform memory for context
        memory_context = self.get_cross_platform_memory(user_identifier)
        
        return session_id, True, memory_context
    
    def get_cross_platform_memory(self, user_identifier: str, max_messages: int = 20) -> Dict:
        """
        Get conversation memory across all platforms for the same user
        """
        normalized_id, current_platform = self.normalize_user_identifier(user_identifier)
        
        # Find all possible identifiers for this user across platforms
        possible_identifiers = [
            user_identifier,  # Current identifier
            normalized_id,    # Normalized version
            f"discord:{normalized_id}",
            f"whatsapp:{normalized_id}",
            f"web:{normalized_id}",
        ]
        
        # For phone numbers, also check without country code variations
        if normalized_id.startswith("+"):
            possible_identifiers.append(normalized_id[1:])  # Remove +
            possible_identifiers.append(normalized_id[4:])  # Remove country code
        
        # Get all sessions for this user across platforms
        sessions = self.db.query(ChatSession).filter(
            ChatSession.tenant_id == self.tenant_id,
            ChatSession.user_identifier.in_(possible_identifiers)
        ).order_by(ChatSession.created_at.desc()).limit(5).all()
        
        # Collect messages from all sessions
        all_messages = []
        platforms_used = set()
        
        for session in sessions:
            platforms_used.add(session.platform or "web")
            
            messages = self.db.query(ChatMessage).filter(
                ChatMessage.session_id == session.id
            ).order_by(ChatMessage.created_at.desc()).limit(10).all()
            
            for msg in messages:
                all_messages.append({
                    "content": msg.content,
                    "is_from_user": msg.is_from_user,
                    "timestamp": msg.created_at.isoformat(),
                    "platform": session.platform or "web",
                    "session_id": session.session_id
                })
        
        # Sort by timestamp and take most recent
        all_messages.sort(key=lambda x: x["timestamp"], reverse=True)
        recent_messages = all_messages[:max_messages]
        
        # Reverse for chronological order
        recent_messages.reverse()
        
        return {
            "messages": recent_messages,
            "platforms_used": list(platforms_used),
            "total_sessions": len(sessions),
            "user_summary": self._generate_user_summary(recent_messages)
        }
    
    def get_conversation_context(self, user_identifier: str, max_messages: int = 10) -> List[Dict]:
        """
        Get recent conversation history for context with cross-platform awareness
        """
        # First try to get from current session
        session = self.db.query(ChatSession).filter(
            ChatSession.tenant_id == self.tenant_id,
            ChatSession.user_identifier == user_identifier,
            ChatSession.is_active == True
        ).order_by(ChatSession.created_at.desc()).first()
        
        if session:
            messages = self.db.query(ChatMessage).filter(
                ChatMessage.session_id == session.id
            ).order_by(ChatMessage.created_at.desc()).limit(max_messages).all()
            
            if messages:
                # Format for LLM context (reverse to chronological order)
                context = []
                for msg in reversed(messages):
                    role = "user" if msg.is_from_user else "assistant"
                    context.append({
                        "role": role,
                        "content": msg.content,
                        "timestamp": msg.created_at.isoformat()
                    })
                return context
        
        # If no current session or no messages, get cross-platform context
        cross_platform_memory = self.get_cross_platform_memory(user_identifier, max_messages)
        
        context = []
        for msg in cross_platform_memory["messages"]:
            role = "user" if msg["is_from_user"] else "assistant"
            context.append({
                "role": role,
                "content": msg["content"],
                "timestamp": msg["timestamp"],
                "platform": msg["platform"]
            })
        
        return context
    
    def store_message_with_context(self, session_id: str, content: str, is_from_user: bool, 
                                 platform_metadata: Dict = None) -> bool:
        """
        Store message with additional platform-specific metadata
        """
        try:
            session = self.db.query(ChatSession).filter(
                ChatSession.session_id == session_id
            ).first()
            
            if not session:
                logger.error(f"Session {session_id} not found")
                return False
            
            message = ChatMessage(
                session_id=session.id,
                content=content,
                is_from_user=is_from_user
            )
            
            # Add platform-specific metadata if provided
            if platform_metadata:
                # You can extend ChatMessage model to include metadata JSON field
                # message.metadata = json.dumps(platform_metadata)
                pass
            
            self.db.add(message)
            self.db.commit()
            
            logger.info(f"Stored message for session {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error storing message: {e}")
            self.db.rollback()
            return False
    
    def get_user_preferences(self, user_identifier: str) -> Dict:
        """
        Extract user preferences from cross-platform conversation history
        """
        cross_platform_memory = self.get_cross_platform_memory(user_identifier, max_messages=50)
        messages = cross_platform_memory["messages"]
        
        preferences = {
            "communication_style": "formal",
            "topics_of_interest": [],
            "preferred_language": "english",
            "platforms_used": cross_platform_memory["platforms_used"],
            "interaction_patterns": {
                "avg_message_length": 0,
                "question_frequency": 0,
                "last_interaction": None,
                "most_active_platform": None,
                "total_conversations": cross_platform_memory["total_sessions"]
            }
        }
        
        if messages:
            user_messages = [msg for msg in messages if msg["is_from_user"]]
            
            if user_messages:
                # Calculate average message length
                total_length = sum(len(msg["content"]) for msg in user_messages)
                preferences["interaction_patterns"]["avg_message_length"] = total_length / len(user_messages)
                
                # Count questions
                question_count = sum(1 for msg in user_messages if "?" in msg["content"])
                preferences["interaction_patterns"]["question_frequency"] = question_count / len(user_messages)
                
                # Last interaction
                preferences["interaction_patterns"]["last_interaction"] = user_messages[-1]["timestamp"]
                
                # Most active platform
                platform_counts = {}
                for msg in user_messages:
                    platform = msg.get("platform", "web")
                    platform_counts[platform] = platform_counts.get(platform, 0) + 1
                
                if platform_counts:
                    preferences["interaction_patterns"]["most_active_platform"] = max(platform_counts, key=platform_counts.get)
        
        return preferences
    
    def _generate_user_summary(self, messages: List[Dict]) -> Dict:
        """
        Generate a summary of user's conversation patterns and preferences
        """
        if not messages:
            return {"summary": "New user with no conversation history"}
        
        user_messages = [msg for msg in messages if msg["is_from_user"]]
        bot_messages = [msg for msg in messages if not msg["is_from_user"]]
        
        # Analyze conversation patterns
        total_messages = len(messages)
        user_msg_count = len(user_messages)
        
        # Extract topics (simple keyword analysis)
        all_text = " ".join([msg["content"].lower() for msg in user_messages])
        topics = self._extract_topics(all_text)
        
        # Determine communication style
        formal_indicators = ["please", "thank you", "could you", "would you"]
        casual_indicators = ["hey", "hi", "what's up", "thanks", "thx"]
        
        formal_count = sum(1 for indicator in formal_indicators if indicator in all_text)
        casual_count = sum(1 for indicator in casual_indicators if indicator in all_text)
        
        communication_style = "formal" if formal_count > casual_count else "casual"
        
        return {
            "total_messages": total_messages,
            "user_messages": user_msg_count,
            "bot_messages": len(bot_messages),
            "topics_discussed": topics,
            "communication_style": communication_style,
            "avg_message_length": sum(len(msg["content"]) for msg in user_messages) / len(user_messages) if user_messages else 0,
            "conversation_span_days": self._calculate_conversation_span(messages)
        }
    
    def _calculate_conversation_span(self, messages: List[Dict]) -> int:
        """Calculate how many days the conversation has spanned"""
        if len(messages) < 2:
            return 0
        
        try:
            first_msg_time = datetime.fromisoformat(messages[0]["timestamp"].replace('Z', '+00:00'))
            last_msg_time = datetime.fromisoformat(messages[-1]["timestamp"].replace('Z', '+00:00'))
            
            span = last_msg_time - first_msg_time
            return span.days
        except:
            return 0
    
    def _extract_topics(self, text: str) -> List[str]:
        """Simple topic extraction with enhanced categories"""
        topics = []
        keywords = {
            "pricing": ["price", "cost", "plan", "payment", "billing", "subscription", "fee"],
            "support": ["help", "problem", "issue", "error", "bug", "trouble", "fix"],
            "features": ["feature", "functionality", "how to", "guide", "tutorial", "capability"],
            "integration": ["integrate", "connect", "setup", "configure", "api", "webhook"],
            "technical": ["technical", "code", "developer", "programming", "database"],
            "business": ["business", "enterprise", "company", "organization", "team"],
            "account": ["account", "login", "password", "profile", "settings", "user"]
        }
        
        text_lower = text.lower()
        for topic, words in keywords.items():
            if any(word in text_lower for word in words):
                topics.append(topic)
        
        return topics
    
    def merge_user_sessions(self, primary_identifier: str, secondary_identifier: str) -> bool:
        """
        Merge sessions from secondary identifier into primary identifier
        Useful when you discover the same user is using multiple identifiers
        """
        try:
            # Get secondary sessions
            secondary_sessions = self.db.query(ChatSession).filter(
                ChatSession.tenant_id == self.tenant_id,
                ChatSession.user_identifier == secondary_identifier
            ).all()
            
            # Update user identifier for all secondary sessions
            for session in secondary_sessions:
                session.user_identifier = primary_identifier
                logger.info(f"Merged session {session.session_id} from {secondary_identifier} to {primary_identifier}")
            
            self.db.commit()
            logger.info(f"Successfully merged {len(secondary_sessions)} sessions")
            return True
            
        except Exception as e:
            logger.error(f"Error merging user sessions: {e}")
            self.db.rollback()
            return False
    
    def cleanup_old_sessions(self, days_old: int = 30) -> int:
        """
        Clean up old inactive sessions to manage memory with improved logic
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        
        # Only deactivate sessions that haven't had messages recently
        old_sessions = self.db.query(ChatSession).filter(
            and_(
                ChatSession.tenant_id == self.tenant_id,
                ChatSession.created_at < cutoff_date,
                ChatSession.is_active == True
            )
        ).all()
        
        deactivated_count = 0
        for session in old_sessions:
            # Check if session has recent messages
            recent_message = self.db.query(ChatMessage).filter(
                and_(
                    ChatMessage.session_id == session.id,
                    ChatMessage.created_at > cutoff_date
                )
            ).first()
            
            if not recent_message:
                session.is_active = False
                deactivated_count += 1
        
        self.db.commit()
        logger.info(f"Deactivated {deactivated_count} old sessions")
        return deactivated_count