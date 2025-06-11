# app/discord/discord_bot.py - Fixed version with proper rate limiting

import discord
from discord.ext import commands
import asyncio
import logging
import ssl
import aiohttp
import certifi
import math
from typing import Optional, Dict, Any, Callable
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager
from app.database import get_db, SessionLocal
from app.tenants.models import Tenant

# Use the correct chatbot engine
from app.chatbot.engine import ChatbotEngine

# PRICING INTEGRATION - ADD THESE IMPORTS
from app.pricing.integration_helpers import track_message_sent
from app.pricing.service import PricingService

logger = logging.getLogger(__name__)

class RateLimiter:
    def __init__(self, calls_per_second=5):
        self.calls_per_second = calls_per_second
        self.call_times = []
    
    async def wait_if_needed(self):
        now = asyncio.get_event_loop().time()
        
        # Remove calls older than 1 second
        self.call_times = [t for t in self.call_times if now - t < 1.0]
        
        # If we're at the limit, wait
        if len(self.call_times) >= self.calls_per_second:
            sleep_time = 1.0 - (now - self.call_times[0])
            if sleep_time > 0:
                logger.debug(f"Rate limiting: waiting {sleep_time:.2f}s")
                await asyncio.sleep(sleep_time)
        
        self.call_times.append(now)

class MessageQueue:
    def __init__(self, max_concurrent=1):
        self.queue = asyncio.Queue()
        self.processing = False
        self.max_concurrent = max_concurrent
        self.active_tasks = 0
    
    async def add_message(self, handler_func, *args, **kwargs):
        await self.queue.put((handler_func, args, kwargs))
        if not self.processing:
            asyncio.create_task(self.process_queue())
    
    async def process_queue(self):
        self.processing = True
        while not self.queue.empty() and self.active_tasks < self.max_concurrent:
            try:
                handler_func, args, kwargs = await self.queue.get()
                self.active_tasks += 1
                asyncio.create_task(self._execute_handler(handler_func, args, kwargs))
            except Exception as e:
                logger.error(f"Queue processing error: {e}")
        self.processing = False
    
    async def _execute_handler(self, handler_func, args, kwargs):
        try:
            await handler_func(*args, **kwargs)
        finally:
            self.active_tasks -= 1

class BotMetrics:
    def __init__(self):
        self.messages_processed = 0
        self.rate_limit_hits = 0
        self.last_rate_limit = None
        self.api_errors = 0
    
    def log_rate_limit(self):
        self.rate_limit_hits += 1
        self.last_rate_limit = asyncio.get_event_loop().time()
        logger.warning(f"Rate limit hit #{self.rate_limit_hits}")

