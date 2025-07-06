# app/instagram/memory.py
"""
Instagram Memory Integration - ENHANCED WITH UNIFIED ENGINE
Integrates Instagram conversations with unified intelligent engine + core memory
"""

import logging
import uuid
import asyncio
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.instagram.models import InstagramConversation, InstagramMessage, InstagramIntegration
from app.chatbot.models import ChatSession, ChatMessage
from app.chatbot.simple_memory import SimpleChatbotMemory

logger = logging.getLogger(__name__)

class InstagramResponseFormatter:
    """Handle Instagram-specific formatting while preserving unified engine intelligence"""
    
    def format_for_instagram(self, response: str, conversation: InstagramConversation) -> Dict:
        """Format unified engine response for Instagram"""
        
        # Handle Instagram length limits (2000 chars)
        if len(response) > 1900:
            response = self._chunk_response(response)
        
        # Generate Instagram quick replies if appropriate
        quick_replies = self._generate_quick_replies(response)
        
        # Handle story reply context
        if conversation.conversation_source == "story_mention":
            response = f"Thanks for your story mention! {response}"
        
        # Add media context hints
        if any(keyword in response.lower() for keyword in ['image', 'photo', 'picture', 'video']):
            response = self._add_media_context(response)
        
        return {
            "content": response,
            "quick_replies": quick_replies,
            "message_type": "text",
            "instagram_formatted": True
        }
    
    def _chunk_response(self, response: str) -> str:
        """Break long responses into Instagram-friendly chunks"""
        if len(response) <= 1900:
            return response
        
        # Find natural break point
        sentences = response.split('. ')
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            if len(current_chunk + sentence) < 1800:
                current_chunk += sentence + ". "
            else:
                chunks.append(current_chunk.strip())
                current_chunk = sentence + ". "
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        # Return first chunk, store others for follow-up
        return chunks[0] + "\n\n(continued...)"
    
    def _generate_quick_replies(self, response: str) -> List[Dict]:
        """Generate Instagram quick replies based on response content"""
        
        # Analyze response for common follow-up patterns
        if "steps" in response.lower() or "process" in response.lower():
            return [
                {"content_type": "text", "title": "Next step?", "payload": "NEXT_STEP"},
                {"content_type": "text", "title": "Start over", "payload": "START_OVER"}
            ]
        
        if "pricing" in response.lower() or "cost" in response.lower():
            return [
                {"content_type": "text", "title": "See plans", "payload": "VIEW_PLANS"},
                {"content_type": "text", "title": "Contact sales", "payload": "CONTACT_SALES"}
            ]
        
        if "contact" in response.lower() or "support" in response.lower():
            return [
                {"content_type": "text", "title": "Call us", "payload": "CALL_SUPPORT"},
                {"content_type": "text", "title": "Email us", "payload": "EMAIL_SUPPORT"}
            ]
        
        return []  # No quick replies
    
    def _add_media_context(self, response: str) -> str:
        """Add context for media-related responses"""
        media_keywords = ['image', 'photo', 'picture', 'video', 'screenshot']
        
        for keyword in media_keywords:
            if keyword in response.lower():
                response += f"\n\n💡 Tip: You can send me {keyword}s directly in this chat!"
                break
        
        return response

class InstagramChunkHandler:
    """Handle chunked responses for Instagram with natural delays"""
    
    def __init__(self, api_service):
        self.api_service = api_service
    
    async def send_chunked_response(self, conversation: InstagramConversation, 
                                  full_response: str, delay_between_chunks: float = 2.5):
        """Send response in natural chunks with delays"""
        
        chunks = self._create_natural_chunks(full_response)
        sent_chunks = []
        
        for i, chunk in enumerate(chunks):
            # Add natural delay between chunks
            if i > 0:
                await asyncio.sleep(delay_between_chunks)
            
            # Send chunk
            success, message_id = self.api_service.send_message(
                conversation.instagram_user_id,
                chunk,
                "text"
            )
            
            if success:
                sent_chunks.append(chunk)
                logger.info(f"📤 Sent chunk {i+1}/{len(chunks)} to Instagram")
            else:
                logger.error(f"❌ Failed to send chunk {i+1} to Instagram")
                break
        
        return ' '.join(sent_chunks) if sent_chunks else None
    
    def _create_natural_chunks(self, response: str) -> List[str]:
        """Break response into natural chunks for Instagram"""
        max_chunk_size = 1500  # Leave room for formatting
        
        if len(response) <= max_chunk_size:
            return [response]
        
        # Break by sentences or logical sections
        sentences = response.split('. ')
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            if len(current_chunk + sentence) <= max_chunk_size:
                current_chunk += sentence + ". "
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence + ". "
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks

