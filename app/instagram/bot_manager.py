# app/instagram/bot_manager.py
"""
Instagram Bot Manager
Multi-tenant Instagram bot orchestration and management
"""

import logging
import asyncio
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from app.database import SessionLocal
from app.instagram.models import InstagramIntegration, InstagramConversation
from app.instagram.service import InstagramAPIService, InstagramConversationManager
from app.tenants.models import Tenant

logger = logging.getLogger(__name__)

class InstagramBotManager:
    """Manage Instagram bots for all tenants"""
    
    def __init__(self):
        self.active_integrations: Dict[int, InstagramIntegration] = {}
        self.api_services: Dict[int, InstagramAPIService] = {}
        self.conversation_managers: Dict[int, InstagramConversationManager] = {}
        self._running = False
        
    async def initialize_bots(self, db: Session):
        """Initialize all active Instagram bots"""
        try:
            logger.info("🚀 Initializing Instagram bots...")
            
            # Get all active integrations
            integrations = db.query(InstagramIntegration).filter(
                InstagramIntegration.bot_enabled == True,
                InstagramIntegration.bot_status.in_(["active", "setup"])
            ).all()
            
            initialized_count = 0
            error_count = 0
            
            for integration in integrations:
                try:
                    success = await self._initialize_integration(integration, db)
                    if success:
                        initialized_count += 1
                        logger.info(f"✅ Instagram bot initialized for tenant {integration.tenant_id}")
                    else:
                        error_count += 1
                        logger.error(f"❌ Failed to initialize Instagram bot for tenant {integration.tenant_id}")
                        
                except Exception as e:
                    error_count += 1
                    logger.error(f"💥 Error initializing bot for tenant {integration.tenant_id}: {str(e)}")
            
            self._running = True
            logger.info(f"🎉 Instagram bot initialization complete: {initialized_count} successful, {error_count} failed")
            
            # Start monitoring task
            asyncio.create_task(self._monitor_integrations())
            
        except Exception as e:
            logger.error(f"💥 Error during Instagram bot initialization: {str(e)}")
    
    async def _initialize_integration(self, integration: InstagramIntegration, db: Session) -> bool:
        """Initialize a single Instagram integration"""
        try:
            tenant_id = integration.tenant_id
            
            # Test API connection
            api_service = InstagramAPIService(integration, db)
            connection_success, connection_msg = api_service.test_api_connection()
            
            if not connection_success:
                integration.bot_status = "error"
                integration.last_error = f"API connection failed: {connection_msg}"
                integration.error_count += 1
                db.commit()
                return False
            
            # Check token expiration
            if integration.is_token_expired():
                logger.warning(f"🔄 Access token expired for tenant {tenant_id}, attempting refresh...")
                refresh_success = api_service.refresh_access_token()
                
                if not refresh_success:
                    integration.bot_status = "error"
                    integration.last_error = "Failed to refresh access token"
                    integration.error_count += 1
                    db.commit()
                    return False
            
            # Subscribe to webhooks if not already subscribed
            if not integration.webhook_subscribed:
                webhook_success = api_service.subscribe_to_webhooks()
                if not webhook_success:
                    logger.warning(f"⚠️ Webhook subscription failed for tenant {tenant_id}")
                    # Don't fail initialization, as manual webhook setup might be used
            
            # Store services for this integration
            self.active_integrations[tenant_id] = integration
            self.api_services[tenant_id] = api_service
            self.conversation_managers[tenant_id] = InstagramConversationManager(db)
            
            # Update status
            integration.bot_status = "active"
            integration.last_error = None
            integration.error_count = 0
            db.commit()
            
            return True
            
        except Exception as e:
            logger.error(f"Error initializing integration for tenant {integration.tenant_id}: {str(e)}")
            
            integration.bot_status = "error"
            integration.last_error = str(e)
            integration.error_count += 1
            db.commit()
            
            return False
    
    async def add_integration(self, tenant_id: int) -> bool:
        """Add new Instagram integration to manager"""
        try:
            db = SessionLocal()
            
            try:
                integration = db.query(InstagramIntegration).filter(
                    InstagramIntegration.tenant_id == tenant_id,
                    InstagramIntegration.bot_enabled == True
                ).first()
                
                if not integration:
                    logger.warning(f"No active integration found for tenant {tenant_id}")
                    return False
                
                success = await self._initialize_integration(integration, db)
                
                if success:
                    logger.info(f"✅ Added Instagram integration for tenant {tenant_id}")
                else:
                    logger.error(f"❌ Failed to add Instagram integration for tenant {tenant_id}")
                
                return success
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error adding integration for tenant {tenant_id}: {str(e)}")
            return False
    
    def remove_integration(self, tenant_id: int) -> bool:
        """Remove Instagram integration from manager"""
        try:
            if tenant_id in self.active_integrations:
                del self.active_integrations[tenant_id]
            
            if tenant_id in self.api_services:
                del self.api_services[tenant_id]
            
            if tenant_id in self.conversation_managers:
                del self.conversation_managers[tenant_id]
            
            logger.info(f"🗑️ Removed Instagram integration for tenant {tenant_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error removing integration for tenant {tenant_id}: {str(e)}")
            return False
    
    def get_integration_status(self, tenant_id: int) -> Optional[Dict[str, Any]]:
        """Get status of Instagram integration"""
        try:
            if tenant_id not in self.active_integrations:
                return None
            
            integration = self.active_integrations[tenant_id]
            
            return {
                "tenant_id": tenant_id,
                "bot_enabled": integration.bot_enabled,
                "bot_status": integration.bot_status,
                "webhook_subscribed": integration.webhook_subscribed,
                "instagram_username": integration.instagram_username,
                "last_message_at": integration.last_message_at.isoformat() if integration.last_message_at else None,
                "error_count": integration.error_count,
                "last_error": integration.last_error,
                "token_expires_at": integration.token_expires_at.isoformat() if integration.token_expires_at else None,
                "is_token_expired": integration.is_token_expired()
            }
            
        except Exception as e:
            logger.error(f"Error getting integration status for tenant {tenant_id}: {str(e)}")
            return None
    
    def get_all_integrations_status(self) -> List[Dict[str, Any]]:
        """Get status of all active integrations"""
        statuses = []
        
        for tenant_id in self.active_integrations.keys():
            status = self.get_integration_status(tenant_id)
            if status:
                statuses.append(status)
        
        return statuses
    
    async def process_incoming_message(self, tenant_id: int, conversation: InstagramConversation, 
                                     message: 'InstagramMessage') -> bool:
        """Process incoming message for a specific tenant"""
        try:
            if tenant_id not in self.conversation_managers:
                logger.error(f"No conversation manager found for tenant {tenant_id}")
                return False
            
            conversation_manager = self.conversation_managers[tenant_id]
            
            # Process with chatbot engine
            response = conversation_manager.process_incoming_message(conversation, message)
            
            if response:
                logger.info(f"✅ Processed Instagram message for tenant {tenant_id}")
                return True
            else:
                logger.error(f"❌ Failed to process Instagram message for tenant {tenant_id}")
                return False
                
        except Exception as e:
            logger.error(f"💥 Error processing message for tenant {tenant_id}: {str(e)}")
            return False
    
    async def send_message(self, tenant_id: int, instagram_user_id: str, 
                          message_content: str, message_type: str = "text") -> bool:
        """Send message via Instagram API"""
        try:
            if tenant_id not in self.api_services:
                logger.error(f"No API service found for tenant {tenant_id}")
                return False
            
            api_service = self.api_services[tenant_id]
            success, message_id = api_service.send_message(
                instagram_user_id, message_content, message_type
            )
            
            if success:
                logger.info(f"✅ Sent Instagram message for tenant {tenant_id}: {message_id}")
            else:
                logger.error(f"❌ Failed to send Instagram message for tenant {tenant_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"💥 Error sending message for tenant {tenant_id}: {str(e)}")
            return False
    
    async def _monitor_integrations(self):
        """Monitor integration health and perform maintenance"""
        while self._running:
            try:
                await asyncio.sleep(300)  # Check every 5 minutes
                
                db = SessionLocal()
                try:
                    # Check for token expirations
                    await self._check_token_expirations(db)
                    
                    # Check for new integrations
                    await self._check_new_integrations(db)
                    
                    # Health check for existing integrations
                    await self._health_check_integrations(db)
                    
                finally:
                    db.close()
                    
            except Exception as e:
                logger.error(f"Error in Instagram monitoring task: {str(e)}")
    
    async def _check_token_expirations(self, db: Session):
        """Check for token expirations and refresh if needed"""
        try:
            # Check tokens expiring in the next 24 hours
            expiry_threshold = datetime.utcnow() + timedelta(hours=24)
            
            expiring_integrations = db.query(InstagramIntegration).filter(
                InstagramIntegration.tenant_id.in_(self.active_integrations.keys()),
                InstagramIntegration.token_expires_at <= expiry_threshold,
                InstagramIntegration.bot_enabled == True
            ).all()
            
            for integration in expiring_integrations:
                tenant_id = integration.tenant_id
                
                if tenant_id in self.api_services:
                    logger.info(f"🔄 Refreshing token for tenant {tenant_id}")
                    
                    api_service = self.api_services[tenant_id]
                    success = api_service.refresh_access_token()
                    
                    if success:
                        logger.info(f"✅ Token refreshed for tenant {tenant_id}")
                    else:
                        logger.error(f"❌ Token refresh failed for tenant {tenant_id}")
                        integration.bot_status = "error"
                        integration.last_error = "Token refresh failed"
                        db.commit()
            
        except Exception as e:
            logger.error(f"Error checking token expirations: {str(e)}")
    
    async def _check_new_integrations(self, db: Session):
        """Check for new integrations to add"""
        try:
            new_integrations = db.query(InstagramIntegration).filter(
                InstagramIntegration.bot_enabled == True,
                InstagramIntegration.bot_status == "setup",
                ~InstagramIntegration.tenant_id.in_(self.active_integrations.keys())
            ).all()
            
            for integration in new_integrations:
                logger.info(f"🆕 Found new Instagram integration for tenant {integration.tenant_id}")
                await self._initialize_integration(integration, db)
                
        except Exception as e:
            logger.error(f"Error checking new integrations: {str(e)}")
    
    async def _health_check_integrations(self, db: Session):
        """Perform health checks on active integrations"""
        try:
            for tenant_id, api_service in self.api_services.items():
                try:
                    success, message = api_service.test_api_connection()
                    
                    integration = self.active_integrations[tenant_id]
                    
                    if success:
                        if integration.bot_status == "error":
                            integration.bot_status = "active"
                            integration.last_error = None
                            integration.error_count = 0
                            logger.info(f"✅ Health check recovered for tenant {tenant_id}")
                    else:
                        integration.bot_status = "error"
                        integration.last_error = f"Health check failed: {message}"
                        integration.error_count += 1
                        logger.error(f"❌ Health check failed for tenant {tenant_id}: {message}")
                
                except Exception as e:
                    logger.error(f"Health check error for tenant {tenant_id}: {str(e)}")
            
            db.commit()
            
        except Exception as e:
            logger.error(f"Error in health check: {str(e)}")
    
    async def stop_all_bots(self):
        """Stop all Instagram bots"""
        try:
            self._running = False
            
            # Clear all active integrations
            self.active_integrations.clear()
            self.api_services.clear()
            self.conversation_managers.clear()
            
            logger.info("🛑 All Instagram bots stopped")
            
        except Exception as e:
            logger.error(f"Error stopping Instagram bots: {str(e)}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get manager statistics"""
        active_count = len(self.active_integrations)
        
        # Get status breakdown
        status_counts = {}
        for integration in self.active_integrations.values():
            status = integration.bot_status
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return {
            "total_active_integrations": active_count,
            "status_breakdown": status_counts,
            "is_running": self._running,
            "manager_uptime": "Active" if self._running else "Stopped"
        }


# Global instance
_instagram_bot_manager = None

def get_instagram_bot_manager() -> InstagramBotManager:
    """Get global Instagram bot manager instance"""
    global _instagram_bot_manager
    if _instagram_bot_manager is None:
        _instagram_bot_manager = InstagramBotManager()
    return _instagram_bot_manager