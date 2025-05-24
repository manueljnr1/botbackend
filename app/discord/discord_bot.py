# app/discord/discord_bot.py - Complete working version

import discord
from discord.ext import commands
import asyncio
import logging
import ssl
import aiohttp
import certifi
from typing import Optional, Dict, Any, Callable
from sqlalchemy.orm import Session
from app.database import get_db, SessionLocal
from app.chatbot.engine import ChatbotEngine
from app.tenants.models import Tenant

logger = logging.getLogger(__name__)

class TenantDiscordBot:
    """Individual Discord bot instance for a tenant"""
    
    def __init__(self, tenant_id: int, token: str, db_session_factory: Callable):
        self.tenant_id = tenant_id
        self.token = token
        self.db_session_factory = db_session_factory
        self.bot = None
        self.is_running = False
        
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
            logger.info(f"Created SSL context with certificates for tenant {tenant_id}")
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
    
    def setup_bot_events(self):
        """Setup Discord bot event handlers"""
        
        @self.bot.event
        async def on_ready():
            logger.info(f"Discord bot for tenant {self.tenant_id} is ready!")
            logger.info(f"Bot name: {self.bot.user.name}")
            logger.info(f"Bot is in {len(self.bot.guilds)} guilds")
            
            # Set bot status
            db = self.get_db_session()
            try:
                tenant = db.query(Tenant).filter(Tenant.id == self.tenant_id).first()
                if tenant and hasattr(tenant, 'discord_status_message') and tenant.discord_status_message:
                    activity = discord.Activity(
                        type=discord.ActivityType.playing,
                        name=tenant.discord_status_message
                    )
                    await self.bot.change_presence(activity=activity)
                    logger.info(f"Set bot status: {tenant.discord_status_message}")
            except Exception as e:
                logger.error(f"Error setting bot status: {e}")
            finally:
                db.close()
        
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
            
            # Process the message
            await self.handle_message(message)
        
        @self.bot.event
        async def on_error(event, *args, **kwargs):
            logger.error(f"Discord bot error in event {event}: {args}", exc_info=True)
        
        @self.bot.command(name='help')
        async def help_command(ctx):
            """Show help information"""
            embed = discord.Embed(
                title="🤖 Bot Help",
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
                name="📞 Support",
                value="If you need additional help, please contact our support team.",
                inline=False
            )
            embed.set_footer(text="Powered by AI Chatbot")
            await ctx.send(embed=embed)
        
        @self.bot.command(name='ping')
        async def ping_command(ctx):
            """Test bot responsiveness"""
            latency = round(self.bot.latency * 1000, 2)
            await ctx.send(f"🏓 Pong! Latency: {latency}ms")
        
        @self.bot.command(name='reset')
        async def reset_conversation(ctx):
            """Reset the conversation for this user"""
            db = self.get_db_session()
            try:
                engine = ChatbotEngine(db)
                # Find and end existing session
                from app.chatbot.models import ChatSession
                session = db.query(ChatSession).filter(
                    ChatSession.tenant_id == self.tenant_id,
                    ChatSession.discord_user_id == str(ctx.author.id),
                    ChatSession.is_active == True
                ).first()
                
                if session:
                    engine.end_session(session.session_id)
                    await ctx.send("✅ Conversation reset! Let's start fresh.")
                    logger.info(f"Reset conversation for user {ctx.author.id} in tenant {self.tenant_id}")
                else:
                    await ctx.send("💬 No active conversation found. Just start chatting!")
            except Exception as e:
                logger.error(f"Error resetting conversation: {e}")
                await ctx.send("❌ Error resetting conversation. Please try again.")
            finally:
                db.close()
    
    async def handle_message(self, message):
        """Handle incoming Discord messages"""
        # Show typing indicator
        async with message.channel.typing():
            db = self.get_db_session()
            try:
                # Get tenant info
                tenant = db.query(Tenant).filter(Tenant.id == self.tenant_id).first()
                if not tenant:
                    await message.reply("❌ Bot configuration error. Please contact support.")
                    logger.error(f"Tenant {self.tenant_id} not found")
                    return
                
                # Create user identifier
                user_identifier = f"discord_{message.author.id}"
                
                # Initialize chatbot engine
                engine = ChatbotEngine(db)
                
                # Clean message content (remove mentions)
                clean_message = message.content
                if message.mentions:
                    for mention in message.mentions:
                        clean_message = clean_message.replace(f'<@{mention.id}>', '').strip()
                        clean_message = clean_message.replace(f'<@!{mention.id}>', '').strip()
                
                if not clean_message:
                    await message.reply("Hi! How can I help you today? 😊")
                    return
                
                logger.info(f"Processing message from {message.author.name}: '{clean_message[:50]}...'")
                
                # Process message with delay simulation (if available)
                if hasattr(engine, 'process_message_with_delay_simple'):
                    result = await engine.process_message_with_delay_simple(
                        api_key=tenant.api_key,
                        user_message=clean_message,
                        user_identifier=user_identifier
                    )
                else:
                    # Fallback to regular processing
                    result = engine.process_message(
                        api_key=tenant.api_key,
                        user_message=clean_message,
                        user_identifier=user_identifier
                    )
                
                if result.get("success"):
                    response = result["response"]
                    
                    # Update session with Discord info
                    if result.get("session_id"):
                        from app.chatbot.models import ChatSession
                        session = db.query(ChatSession).filter(
                            ChatSession.session_id == result["session_id"]
                        ).first()
                        if session:
                            session.discord_channel_id = str(message.channel.id)
                            session.discord_user_id = str(message.author.id)
                            session.discord_guild_id = str(message.guild.id) if message.guild else None
                            session.platform = "discord"
                            db.commit()
                    
                    # Split long messages for Discord's 2000 character limit
                    if len(response) > 2000:
                        chunks = [response[i:i+1900] for i in range(0, len(response), 1900)]
                        for i, chunk in enumerate(chunks):
                            if i == 0:
                                await message.reply(chunk)
                            else:
                                await message.channel.send(chunk)
                    else:
                        await message.reply(response)
                        
                    logger.info(f"Sent response to {message.author.name}")
                else:
                    error_msg = result.get("error", "I'm having trouble right now. Please try again later.")
                    await message.reply(f"❌ {error_msg}")
                    logger.error(f"Chat engine error: {error_msg}")
                    
            except Exception as e:
                logger.error(f"Error handling Discord message: {e}", exc_info=True)
                await message.reply("❌ Something went wrong. Please try again later.")
            finally:
                db.close()
    
    async def start(self):
        """Start the Discord bot"""
        try:
            self.is_running = True
            logger.info(f"Starting Discord bot for tenant {self.tenant_id}...")
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
        await asyncio.sleep(2)  # Brief pause
        return await self.start_tenant_bot(tenant_id)
    
    async def start_all_bots(self):
        """Start Discord bots for all enabled tenants"""
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
            
            logger.info(f"Starting Discord bots for {len(discord_tenants)} tenants")
            
            for tenant in discord_tenants:
                await self.start_tenant_bot(tenant.id)
                await asyncio.sleep(1)  # Brief delay between starts
                
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
            "latency": None
        }
        
        if tenant_id not in self.active_bots:
            return default_status
        
        try:
            bot = self.active_bots[tenant_id]
            
            status = {
                "running": bool(bot.is_running),
                "connected": False,
                "guilds": 0,
                "latency": None
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