class InstagramMemoryManager:
    """ENHANCED: Manage Instagram conversation memory with unified intelligent engine"""
    
    def __init__(self, db: Session, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id
        self.core_memory = SimpleChatbotMemory(db, tenant_id)
        self.formatter = InstagramResponseFormatter()
        self.chunk_handler = None  # Initialize when needed
    
    def process_with_unified_engine(self, instagram_conversation: InstagramConversation, 
                                  instagram_message: InstagramMessage) -> Optional[Dict]:
        """🔥 NEW: Process with unified engine while maintaining Instagram context"""
        try:
            from app.chatbot.unified_intelligent_engine import get_unified_intelligent_engine
            
            # 1. Get user identifier for core memory
            user_identifier = instagram_conversation.get_user_identifier()
            
            # 2. Sync Instagram message to core memory BEFORE processing
            self.sync_instagram_message_to_core(instagram_message)
            
            # 3. Get tenant API key
            tenant = self.db.query(self._get_tenant_model()).filter(
                self._get_tenant_model().id == self.tenant_id
            ).first()
            
            if not tenant or not tenant.api_key:
                logger.error(f"No API key found for tenant {self.tenant_id}")
                return None
            
            # 4. Process with unified engine (gets full conversation context)
            unified_engine = get_unified_intelligent_engine(self.db)
            
            result = unified_engine.process_message(
                api_key=tenant.api_key,
                user_message=instagram_message.get_display_content(),
                user_identifier=user_identifier,
                platform="instagram"
            )
            
            # 5. Handle Instagram-specific response formatting
            if result.get("success"):
                formatted_response = self.formatter.format_for_instagram(
                    result["response"], 
                    instagram_conversation
                )
                
                # Add unified engine metadata
                formatted_response.update({
                    "answered_by": result.get("answered_by"),
                    "intent": result.get("intent"),
                    "context": result.get("context"),
                    "architecture": result.get("architecture"),
                    "token_efficiency": result.get("token_efficiency")
                })
                
                logger.info(f"✅ Unified engine processed Instagram message - {result.get('answered_by')}")
                return formatted_response
            else:
                logger.error(f"❌ Unified engine failed: {result.get('error')}")
                return None
                
        except Exception as e:
            logger.error(f"💥 Error in unified engine processing: {str(e)}")
            return None
    
    async def process_with_chunked_response(self, instagram_conversation: InstagramConversation, 
                                          instagram_message: InstagramMessage, 
                                          api_service) -> Optional[str]:
        """🔥 NEW: Process with unified engine + chunked response support"""
        
        # Initialize chunk handler if needed
        if not self.chunk_handler:
            self.chunk_handler = InstagramChunkHandler(api_service)
        
        # Get formatted response from unified engine
        formatted_response = self.process_with_unified_engine(
            instagram_conversation, instagram_message
        )
        
        if not formatted_response:
            return None
        
        response_content = formatted_response["content"]
        
        # Check if response needs chunking
        if len(response_content) > 1500:
            logger.info(f"📝 Response too long ({len(response_content)} chars), using chunks")
            
            # Send chunked response with delays
            final_response = await self.chunk_handler.send_chunked_response(
                instagram_conversation, 
                response_content
            )
            
            return final_response
        else:
            # Send single message with quick replies
            success, message_id = api_service.send_message(
                instagram_conversation.instagram_user_id,
                response_content,
                formatted_response["message_type"],
                formatted_response.get("quick_replies")
            )
            
            if success:
                logger.info(f"📤 Sent single Instagram message: {message_id}")
                return response_content
            else:
                logger.error(f"❌ Failed to send Instagram message")
                return None
    
    def _get_tenant_model(self):
        """Get tenant model - avoid circular imports"""
        from app.tenants.models import Tenant
        return Tenant
    
    # EXISTING METHODS - Keep all original functionality
    def get_or_create_chat_session(self, instagram_conversation: InstagramConversation) -> Tuple[str, bool]:
        """Get or create corresponding ChatSession for Instagram conversation"""
        try:
            user_identifier = instagram_conversation.get_user_identifier()
            session_id, is_new = self.core_memory.get_or_create_session(user_identifier, "instagram")
            
            if is_new:
                logger.info(f"📱 Created new chat session {session_id} for Instagram conversation {instagram_conversation.conversation_id}")
            
            return session_id, is_new
            
        except Exception as e:
            logger.error(f"Error getting/creating chat session: {str(e)}")
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
        """Sync Instagram message to core memory system"""
        try:
            conversation = self.db.query(InstagramConversation).filter(
                InstagramConversation.id == instagram_message.conversation_id
            ).first()
            
            if not conversation:
                logger.error(f"No conversation found for message {instagram_message.id}")
                return False
            
            session_id, _ = self.get_or_create_chat_session(conversation)
            
            chat_session = self.db.query(ChatSession).filter(
                ChatSession.session_id == session_id
            ).first()
            
            if not chat_session:
                logger.error(f"Chat session {session_id} not found")
                return False
            
            # Check if message already exists
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
        """Get unified conversation history from both Instagram and core systems"""
        try:
            user_identifier = instagram_conversation.get_user_identifier()
            core_history = self.core_memory.get_conversation_history(user_identifier, max_messages)
            
            if core_history:
                logger.debug(f"Retrieved {len(core_history)} messages from core memory")
                return core_history
            
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
        """Store bot response in core memory system"""
        try:
            session_id, _ = self.get_or_create_chat_session(instagram_conversation)
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
        """Store user message in core memory system"""
        try:
            session_id, _ = self.get_or_create_chat_session(instagram_conversation)
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
        """Sync entire Instagram conversation to core memory system"""
        try:
            messages = self.db.query(InstagramMessage).filter(
                InstagramMessage.conversation_id == instagram_conversation.id
            ).order_by(InstagramMessage.created_at.asc()).all()
            
            if not messages:
                logger.info(f"No messages to sync for conversation {instagram_conversation.conversation_id}")
                return True
            
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
        """Get comprehensive session statistics"""
        try:
            user_identifier = instagram_conversation.get_user_identifier()
            core_stats = self.core_memory.get_session_stats(user_identifier)
            
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
            
            combined_stats = {
                "core_memory": core_stats,
                "instagram_specific": instagram_stats,
                "platform": "instagram",
                "unified_engine_enabled": True
            }
            
            return combined_stats
            
        except Exception as e:
            logger.error(f"Error getting session stats: {str(e)}")
            return {"error": str(e)}
    
    def cleanup_old_sessions(self, days_old: int = 90) -> int:
        """Clean up old Instagram conversations and corresponding chat sessions"""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days_old)
            
            old_conversations = self.db.query(InstagramConversation).filter(
                InstagramConversation.tenant_id == self.tenant_id,
                InstagramConversation.created_at < cutoff_date,
                InstagramConversation.is_active == True
            ).all()
            
            cleaned_count = 0
            
            for conversation in old_conversations:
                recent_message = self.db.query(InstagramMessage).filter(
                    and_(
                        InstagramMessage.conversation_id == conversation.id,
                        InstagramMessage.created_at > cutoff_date
                    )
                ).first()
                
                if not recent_message:
                    conversation.is_active = False
                    conversation.conversation_status = "archived"
                    cleaned_count += 1
            
            core_cleaned = self.core_memory.cleanup_old_sessions(days_old)
            self.db.commit()
            
            logger.info(f"🧹 Cleaned up {cleaned_count} Instagram conversations and {core_cleaned} core sessions")
            return cleaned_count + core_cleaned
            
        except Exception as e:
            logger.error(f"Error cleaning up old sessions: {str(e)}")
            self.db.rollback()
            return 0
    
    def migrate_instagram_conversations_to_core(self, limit: int = 100) -> Dict[str, int]:
        """Migrate Instagram conversations to core memory system (batch operation)"""
        try:
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
                    message_count_before = self.db.query(InstagramMessage).filter(
                        InstagramMessage.conversation_id == conversation.id
                    ).count()
                    
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
    
    # def get_cross_platform_context(self, instagram_user_id: str, platforms: List[str] = None) -> Dict:
    #     """Get conversation context across multiple platforms for the same user"""
    #     try:
    #         if platforms is None:
    #             platforms = ["instagram", "discord", "slack", "web"]
            
    #         user_identifier = f"instagram:{instagram_user_id}"
    #         core_context = self.core_memory.get_conversation_history(user_identifier, max_messages=50)
            
    #         platforms_used = set()
    #         message_counts_by_platform = {}
            
    #         for message in core_context:
    #             platform = message.get("platform", "unknown")
    #             platforms_used.add(platform)
    #             message_counts_by_platform[platform] = message_counts_by_platform.get(platform, 0) + 1
            
    #         return {
    #             "user_identifier": user_identifier,
    #             "total_messages": len(core_context),
    #             "platforms_used": list(platforms_used),
    #             "message_counts_by_platform": message_counts_by_platform,
    #             "recent_messages": core_context[-10:] if core_context else [],
    #             "conversation_span_days": self._calculate_conversation_span(core_context),
    #             "cross_platform_user": len(platforms_used) > 1,
    #             "unified_engine_enabled": True
    #         }
            
    #     except Exception as e:
    #         logger.error(f"Error getting cross-platform context: {str(e)}")
    #         return {
    #             "error": str(e),
    #             "user_identifier": f"instagram:{instagram_user_id}",
    #             "total_messages": 0,
    #             "platforms_used": [],
    #             "message_counts_by_platform": {},
    #             "recent_messages": []
    #         }
    
    # def _calculate_conversation_span(self, messages: List[Dict]) -> int:
    #     """Calculate conversation span in days"""
    #     if len(messages) < 2:
    #         return 0
        
        # try:
        #     first_msg_time = datetime.fromisoformat(messages[0]["timestamp"].replace('Z', '+00:00'))
        #     last_msg_time = datetime.fromisoformat(messages[-1]["timestamp"].replace('Z', '+00:00'))
            
        #     span = last_msg_time - first_msg_time
        #     return span.days
        # except:
        #     return 0