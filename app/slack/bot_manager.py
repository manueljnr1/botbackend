# app/slack/bot_manager.py
"""
Enhanced Slack Bot Manager with Unified Intelligent Engine and Intelligent Response Chunking
"""

import asyncio
import logging
import re
from typing import Dict, Optional, List, Set, Any, Tuple, Union, TYPE_CHECKING
import time
from dataclasses import dataclass
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.errors import SlackApiError
from sqlalchemy.orm import Session
from app.database import get_db
from app.tenants.models import Tenant

# CHANGE THIS IMPORT PATH to match where your unified_intelligent_engine.py is located:
from app.chatbot.unified_intelligent_engine import get_unified_intelligent_engine


# Import thread memory manager (unchanged)
try:
    from app.slack.thread_memory import SlackThreadMemoryManager
except ImportError:
    logger = logging.getLogger(__name__)
    logger.warning("SlackThreadMemoryManager not found - thread features disabled")
    SlackThreadMemoryManager = None

logger = logging.getLogger(__name__)

@dataclass
class ChunkMetadata:
    """Metadata for intelligent chunking decisions"""
    chunk_type: str
    is_final: bool
    requires_confirmation: bool
    estimated_reading_time: float
    priority: str

class SlackResponseChunker:
    """Intelligent response chunking system"""
    
    def __init__(self, max_chunk_size: int = 3500, min_chunk_size: int = 100):
        self.max_chunk_size = max_chunk_size
        self.min_chunk_size = min_chunk_size
        
        # Chunking patterns
        self.sentence_endings = re.compile(r'[.!?]+[\s\n]')
        self.paragraph_breaks = re.compile(r'\n\s*\n')
    
    def analyze_content_type(self, response: str, metadata: Dict[str, Any]) -> str:
        """Determine the best chunking strategy"""
        answered_by = metadata.get('answered_by', '').lower()
        intent = metadata.get('intent', '').lower()
        
        if 'faq' in answered_by:
            return 'faq'
        elif 'knowledge' in answered_by:
            return 'knowledge_base'
        elif any(word in response.lower() for word in ['step', 'first', 'then', 'next']):
            return 'instruction'
        elif intent in ['support', 'functional']:
            return 'support'
        else:
            return 'conversational'
    
    def chunk_by_content_type(self, response: str, content_type: str, engagement_level: str = 'medium') -> List[Dict[str, Any]]:
        """Apply content-specific chunking"""
        
        # Simple chunking - if response is short, return as single chunk
        if len(response) <= self.max_chunk_size:
            return [{
                'content': response,
                'metadata': ChunkMetadata(
                    chunk_type=content_type,
                    is_final=True,
                    requires_confirmation=False,
                    estimated_reading_time=len(response) / 200,
                    priority='medium'
                ),
                'delay': 1.0 if content_type == 'faq' else 1.5
            }]
        
        # For longer responses, split by paragraphs
        paragraphs = [p.strip() for p in self.paragraph_breaks.split(response) if p.strip()]
        chunks = []
        
        for i, paragraph in enumerate(paragraphs):
            chunks.append({
                'content': paragraph,
                'metadata': ChunkMetadata(
                    chunk_type=content_type,
                    is_final=(i == len(paragraphs) - 1),
                    requires_confirmation=False,
                    estimated_reading_time=len(paragraph) / 200,
                    priority='medium'
                ),
                'delay': 1.2 if i == 0 else 1.8
            })
        
        return chunks
    
    def should_add_interaction(self, chunk: Dict[str, Any], chunk_index: int, total_chunks: int, engagement_level: str) -> bool:
        """Determine if we should add interactive elements"""
        metadata = chunk['metadata']
        
        # Add interaction for instruction sequences
        if metadata.chunk_type == 'instruction' and total_chunks > 3 and chunk_index % 2 == 1:
            return True
        
        # Add interaction if user engagement is low
        if engagement_level == 'low' and metadata.requires_confirmation:
            return True
        
        return False
    
    def generate_interaction_text(self, chunk_type: str, engagement_level: str) -> str:
        """Generate appropriate interaction text"""
        interactions = {
            'instruction': ["Would you like me to continue with the next step?", "Ready for the next part?"],
            'knowledge_base': ["Would you like me to explain any part in more detail?", "Should I continue?"],
            'support': ["Does this help with your issue?", "Any other questions about this?"]
        }
        
        import random
        return random.choice(interactions.get(chunk_type, ["Any questions so far?"]))