class TenantDiscordBot:
    """Individual Discord bot instance for a tenant"""
    
    def __init__(self, tenant_id: int, token: str, db_session_factory: Callable):
        self.tenant_id = tenant_id
        self.token = token
        self.db_session_factory = db_session_factory
        self.bot = None
        self.is_running = False
        
        # Rate limiting and queue management
        self.rate_limiter = RateLimiter(calls_per_second=2)  # Conservative limit
        self.message_queue = MessageQueue(max_concurrent=1)  # One message at a time
        self.metrics = BotMetrics()
        
        # Bot configuration
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True
        
        # Create SSL context with proper certificates
        try:
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            ssl_context.check_hostname = True
            ssl_context.verify_mode = ssl.CERT_REQUIRED
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            logger.info(f"Created SSL context with certificates for tenant {self.tenant_id}")
        except Exception as e:
            logger.warning(f"Could not create verified SSL context: {e}. Using default.")
            connector = None
        
        # Create bot with SSL connector (if available)
        if connector:
            self.bot = commands.Bot(
                command_prefix='!',
                intents=intents,
                help_command=None,
                connector=connector
            )
        else:
            self.bot = commands.Bot(
                command_prefix='!',
                intents=intents,
                help_command=None
            )
        
        # Setup bot events and commands
        self.setup_bot_events()
    
    def get_db_session(self) -> Session:
        """Get a new database session"""
        return self.db_session_factory()
    
    @asynccontextmanager
    async def get_db_context(self):
        """Context manager for database sessions"""
        db = self.get_db_session()
        try:
            yield db
        except Exception as e:
            db.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            db.close()
    
    async def send_with_retry(self, target, content=None, embed=None, max_retries=3):
        """Send message with exponential backoff on rate limits"""
        for attempt in range(max_retries):
            try:
                # Wait for rate limiter
                await self.rate_limiter.wait_if_needed()
                
                if content and len(content) > 2000:
                    chunks = [content[i:i+1900] for i in range(0, len(content), 1900)]
                    for i, chunk in enumerate(chunks):
                        if hasattr(target, 'reply') and i == 0:
                            await target.reply(chunk)
                        else:
                            channel = target.channel if hasattr(target, 'channel') else target
                            await channel.send(chunk)
                        await asyncio.sleep(0.5)  # Delay between chunks
                else:
                    if embed:
                        if hasattr(target, 'send'):
                            await target.send(embed=embed)
                        else:
                            await target.reply(embed=embed)
                    else:
                        if hasattr(target, 'reply'):
                            await target.reply(content)
                        else:
                            await target.send(content)
                return True
                
            except discord.HTTPException as e:
                if e.status == 429:  # Rate limited
                    self.metrics.log_rate_limit()
                    retry_after = getattr(e, 'retry_after', 2 ** attempt)
                    logger.warning(f"Rate limited, waiting {retry_after}s (attempt {attempt + 1})")
                    await asyncio.sleep(retry_after)
                else:
                    self.metrics.api_errors += 1
                    logger.error(f"Discord API error: {e}")
                    if attempt == max_retries - 1:
                        return False
                    await asyncio.sleep(2 ** attempt)
            except Exception as e:
                logger.error(f"Unexpected error sending message: {e}")
                return False
        
        return False
    
    def setup_bot_events(self):
        """Setup Discord bot event handlers"""
        
        @self.bot.event
        async def on_ready():
            logger.info(f"Discord bot for tenant {self.tenant_id} is ready!")
            logger.info(f"Bot name: {self.bot.user.name}")
            logger.info(f"Bot is in {len(self.bot.guilds)} guilds")
            logger.info(f"✨ Features: Rate Limiting + Simple Memory + Human Delays")
            
            # Set bot status with rate limiting
            async with self.get_db_context() as db:
                try:
                    tenant = db.query(Tenant).filter(Tenant.id == self.tenant_id).first()
                    if tenant and hasattr(tenant, 'discord_status_message') and tenant.discord_status_message:
                        await self.rate_limiter.wait_if_needed()
                        activity = discord.Activity(
                            type=discord.ActivityType.playing,
                            name=tenant.discord_status_message
                        )
                        await self.bot.change_presence(activity=activity)
                        logger.info(f"Set bot status: {tenant.discord_status_message}")
                except Exception as e:
                    logger.error(f"Error setting bot status: {e}")
        
        @self.bot.event
        async def on_message(message):
            # Ignore bot messages
            if message.author.bot:
                return
            
            # Process commands first
            await self.bot.process_commands(message)
            
            # Only respond to DMs or mentions (and not commands)
            if not (isinstance(message.channel, discord.DMChannel) or self.bot.user in message.mentions):
                return
            
            # Skip if this was a command
            if message.content.startswith('!'):
                return
            
            # Queue the message for processing
            await self.message_queue.add_message(self._process_message_with_limits, message)
        
        @self.bot.event
        async def on_error(event, *args, **kwargs):
            logger.error(f"Discord bot error in event {event}: {args}", exc_info=True)
        
        # Help command
        @self.bot.command(name='help')
        async def help_command(ctx):
            """Show help information"""
            embed = discord.Embed(
                title="🤖 AI Assistant Help",
                description="I'm here to help answer your questions!",
                color=0x00ff00
            )
            embed.add_field(
                name="💬 How to chat",
                value="Just send me a direct message or mention me in a channel!",
                inline=False
            )
            embed.add_field(
                name="🛠️ Commands",
                value="`!help` - Show this help message\n`!reset` - Reset our conversation\n`!ping` - Test if I'm working",
                inline=False
            )
            embed.add_field(
                name="🧠 Memory",
                value="I remember our conversations, so you can refer to things we discussed earlier!",
                inline=False
            )
            embed.add_field(
                name="📞 Support",
                value="If you need additional help, please contact our support team.",
                inline=False
            )
            embed.set_footer(text="✨ Powered by AI with Rate Limiting")
            
            # Use rate-limited sending
            success = await self.send_with_retry(ctx, embed=embed)
            if not success:
                logger.error(f"Failed to send help embed after retries")
        
        @self.bot.command(name='ping')
        async def ping_command(ctx):
            """Test bot responsiveness"""
            latency = round(self.bot.latency * 1000, 2)
            success = await self.send_with_retry(ctx, f"🏓 Pong! Latency: {latency}ms")
            if not success:
                logger.error(f"Failed to send ping response")
        
        @self.bot.command(name='reset')
        async def reset_conversation(ctx):
            """Reset the conversation for this user"""
            async with self.get_db_context() as db:
                try:
                    # Use the correct chatbot engine
                    engine = ChatbotEngine(db)
                    
                    # Clear session
                    user_identifier = f"discord:{ctx.author.id}"
                    
                    # Find and end existing session
                    from app.chatbot.models import ChatSession
                    session = db.query(ChatSession).filter(
                        ChatSession.tenant_id == self.tenant_id,
                        ChatSession.user_identifier == user_identifier,
                        ChatSession.is_active == True
                    ).first()
                    
                    if session:
                        engine.end_session(session.session_id)
                        await self.send_with_retry(ctx, "✅ Reset conversation history! Let's start fresh.")
                        logger.info(f"Reset conversation for user {ctx.author.id} in tenant {self.tenant_id}")
                    else:
                        await self.send_with_retry(ctx, "💬 No active conversation found. Just start chatting!")
                        
                except Exception as e:
                    logger.error(f"Error resetting conversation: {e}")
                    await self.send_with_retry(ctx, "❌ Error resetting conversation. Please try again.")
    
    async def _process_message_with_limits(self, message):
        """Process message with rate limiting and proper database handling"""
        async with message.channel.typing():
            async with self.get_db_context() as db:
                try:
                    # Get tenant info
                    tenant = db.query(Tenant).filter(Tenant.id == self.tenant_id).first()
                    if not tenant:
                        await self.send_with_retry(message, "❌ Bot configuration error. Please contact support.")
                        logger.error(f"Tenant {self.tenant_id} not found")
                        return
                    
                    # PRICING CHECK - Check message limits BEFORE processing
                    logger.info(f"🔍 Checking Discord message limits for tenant {self.tenant_id}")
                    pricing_service = PricingService(db)
                    
                    if not pricing_service.check_message_limit(self.tenant_id):
                        logger.warning(f"🚫 Discord message limit exceeded for tenant {self.tenant_id}")
                        
                        # Send limit exceeded message to Discord user
                        limit_embed = discord.Embed(
                            title="💰 Message Limit Reached",
                            description="You've reached your message limit for this month.",
                            color=0xff6b35
                        )
                        limit_embed.add_field(
                            name="What now?",
                            value="Please upgrade your plan to continue chatting with me!",
                            inline=False
                        )
                        limit_embed.add_field(
                            name="Need help?",
                            value="Contact our support team to upgrade your plan.",
                            inline=False
                        )
                        await self.send_with_retry(message, embed=limit_embed)
                        return
                    
                    logger.info(f"✅ Discord message limit check passed for tenant {self.tenant_id}")
                    
                    # Initialize the correct chatbot engine
                    engine = ChatbotEngine(db)
                    
                    # Clean message content (remove mentions)
                    clean_message = message.content
                    if message.mentions:
                        for mention in message.mentions:
                            clean_message = clean_message.replace(f'<@{mention.id}>', '').strip()
                            clean_message = clean_message.replace(f'<@!{mention.id}>', '').strip()
                    
                    if not clean_message:
                        await self.send_with_retry(message, "Hi! How can I help you today? 😊")
                        return
                    
                    logger.info(f"📨🎮 Processing Discord message from {message.author.name}: '{clean_message[:50]}...'")
                    
                    # Use the standard processing method
                    result = await engine.process_discord_message_simple_with_delay(
                        api_key=tenant.api_key,
                        user_message=clean_message,
                        discord_user_id=str(message.author.id),
                        channel_id=str(message.channel.id),
                        guild_id=str(message.guild.id) if message.guild else "DM",
                        max_context=20
                    )
                    
                    if result.get("success"):
                        response = result["response"]
                        
                        # PRICING TRACK - Log successful message usage
                        logger.info(f"📊 Tracking Discord message usage for tenant {self.tenant_id}")
                        track_success = track_message_sent(self.tenant_id, db)
                        logger.info(f"📈 Discord message tracking result: {track_success}")
                        
                        # Enhanced logging with delay info
                        log_parts = [f"✅ Responded to {message.author.name} in tenant {self.tenant_id}"]
                        
                        if result.get('response_delay'):
                            log_parts.append(f"(delay: {result.get('response_delay', 0):.2f}s)")
                        
                        if result.get('context_messages'):
                            log_parts.append(f"[Memory: {result.get('context_messages')} msgs]")
                        
                        logger.info(" ".join(log_parts))
                        
                        # Send response with rate limiting
                        success = await self.send_with_retry(message, response)
                        if success:
                            self.metrics.messages_processed += 1
                        else:
                            logger.error(f"Failed to send response after retries")
                            
                    else:
                        error_msg = result.get("error", "I'm having trouble right now. Please try again later.")
                        await self.send_with_retry(message, f"❌ {error_msg}")
                        logger.error(f"Chat engine error: {error_msg}")
                        
                except Exception as e:
                    logger.error(f"💥 Error handling Discord message: {e}", exc_info=True)
                    await self.send_with_retry(message, "❌ Something went wrong. Please try again later.")
    
    async def start(self):
        """Start the Discord bot"""
        try:
            self.is_running = True
            logger.info(f"Starting Discord bot for tenant {self.tenant_id} with rate limiting...")
            await self.bot.start(self.token)
        except aiohttp.ClientConnectorError as e:
            if "certificate verify failed" in str(e).lower():
                logger.warning(f"SSL Certificate error for tenant {self.tenant_id}. Trying fallback...")
                await self._start_with_fallback_ssl()
            else:
                logger.error(f"Connection error for tenant {self.tenant_id}: {e}")
                self.is_running = False
                raise
        except discord.LoginFailure:
            logger.error(f"Invalid Discord token for tenant {self.tenant_id}")
            self.is_running = False
            raise ValueError("Invalid Discord bot token")
        except Exception as e:
            logger.error(f"Error starting Discord bot for tenant {self.tenant_id}: {e}")
            self.is_running = False
            raise
    
    async def _start_with_fallback_ssl(self):
        """Fallback method with relaxed SSL - use only for development"""
        logger.warning(f"Using fallback SSL for tenant {self.tenant_id}")
        
        # Create relaxed SSL context
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        
        # Recreate bot with fallback connector
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True
        
        self.bot = commands.Bot(
            command_prefix='!',
            intents=intents,
            help_command=None,
            connector=connector
        )
        
        self.setup_bot_events()
        await self.bot.start(self.token)
    
    async def stop(self):
        """Stop the Discord bot"""
        try:
            if self.bot and not self.bot.is_closed():
                logger.info(f"Stopping Discord bot for tenant {self.tenant_id}")
                await self.bot.close()
        except Exception as e:
            logger.error(f"Error stopping bot for tenant {self.tenant_id}: {e}")
        finally:
            self.is_running = False

