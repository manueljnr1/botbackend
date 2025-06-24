# app/instagram/memory.py
"""
Instagram Memory Integration
Integrates Instagram conversations with the existing memory system
"""

import logging
import uuid
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.instagram.models import InstagramConversation, InstagramMessage, InstagramIntegration
from app.chatbot.models import ChatSession, ChatMessage
from app.chatbot.simple_memory import SimpleChatbotMemory

logger = logging.getLogger(__name__)

class InstagramMemoryManager:
    """Manage Instagram conversation memory and integration with core memory system"""
    
    def __init__(self, db: Session, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id
        self.core_memory = SimpleChatbotMemory(db, tenant_id)
    
    def get_or_create_chat_session(self, instagram_conversation: InstagramConversation) -> Tuple[str, bool]:
        """
        Get or create corresponding ChatSession for Instagram conversation
        
        Args:
            instagram_conversation: Instagram conversation object
            
        Returns:
            Tuple[str, bool]: (session_id, is_new_session)
        """
        try:
            user_identifier = instagram_conversation.get_user_identifier()
            
            # Use the core memory system to get/create session
            session_id, is_new = self.core_memory.get_or_create_session(user_identifier, "instagram")
            
            # Update Instagram conversation with session reference if new
            if is_new:
                logger.info(f"📱 Created new chat session {session_id} for Instagram conversation {instagram_conversation.conversation_id}")
            
            return session_id, is_new
            
        except Exception as e:
            logger.error(f"Error getting/creating chat session: {str(e)}")
            # Fallback to direct session creation
            return self._create_fallback_session(instagram_conversation)
    
    def _create_fallback_session(self, instagram_conversation: InstagramConversation) -> Tuple[str, bool]:
        """Fallback session creation if core memory fails"""
        try:
            session_id = str(uuid.uuid4())
            user_identifier = instagram_conversation.get_user_identifier()
            
            chat_session = ChatSession(
                session_id=session_id,
                tenant_id=self.tenant_id,
                user_identifier=user_identifier,
                platform="instagram",
                is_active=True
            )
            
            self.db.add(chat_session)
            self.db.commit()
            self.db.refresh(chat_session)
            
            logger.info(f"📱 Created fallback chat session {session_id}")
            return session_id, True
            
        except Exception as e:
            logger.error(f"Error creating fallback session: {str(e)}")
            return f"fallback_{uuid.uuid4()}", True
    
    def sync_instagram_message_to_core(self, instagram_message: InstagramMessage) -> bool:
        """
        Sync Instagram message to core memory system
        
        Args:
            instagram_message: Instagram message to sync
            
        Returns:
            bool: Success status
        """
        try:
            # Get Instagram conversation
            conversation = self.db.query(InstagramConversation).filter(
                InstagramConversation.id == instagram_message.conversation_id
            ).first()
            
            if not conversation:
                logger.error(f"No conversation found for message {instagram_message.id}")
                return False
            
            # Get or create corresponding chat session
            session_id, _ = self.get_or_create_chat_session(conversation)
            
            # Get the ChatSession object
            chat_session = self.db.query(ChatSession).filter(
                ChatSession.session_id == session_id
            ).first()
            
            if not chat_session:
                logger.error(f"Chat session {session_id} not found")
                return False
            
            # Check if message already exists in core system
            existing_message = self.db.query(ChatMessage).filter(
                ChatMessage.session_id == chat_session.id,
                ChatMessage.content == instagram_message.get_display_content(),
                ChatMessage.is_from_user == instagram_message.is_from_user,
                ChatMessage.created_at == instagram_message.created_at
            ).first()
            
            if existing_message:
                logger.debug(f"Message already synced: {instagram_message.id}")
                return True
            
            # Create new ChatMessage
            chat_message = ChatMessage(
                session_id=chat_session.id,
                content=instagram_message.get_display_content(),
                is_from_user=instagram_message.is_from_user,
                created_at=instagram_message.created_at
            )
            
            self.db.add(chat_message)
            self.db.commit()
            
            logger.info(f"✅ Synced Instagram message to core memory: {instagram_message.id}")
            return True
            
        except Exception as e:
            logger.error(f"Error syncing Instagram message to core: {str(e)}")
            self.db.rollback()
            return False
    
    def get_conversation_history_unified(self, instagram_conversation: InstagramConversation, 
                                       max_messages: int = 20) -> List[Dict]:
        """
        Get unified conversation history from both Instagram and core systems
        
        Args:
            instagram_conversation: Instagram conversation object
            max_messages: Maximum number of messages to retrieve
            
        Returns:
            List[Dict]: Unified conversation history
        """
        try:
            user_identifier = instagram_conversation.get_user_identifier()
            
            # Get history from core memory system
            core_history = self.core_memory.get_conversation_history(user_identifier, max_messages)
            
            if core_history:
                logger.debug(f"Retrieved {len(core_history)} messages from core memory")
                return core_history
            
            # Fallback to Instagram-specific history
            return self._get_instagram_only_history(instagram_conversation, max_messages)
            
        except Exception as e:
            logger.error(f"Error getting unified conversation history: {str(e)}")
            return self._get_instagram_only_history(instagram_conversation, max_messages)
    
    def _get_instagram_only_history(self, instagram_conversation: InstagramConversation, 
                                   max_messages: int) -> List[Dict]:
        """Get conversation history from Instagram messages only"""
        try:
            messages = self.db.query(InstagramMessage).filter(
                InstagramMessage.conversation_id == instagram_conversation.id
            ).order_by(InstagramMessage.created_at.desc()).limit(max_messages).all()
            
            # Convert to core memory format (chronological order)
            history = []
            for message in reversed(messages):
                role = "user" if message.is_from_user else "assistant"
                history.append({
                    "role": role,
                    "content": message.get_display_content(),
                    "timestamp": message.created_at.isoformat(),
                    "platform": "instagram"
                })
            
            logger.debug(f"Retrieved {len(history)} messages from Instagram-only history")
            return history
            
        except Exception as e:
            logger.error(f"Error getting Instagram-only history: {str(e)}")
            return []
    
    def store_bot_response_in_core(self, instagram_conversation: InstagramConversation, 
                                  response_content: str) -> bool:
        """
        Store bot response in core memory system
        
        Args:
            instagram_conversation: Instagram conversation object
            response_content: Bot response content
            
        Returns:
            bool: Success status
        """
        try:
            # Get or create chat session
            session_id, _ = self.get_or_create_chat_session(instagram_conversation)
            
            # Store using core memory system
            success = self.core_memory.store_message(session_id, response_content, False)
            
            if success:
                logger.debug(f"✅ Stored bot response in core memory")
            else:
                logger.error(f"❌ Failed to store bot response in core memory")
            
            return success
            
        except Exception as e:
            logger.error(f"Error storing bot response in core: {str(e)}")
            return False
    
    def store_user_message_in_core(self, instagram_conversation: InstagramConversation, 
                                  message_content: str) -> bool:
        """
        Store user message in core memory system
        
        Args:
            instagram_conversation: Instagram conversation object
            message_content: User message content
            
        Returns:
            bool: Success status
        """
        try:
            # Get or create chat session
            session_id, _ = self.get_or_create_chat_session(instagram_conversation)
            
            # Store using core memory system
            success = self.core_memory.store_message(session_id, message_content, True)
            
            if success:
                logger.debug(f"✅ Stored user message in core memory")
            else:
                logger.error(f"❌ Failed to store user message in core memory")
            
            return success
            
        except Exception as e:
            logger.error(f"Error storing user message in core: {str(e)}")
            return False
    
    def sync_conversation_to_core(self, instagram_conversation: InstagramConversation) -> bool:
        """
        Sync entire Instagram conversation to core memory system
        
        Args:
            instagram_conversation: Instagram conversation to sync
            
        Returns:
            bool: Success status
        """
        try:
            # Get all messages from Instagram conversation
            messages = self.db.query(InstagramMessage).filter(
                InstagramMessage.conversation_id == instagram_conversation.id
            ).order_by(InstagramMessage.created_at.asc()).all()
            
            if not messages:
                logger.info(f"No messages to sync for conversation {instagram_conversation.conversation_id}")
                return True
            
            # Get or create chat session
            session_id, _ = self.get_or_create_chat_session(instagram_conversation)
            
            synced_count = 0
            for message in messages:
                success = self.sync_instagram_message_to_core(message)
                if success:
                    synced_count += 1
            
            logger.info(f"✅ Synced {synced_count}/{len(messages)} messages to core memory")
            return synced_count == len(messages)
            
        except Exception as e:
            logger.error(f"Error syncing conversation to core: {str(e)}")
            return False
    
    def get_session_stats(self, instagram_conversation: InstagramConversation) -> Dict:
        """
        Get comprehensive session statistics
        
        Args:
            instagram_conversation: Instagram conversation object
            
        Returns:
            Dict: Session statistics
        """
        try:
            user_identifier = instagram_conversation.get_user_identifier()
            
            # Get core memory stats
            core_stats = self.core_memory.get_session_stats(user_identifier)
            
            # Get Instagram-specific stats
            instagram_stats = {
                "instagram_conversation_id": instagram_conversation.conversation_id,
                "instagram_user_id": instagram_conversation.instagram_user_id,
                "instagram_username": instagram_conversation.instagram_username,
                "conversation_status": instagram_conversation.conversation_status,
                "total_instagram_messages": instagram_conversation.total_messages,
                "user_instagram_messages": instagram_conversation.user_messages,
                "bot_instagram_messages": instagram_conversation.bot_messages,
                "conversation_created_at": instagram_conversation.created_at.isoformat(),
                "last_instagram_message_at": instagram_conversation.last_message_at.isoformat() if instagram_conversation.last_message_at else None
            }
            
            # Combine stats
            combined_stats = {
                "core_memory": core_stats,
                "instagram_specific": instagram_stats,
                "platform": "instagram"
            }
            
            return combined_stats
            
        except Exception as e:
            logger.error(f"Error getting session stats: {str(e)}")
            return {"error": str(e)}
    
    def cleanup_old_sessions(self, days_old: int = 90) -> int:
        """
        Clean up old Instagram conversations and corresponding chat sessions
        
        Args:
            days_old: Age threshold in days
            
        Returns:
            int: Number of sessions cleaned up
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days_old)
            
            # Find old Instagram conversations
            old_conversations = self.db.query(InstagramConversation).filter(
                InstagramConversation.tenant_id == self.tenant_id,
                InstagramConversation.created_at < cutoff_date,
                InstagramConversation.is_active == True
            ).all()
            
            cleaned_count = 0
            
            for conversation in old_conversations:
                # Check if conversation has recent messages
                recent_message = self.db.query(InstagramMessage).filter(
                    and_(
                        InstagramMessage.conversation_id == conversation.id,
                        InstagramMessage.created_at > cutoff_date
                    )
                ).first()
                
                # Only deactivate if no recent messages
                if not recent_message:
                    conversation.is_active = False
                    conversation.conversation_status = "archived"
                    cleaned_count += 1
            
            # Also clean up core memory sessions
            core_cleaned = self.core_memory.cleanup_old_sessions(days_old)
            
            self.db.commit()
            
            logger.info(f"🧹 Cleaned up {cleaned_count} Instagram conversations and {core_cleaned} core sessions")
            return cleaned_count + core_cleaned
            
        except Exception as e:
            logger.error(f"Error cleaning up old sessions: {str(e)}")
            self.db.rollback()
            return 0
    
    def migrate_instagram_conversations_to_core(self, limit: int = 100) -> Dict[str, int]:
        """
        Migrate Instagram conversations to core memory system (batch operation)
        
        Args:
            limit: Maximum number of conversations to migrate per batch
            
        Returns:
            Dict[str, int]: Migration statistics
        """
        try:
            # Find Instagram conversations that may not be synced
            conversations = self.db.query(InstagramConversation).filter(
                InstagramConversation.tenant_id == self.tenant_id,
                InstagramConversation.is_active == True
            ).limit(limit).all()
            
            stats = {
                "total_conversations": len(conversations),
                "successful_migrations": 0,
                "failed_migrations": 0,
                "messages_synced": 0
            }
            
            for conversation in conversations:
                try:
                    # Count messages before sync
                    message_count_before = self.db.query(InstagramMessage).filter(
                        InstagramMessage.conversation_id == conversation.id
                    ).count()
                    
                    # Perform sync
                    success = self.sync_conversation_to_core(conversation)
                    
                    if success:
                        stats["successful_migrations"] += 1
                        stats["messages_synced"] += message_count_before
                    else:
                        stats["failed_migrations"] += 1
                        
                except Exception as e:
                    logger.error(f"Error migrating conversation {conversation.conversation_id}: {str(e)}")
                    stats["failed_migrations"] += 1
            
            logger.info(f"📊 Migration batch complete: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"Error in batch migration: {str(e)}")
            return {
                "total_conversations": 0,
                "successful_migrations": 0,
                "failed_migrations": 1,
                "messages_synced": 0,
                "error": str(e)
            }
    
    def get_cross_platform_context(self, instagram_user_id: str, platforms: List[str] = None) -> Dict:
        """
        Get conversation context across multiple platforms for the same user
        
        Args:
            instagram_user_id: Instagram user ID
            platforms: List of platforms to include (default: all)
            
        Returns:
            Dict: Cross-platform conversation context
        """
        try:
            if platforms is None:
                platforms = ["instagram", "discord", "slack", "web"]
            
            user_identifier = f"instagram:{instagram_user_id}"
            
            # Get core memory context (which may include cross-platform data)
            core_context = self.core_memory.get_conversation_history(user_identifier, max_messages=50)
            
            # Analyze platforms used
            platforms_used = set()
            message_counts_by_platform = {}
            
            for message in core_context:
                platform = message.get("platform", "unknown")
                platforms_used.add(platform)
                message_counts_by_platform[platform] = message_counts_by_platform.get(platform, 0) + 1
            
            return {
                "user_identifier": user_identifier,
                "total_messages": len(core_context),
                "platforms_used": list(platforms_used),
                "message_counts_by_platform": message_counts_by_platform,
                "recent_messages": core_context[-10:] if core_context else [],
                "conversation_span_days": self._calculate_conversation_span(core_context),
                "cross_platform_user": len(platforms_used) > 1
            }
            
        except Exception as e:
            logger.error(f"Error getting cross-platform context: {str(e)}")
            return {
                "error": str(e),
                "user_identifier": f"instagram:{instagram_user_id}",
                "total_messages": 0,
                "platforms_used": [],
                "message_counts_by_platform": {},
                "recent_messages": []
            }
    
    def _calculate_conversation_span(self, messages: List[Dict]) -> int:
        """Calculate conversation span in days"""
        if len(messages) < 2:
            return 0
        
        try:
            first_msg_time = datetime.fromisoformat(messages[0]["timestamp"].replace('Z', '+00:00'))
            last_msg_time = datetime.fromisoformat(messages[-1]["timestamp"].replace('Z', '+00:00'))
            
            span = last_msg_time - first_msg_time
            return span.days
        except:
            return 0