class SlackBotManager:
    """Enhanced Slack Bot Manager with Unified Intelligence and Smart Chunking"""
    
    def __init__(self):
        self.bots: Dict[int, AsyncApp] = {}
        self.handlers: Dict[int, AsyncSlackRequestHandler] = {}
        self.clients: Dict[int, AsyncWebClient] = {}
        self.thread_managers: Dict[int, Any] = {}
        self.chunkers: Dict[int, SlackResponseChunker] = {}  # NEW: Per-tenant chunkers
        self.is_initialized = False
        
        # Message deduplication (unchanged)
        self.processed_messages: Dict[str, float] = {}
        self.processing_messages: Set[str] = set()
        self.cleanup_interval = 300
        self.last_cleanup = time.time()
    
    # Keep all your existing helper methods unchanged:
    def _cleanup_old_messages(self):
        """Clean up old processed messages to prevent memory leaks"""
        current_time = time.time()
        if current_time - self.last_cleanup < self.cleanup_interval:
            return
            
        cutoff_time = current_time - 600
        old_messages = [msg_id for msg_id, timestamp in self.processed_messages.items() 
                       if timestamp < cutoff_time]
        
        for msg_id in old_messages:
            self.processed_messages.pop(msg_id, None)
        
        self.last_cleanup = current_time
    
    def _get_message_id(self, event: dict) -> str:
        """Generate unique message ID for deduplication"""
        thread_ts = event.get('thread_ts', event.get('ts', ''))
        return f"{event.get('ts', '')}_{event.get('user', '')}_{event.get('channel', '')}_{thread_ts}"
    
    def _is_message_processed(self, message_id: str) -> bool:
        """Check if message was already processed"""
        return message_id in self.processed_messages or message_id in self.processing_messages
    
    def _mark_message_processing(self, message_id: str):
        """Mark message as currently being processed"""
        self.processing_messages.add(message_id)
    
    def _mark_message_processed(self, message_id: str):
        """Mark message as processed"""
        self.processing_messages.discard(message_id)
        self.processed_messages[message_id] = time.time()
    
    async def initialize_bots(self, db: Session):
        """Initialize all Slack bots for active tenants - UPDATED"""
        if self.is_initialized:
            logger.info("Slack bots already initialized, skipping...")
            return
        
        try:
            tenants = db.query(Tenant).filter(
                Tenant.is_active == True,
                Tenant.slack_enabled == True,
                Tenant.slack_bot_token.isnot(None),
                Tenant.slack_signing_secret.isnot(None)
            ).all()
            
            logger.info(f"Found {len(tenants)} tenants with Slack configuration")
            
            for tenant in tenants:
                success = await self.create_bot_for_tenant(tenant, db)
                if success:
                    logger.info(f"✅ Successfully initialized Slack bot for tenant {tenant.id}")
                else:
                    logger.warning(f"❌ Failed to initialize Slack bot for tenant {tenant.id}")
            
            self.is_initialized = True
            logger.info(f"Initialized {len(self.bots)} Slack bots successfully")
            
        except Exception as e:
            logger.error(f"Error initializing Slack bots: {e}")
    
    async def create_bot_for_tenant(self, tenant: Tenant, db: Session) -> bool:
        """Create and configure a Slack bot - UPDATED with chunker"""
        try:
            if not tenant.slack_bot_token or not tenant.slack_signing_secret:
                logger.warning(f"Missing Slack credentials for tenant {tenant.id}")
                return False
            
            if tenant.id in self.bots:
                logger.info(f"Slack bot for tenant {tenant.id} already exists, skipping creation")
                return True
            
            # Create Slack app
            app = AsyncApp(
                token=tenant.slack_bot_token,
                signing_secret=tenant.slack_signing_secret,
                process_before_response=True
            )
            
            # Create web client
            client = AsyncWebClient(token=tenant.slack_bot_token)
            
            # Create thread memory manager (if available)
            thread_manager = None
            if SlackThreadMemoryManager:
                thread_manager = SlackThreadMemoryManager(db, tenant.id)
            
            # NEW: Create intelligent chunker for this tenant
            chunker = SlackResponseChunker(max_chunk_size=3500)
            
            # Set up event handlers with chunker
            await self._setup_event_handlers(app, tenant, db, thread_manager, chunker)
            
            # Create request handler
            handler = AsyncSlackRequestHandler(app)
            
            # Store references
            self.bots[tenant.id] = app
            self.clients[tenant.id] = client
            self.handlers[tenant.id] = handler
            self.chunkers[tenant.id] = chunker  # NEW: Store chunker
            if thread_manager:
                self.thread_managers[tenant.id] = thread_manager
            
            logger.info(f"Created Slack bot for tenant {tenant.id} ({tenant.name})")
            return True
            
        except Exception as e:
            logger.error(f"Error creating Slack bot for tenant {tenant.id}: {e}")
            return False
    
    async def _setup_event_handlers(self, app: AsyncApp, tenant: Tenant, db: Session, 
                                  thread_manager: Optional[Any] = None, chunker: SlackResponseChunker = None):
        """UPDATED: Set up enhanced event handlers with unified intelligence"""
        
        @app.event("message")
        async def handle_message(event, say, client):
            try:
                self._cleanup_old_messages()
                
                # Skip bot messages and certain subtypes
                if event.get("bot_id") or event.get("subtype") in ["message_deleted", "message_changed"]:
                    return
                
                message_id = self._get_message_id(event)
                
                if self._is_message_processed(message_id):
                    logger.info(f"⏭️ Skipping already processed message {message_id}")
                    return
                
                self._mark_message_processing(message_id)
                
                try:
                    # Extract message details (same as before)
                    user_id = event["user"]
                    channel_id = event["channel"]
                    message_text = event.get("text", "")
                    message_ts = event.get("ts")
                    thread_ts = event.get("thread_ts")
                    
                    is_thread_reply = bool(thread_ts and thread_ts != message_ts)
                    thread_identifier = thread_ts if is_thread_reply else None
                    
                    logger.info(f"📨💬 Processing Slack message from {user_id}: '{message_text[:50]}...'")
                    
                    # Channel info and response logic (same as before)
                    channel_info = await client.conversations_info(channel=channel_id)
                    is_dm = channel_info["channel"]["is_im"]
                    
                    bot_user_id = await self._get_bot_user_id(client)
                    is_mentioned = f"<@{bot_user_id}>" in message_text
                    
                    # Determine if should respond (same logic)
                    should_respond = False
                    if is_dm:
                        should_respond = True
                    elif is_thread_reply and thread_manager:
                        if is_mentioned:
                            should_respond = True
                        else:
                            thread_history = thread_manager.get_thread_conversation_history(
                                channel_id, user_id, thread_identifier, max_messages=50
                            )
                            bot_participated = any(not msg["is_from_user"] for msg in thread_history)
                            should_respond = bot_participated
                    else:
                        should_respond = is_mentioned
                    
                    if not should_respond:
                        logger.info(f"⏭️ Not responding - conditions not met")
                        self._mark_message_processed(message_id)
                        return
                    
                    # Clean message
                    cleaned_text = self._clean_message_text(message_text, bot_user_id)
                    
                    # Store in thread memory
                    if thread_manager:
                        thread_manager.add_message_to_thread(
                            channel_id=channel_id,
                            user_id=user_id,
                            message=cleaned_text,
                            is_from_user=True,
                            thread_ts=thread_identifier,
                            message_ts=message_ts
                        )
                    
                    # 🚀 NEW: Use unified intelligent engine
                    engine = get_unified_intelligent_engine(next(get_db()))
                    user_identifier = f"slack_{user_id}_{channel_id}"
                    
                    # Process with unified engine
                    result = await engine.process_message(
                        api_key=tenant.api_key,
                        user_message=cleaned_text,
                        user_identifier=user_identifier,
                        platform="slack"
                    )
                    
                    if result.get("success"):
                        response_content = result["response"]
                        
                        # 🧩 NEW: Intelligent chunking
                        if chunker:
                            chunks = chunker.chunk_by_content_type(
                                response=response_content,
                                content_type=chunker.analyze_content_type(response_content, result),
                                engagement_level=result.get('engagement_level', 'medium')
                            )
                            
                            logger.info(f"🧩 Chunked response into {len(chunks)} chunks")
                            
                            # Determine threading
                            response_thread_ts = None
                            if is_dm:
                                response_thread_ts = None
                            elif is_thread_reply:
                                response_thread_ts = thread_ts
                            else:
                                response_thread_ts = message_ts
                            
                            # Send chunked response
                            await self._send_chunked_response(
                                client=client,
                                channel=channel_id,
                                chunks=chunks,
                                thread_ts=response_thread_ts,
                                engagement_level=result.get('engagement_level', 'medium'),
                                chunker=chunker
                            )
                        else:
                            # Fallback to single message
                            await say(text=response_content, channel=channel_id)
                        
                        # Enhanced logging
                        log_msg = f"✅ Unified response sent to {user_id} | Intent: {result.get('intent', 'unknown')}"
                        logger.info(log_msg)
                        
                    else:
                        error_message = "I'm having trouble processing your message right now. Please try again later."
                        await say(text=error_message, channel=channel_id)
                        logger.error(f"❌ Unified engine failed: {result.get('error')}")
                        
                finally:
                    self._mark_message_processed(message_id)
                    
            except Exception as e:
                logger.error(f"💥 Error handling Slack message for tenant {tenant.id}: {e}")
                if 'message_id' in locals():
                    self._mark_message_processed(message_id)
        
        # Keep your existing app mention handler but update the processing part
        @app.event("app_mention")
        async def handle_mention(event, say, client):
            # Same structure as above but simplified for mentions
            try:
                message_id = self._get_message_id(event)
                
                if self._is_message_processed(message_id):
                    return
                
                self._mark_message_processing(message_id)
                
                try:
                    user_id = event["user"]
                    channel_id = event["channel"]
                    message_text = event.get("text", "")
                    message_ts = event.get("ts")
                    thread_ts = event.get("thread_ts")
                    
                    bot_user_id = await self._get_bot_user_id(client)
                    cleaned_text = self._clean_message_text(message_text, bot_user_id)
                    
                    # Use unified engine
                    engine = get_unified_intelligent_engine(next(get_db()))
                    user_identifier = f"slack_{user_id}_{channel_id}"
                    
                    result = await asyncio.to_thread(
                        engine.process_message,
                        api_key=tenant.api_key,
                        user_message=cleaned_text,
                        user_identifier=user_identifier,
                        platform="slack"
                    )
                    
                    if result.get("success"):
                        response_content = result["response"]
                        
                        if chunker:
                            chunks = chunker.chunk_by_content_type(
                                response=response_content,
                                content_type=chunker.analyze_content_type(response_content, result),
                                engagement_level=result.get('engagement_level', 'medium')
                            )
                            
                            await self._send_chunked_response(
                                client=client,
                                channel=channel_id,
                                chunks=chunks,
                                thread_ts=thread_ts or message_ts,
                                engagement_level=result.get('engagement_level', 'medium'),
                                chunker=chunker
                            )
                        else:
                            await say(text=response_content, thread_ts=thread_ts or message_ts)
                        
                        logger.info(f"✅ Responded to mention from {user_id}")
                    
                finally:
                    self._mark_message_processed(message_id)
                    
            except Exception as e:
                logger.error(f"💥 Error handling mention: {e}")
                if 'message_id' in locals():
                    self._mark_message_processed(message_id)
        
        # Keep your existing channel event handlers unchanged
        @app.event("channel_created")
        @app.event("channel_rename")
        @app.event("group_rename")
        async def handle_channel_updates(event, client):
            """Update channel context when channels are created or renamed"""
            try:
                if not thread_manager:
                    return
                    
                channel = event.get("channel", {})
                channel_id = channel.get("id")
                
                if channel_id:
                    thread_manager.update_channel_context(
                        channel_id=channel_id,
                        channel_name=channel.get("name"),
                        channel_type="private" if channel.get("is_group") else "public",
                        topic=channel.get("topic", {}).get("value")
                    )
                    logger.info(f"Updated channel context for {channel_id}")
                    
            except Exception as e:
                logger.error(f"Error handling channel update: {e}")
    
    async def _send_chunked_response(self, client: AsyncWebClient, channel: str, chunks: List[Dict[str, Any]], 
                                   thread_ts: Optional[str] = None, engagement_level: str = 'medium',
                                   chunker: SlackResponseChunker = None) -> List[str]:
        """NEW: Send response in intelligent chunks"""
        sent_messages = []
        
        try:
            for i, chunk in enumerate(chunks):
                # Show typing indicator
                try:
                    await client.conversations_typing(channel=channel)
                except:
                    pass
                
                # Apply delay
                delay = chunk.get('delay', 1.5)
                if engagement_level == 'high':
                    delay *= 0.8
                elif engagement_level == 'low':
                    delay *= 1.3
                
                await asyncio.sleep(delay)
                
                # Send chunk
                response = await client.chat_postMessage(
                    channel=channel,
                    text=chunk['content'],
                    thread_ts=thread_ts
                )
                
                if response.get("ok"):
                    sent_messages.append(response.get("ts"))
                    logger.debug(f"📤 Sent chunk {i+1}/{len(chunks)}")
                
                # Add interaction if needed
                if chunker and chunker.should_add_interaction(chunk, i, len(chunks), engagement_level):
                    await asyncio.sleep(0.8)
                    interaction_text = chunker.generate_interaction_text(
                        chunk['metadata'].chunk_type, engagement_level
                    )
                    await client.chat_postMessage(
                        channel=channel,
                        text=interaction_text,
                        thread_ts=thread_ts
                    )
            
            logger.info(f"✅ Successfully sent {len(chunks)} chunks")
            
        except Exception as e:
            logger.error(f"Error sending chunked response: {e}")
        
        return sent_messages
    
    # Keep ALL your existing methods unchanged:
    def _clean_message_text(self, text: str, bot_user_id: str) -> str:
        """Clean message text by removing mentions and extra whitespace"""
        text = text.replace(f"<@{bot_user_id}>", "").strip()
        text = " ".join(text.split())
        return text
    
    async def _get_bot_user_id(self, client: AsyncWebClient) -> str:
        """Get the bot's user ID"""
        try:
            auth_response = await client.auth_test()
            return auth_response["user_id"]
        except SlackApiError as e:
            logger.error(f"Error getting bot user ID: {e}")
            return ""
    
    def get_handler(self, tenant_id: int) -> Optional[AsyncSlackRequestHandler]:
        """Get Slack request handler for a specific tenant"""
        return self.handlers.get(tenant_id)
    
    def get_client(self, tenant_id: int) -> Optional[AsyncWebClient]:
        """Get Slack client for a specific tenant"""
        return self.clients.get(tenant_id)
    
    def get_thread_manager(self, tenant_id: int):
        """Get thread memory manager for a specific tenant"""
        return self.thread_managers.get(tenant_id)
    
    def get_chunker(self, tenant_id: int) -> Optional[SlackResponseChunker]:
        """NEW: Get response chunker for a specific tenant"""
        return self.chunkers.get(tenant_id)
    
    async def send_message(self, tenant_id: int, channel: str, text: str, 
                          thread_ts: Optional[str] = None, use_chunking: bool = False) -> bool:
        """UPDATED: Send message with optional chunking"""
        try:
            client = self.get_client(tenant_id)
            if not client:
                logger.error(f"No Slack client found for tenant {tenant_id}")
                return False
            
            if use_chunking and len(text) > 3500:
                chunker = self.get_chunker(tenant_id)
                if chunker:
                    chunks = chunker.chunk_by_content_type(text, 'conversational', 'medium')
                    sent_messages = await self._send_chunked_response(
                        client=client, channel=channel, chunks=chunks,
                        thread_ts=thread_ts, engagement_level='medium', chunker=chunker
                    )
                    return len(sent_messages) > 0
            
            # Standard single message
            response = await client.chat_postMessage(
                channel=channel, text=text, thread_ts=thread_ts
            )
            return response["ok"]
            
        except SlackApiError as e:
            logger.error(f"Error sending Slack message for tenant {tenant_id}: {e}")
            return False
    
    # Keep all your other existing methods unchanged (update_bot_for_tenant, get_bot_status, etc.)
    # Just add chunker cleanup to update_bot_for_tenant:
    async def update_bot_for_tenant(self, tenant: Tenant, db: Session) -> bool:
        """Update or create bot configuration for a tenant"""
        try:
            if tenant.id in self.bots:
                logger.info(f"Removing existing Slack bot for tenant {tenant.id}")
                del self.bots[tenant.id]
                del self.handlers[tenant.id]
                del self.clients[tenant.id]
                del self.chunkers[tenant.id]  # NEW: Also remove chunker
                if tenant.id in self.thread_managers:
                    del self.thread_managers[tenant.id]
            
            if tenant.slack_enabled and tenant.slack_bot_token and tenant.slack_signing_secret:
                return await self.create_bot_for_tenant(tenant, db)
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating Slack bot for tenant {tenant.id}: {e}")
            return False
    
    async def get_bot_status(self, tenant_id: int) -> dict:
        """Get status information for a tenant's Slack bot - UPDATED"""
        try:
            client = self.get_client(tenant_id)
            if not client:
                return {"status": "not_configured", "message": "Slack bot not configured"}
            
            auth_response = await client.auth_test()
            thread_manager = self.get_thread_manager(tenant_id)
            thread_stats = thread_manager.get_thread_statistics() if thread_manager else {}
            
            # NEW: Add chunker info
            chunker = self.get_chunker(tenant_id)
            chunker_info = {
                "available": bool(chunker),
                "max_chunk_size": chunker.max_chunk_size if chunker else 0
            }
            
            return {
                "status": "active",
                "bot_name": auth_response.get("user"),
                "team_name": auth_response.get("team"),
                "bot_id": auth_response.get("user_id"),
                "team_id": auth_response.get("team_id"),
                "thread_statistics": thread_stats,
                "chunker_info": chunker_info,  # NEW
                "features": [
                    "unified_intelligence", "intelligent_chunking", 
                    "thread_awareness", "natural_delays"
                ]
            }
            
        except SlackApiError as e:
            return {"status": "error", "message": f"Slack API error: {e.response['error']}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    # Keep all your other existing methods (get_channels, get_thread_analytics, etc.)
    async def get_channels(self, tenant_id: int) -> List[dict]:
        """Get list of channels the bot can access"""
        try:
            client = self.get_client(tenant_id)
            if not client:
                return []
            
            response = await client.conversations_list(
                types="public_channel,private_channel",
                exclude_archived=True
            )
            
            channels = []
            for channel in response["channels"]:
                channels.append({
                    "id": channel["id"],
                    "name": channel["name"],
                    "is_channel": channel["is_channel"],
                    "is_private": channel["is_private"],
                    "is_member": channel.get("is_member", False)
                })
            
            return channels
            
        except SlackApiError as e:
            logger.error(f"Error getting Slack channels for tenant {tenant_id}: {e}")
            return []
    
    async def get_thread_analytics(self, tenant_id: int) -> Dict[str, Any]:
        """Get thread-specific analytics for a tenant - UPDATED"""
        try:
            thread_manager = self.get_thread_manager(tenant_id)
            if not thread_manager:
                return {"error": "Thread manager not available", "success": False}
            
            stats = thread_manager.get_thread_statistics()
            
            # NEW: Add chunking analytics
            chunker = self.get_chunker(tenant_id)
            chunking_info = {
                "chunking_enabled": bool(chunker),
                "max_chunk_size": chunker.max_chunk_size if chunker else 0,
                "features": ["content_type_detection", "engagement_adaptation"] if chunker else []
            }
            
            return {
                "success": True,
                "tenant_id": tenant_id,
                "thread_analytics": stats,
                "chunking_analytics": chunking_info,  # NEW
                "unified_engine_features": [
                    "intent_classification", "context_relevance", 
                    "conversation_flow", "security_enhanced"
                ]
            }
            
        except Exception as e:
            logger.error(f"Error getting thread analytics: {e}")
            return {"error": str(e), "success": False}

# Global instance
_slack_bot_manager = None

def get_slack_bot_manager() -> SlackBotManager:
    """Get the global Slack bot manager instance"""
    global _slack_bot_manager
    if _slack_bot_manager is None:
        _slack_bot_manager = SlackBotManager()
    return _slack_bot_manager