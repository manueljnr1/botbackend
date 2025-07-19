"""
Enhanced Memory System with Session Lifecycle Management
Implements: Active → Idle → Dormant → Expired session states
Adds: 3-hour context windows, automatic cleanup, performance optimization
"""

from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import and_
import logging
import uuid
from app.chatbot.models import ChatSession, ChatMessage



logger = logging.getLogger(__name__)




def safe_datetime_subtract(dt1, dt2):
    """Safely subtract two datetime objects, handling timezone issues"""
    try:
        if dt1 is None or dt2 is None:
            return timedelta(0)
        
        # Convert both to naive UTC datetimes for safe subtraction
        if dt1.tzinfo is not None:
            dt1_naive = dt1.astimezone(timezone.utc).replace(tzinfo=None)
        else:
            dt1_naive = dt1
            
        if dt2.tzinfo is not None:
            dt2_naive = dt2.astimezone(timezone.utc).replace(tzinfo=None)
        else:
            dt2_naive = dt2
            
        return dt1_naive - dt2_naive
        
    except Exception as e:
        logger.warning(f"Datetime subtraction error: {str(e)}")
        return timedelta(0)



class SimpleChatbotMemory:
    """
    Enhanced memory management with session lifecycle:
    - Active: User actively chatting
    - Idle: No messages for 30 minutes (context preserved)
    - Dormant: No messages for 3 hours (context cleared, session preserved)
    - Expired: No messages for 7 days (session archived)
    """
    
    def __init__(self, db: Session, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id
        
       
        self.IDLE_THRESHOLD = timedelta(minutes=30)
        self.DORMANT_THRESHOLD = timedelta(hours=3)
        self.EXPIRED_THRESHOLD = timedelta(days=7)
        self.CONTEXT_WINDOW = timedelta(hours=3)
    
    def get_or_create_session(self, user_identifier: str, platform: str = "web") -> Tuple[str, bool]:
        """
        Enhanced session management with lifecycle awareness
        Returns: (session_id, is_new_session)
        """
        
        existing_session = self.db.query(ChatSession).filter(
            ChatSession.tenant_id == self.tenant_id,
            ChatSession.user_identifier == user_identifier,
            ChatSession.is_active == True
        ).first()
        
        if existing_session:
           
            session_state = self._get_session_state(existing_session)
            
            if session_state == "expired":
                
                logger.info(f"Archiving expired session {existing_session.session_id}")
                existing_session.is_active = False
                self.db.commit()
                return self._create_new_session(user_identifier, platform)
            
            elif session_state == "dormant":
               
                logger.info(f"Reactivating dormant session {existing_session.session_id}")
                
                return existing_session.session_id, False
            
            else:
                # Session is active or idle
                logger.info(f"Found {session_state} session {existing_session.session_id} for {user_identifier}")
                return existing_session.session_id, False
        
        # Create new session if none exists
        return self._create_new_session(user_identifier, platform)
    
    def _create_new_session(self, user_identifier: str, platform: str) -> Tuple[str, bool]:
        """Create a new session"""
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
    
    def _get_session_state(self, session: ChatSession) -> str:
        """
        Determine session lifecycle state based on last activity
        Returns: 'active', 'idle', 'dormant', or 'expired'
        """
        # Get last message timestamp
        last_message = self.db.query(ChatMessage).filter(
            ChatMessage.session_id == session.id
        ).order_by(ChatMessage.created_at.desc()).first()
        
        if not last_message:
            # No messages yet - consider active
            return "active"
        
        time_since_last = safe_datetime_subtract(datetime.utcnow(), last_message.created_at)
        
        if time_since_last >= self.EXPIRED_THRESHOLD:
            return "expired"
        elif time_since_last >= self.DORMANT_THRESHOLD:
            return "dormant"
        elif time_since_last >= self.IDLE_THRESHOLD:
            return "idle"
        else:
            return "active"
    
    def get_conversation_history(self, user_identifier: str, max_messages: int = 30) -> List[Dict]:
        """
        Enhanced conversation history with 3-hour context window
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
        
        # 🆕 ENHANCED: Apply 3-hour context window
        context_cutoff = datetime.utcnow() - self.CONTEXT_WINDOW
        
        # Get recent messages within context window
        messages = self.db.query(ChatMessage).filter(
            and_(
                ChatMessage.session_id == session.id,
                ChatMessage.created_at >= context_cutoff  # 🆕 3-hour window
            )
        ).order_by(ChatMessage.created_at.desc()).limit(max_messages).all()
        
        if not messages:
            logger.info(f"No messages within 3-hour context window for {user_identifier}")
            return []
        
        # Convert to format expected by chatbot (chronological order)
        conversation = []
        for msg in reversed(messages):  # Reverse to get chronological order
            role = "user" if msg.is_from_user else "assistant"
            conversation.append({
                "role": role,
                "content": msg.content,
                "timestamp": msg.created_at.isoformat(),
                "is_user": msg.is_from_user  # 🆕 Added for compatibility
            })
        
        logger.info(f"Retrieved {len(conversation)} messages within 3-hour window for {user_identifier}")
        return conversation
    
    def get_recent_messages(self, session_id: str, limit: int = 6) -> List[Dict[str, Any]]:
        """
        Enhanced: Get recent messages with 3-hour context window for context analysis
        
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
            
            # 🆕 ENHANCED: Apply 3-hour context window
            context_cutoff = datetime.utcnow() - self.CONTEXT_WINDOW
            
            # Get recent messages from this session within context window
            messages = self.db.query(ChatMessage).filter(
                and_(
                    ChatMessage.session_id == session.id,  # Use session.id (primary key)
                    ChatMessage.created_at >= context_cutoff  # 🆕 3-hour window
                )
            ).order_by(ChatMessage.created_at.desc()).limit(limit).all()
            
            if not messages:
                logger.info(f"No recent messages within 3-hour window for session {session_id}")
                return []
            
            # Convert to format expected by context analyzer
            message_list = []
            for msg in reversed(messages):  # Reverse to get chronological order
                message_list.append({
                    "content": msg.content,
                    "is_user": msg.is_from_user,
                    "role": "user" if msg.is_from_user else "bot",
                    "timestamp": msg.created_at  # Keep as datetime for easier processing
                })
            
            logger.info(f"Retrieved {len(message_list)} recent messages within 3-hour window for context analysis")
            return message_list
            
        except Exception as e:
            logger.error(f"Error getting recent messages for context analysis: {e}")
            return []
    
    def store_message(self, session_id: str, content: str, is_from_user: bool) -> bool:
        """
        Store a message in the conversation - enhanced with session state update
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
            
            # 🆕 ENHANCED: Update session activity (optional - could add last_activity field)
            # For now, the session state is determined by message timestamps
            
            self.db.commit()
            
            logger.info(f"Stored {'user' if is_from_user else 'bot'} message for session {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error storing message: {e}")
            self.db.rollback()
            return False
    
    def build_context_prompt(self, user_message: str, conversation_history: List[Dict], system_prompt: str = None) -> str:
        """
        Enhanced context prompt building with better token management
        """
        prompt_parts = []
        
        # Add system prompt if provided
        if system_prompt:
            prompt_parts.append(system_prompt)
        
        # Add conversation history if available
        if conversation_history:
            prompt_parts.append("\nRecent conversation history (3-hour window):")
            
            # 🆕 ENHANCED: Smart message limiting based on token estimate
            # Estimate ~50 tokens per message, limit to ~500 tokens for history
            max_history_messages = min(10, len(conversation_history))
            recent_messages = conversation_history[-max_history_messages:]
            
            for msg in recent_messages:
                role_label = "User" if msg["role"] == "user" else "Assistant"
                # Truncate very long messages to save tokens
                content = msg["content"]
                if len(content) > 200:
                    content = content[:200] + "..."
                prompt_parts.append(f"{role_label}: {content}")
            
            prompt_parts.append("---")
        
        # Add current message
        prompt_parts.append(f"User: {user_message}")
        
        return "\n".join(prompt_parts)
    
    def cleanup_old_sessions(self, days_old: int = 30) -> int:
        """
        Enhanced cleanup with session lifecycle awareness
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days_old)
            
            # Find sessions older than cutoff
            old_sessions = self.db.query(ChatSession).filter(
                and_(
                    ChatSession.tenant_id == self.tenant_id,
                    ChatSession.created_at < cutoff_date,
                    ChatSession.is_active == True
                )
            ).all()
            
            archived_count = 0
            for session in old_sessions:
                session_state = self._get_session_state(session)
                
                # Archive expired sessions
                if session_state == "expired":
                    session.is_active = False
                    archived_count += 1
                    logger.info(f"Archived expired session {session.session_id}")
            
            self.db.commit()
            logger.info(f"Enhanced cleanup: Archived {archived_count} expired sessions")
            return archived_count
            
        except Exception as e:
            logger.error(f"Enhanced cleanup error: {e}")
            self.db.rollback()
            return 0
    
    def cleanup_old_messages(self, days_old: int = 90) -> int:
        """
        🆕 NEW: Clean up very old message content for privacy and performance
        Keep message metadata but clear content for messages older than specified days
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days_old)
            
            # Find old messages to clean up
            old_messages = self.db.query(ChatMessage).join(ChatSession).filter(
                and_(
                    ChatSession.tenant_id == self.tenant_id,
                    ChatMessage.created_at < cutoff_date,
                    ChatMessage.content.isnot(None)  # Only messages that still have content
                )
            ).all()
            
            cleaned_count = 0
            for message in old_messages:
                # Clear content but keep metadata for analytics
                message.content = "[CONTENT_CLEANED_FOR_PRIVACY]"
                cleaned_count += 1
            
            self.db.commit()
            logger.info(f"Privacy cleanup: Cleaned content from {cleaned_count} old messages")
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Message cleanup error: {e}")
            self.db.rollback()
            return 0
    
    def get_session_stats(self, user_identifier: str) -> Dict:
        """
        Enhanced stats with session lifecycle information
        """
        session = self.db.query(ChatSession).filter(
            ChatSession.tenant_id == self.tenant_id,
            ChatSession.user_identifier == user_identifier,
            ChatSession.is_active == True
        ).first()
        
        if not session:
            return {"session_exists": False}
        
        # Get session state
        session_state = self._get_session_state(session)
        
        # Get message counts within context window
        context_cutoff = datetime.utcnow() - self.CONTEXT_WINDOW
        
        total_messages = self.db.query(ChatMessage).filter(
            ChatMessage.session_id == session.id
        ).count()
        
        recent_messages = self.db.query(ChatMessage).filter(
            and_(
                ChatMessage.session_id == session.id,
                ChatMessage.created_at >= context_cutoff
            )
        ).count()
        
        user_message_count = self.db.query(ChatMessage).filter(
            and_(
                ChatMessage.session_id == session.id,
                ChatMessage.is_from_user == True,
                ChatMessage.created_at >= context_cutoff
            )
        ).count()
        
        # Get last activity
        last_message = self.db.query(ChatMessage).filter(
            ChatMessage.session_id == session.id
        ).order_by(ChatMessage.created_at.desc()).first()
        
        last_activity = last_message.created_at.isoformat() if last_message else session.created_at.isoformat()
        
        return {
            "session_exists": True,
            "session_id": session.session_id,
            "session_state": session_state,
            "total_messages": total_messages,
            "recent_messages_3h": recent_messages,
            "user_messages_3h": user_message_count,
            "bot_messages_3h": recent_messages - user_message_count,
            "created_at": session.created_at.isoformat(),
            "last_activity": last_activity,
            "platform": session.platform,
            "context_window_hours": 3,
            "lifecycle_thresholds": {
                "idle_minutes": 30,
                "dormant_hours": 3,
                "expired_days": 7
            }
        }
    
    def force_session_state_transition(self, session_id: str, new_state: str) -> bool:
        """
        🆕 NEW: Manually transition session state (for admin/testing purposes)
        
        Args:
            session_id: Session to modify
            new_state: 'active', 'idle', 'dormant', or 'expired'
            
        Returns:
            True if successful, False otherwise
        """
        try:
            session = self.db.query(ChatSession).filter(
                ChatSession.session_id == session_id,
                ChatSession.tenant_id == self.tenant_id
            ).first()
            
            if not session:
                logger.error(f"Session {session_id} not found for state transition")
                return False
            
            if new_state == "expired":
                session.is_active = False
                logger.info(f"Manually expired session {session_id}")
            elif new_state in ["active", "idle", "dormant"]:
                session.is_active = True
                logger.info(f"Manually set session {session_id} to {new_state}")
            else:
                logger.error(f"Invalid session state: {new_state}")
                return False
            
            self.db.commit()
            return True
            
        except Exception as e:
            logger.error(f"Force session state transition error: {e}")
            self.db.rollback()
            return False
    
    def get_tenant_session_summary(self) -> Dict[str, Any]:
        """
        🆕 NEW: Get overview of all sessions for this tenant (for monitoring/analytics)
        """
        try:
            # Get all active sessions for tenant
            active_sessions = self.db.query(ChatSession).filter(
                and_(
                    ChatSession.tenant_id == self.tenant_id,
                    ChatSession.is_active == True
                )
            ).all()
            
            # Categorize by state
            state_counts = {
                "active": 0,
                "idle": 0,
                "dormant": 0,
                "total_active": len(active_sessions)
            }
            
            # Get inactive (expired) count
            inactive_sessions = self.db.query(ChatSession).filter(
                and_(
                    ChatSession.tenant_id == self.tenant_id,
                    ChatSession.is_active == False
                )
            ).count()
            
            # Analyze active session states
            for session in active_sessions:
                state = self._get_session_state(session)
                if state in state_counts:
                    state_counts[state] += 1
            
            # Get total message count for tenant (last 24 hours)
            yesterday = datetime.utcnow() - timedelta(days=1)
            recent_message_count = self.db.query(ChatMessage).join(ChatSession).filter(
                and_(
                    ChatSession.tenant_id == self.tenant_id,
                    ChatMessage.created_at >= yesterday
                )
            ).count()
            
            return {
                "tenant_id": self.tenant_id,
                "session_states": state_counts,
                "inactive_sessions": inactive_sessions,
                "recent_messages_24h": recent_message_count,
                "context_window_hours": 3,
                "lifecycle_enabled": True,
                "last_updated": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Tenant session summary error: {e}")
            return {
                "error": str(e),
                "tenant_id": self.tenant_id,
                "last_updated": datetime.utcnow().isoformat()
            }
    
    def perform_maintenance(self) -> Dict[str, int]:
        """
        🆕 NEW: Comprehensive maintenance routine
        - Archive expired sessions
        - Clean old message content
        - Update session states
        
        Returns:
            Dictionary with counts of maintenance actions performed
        """
        try:
            logger.info(f"Starting maintenance for tenant {self.tenant_id}")
            
            # Archive expired sessions (7+ days inactive)
            archived = self.cleanup_old_sessions(days_old=7)
            
            # Clean old message content (90+ days old)
            cleaned = self.cleanup_old_messages(days_old=90)
            
          
            maintenance_result = {
                "archived_sessions": archived,
                "cleaned_messages": cleaned,
                "tenant_id": self.tenant_id,
                "maintenance_completed_at": datetime.utcnow().isoformat()
            }
            
            logger.info(f"Maintenance completed for tenant {self.tenant_id}: {maintenance_result}")
            return maintenance_result
            
        except Exception as e:
            logger.error(f"Maintenance error for tenant {self.tenant_id}: {e}")
            return {
                "error": str(e),
                "tenant_id": self.tenant_id,
                "maintenance_completed_at": datetime.utcnow().isoformat()
            }
        
    def store_troubleshooting_state(self, session_id: str, kb_id: int, current_step: str, flow_data: Dict):
        """Store current troubleshooting state in session"""
        try:
            session = self.db.query(ChatSession).filter(
                ChatSession.session_id == session_id
            ).first()
            
            if session:
                troubleshooting_state = {
                    "kb_id": kb_id,
                    "current_step": current_step,
                    "flow_data": flow_data,
                    "started_at": datetime.utcnow().isoformat(),
                    "active": True
                }
                
                # Use session_metadata instead of metadata
                if not hasattr(session, 'session_metadata') or session.session_metadata is None:
                    session.session_metadata = {}
                
                session.session_metadata["troubleshooting_state"] = troubleshooting_state
                
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(session, "session_metadata")
                
                self.db.commit()
                logger.info(f"✅ Stored troubleshooting state for session {session_id}: step {current_step}")
                return True
                
        except Exception as e:
            logger.error(f"❌ Error storing troubleshooting state: {e}")
            return False

    def get_troubleshooting_state(self, session_id: str) -> Optional[Dict]:
        """Get current troubleshooting state"""
        try:
            session = self.db.query(ChatSession).filter(
                ChatSession.session_id == session_id
            ).first()
            
            if session and hasattr(session, 'session_metadata') and session.session_metadata:
                state = session.session_metadata.get("troubleshooting_state")
                
                if state and state.get("active", False):
                    logger.info(f"📋 Found active troubleshooting state: step {state.get('current_step')}")
                    return state
                    
            return None
            
        except Exception as e:
            logger.error(f"❌ Error getting troubleshooting state: {e}")
            return None

    def update_troubleshooting_step(self, session_id: str, next_step: str):
        """Move to next step in troubleshooting flow"""
        try:
            session = self.db.query(ChatSession).filter(
                ChatSession.session_id == session_id
            ).first()
            
            if session and session.session_metadata and "troubleshooting_state" in session.session_metadata:
                session.session_metadata["troubleshooting_state"]["current_step"] = next_step
                session.session_metadata["troubleshooting_state"]["updated_at"] = datetime.utcnow().isoformat()
                
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(session, "session_metadata")
                
                self.db.commit()
                logger.info(f"🔄 Updated troubleshooting step to: {next_step}")
                return True
                
        except Exception as e:
            logger.error(f"❌ Error updating troubleshooting step: {e}")
            return False

    def clear_troubleshooting_state(self, session_id: str):
        """Clear troubleshooting state when flow completes"""
        try:
            session = self.db.query(ChatSession).filter(
                ChatSession.session_id == session_id
            ).first()
            
            if session and session.session_metadata and "troubleshooting_state" in session.session_metadata:
                session.session_metadata["troubleshooting_state"]["active"] = False
                session.session_metadata["troubleshooting_state"]["completed_at"] = datetime.utcnow().isoformat()
                
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(session, "session_metadata")
                self.db.commit()
                
                logger.info(f"✅ Cleared troubleshooting state for session {session_id}")
                
        except Exception as e:
            logger.error(f"❌ Error clearing troubleshooting state: {e}")



    

    
    def store_sales_conversation_state(self, session_id: str, kb_id: int, flow_type: str, current_step: str, flow_data: Dict):
        """Store current sales conversation state"""
        try:
            session = self.db.query(ChatSession).filter(
                ChatSession.session_id == session_id
            ).first()
            
            if session:
                sales_state = {
                    "kb_id": kb_id,
                    "flow_type": flow_type,  # "pricing_inquiry", "feature_inquiry", etc.
                    "current_step": current_step,
                    "flow_data": flow_data,
                    "started_at": datetime.utcnow().isoformat(),
                    "active": True,
                    "conversation_type": "sales"
                }
                
                if not hasattr(session, 'session_metadata') or session.session_metadata is None:
                    session.session_metadata = {}
                
                session.session_metadata["sales_conversation_state"] = sales_state
                
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(session, "session_metadata")
                
                self.db.commit()
                logger.info(f"💼 Stored sales conversation state: {flow_type} - step {current_step}")
                return True
                
        except Exception as e:
            logger.error(f"❌ Error storing sales conversation state: {e}")
            return False

    def get_sales_conversation_state(self, session_id: str) -> Optional[Dict]:
        """Get current sales conversation state"""
        try:
            session = self.db.query(ChatSession).filter(
                ChatSession.session_id == session_id
            ).first()
            
            if session and hasattr(session, 'session_metadata') and session.session_metadata:
                state = session.session_metadata.get("sales_conversation_state")
                
                if state and state.get("active", False):
                    logger.info(f"💼 Found active sales conversation: {state.get('flow_type')} - step {state.get('current_step')}")
                    return state
                    
            return None
            
        except Exception as e:
            logger.error(f"❌ Error getting sales conversation state: {e}")
            return None

    def update_sales_conversation_step(self, session_id: str, next_step: str):
        """Move to next step in sales conversation"""
        try:
            session = self.db.query(ChatSession).filter(
                ChatSession.session_id == session_id
            ).first()
            
            if session and session.session_metadata and "sales_conversation_state" in session.session_metadata:
                session.session_metadata["sales_conversation_state"]["current_step"] = next_step
                session.session_metadata["sales_conversation_state"]["updated_at"] = datetime.utcnow().isoformat()
                
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(session, "session_metadata")
                
                self.db.commit()
                logger.info(f"💼 Updated sales conversation step to: {next_step}")
                return True
                
        except Exception as e:
            logger.error(f"❌ Error updating sales conversation step: {e}")
            return False

    def clear_sales_conversation_state(self, session_id: str):
        """Clear sales conversation state when flow completes"""
        try:
            session = self.db.query(ChatSession).filter(
                ChatSession.session_id == session_id
            ).first()
            
            if session and session.session_metadata and "sales_conversation_state" in session.session_metadata:
                session.session_metadata["sales_conversation_state"]["active"] = False
                session.session_metadata["sales_conversation_state"]["completed_at"] = datetime.utcnow().isoformat()
                
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(session, "session_metadata")
                self.db.commit()
                
                logger.info(f"💼 Cleared sales conversation state")
                
        except Exception as e:
            logger.error(f"❌ Error clearing sales conversation state: {e}")