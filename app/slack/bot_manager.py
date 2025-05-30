# app/slack/bot_manager.py
"""
Enhanced Slack Bot Manager with Thread-Aware Conversations and Delays
"""

import asyncio
import logging
from typing import Dict, Optional, List, Set, Any
import time
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.errors import SlackApiError
from sqlalchemy.orm import Session
from app.database import get_db
from app.tenants.models import Tenant

# Use the correct chatbot engine
from app.chatbot.engine import ChatbotEngine

# Import thread memory manager (will be created)
try:
    from app.slack.thread_memory import SlackThreadMemoryManager
except ImportError:
    # Fallback for when thread_memory.py doesn't exist yet
    logger = logging.getLogger(__name__)
    logger.warning("SlackThreadMemoryManager not found - thread features disabled")
    SlackThreadMemoryManager = None

logger = logging.getLogger(__name__)

class SlackBotManager:
    """Enhanced Slack Bot Manager with Thread-Aware Conversations and Delays"""
    
    def __init__(self):
        self.bots: Dict[int, AsyncApp] = {}
        self.handlers: Dict[int, AsyncSlackRequestHandler] = {}
        self.clients: Dict[int, AsyncWebClient] = {}
        self.thread_managers: Dict[int, SlackThreadMemoryManager] = {}  # Thread memory managers
        self.is_initialized = False
        
        # Message deduplication
        self.processed_messages: Dict[str, float] = {}
        self.processing_messages: Set[str] = set()
        self.cleanup_interval = 300
        self.last_cleanup = time.time()
    
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
        
        # Also cleanup old thread memories periodically
        for thread_manager in self.thread_managers.values():
            try:
                cleaned = thread_manager.cleanup_old_threads(days_old=30)
                if cleaned > 0:
                    logger.info(f"Cleaned up {cleaned} old thread memories")
            except Exception as e:
                logger.error(f"Error cleaning up thread memories: {e}")
    
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
        """Initialize all Slack bots for active tenants"""
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
        """Create and configure a Slack bot for a specific tenant"""
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
            
            # Set up event handlers
            await self._setup_event_handlers(app, tenant, db, thread_manager)
            
            # Create request handler
            handler = AsyncSlackRequestHandler(app)
            
            # Store references
            self.bots[tenant.id] = app
            self.clients[tenant.id] = client
            self.handlers[tenant.id] = handler
            if thread_manager:
                self.thread_managers[tenant.id] = thread_manager
            
            logger.info(f"Created Slack bot for tenant {tenant.id} ({tenant.name})")
            return True
            
        except Exception as e:
            logger.error(f"Error creating Slack bot for tenant {tenant.id}: {e}")
            return False
    
    async def _setup_event_handlers(self, app: AsyncApp, tenant: Tenant, db: Session, 
                                  thread_manager: Optional[Any] = None):
        """Set up enhanced Slack event handlers with delays"""
        
        # Enhanced message handler with delays
        @app.event("message")
        async def handle_message(event, say, client):
            try:
                self._cleanup_old_messages()
                
                # Skip bot messages and certain subtypes
                if event.get("bot_id") or event.get("subtype") in ["message_deleted", "message_changed"]:
                    return
                
                # Generate message ID for deduplication
                message_id = self._get_message_id(event)
                
                if self._is_message_processed(message_id):
                    logger.info(f"⏭️ Skipping already processed message {message_id}")
                    return
                
                self._mark_message_processing(message_id)
                
                try:
                    # Extract message details
                    user_id = event["user"]
                    channel_id = event["channel"]
                    message_text = event.get("text", "")
                    message_ts = event.get("ts")
                    thread_ts = event.get("thread_ts")
                    
                    # Determine if this is a thread reply or new thread
                    is_thread_reply = bool(thread_ts and thread_ts != message_ts)
                    thread_identifier = thread_ts if is_thread_reply else None
                    
                    logger.info(f"📨💬 Processing Slack message from {user_id} in {'thread' if is_thread_reply else 'channel'}: '{message_text[:50]}...'")
                    
                    # Get channel info for DM/mention detection
                    try:
                        channel_info = await client.conversations_info(channel=channel_id)
                        is_dm = channel_info["channel"]["is_im"]
                        
                        # Update channel context if thread manager available
                        if thread_manager:
                            await self._update_channel_context(
                                thread_manager, channel_info["channel"], client
                            )
                        
                        # Get bot user ID for mention checking
                        bot_user_id = await self._get_bot_user_id(client)
                        is_mentioned = f"<@{bot_user_id}>" in message_text
                        
                        # Thread-aware response logic
                        should_respond = False
                        
                        if is_dm:
                            should_respond = True
                        elif is_thread_reply and thread_manager:
                            # In threads, check if bot was mentioned or if bot participated before
                            if is_mentioned:
                                should_respond = True
                            else:
                                # Check if bot has participated in this thread
                                thread_history = thread_manager.get_thread_conversation_history(
                                    channel_id, user_id, thread_identifier, max_messages=50
                                )
                                bot_participated = any(not msg["is_from_user"] for msg in thread_history)
                                should_respond = bot_participated
                        elif not thread_manager:
                            # Fallback logic without thread manager
                            should_respond = is_dm or is_mentioned
                        else:
                            # Main channel - only respond to mentions
                            should_respond = is_mentioned
                        
                        if not should_respond:
                            logger.info(f"⏭️ Not responding - conditions not met")
                            self._mark_message_processed(message_id)
                            return
                        
                        # Clean message text
                        cleaned_text = self._clean_message_text(message_text, bot_user_id)
                        
                        # Store user message in thread memory (if available)
                        if thread_manager:
                            thread_manager.add_message_to_thread(
                                channel_id=channel_id,
                                user_id=user_id,
                                message=cleaned_text,
                                is_from_user=True,
                                thread_ts=thread_identifier,
                                message_ts=message_ts
                            )
                        
                        # Initialize the correct chatbot engine
                        engine = ChatbotEngine(next(get_db()))
                        
                        if thread_manager:
                            # Use enhanced processing with thread context
                            result = await self._process_slack_message_with_thread_context(
                                engine=engine,
                                tenant=tenant,
                                thread_manager=thread_manager,
                                channel_id=channel_id,
                                user_id=user_id,
                                message=cleaned_text,
                                thread_ts=thread_identifier
                            )
                        else:
                            # Use standard processing method
                            result = await engine.process_slack_message_simple_with_delay(
                                api_key=tenant.api_key,
                                user_message=cleaned_text,
                                slack_user_id=user_id,
                                channel_id=channel_id,
                                team_id=tenant.slack_team_id,
                                max_context=20
                            )
                        
                        if result.get("success"):
                            # Determine response threading
                            response_thread_ts = None
                            if is_dm:
                                response_thread_ts = None  # No threading in DMs
                            elif is_thread_reply:
                                response_thread_ts = thread_ts  # Reply in existing thread
                            else:
                                # New mention in channel - start new thread
                                response_thread_ts = message_ts
                            
                            # Send response
                            response_msg = await say(
                                text=result["response"],
                                channel=channel_id,
                                thread_ts=response_thread_ts
                            )
                            
                            # Store bot response in thread memory (if available)
                            if response_msg and response_msg.get("ts") and thread_manager:
                                thread_manager.add_message_to_thread(
                                    channel_id=channel_id,
                                    user_id=user_id,
                                    message=result["response"],
                                    is_from_user=False,
                                    thread_ts=thread_identifier or response_thread_ts,
                                    message_ts=response_msg["ts"]
                                )
                            
                            # Enhanced logging with delay info
                            log_msg = f"✅ Responded to Slack message from {user_id} in tenant {tenant.id}"
                            if result.get('response_delay'):
                                log_msg += f" (delay: {result.get('response_delay', 0):.2f}s)"
                            logger.info(log_msg)
                            
                        else:
                            error_message = "I'm having trouble processing your message right now. Please try again later."
                            await say(
                                text=error_message,
                                channel=channel_id,
                                thread_ts=response_thread_ts if 'response_thread_ts' in locals() else None
                            )
                            logger.error(f"❌ Failed to process message: {result.get('error')}")
                        
                    except SlackApiError as e:
                        logger.error(f"❌ Slack API error: {e}")
                        
                finally:
                    self._mark_message_processed(message_id)
                    
            except Exception as e:
                logger.error(f"💥 Error handling Slack message for tenant {tenant.id}: {e}")
                if 'message_id' in locals():
                    self._mark_message_processed(message_id)
        
        # Enhanced app mention handler
        @app.event("app_mention")
        async def handle_mention(event, say, client):
            try:
                message_id = self._get_message_id(event)
                
                if self._is_message_processed(message_id):
                    logger.info(f"⏭️ Skipping already processed mention {message_id}")
                    return
                
                self._mark_message_processing(message_id)
                
                try:
                    user_id = event["user"]
                    channel_id = event["channel"]
                    message_text = event.get("text", "")
                    message_ts = event.get("ts")
                    thread_ts = event.get("thread_ts")
                    
                    logger.info(f"🔔 Processing Slack mention from {user_id}: '{message_text[:50]}...'")
                    
                    # Clean message text
                    bot_user_id = await self._get_bot_user_id(client)
                    cleaned_text = self._clean_message_text(message_text, bot_user_id)
                    
                    # Store user message in thread memory
                    if thread_manager:
                        thread_manager.add_message_to_thread(
                            channel_id=channel_id,
                            user_id=user_id,
                            message=cleaned_text,
                            is_from_user=True,
                            thread_ts=thread_ts,
                            message_ts=message_ts
                        )
                    
                    # Process with the correct engine
                    engine = ChatbotEngine(next(get_db()))
                    
                    if thread_manager:
                        result = await self._process_slack_message_with_thread_context(
                            engine=engine,
                            tenant=tenant,
                            thread_manager=thread_manager,
                            channel_id=channel_id,
                            user_id=user_id,
                            message=cleaned_text,
                            thread_ts=thread_ts
                        )
                    else:
                        result = await engine.process_slack_message_simple_with_delay(
                            api_key=tenant.api_key,
                            user_message=cleaned_text,
                            slack_user_id=user_id,
                            channel_id=channel_id,
                            team_id=tenant.slack_team_id,
                            max_context=20
                        )
                    
                    if result.get("success"):
                        # Always reply in thread for mentions
                        response_msg = await say(
                            text=result["response"],
                            thread_ts=thread_ts or message_ts  # Create thread if not exists
                        )
                        
                        # Store bot response
                        if response_msg and response_msg.get("ts") and thread_manager:
                            thread_manager.add_message_to_thread(
                                channel_id=channel_id,
                                user_id=user_id,
                                message=result["response"],
                                is_from_user=False,
                                thread_ts=thread_ts or message_ts,
                                message_ts=response_msg["ts"]
                            )
                        
                        # Enhanced logging
                        log_msg = f"✅ Responded to Slack mention from {user_id} in tenant {tenant.id}"
                        logger.info(log_msg)
                    else:
                        logger.error(f"❌ Failed to process mention: {result.get('error')}")
                        
                finally:
                    self._mark_message_processed(message_id)
                    
            except Exception as e:
                logger.error(f"💥 Error handling Slack mention for tenant {tenant.id}: {e}")
                if 'message_id' in locals():
                    self._mark_message_processed(message_id)
        
        # Channel events for context updates (unchanged)
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
                    # Update channel context
                    thread_manager.update_channel_context(
                        channel_id=channel_id,
                        channel_name=channel.get("name"),
                        channel_type="private" if channel.get("is_group") else "public",
                        topic=channel.get("topic", {}).get("value")
                    )
                    logger.info(f"Updated channel context for {channel_id}")
                    
            except Exception as e:
                logger.error(f"Error handling channel update: {e}")
    
    # Enhanced processing method with thread context (calendar support removed)
    async def _process_slack_message_with_thread_context(self, engine: ChatbotEngine, 
                                                        tenant: Tenant, thread_manager: Any,
                                                        channel_id: str, user_id: str, message: str, 
                                                        thread_ts: Optional[str] = None) -> dict:
        """Process message with thread context"""
        try:
            # Generate enhanced prompt with thread context
            system_prompt = None
            if hasattr(tenant, 'system_prompt') and tenant.system_prompt:
                system_prompt = tenant.system_prompt.replace("$company_name", tenant.name)
            
            enhanced_prompt = thread_manager.generate_context_prompt(
                user_message=message,
                channel_id=channel_id,
                user_id=user_id,
                thread_ts=thread_ts,
                system_prompt=system_prompt
            )
            
            # Use correct method
            result = await engine.process_slack_message_simple_with_delay(
                api_key=tenant.api_key,
                user_message=enhanced_prompt,  # Use enhanced prompt instead of raw message
                slack_user_id=user_id,
                channel_id=channel_id,
                team_id=tenant.slack_team_id,
                max_context=5  # Reduced since we're handling context in thread manager
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing Slack message with thread context: {e}")
            return {"success": False, "error": str(e)}
    
    async def _update_channel_context(self, thread_manager: Optional[Any], 
                                    channel_data: dict, client: AsyncWebClient):
        """Update channel context information"""
        if not thread_manager:
            return  # Skip if thread manager not available
            
        try:
            channel_id = channel_data["id"]
            channel_name = channel_data.get("name", "")
            
            # Determine channel type
            if channel_data.get("is_im"):
                channel_type = "dm"
            elif channel_data.get("is_group"):
                channel_type = "group"
            elif channel_data.get("is_private"):
                channel_type = "private"
            else:
                channel_type = "public"
            
            # Get topic if available
            topic = None
            if channel_data.get("topic", {}).get("value"):
                topic = channel_data["topic"]["value"]
            
            # Update context
            thread_manager.update_channel_context(
                channel_id=channel_id,
                channel_name=channel_name,
                channel_type=channel_type,
                topic=topic
            )
            
        except Exception as e:
            logger.error(f"Error updating channel context: {e}")
    
    def _clean_message_text(self, text: str, bot_user_id: str) -> str:
        """Clean message text by removing mentions and extra whitespace"""
        # Remove bot mentions
        text = text.replace(f"<@{bot_user_id}>", "").strip()
        
        # Remove extra whitespace
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
    
    def get_thread_manager(self, tenant_id: int) -> Optional[SlackThreadMemoryManager]:
        """Get thread memory manager for a specific tenant"""
        return self.thread_managers.get(tenant_id)
    
    async def send_message(self, tenant_id: int, channel: str, text: str, 
                          thread_ts: Optional[str] = None) -> bool:
        """Send a message using a tenant's Slack bot"""
        try:
            client = self.get_client(tenant_id)
            if not client:
                logger.error(f"No Slack client found for tenant {tenant_id}")
                return False
            
            response = await client.chat_postMessage(
                channel=channel,
                text=text,
                thread_ts=thread_ts
            )
            
            return response["ok"]
            
        except SlackApiError as e:
            logger.error(f"Error sending Slack message for tenant {tenant_id}: {e}")
            return False
    
    async def update_bot_for_tenant(self, tenant: Tenant, db: Session) -> bool:
        """Update or create bot configuration for a tenant"""
        try:
            # Remove existing bot if it exists
            if tenant.id in self.bots:
                logger.info(f"Removing existing Slack bot for tenant {tenant.id}")
                del self.bots[tenant.id]
                del self.handlers[tenant.id]
                del self.clients[tenant.id]
                if tenant.id in self.thread_managers:
                    del self.thread_managers[tenant.id]
            
            # Create new bot if Slack is enabled
            if tenant.slack_enabled and tenant.slack_bot_token and tenant.slack_signing_secret:
                return await self.create_bot_for_tenant(tenant, db)
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating Slack bot for tenant {tenant.id}: {e}")
            return False
    
    async def get_bot_status(self, tenant_id: int) -> dict:
        """Get status information for a tenant's Slack bot"""
        try:
            client = self.get_client(tenant_id)
            if not client:
                return {
                    "status": "not_configured",
                    "message": "Slack bot not configured for this tenant"
                }
            
            # Test the connection
            auth_response = await client.auth_test()
            
            # Get thread statistics
            thread_manager = self.get_thread_manager(tenant_id)
            thread_stats = thread_manager.get_thread_statistics() if thread_manager else {}
            
            return {
                "status": "active",
                "bot_name": auth_response.get("user"),
                "team_name": auth_response.get("team"),
                "bot_id": auth_response.get("user_id"),
                "team_id": auth_response.get("team_id"),
                "thread_statistics": thread_stats,
                "features": ["simple_memory", "thread_awareness", "human_delays"]
            }
            
        except SlackApiError as e:
            return {
                "status": "error",
                "message": f"Slack API error: {e.response['error']}"
            }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }
    
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
        """Get thread-specific analytics for a tenant"""
        try:
            thread_manager = self.get_thread_manager(tenant_id)
            if not thread_manager:
                return {
                    "error": "Thread manager not available - thread features not enabled",
                    "success": False
                }
            
            stats = thread_manager.get_thread_statistics()
            return {
                "success": True,
                "tenant_id": tenant_id,
                "thread_analytics": stats
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