# app/telegram/router.py
"""
Telegram API Router
Handles Telegram webhook endpoints and management APIs
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Header, Request, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional, List
from pydantic import BaseModel
import json

from app.database import get_db
from app.telegram.bot_manager import get_telegram_bot_manager
from app.telegram.models import TelegramIntegration, TelegramChat
from app.telegram.message_handler import TelegramMessageHandler
from app.telegram.service import TelegramService
from app.telegram.utils import TelegramUtils
from app.tenants.router import get_tenant_from_api_key
from app.tenants.models import Tenant
from app.auth.router import get_admin_user
from app.auth.models import User

logger = logging.getLogger(__name__)

router = APIRouter()

# ============ PYDANTIC MODELS ============

class TelegramBotSetupRequest(BaseModel):
    bot_token: str
    welcome_message: Optional[str] = None
    help_message: Optional[str] = None
    enable_groups: bool = False
    enable_typing_indicator: bool = True
    max_messages_per_minute: int = 30

class TelegramBotUpdateRequest(BaseModel):
    welcome_message: Optional[str] = None
    help_message: Optional[str] = None
    enable_groups: Optional[bool] = None
    enable_typing_indicator: Optional[bool] = None
    enable_privacy_mode: Optional[bool] = None
    max_messages_per_minute: Optional[int] = None

class TelegramBroadcastRequest(BaseModel):
    message: str
    target_chat_ids: List[str]

class TelegramTestMessageRequest(BaseModel):
    chat_id: str
    message: str

# ============ WEBHOOK ENDPOINTS ============

@router.post("/webhook/{tenant_id}")
async def telegram_webhook(
    tenant_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    x_telegram_bot_api_secret_token: Optional[str] = Header(None)
):
    """
    Telegram webhook endpoint for receiving updates
    """
    try:
        # Get the raw body
        body = await request.body()
        
        if not body:
            logger.warning(f"Empty webhook body for tenant {tenant_id}")
            raise HTTPException(status_code=400, detail="Empty request body")
        
        # Parse JSON
        try:
            update = json.loads(body)
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON in webhook for tenant {tenant_id}")
            raise HTTPException(status_code=400, detail="Invalid JSON")
        
        # Get Telegram integration
        integration = db.query(TelegramIntegration).filter(
            TelegramIntegration.tenant_id == tenant_id,
            TelegramIntegration.is_active == True
        ).first()
        
        if not integration:
            logger.warning(f"No active Telegram integration found for tenant {tenant_id}")
            raise HTTPException(status_code=404, detail="Integration not found")
        
        # Verify webhook secret token
        if integration.webhook_secret and x_telegram_bot_api_secret_token:
            if x_telegram_bot_api_secret_token != integration.webhook_secret:
                logger.warning(f"Invalid webhook secret for tenant {tenant_id}")
                raise HTTPException(status_code=403, detail="Invalid secret token")
        
        # Validate update format
        if not TelegramService.validate_webhook_request(update):
            logger.warning(f"Invalid webhook update format for tenant {tenant_id}")
            raise HTTPException(status_code=400, detail="Invalid update format")
        
        # Process update in background
        background_tasks.add_task(process_telegram_update, update, integration, db)
        
        # Return success immediately
        return {"ok": True}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"💥 Error in Telegram webhook for tenant {tenant_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

async def process_telegram_update(update: Dict[str, Any], integration: TelegramIntegration, db: Session):
    """
    Background task to process Telegram update
    """
    try:
        handler = TelegramMessageHandler(db)
        success = await handler.process_update(update, integration)
        
        if success:
            logger.info(f"✅ Successfully processed Telegram update for tenant {integration.tenant_id}")
        else:
            logger.error(f"❌ Failed to process Telegram update for tenant {integration.tenant_id}")
            
    except Exception as e:
        logger.error(f"💥 Error processing Telegram update: {str(e)}")

# ============ MANAGEMENT ENDPOINTS ============

@router.post("/setup")
async def setup_telegram_bot(
    request: TelegramBotSetupRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Setup Telegram bot for tenant
    """
    try:
        # Get tenant
        tenant = get_tenant_from_api_key(api_key, db)
        
        # Validate bot token format
        if not TelegramUtils.validate_bot_token(request.bot_token):
            raise HTTPException(status_code=400, detail="Invalid bot token format")
        
        # Test bot token by getting bot info
        telegram_service = TelegramService(request.bot_token)
        bot_info_result = await telegram_service.get_me()
        
        if not bot_info_result.get("success"):
            await telegram_service.close()
            error_msg = bot_info_result.get("error", "Invalid bot token")
            raise HTTPException(status_code=400, detail=f"Bot token validation failed: {error_msg}")
        
        bot_info = bot_info_result["result"]
        await telegram_service.close()
        
        # Check if integration exists
        existing_integration = db.query(TelegramIntegration).filter(
            TelegramIntegration.tenant_id == tenant.id
        ).first()
        
        if existing_integration:
            # Update existing integration
            existing_integration.bot_token = request.bot_token
            existing_integration.bot_username = bot_info.get("username")
            existing_integration.bot_name = bot_info.get("first_name")
            existing_integration.welcome_message = request.welcome_message
            existing_integration.help_message = request.help_message
            existing_integration.enable_groups = request.enable_groups
            existing_integration.enable_typing_indicator = request.enable_typing_indicator
            existing_integration.max_messages_per_minute = request.max_messages_per_minute
            existing_integration.is_active = True
            
            integration = existing_integration
        else:
            # Create new integration
            integration = TelegramIntegration(
                tenant_id=tenant.id,
                bot_token=request.bot_token,
                bot_username=bot_info.get("username"),
                bot_name=bot_info.get("first_name"),
                welcome_message=request.welcome_message,
                help_message=request.help_message,
                enable_groups=request.enable_groups,
                enable_typing_indicator=request.enable_typing_indicator,
                max_messages_per_minute=request.max_messages_per_minute,
                is_active=True
            )
            db.add(integration)
        
        db.commit()
        db.refresh(integration)
        
        # Initialize bot with bot manager
        bot_manager = get_telegram_bot_manager()
        init_result = await bot_manager.add_bot(tenant.id, request.bot_token, db)
        
        if not init_result.get("success"):
            # Rollback integration if bot initialization failed
            integration.is_active = False
            db.commit()
            raise HTTPException(status_code=500, detail=f"Bot initialization failed: {init_result.get('error')}")
        
        logger.info(f"✅ Telegram bot setup completed for tenant {tenant.id}")
        
        return {
            "success": True,
            "message": "Telegram bot setup successfully",
            "bot_info": {
                "username": integration.bot_username,
                "name": integration.bot_name,
                "webhook_url": integration.webhook_url
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"💥 Error setting up Telegram bot: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to setup Telegram bot")

@router.get("/status")
async def get_telegram_status(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Get Telegram integration status for tenant
    """
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        # Get integration
        integration = db.query(TelegramIntegration).filter(
            TelegramIntegration.tenant_id == tenant.id
        ).first()
        
        if not integration:
            return {
                "success": True,
                "configured": False,
                "message": "Telegram bot not configured"
            }
        
        # Get bot manager status
        bot_manager = get_telegram_bot_manager()
        is_active = bot_manager.is_bot_active(tenant.id)
        
        # Get chat statistics
        total_chats = db.query(TelegramChat).filter(
            TelegramChat.tenant_id == tenant.id
        ).count()
        
        active_chats = db.query(TelegramChat).filter(
            TelegramChat.tenant_id == tenant.id,
            TelegramChat.is_active == True
        ).count()
        
        return {
            "success": True,
            "configured": True,
            "active": integration.is_active and is_active,
            "bot_info": {
                "username": integration.bot_username,
                "name": integration.bot_name,
                "webhook_set": integration.is_webhook_set,
                "webhook_url": integration.webhook_url
            },
            "settings": {
                "enable_groups": integration.enable_groups,
                "enable_typing_indicator": integration.enable_typing_indicator,
                "enable_privacy_mode": integration.enable_privacy_mode,
                "max_messages_per_minute": integration.max_messages_per_minute
            },
            "statistics": {
                "total_messages_received": integration.total_messages_received,
                "total_messages_sent": integration.total_messages_sent,
                "total_chats": total_chats,
                "active_chats": active_chats,
                "last_activity": integration.last_webhook_received.isoformat() if integration.last_webhook_received else None,
                "error_count": integration.error_count,
                "last_error": integration.last_error
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting Telegram status: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get status")

@router.put("/settings")
async def update_telegram_settings(
    request: TelegramBotUpdateRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Update Telegram bot settings
    """
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        # Get integration
        integration = db.query(TelegramIntegration).filter(
            TelegramIntegration.tenant_id == tenant.id,
            TelegramIntegration.is_active == True
        ).first()
        
        if not integration:
            raise HTTPException(status_code=404, detail="Telegram bot not configured")
        
        # Update settings
        if request.welcome_message is not None:
            integration.welcome_message = request.welcome_message
        if request.help_message is not None:
            integration.help_message = request.help_message
        if request.enable_groups is not None:
            integration.enable_groups = request.enable_groups
        if request.enable_typing_indicator is not None:
            integration.enable_typing_indicator = request.enable_typing_indicator
        if request.enable_privacy_mode is not None:
            integration.enable_privacy_mode = request.enable_privacy_mode
        if request.max_messages_per_minute is not None:
            integration.max_messages_per_minute = max(1, min(60, request.max_messages_per_minute))
        
        db.commit()
        
        logger.info(f"✅ Updated Telegram settings for tenant {tenant.id}")
        
        return {
            "success": True,
            "message": "Settings updated successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating Telegram settings: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to update settings")

@router.post("/restart")
async def restart_telegram_bot(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Restart Telegram bot for tenant
    """
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        # Check if integration exists
        integration = db.query(TelegramIntegration).filter(
            TelegramIntegration.tenant_id == tenant.id
        ).first()
        
        if not integration:
            raise HTTPException(status_code=404, detail="Telegram bot not configured")
        
        # Restart bot
        bot_manager = get_telegram_bot_manager()
        result = await bot_manager.restart_bot(tenant.id, db)
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=f"Failed to restart bot: {result.get('error')}")
        
        logger.info(f"✅ Restarted Telegram bot for tenant {tenant.id}")
        
        return {
            "success": True,
            "message": "Telegram bot restarted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error restarting Telegram bot: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to restart bot")

@router.delete("/remove")
async def remove_telegram_bot(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Remove Telegram bot for tenant
    """
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        # Remove bot
        bot_manager = get_telegram_bot_manager()
        result = await bot_manager.remove_bot(tenant.id, db)
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=f"Failed to remove bot: {result.get('error')}")
        
        logger.info(f"✅ Removed Telegram bot for tenant {tenant.id}")
        
        return {
            "success": True,
            "message": "Telegram bot removed successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing Telegram bot: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to remove bot")

# ============ CHAT MANAGEMENT ============

@router.get("/chats")
async def get_telegram_chats(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db),
    limit: int = 50,
    active_only: bool = True
):
    """
    Get Telegram chats for tenant
    """
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        query = db.query(TelegramChat).filter(TelegramChat.tenant_id == tenant.id)
        
        if active_only:
            query = query.filter(TelegramChat.is_active == True)
        
        chats = query.order_by(TelegramChat.last_message_at.desc()).limit(limit).all()
        
        chat_data = []
        for chat in chats:
            chat_data.append({
                "chat_id": chat.chat_id,
                "chat_type": chat.chat_type,
                "user_id": chat.user_id,
                "username": chat.username,
                "display_name": chat.display_name,
                "first_name": chat.first_name,
                "last_name": chat.last_name,
                "language_code": chat.language_code,
                "is_active": chat.is_active,
                "total_messages": chat.total_messages,
                "first_message_at": chat.first_message_at.isoformat(),
                "last_message_at": chat.last_message_at.isoformat()
            })
        
        return {
            "success": True,
            "chats": chat_data,
            "total_count": len(chat_data)
        }
        
    except Exception as e:
        logger.error(f"Error getting Telegram chats: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get chats")

# ============ ADMIN ENDPOINTS ============

@router.get("/admin/bots")
async def admin_get_all_telegram_bots(
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
    limit: int = 100
):
    """
    Admin endpoint to get all Telegram bots
    """
    try:
        integrations = db.query(TelegramIntegration).join(Tenant).limit(limit).all()
        
        bot_data = []
        bot_manager = get_telegram_bot_manager()
        
        for integration in integrations:
            is_active = bot_manager.is_bot_active(integration.tenant_id)
            
            bot_data.append({
                "tenant_id": integration.tenant_id,
                "tenant_name": integration.tenant.name,
                "business_name": integration.tenant.business_name,
                "bot_username": integration.bot_username,
                "bot_name": integration.bot_name,
                "is_configured": integration.is_configured(),
                "is_active": integration.is_active and is_active,
                "is_webhook_set": integration.is_webhook_set,
                "webhook_url": integration.webhook_url,
                "total_messages": integration.total_messages_received + integration.total_messages_sent,
                "error_count": integration.error_count,
                "last_activity": max(
                    integration.last_webhook_received or integration.created_at,
                    integration.last_message_sent or integration.created_at
                ).isoformat(),
                "created_at": integration.created_at.isoformat()
            })
        
        return {
            "success": True,
            "bots": bot_data,
            "total_count": len(bot_data),
            "active_count": sum(1 for bot in bot_data if bot["is_active"])
        }
        
    except Exception as e:
        logger.error(f"Error getting all Telegram bots: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get bots")

@router.post("/admin/restart-all")
async def admin_restart_all_telegram_bots(
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    Admin endpoint to restart all Telegram bots
    """
    try:
        bot_manager = get_telegram_bot_manager()
        result = await bot_manager.initialize_bots(db)
        
        return {
            "success": True,
            "message": f"Restarted Telegram bots: {result.get('message')}",
            "details": result
        }
        
    except Exception as e:
        logger.error(f"Error restarting all Telegram bots: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to restart bots")

@router.post("/admin/{tenant_id}/restart")
async def admin_restart_tenant_telegram_bot(
    tenant_id: int,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    Admin endpoint to restart specific tenant's Telegram bot
    """
    try:
        bot_manager = get_telegram_bot_manager()
        result = await bot_manager.restart_bot(tenant_id, db)
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=f"Failed to restart bot: {result.get('error')}")
        
        return {
            "success": True,
            "message": f"Restarted Telegram bot for tenant {tenant_id}",
            "details": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error restarting Telegram bot for tenant {tenant_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to restart bot")

# ============ TESTING ENDPOINTS ============

@router.post("/test/send-message")
async def test_send_telegram_message(
    request: TelegramTestMessageRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Test endpoint to send a message via Telegram bot
    """
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        # Get bot manager
        bot_manager = get_telegram_bot_manager()
        telegram_service = bot_manager.get_bot_service(tenant.id)
        
        if not telegram_service:
            raise HTTPException(status_code=404, detail="Telegram bot not active")
        
        # Send test message
        result = await telegram_service.send_message(
            chat_id=request.chat_id,
            text=request.message,
            parse_mode="Markdown"
        )
        
        if result.get("success"):
            return {
                "success": True,
                "message": "Test message sent successfully",
                "telegram_response": result["result"]
            }
        else:
            raise HTTPException(status_code=500, detail=f"Failed to send message: {result.get('error')}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending test message: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to send test message")

@router.get("/test/webhook-info")
async def test_get_webhook_info(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Test endpoint to get webhook information
    """
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        # Get bot manager
        bot_manager = get_telegram_bot_manager()
        telegram_service = bot_manager.get_bot_service(tenant.id)
        
        if not telegram_service:
            raise HTTPException(status_code=404, detail="Telegram bot not active")
        
        # Get webhook info
        result = await telegram_service.get_webhook_info()
        
        if result.get("success"):
            return {
                "success": True,
                "webhook_info": result["result"]
            }
        else:
            raise HTTPException(status_code=500, detail=f"Failed to get webhook info: {result.get('error')}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting webhook info: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get webhook info")

@router.post("/test/health-check")
async def test_telegram_bot_health(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Test endpoint for bot health check
    """
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        # Get bot manager
        bot_manager = get_telegram_bot_manager()
        result = await bot_manager.health_check(tenant.id)
        
        return result
        
    except Exception as e:
        logger.error(f"Error in health check: {str(e)}")
        raise HTTPException(status_code=500, detail="Health check failed")

# ============ BROADCAST ENDPOINTS ============

@router.post("/broadcast")
async def broadcast_telegram_message(
    request: TelegramBroadcastRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Broadcast message to multiple Telegram chats
    """
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        if not request.target_chat_ids:
            raise HTTPException(status_code=400, detail="No target chat IDs provided")
        
        # Limit broadcast size
        if len(request.target_chat_ids) > 100:
            raise HTTPException(status_code=400, detail="Maximum 100 chat IDs allowed per broadcast")
        
        # Get bot manager
        bot_manager = get_telegram_bot_manager()
        result = await bot_manager.broadcast_message(
            tenant_id=tenant.id,
            message=request.message,
            target_chat_ids=request.target_chat_ids
        )
        
        if result.get("success"):
            return {
                "success": True,
                "message": f"Broadcast completed: {result['sent_count']}/{result['total_targets']} messages sent",
                "details": {
                    "sent_count": result["sent_count"],
                    "failed_count": result["failed_count"],
                    "total_targets": result["total_targets"],
                    "failed_chats": result.get("failed_chats", [])
                }
            }
        else:
            raise HTTPException(status_code=500, detail=f"Broadcast failed: {result.get('error')}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error broadcasting message: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to broadcast message")

# ============ ANALYTICS ENDPOINTS ============

@router.get("/analytics")
async def get_telegram_analytics(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db),
    days: int = 30
):
    """
    Get Telegram analytics for tenant
    """
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        # Get integration
        integration = db.query(TelegramIntegration).filter(
            TelegramIntegration.tenant_id == tenant.id
        ).first()
        
        if not integration:
            return {
                "success": True,
                "configured": False,
                "message": "Telegram bot not configured"
            }
        
        # Calculate date range
        from datetime import datetime, timedelta
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # Get chat statistics
        total_chats = db.query(TelegramChat).filter(
            TelegramChat.tenant_id == tenant.id
        ).count()
        
        new_chats = db.query(TelegramChat).filter(
            TelegramChat.tenant_id == tenant.id,
            TelegramChat.first_message_at >= start_date
        ).count()
        
        active_chats = db.query(TelegramChat).filter(
            TelegramChat.tenant_id == tenant.id,
            TelegramChat.last_message_at >= start_date
        ).count()
        
        # Get message statistics from integration
        return {
            "success": True,
            "configured": True,
            "period_days": days,
            "bot_info": {
                "username": integration.bot_username,
                "name": integration.bot_name,
                "active": integration.is_active
            },
            "message_stats": {
                "total_received": integration.total_messages_received,
                "total_sent": integration.total_messages_sent,
                "total_messages": integration.total_messages_received + integration.total_messages_sent
            },
            "chat_stats": {
                "total_chats": total_chats,
                "new_chats_period": new_chats,
                "active_chats_period": active_chats
            },
            "error_stats": {
                "error_count": integration.error_count,
                "last_error": integration.last_error,
                "last_error_at": integration.last_error_at.isoformat() if integration.last_error_at else None
            },
            "activity": {
                "last_webhook_received": integration.last_webhook_received.isoformat() if integration.last_webhook_received else None,
                "last_message_sent": integration.last_message_sent.isoformat() if integration.last_message_sent else None,
                "created_at": integration.created_at.isoformat()
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting Telegram analytics: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get analytics")

# ============ UTILITY ENDPOINTS ============

@router.get("/validate-token/{bot_token}")
async def validate_telegram_bot_token(
    bot_token: str,
    current_user: User = Depends(get_admin_user)
):
    """
    Admin endpoint to validate a Telegram bot token
    """
    try:
        # Validate token format
        if not TelegramUtils.validate_bot_token(bot_token):
            return {
                "success": False,
                "valid": False,
                "error": "Invalid bot token format"
            }
        
        # Test token by calling getMe
        telegram_service = TelegramService(bot_token)
        result = await telegram_service.get_me()
        await telegram_service.close()
        
        if result.get("success"):
            bot_info = result["result"]
            return {
                "success": True,
                "valid": True,
                "bot_info": {
                    "id": bot_info.get("id"),
                    "username": bot_info.get("username"),
                    "first_name": bot_info.get("first_name"),
                    "is_bot": bot_info.get("is_bot", False),
                    "can_join_groups": bot_info.get("can_join_groups", False),
                    "can_read_all_group_messages": bot_info.get("can_read_all_group_messages", False),
                    "supports_inline_queries": bot_info.get("supports_inline_queries", False)
                }
            }
        else:
            return {
                "success": True,
                "valid": False,
                "error": result.get("error", "Token validation failed")
            }
        
    except Exception as e:
        logger.error(f"Error validating bot token: {str(e)}")
        return {
            "success": False,
            "valid": False,
            "error": str(e)
        }