class DiscordBotManager:
    """Manages multiple Discord bots for different tenants"""
    
    def __init__(self, db_session_factory: Callable = None):
        # Fix: Use a proper session factory function
        if db_session_factory is None:
            self.db_session_factory = lambda: SessionLocal()
        else:
            self.db_session_factory = db_session_factory
            
        self.active_bots: Dict[int, TenantDiscordBot] = {}
        self.bot_tasks: Dict[int, asyncio.Task] = {}
    
    def get_db_session(self) -> Session:
        """Get a new database session"""
        return self.db_session_factory()
    
    async def start_tenant_bot(self, tenant_id: int) -> bool:
        """Start Discord bot for a specific tenant"""
        db = self.get_db_session()
        try:
            tenant = db.query(Tenant).filter(
                Tenant.id == tenant_id,
                Tenant.is_active == True
            ).first()
            
            # Check if tenant has Discord enabled and configured
            discord_enabled = getattr(tenant, 'discord_enabled', False) if tenant else False
            discord_token = getattr(tenant, 'discord_bot_token', None) if tenant else None
            
            if not tenant or not discord_token:
                logger.warning(f"Cannot start Discord bot for tenant {tenant_id}: missing config")
                return False
            
            if not discord_enabled:
                logger.info(f"Discord bot disabled for tenant {tenant_id}")
                return False
            
            # Stop existing bot if running
            await self.stop_tenant_bot(tenant_id)
            
            # Create new bot instance
            logger.info(f"Creating Discord bot instance for tenant {tenant_id}")
            bot_instance = TenantDiscordBot(
                tenant_id=tenant_id,
                token=discord_token,
                db_session_factory=self.db_session_factory
            )
            
            # Start bot in background task
            task = asyncio.create_task(bot_instance.start())
            
            self.active_bots[tenant_id] = bot_instance
            self.bot_tasks[tenant_id] = task
            
            logger.info(f"Started Discord bot for tenant {tenant_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error starting Discord bot for tenant {tenant_id}: {e}", exc_info=True)
            return False
        finally:
            db.close()
    
    async def stop_tenant_bot(self, tenant_id: int) -> bool:
        """Stop Discord bot for a specific tenant"""
        try:
            # Cancel task
            if tenant_id in self.bot_tasks:
                task = self.bot_tasks[tenant_id]
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                del self.bot_tasks[tenant_id]
            
            # Stop bot
            if tenant_id in self.active_bots:
                bot = self.active_bots[tenant_id]
                await bot.stop()
                del self.active_bots[tenant_id]
            
            logger.info(f"Stopped Discord bot for tenant {tenant_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error stopping Discord bot for tenant {tenant_id}: {e}", exc_info=True)
            return False
    
    async def restart_tenant_bot(self, tenant_id: int) -> bool:
        """Restart Discord bot for a specific tenant"""
        logger.info(f"Restarting Discord bot for tenant {tenant_id}")
        await self.stop_tenant_bot(tenant_id)
        await asyncio.sleep(5)  # Longer pause for rate limit recovery
        return await self.start_tenant_bot(tenant_id)
    
    async def start_all_bots(self):
        """Start Discord bots for all enabled tenants with proper throttling"""
        db = self.get_db_session()
        try:
            # Query for tenants with Discord enabled
            tenants = db.query(Tenant).filter(
                Tenant.is_active == True
            ).all()
            
            # Filter tenants that have Discord configured
            discord_tenants = []
            for tenant in tenants:
                if (hasattr(tenant, 'discord_enabled') and 
                    hasattr(tenant, 'discord_bot_token') and 
                    getattr(tenant, 'discord_enabled', False) and 
                    getattr(tenant, 'discord_bot_token', None)):
                    discord_tenants.append(tenant)
            
            logger.info(f"Starting Discord bots for {len(discord_tenants)} tenants with throttling")
            
            for i, tenant in enumerate(discord_tenants):
                await self.start_tenant_bot(tenant.id)
                
                # Progressive delay to avoid API burst
                if i < len(discord_tenants) - 1:  # Don't wait after last bot
                    delay = min(10 + (i * 5), 60)  # 10-60 second delays
                    logger.info(f"Waiting {delay}s before starting next bot...")
                    await asyncio.sleep(delay)
                
        except Exception as e:
            logger.error(f"Error starting all bots: {e}", exc_info=True)
        finally:
            db.close()
    
    async def stop_all_bots(self):
        """Stop all Discord bots"""
        logger.info("Stopping all Discord bots")
        
        for tenant_id in list(self.active_bots.keys()):
            await self.stop_tenant_bot(tenant_id)
    
    def get_bot_status(self, tenant_id: int) -> Dict[str, Any]:
        """Get status of Discord bot for a tenant - with safe values"""
        
        default_status = {
            "running": False,
            "connected": False,
            "guilds": 0,
            "latency": None,
            "features": ["rate_limiting", "simple_memory", "human_delays"],
            "metrics": {
                "messages_processed": 0,
                "rate_limit_hits": 0,
                "api_errors": 0
            }
        }
        
        if tenant_id not in self.active_bots:
            return default_status
        
        try:
            bot = self.active_bots[tenant_id]
            
            status = {
                "running": bool(bot.is_running),
                "connected": False,
                "guilds": 0,
                "latency": None,
                "features": ["rate_limiting", "simple_memory", "human_delays"],
                "metrics": {
                    "messages_processed": bot.metrics.messages_processed,
                    "rate_limit_hits": bot.metrics.rate_limit_hits,
                    "api_errors": bot.metrics.api_errors
                }
            }
            
            # Check if bot is connected
            if bot.bot and not bot.bot.is_closed():
                status["connected"] = True
                
                # Get guild count safely
                try:
                    if hasattr(bot.bot, 'guilds') and bot.bot.guilds is not None:
                        status["guilds"] = len(bot.bot.guilds)
                except Exception:
                    status["guilds"] = 0
                
                # Get latency safely
                try:
                    if hasattr(bot.bot, 'latency') and bot.bot.latency is not None:
                        latency = float(bot.bot.latency)
                        if not (math.isinf(latency) or math.isnan(latency)):
                            if 0 <= latency <= 30:  # Discord latency in seconds, max 30s
                                status["latency"] = round(latency * 1000, 2)  # Convert to ms
                except Exception:
                    status["latency"] = None
            
            return status
            
        except Exception as e:
            logger.error(f"Error getting status for tenant {tenant_id}: {e}")
            return default_status