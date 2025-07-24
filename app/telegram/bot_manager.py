# app/telegram/bot_manager.py
"""
Telegram Bot Manager
Manages multiple Telegram bots for different tenants
"""

import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from app.telegram.service import TelegramService
from app.telegram.models import TelegramIntegration
from app.telegram.utils import TelegramUtils
from app.tenants.models import Tenant
from app.config import settings

logger = logging.getLogger(__name__)

class TelegramBotManager:
    """
    Manages Telegram bots for all tenants
    Handles bot initialization, webhook setup, and lifecycle management
    """
    
    def __init__(self):
        self.active_bots: Dict[int, TelegramService] = {}  # tenant_id -> TelegramService
        self.webhook_base_url = self._get_webhook_base_url()
    
    def _get_webhook_base_url(self) -> str:
        """Get base URL for webhooks"""
        # Use the configured base URL or construct from environment
        base_url = getattr(settings, 'WEBHOOK_BASE_URL', None)
        if not base_url:
            # Fallback to frontend URL or default
            base_url = settings.FRONTEND_URL or "https://agentlyra.up.railway.app"
        
        # Ensure no trailing slash
        return base_url.rstrip('/')
    
    async def initialize_bots(self, db: Session) -> Dict[str, any]:
        """
        Initialize all active Telegram bots
        
        Args:
            db: Database session
            
        Returns:
            Dictionary with initialization results
        """
        logger.info("🤖 Initializing Telegram bots for all tenants...")
        
        try:
            # Get all active Telegram integrations
            integrations = db.query(TelegramIntegration).filter(
                TelegramIntegration.is_active == True,
                TelegramIntegration.bot_token.isnot(None)
            ).all()
            
            if not integrations:
                logger.info("No active Telegram integrations found")
                return {"success": True, "message": "No bots to initialize", "initialized_count": 0}
            
            logger.info(f"Found {len(integrations)} active Telegram integrations")
            
            # Initialize each bot
            initialized_count = 0
            failed_count = 0
            results = []
            
            for integration in integrations:
                try:
                    result = await self._initialize_single_bot(integration, db)
                    results.append(result)
                    
                    if result["success"]:
                        initialized_count += 1
                        logger.info(f"✅ Initialized Telegram bot for tenant {integration.tenant_id}")
                    else:
                        failed_count += 1
                        logger.error(f"❌ Failed to initialize bot for tenant {integration.tenant_id}: {result.get('error')}")
                        
                except Exception as e:
                    failed_count += 1
                    error_msg = f"Exception initializing bot for tenant {integration.tenant_id}: {str(e)}"
                    logger.error(error_msg)
                    results.append({
                        "tenant_id": integration.tenant_id,
                        "success": False,
                        "error": error_msg
                    })
            
            logger.info(f"🎉 Telegram bot initialization completed: {initialized_count} success, {failed_count} failed")
            
            return {
                "success": True,
                "message": f"Initialized {initialized_count}/{len(integrations)} Telegram bots",
                "initialized_count": initialized_count,
                "failed_count": failed_count,
                "results": results
            }
            
        except Exception as e:
            logger.error(f"💥 Error in Telegram bot initialization: {str(e)}")
            return {
                "success": False,
                "error": f"Bot initialization failed: {str(e)}",
                "initialized_count": 0
            }
    
    async def _initialize_single_bot(self, integration: TelegramIntegration, db: Session) -> Dict[str, any]:
        """
        Initialize a single Telegram bot
        
        Args:
            integration: TelegramIntegration instance
            db: Database session
            
        Returns:
            Dictionary with initialization result
        """
        try:
            tenant_id = integration.tenant_id
            
            # Validate bot token format
            if not TelegramUtils.validate_bot_token(integration.bot_token):
                return {
                    "tenant_id": tenant_id,
                    "success": False,
                    "error": "Invalid bot token format"
                }
            
            # Create Telegram service
            telegram_service = TelegramService(integration.bot_token)
            
            # Test bot connection by getting bot info
            bot_info_result = await telegram_service.get_me()
            if not bot_info_result.get("success"):
                await telegram_service.close()
                return {
                    "tenant_id": tenant_id,
                    "success": False,
                    "error": f"Bot API error: {bot_info_result.get('error', 'Unknown error')}"
                }
            
            bot_info = bot_info_result["result"]
            
            # Update integration with bot info
            integration.bot_username = bot_info.get("username")
            integration.bot_name = bot_info.get("first_name")
            
            # Setup webhook
            webhook_result = await self._setup_webhook(telegram_service, integration)
            if not webhook_result.get("success"):
                await telegram_service.close()
                return {
                    "tenant_id": tenant_id,
                    "success": False,
                    "error": f"Webhook setup failed: {webhook_result.get('error')}"
                }
            
            # Store active bot service
            self.active_bots[tenant_id] = telegram_service
            
            # Update integration status
            integration.is_webhook_set = True
            integration.activated_at = datetime.utcnow()
            integration.last_error = None
            integration.error_count = 0
            
            db.commit()
            
            return {
                "tenant_id": tenant_id,
                "success": True,
                "bot_username": integration.bot_username,
                "bot_name": integration.bot_name,
                "webhook_url": integration.webhook_url
            }
            
        except Exception as e:
            logger.error(f"Error initializing bot for tenant {integration.tenant_id}: {e}")
            return {
                "tenant_id": integration.tenant_id,
                "success": False,
                "error": str(e)
            }
    
    async def _setup_webhook(self, telegram_service: TelegramService, 
                           integration: TelegramIntegration) -> Dict[str, any]:
        """
        Setup webhook for bot
        
        Args:
            telegram_service: TelegramService instance
            integration: TelegramIntegration instance
            
        Returns:
            Setup result
        """
        try:
            # Construct webhook URL
            webhook_url = f"{self.webhook_base_url}/api/telegram/webhook/{integration.tenant_id}"
            
            # Validate webhook URL
            if not TelegramUtils.validate_webhook_url(webhook_url):
                return {
                    "success": False,
                    "error": f"Invalid webhook URL: {webhook_url}"
                }
            
            # Generate webhook secret if not exists
            if not integration.webhook_secret:
                integration.webhook_secret = TelegramUtils.generate_webhook_secret()
            
            # Set webhook
            webhook_result = await telegram_service.set_webhook(
                webhook_url=webhook_url,
                secret_token=integration.webhook_secret,
                max_connections=40,
                drop_pending_updates=True  # Clear old updates on restart
            )
            
            if webhook_result.get("success"):
                integration.webhook_url = webhook_url
                logger.info(f"✅ Webhook set for tenant {integration.tenant_id}: {webhook_url}")
                return {"success": True, "webhook_url": webhook_url}
            else:
                error_msg = webhook_result.get("error", "Unknown webhook error")
                logger.error(f"❌ Webhook setup failed for tenant {integration.tenant_id}: {error_msg}")
                return {"success": False, "error": error_msg}
                
        except Exception as e:
            logger.error(f"Exception setting up webhook: {e}")
            return {"success": False, "error": str(e)}
    
    async def add_bot(self, tenant_id: int, bot_token: str, db: Session) -> Dict[str, any]:
        """
        Add a new Telegram bot for a tenant
        
        Args:
            tenant_id: Tenant ID
            bot_token: Telegram bot token
            db: Database session
            
        Returns:
            Addition result
        """
        try:
            # Validate bot token
            if not TelegramUtils.validate_bot_token(bot_token):
                return {"success": False, "error": "Invalid bot token format"}
            
            # Check if integration already exists
            existing = db.query(TelegramIntegration).filter(
                TelegramIntegration.tenant_id == tenant_id
            ).first()
            
            if existing:
                # Update existing integration
                existing.bot_token = bot_token
                existing.is_active = True
                integration = existing
            else:
                # Create new integration
                integration = TelegramIntegration(
                    tenant_id=tenant_id,
                    bot_token=bot_token,
                    is_active=True,
                    enable_typing_indicator=True,
                    max_messages_per_minute=30
                )
                db.add(integration)
            
            db.commit()
            db.refresh(integration)
            
            # Initialize the bot
            result = await self._initialize_single_bot(integration, db)
            
            if result["success"]:
                logger.info(f"✅ Successfully added Telegram bot for tenant {tenant_id}")
            else:
                logger.error(f"❌ Failed to add Telegram bot for tenant {tenant_id}: {result.get('error')}")
            
            return result
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error adding Telegram bot: {e}")
            return {"success": False, "error": str(e)}
    
    async def remove_bot(self, tenant_id: int, db: Session) -> Dict[str, any]:
        """
        Remove Telegram bot for a tenant
        
        Args:
            tenant_id: Tenant ID
            db: Database session
            
        Returns:
            Removal result
        """
        try:
            # Get integration
            integration = db.query(TelegramIntegration).filter(
                TelegramIntegration.tenant_id == tenant_id
            ).first()
            
            if not integration:
                return {"success": False, "error": "No Telegram integration found"}
            
            # Remove webhook if bot is active
            if tenant_id in self.active_bots:
                telegram_service = self.active_bots[tenant_id]
                
                try:
                    await telegram_service.delete_webhook(drop_pending_updates=True)
                    logger.info(f"✅ Webhook deleted for tenant {tenant_id}")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to delete webhook for tenant {tenant_id}: {e}")
                
                try:
                    await telegram_service.close()
                except Exception as e:
                    logger.warning(f"⚠️ Failed to close Telegram service for tenant {tenant_id}: {e}")
                
                # Remove from active bots
                del self.active_bots[tenant_id]
            
            # Deactivate integration (don't delete to preserve history)
            integration.is_active = False
            integration.is_webhook_set = False
            integration.webhook_url = None
            
            db.commit()
            
            logger.info(f"✅ Removed Telegram bot for tenant {tenant_id}")
            return {
                "success": True,
                "message": f"Telegram bot removed for tenant {tenant_id}"
            }
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error removing Telegram bot: {e}")
            return {"success": False, "error": str(e)}
    
    async def restart_bot(self, tenant_id: int, db: Session) -> Dict[str, any]:
        """
        Restart a specific Telegram bot
        
        Args:
            tenant_id: Tenant ID
            db: Database session
            
        Returns:
            Restart result
        """
        try:
            # First remove the bot
            await self.remove_bot(tenant_id, db)
            
            # Wait a moment
            await asyncio.sleep(1)
            
            # Get integration
            integration = db.query(TelegramIntegration).filter(
                TelegramIntegration.tenant_id == tenant_id
            ).first()
            
            if not integration or not integration.bot_token:
                return {"success": False, "error": "No valid Telegram integration found"}
            
            # Reactivate and initialize
            integration.is_active = True
            db.commit()
            
            result = await self._initialize_single_bot(integration, db)
            
            if result["success"]:
                logger.info(f"✅ Restarted Telegram bot for tenant {tenant_id}")
            else:
                logger.error(f"❌ Failed to restart Telegram bot for tenant {tenant_id}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error restarting Telegram bot: {e}")
            return {"success": False, "error": str(e)}
    
    async def stop_all_bots(self) -> Dict[str, any]:
        """
        Stop all active Telegram bots
        
        Returns:
            Stop result
        """
        try:
            logger.info("🛑 Stopping all Telegram bots...")
            
            stopped_count = 0
            failed_count = 0
            
            for tenant_id, telegram_service in list(self.active_bots.items()):
                try:
                    # Delete webhook
                    await telegram_service.delete_webhook(drop_pending_updates=True)
                    
                    # Close service
                    await telegram_service.close()
                    
                    stopped_count += 1
                    logger.info(f"✅ Stopped Telegram bot for tenant {tenant_id}")
                    
                except Exception as e:
                    failed_count += 1
                    logger.error(f"❌ Failed to stop Telegram bot for tenant {tenant_id}: {e}")
            
            # Clear active bots
            self.active_bots.clear()
            
            logger.info(f"🏁 Telegram bot shutdown completed: {stopped_count} stopped, {failed_count} failed")
            
            return {
                "success": True,
                "message": f"Stopped {stopped_count} Telegram bots",
                "stopped_count": stopped_count,
                "failed_count": failed_count
            }
            
        except Exception as e:
            logger.error(f"💥 Error stopping Telegram bots: {e}")
            return {"success": False, "error": str(e)}
    
    def get_bot_service(self, tenant_id: int) -> Optional[TelegramService]:
        """
        Get Telegram service for a tenant
        
        Args:
            tenant_id: Tenant ID
            
        Returns:
            TelegramService instance or None
        """
        return self.active_bots.get(tenant_id)
    
    def is_bot_active(self, tenant_id: int) -> bool:
        """
        Check if bot is active for a tenant
        
        Args:
            tenant_id: Tenant ID
            
        Returns:
            True if bot is active
        """
        return tenant_id in self.active_bots
    
    def get_active_bot_count(self) -> int:
        """
        Get number of active bots
        
        Returns:
            Number of active bots
        """
        return len(self.active_bots)
    
    def get_bot_stats(self) -> Dict[str, any]:
        """
        Get statistics about active bots
        
        Returns:
            Bot statistics
        """
        return {
            "total_active_bots": len(self.active_bots),
            "active_tenant_ids": list(self.active_bots.keys()),
            "webhook_base_url": self.webhook_base_url
        }
    
    async def health_check(self, tenant_id: int) -> Dict[str, any]:
        """
        Perform health check on a specific bot
        
        Args:
            tenant_id: Tenant ID
            
        Returns:
            Health check result
        """
        try:
            if tenant_id not in self.active_bots:
                return {
                    "success": False,
                    "error": "Bot not active",
                    "tenant_id": tenant_id
                }
            
            telegram_service = self.active_bots[tenant_id]
            
            # Test bot connection
            bot_info_result = await telegram_service.get_me()
            if not bot_info_result.get("success"):
                return {
                    "success": False,
                    "error": f"Bot API error: {bot_info_result.get('error')}",
                    "tenant_id": tenant_id
                }
            
            # Check webhook status
            webhook_info_result = await telegram_service.get_webhook_info()
            webhook_status = "unknown"
            if webhook_info_result.get("success"):
                webhook_data = webhook_info_result["result"]
                webhook_status = "active" if webhook_data.get("url") else "inactive"
            
            return {
                "success": True,
                "tenant_id": tenant_id,
                "bot_info": bot_info_result["result"],
                "webhook_status": webhook_status,
                "last_check": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Health check failed for tenant {tenant_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "tenant_id": tenant_id
            }
    
    async def broadcast_message(self, tenant_id: int, message: str, 
                               target_chat_ids: List[str]) -> Dict[str, any]:
        """
        Broadcast message to multiple chats
        
        Args:
            tenant_id: Tenant ID
            message: Message to broadcast
            target_chat_ids: List of chat IDs to send to
            
        Returns:
            Broadcast result
        """
        try:
            if tenant_id not in self.active_bots:
                return {"success": False, "error": "Bot not active"}
            
            telegram_service = self.active_bots[tenant_id]
            
            sent_count = 0
            failed_count = 0
            failed_chats = []
            
            for chat_id in target_chat_ids:
                try:
                    result = await telegram_service.send_message(chat_id, message)
                    if result.get("success"):
                        sent_count += 1
                    else:
                        failed_count += 1
                        failed_chats.append({
                            "chat_id": chat_id,
                            "error": result.get("error")
                        })
                except Exception as e:
                    failed_count += 1
                    failed_chats.append({
                        "chat_id": chat_id,
                        "error": str(e)
                    })
                
                # Small delay to avoid rate limits
                await asyncio.sleep(0.1)
            
            return {
                "success": True,
                "sent_count": sent_count,
                "failed_count": failed_count,
                "failed_chats": failed_chats,
                "total_targets": len(target_chat_ids)
            }
            
        except Exception as e:
            logger.error(f"Broadcast failed for tenant {tenant_id}: {e}")
            return {"success": False, "error": str(e)}

# Global bot manager instance
_telegram_bot_manager: Optional[TelegramBotManager] = None

def get_telegram_bot_manager() -> TelegramBotManager:
    """
    Get the global Telegram bot manager instance
    
    Returns:
        TelegramBotManager instance
    """
    global _telegram_bot_manager
    if _telegram_bot_manager is None:
        _telegram_bot_manager = TelegramBotManager()
    return _telegram_bot_manager