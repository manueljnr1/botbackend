# app/slack/router.py
"""
FastAPI Router for Slack Integration
Handles Slack webhook events and management endpoints
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import List, Optional

# Define ThreadAnalyticsResponse if not already defined elsewhere


from pydantic import BaseModel
import hmac
import hashlib
import time
import json

from app.database import get_db
from app.tenants.models import Tenant
from app.tenants.router import get_tenant_from_api_key, get_current_tenant
from app.slack.bot_manager import get_slack_bot_manager
from app.auth.models import User
from app.auth.router import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

# Pydantic models
class SlackConfig(BaseModel):
    bot_token: str
    signing_secret: str
    app_id: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    enabled: bool = True

class SlackConfigUpdate(BaseModel):
    bot_token: Optional[str] = None
    signing_secret: Optional[str] = None
    app_id: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    enabled: Optional[bool] = None

class SlackTestMessage(BaseModel):
    channel: str
    message: str
    thread_ts: Optional[str] = None

class SlackChannelResponse(BaseModel):
    id: str
    name: str
    is_channel: bool
    is_private: bool
    is_member: bool

class SlackStatusResponse(BaseModel):
    status: str
    message: Optional[str] = None
    bot_name: Optional[str] = None
    team_name: Optional[str] = None
    bot_id: Optional[str] = None
    team_id: Optional[str] = None

class ThreadAnalyticsResponse(BaseModel):
    thread_id: str
    analytics: dict



def verify_slack_signature(request_body: bytes, timestamp: str, signature: str, signing_secret: str) -> bool:
    """Verify Slack request signature"""
    try:
        # Create the signature base string
        sig_basestring = f"v0:{timestamp}:{request_body.decode('utf-8')}"
        
        # Create the signature
        my_signature = 'v0=' + hmac.new(
            signing_secret.encode('utf-8'),
            sig_basestring.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Compare signatures
        return hmac.compare_digest(my_signature, signature)
    except Exception as e:
        logger.error(f"Error verifying Slack signature: {e}")
        return False




@router.post("/events")
async def handle_slack_events(request: Request):
    """
    General Slack events endpoint for challenge verification and routing
    """
    try:
        body = await request.body()
        data = json.loads(body)
        
        # Handle URL verification challenge FIRST
        if data.get("type") == "url_verification":
            challenge = data.get("challenge")
            logger.info(f"✅ Slack URL verification challenge: {challenge}")
            return challenge  # Return string directly
        
        # For actual events, you could route to tenant-specific handlers
        # or handle them here directly
        logger.info(f"📢 Received Slack event: {data.get('type')}")
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Error in Slack events endpoint: {e}")
        return {"status": "ok"}


# SINGLE WEBHOOK HANDLER - REMOVED DUPLICATE
@router.post("/webhook/{tenant_id}")
async def slack_webhook(
    tenant_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Slack webhook endpoint for a specific tenant - ENHANCED DEBUG VERSION
    """
    try:
        # Get request details
        body = await request.body()
        headers = request.headers
        
        logger.info(f"📨 Received Slack webhook for tenant {tenant_id}")
        
        # DEBUG: Check all tenants first
        all_tenants = db.query(Tenant).all()
        logger.info(f"🔍 DEBUG: Found {len(all_tenants)} total tenants in database")
        
        for tenant in all_tenants:
            logger.info(f"   Tenant {tenant.id}: name={tenant.name}, active={tenant.is_active}, slack_enabled={getattr(tenant, 'slack_enabled', 'MISSING')}")
        
        # Get specific tenant with detailed logging
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        
        if not tenant:
            logger.error(f"❌ Tenant {tenant_id} does not exist in database at all!")
            raise HTTPException(status_code=404, detail=f"Tenant {tenant_id} not found")
        
        logger.info(f"✅ Found tenant {tenant_id}: name={tenant.name}")
        
        # Check if tenant is active
        if not tenant.is_active:
            logger.error(f"❌ Tenant {tenant_id} exists but is INACTIVE")
            raise HTTPException(status_code=404, detail=f"Tenant {tenant_id} is inactive")
        
        logger.info(f"✅ Tenant {tenant_id} is active")
        
        # Check if Slack is enabled
        slack_enabled = getattr(tenant, 'slack_enabled', None)
        if slack_enabled is None:
            logger.error(f"❌ Tenant {tenant_id} has NO slack_enabled field - run migration!")
            raise HTTPException(status_code=500, detail="Slack fields missing - run migration")
        
        if not slack_enabled:
            logger.error(f"❌ Tenant {tenant_id} has Slack DISABLED (slack_enabled={slack_enabled})")
            
            # DEBUG: Show all Slack fields
            logger.info(f"🔍 DEBUG Slack fields for tenant {tenant_id}:")
            logger.info(f"   slack_enabled: {getattr(tenant, 'slack_enabled', 'MISSING')}")
            logger.info(f"   slack_bot_token: {'SET' if getattr(tenant, 'slack_bot_token', None) else 'MISSING'}")
            logger.info(f"   slack_signing_secret: {'SET' if getattr(tenant, 'slack_signing_secret', None) else 'MISSING'}")
            
            raise HTTPException(status_code=404, detail=f"Slack not enabled for tenant {tenant_id}")
        
        logger.info(f"✅ Tenant {tenant_id} has Slack ENABLED")
        
        # Parse request
        try:
            payload = json.loads(body.decode('utf-8'))
        except json.JSONDecodeError:
            logger.error("❌ Failed to parse JSON from Slack webhook")
            raise HTTPException(status_code=400, detail="Invalid JSON")
        
        # Handle URL verification challenge
        if payload.get("type") == "url_verification":
            challenge = payload.get("challenge")
            logger.info(f"✅ Slack URL verification challenge: {challenge}")
            return {"challenge": challenge}
        
        # Handle other events
        if payload.get("type") == "event_callback":
            event = payload.get("event", {})
            event_type = event.get("type")
            logger.info(f"📢 Received Slack event: {event_type}")
            
            # Get bot manager and handler for event processing
            bot_manager = get_slack_bot_manager()
            handler = bot_manager.get_handler(tenant_id)
            
            if not handler:
                logger.info(f"🔧 Initializing Slack bot for tenant {tenant_id}")
                await bot_manager.create_bot_for_tenant(tenant, db)
                handler = bot_manager.get_handler(tenant_id)
                
                if not handler:
                    logger.error(f"❌ Failed to initialize Slack bot for tenant {tenant_id}")
                    return JSONResponse(content={"status": "ok"})
            
            # Process the request
            try:
                response = await handler.handle(request)
                logger.info(f"✅ Slack event processed successfully for tenant {tenant_id}")
                return response if response else JSONResponse(content={"status": "ok"})
            except Exception as e:
                logger.error(f"❌ Error processing Slack event: {e}")
                return JSONResponse(content={"status": "ok"})
        
        # Return OK for any other event types
        logger.info(f"📝 Unhandled Slack event type: {payload.get('type', 'unknown')}")
        return JSONResponse(content={"status": "ok"})
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"💥 Error in Slack webhook for tenant {tenant_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        # Still return OK to Slack to prevent retries
        return JSONResponse(content={"status": "ok"})

@router.post("/config")
async def configure_slack(
    config: SlackConfig,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Configure Slack integration for a tenant"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        logger.info(f"Configuring Slack for tenant {tenant.id}")
        
        tenant.slack_bot_token = config.bot_token
        tenant.slack_signing_secret = config.signing_secret
        tenant.slack_app_id = config.app_id
        tenant.slack_client_id = config.client_id
        tenant.slack_client_secret = config.client_secret
        tenant.slack_enabled = config.enabled
        
        db.commit()
        logger.info(f"✅ Slack configured for tenant {tenant.id}")
        
        # Update bot manager
        bot_manager = get_slack_bot_manager()
        await bot_manager.update_bot_for_tenant(tenant, db)
        
        return {
            "success": True,
            "message": "Slack configuration updated successfully",
            "webhook_url": f"/api/slack/webhook/{tenant.id}",
            "enabled": tenant.slack_enabled
        }
        
    except Exception as e:
        logger.error(f"Error configuring Slack: {e}")
        raise HTTPException(status_code=500, detail="Failed to configure Slack")

@router.get("/config")
async def get_slack_config(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get current Slack configuration for a tenant"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        return {
            "enabled": tenant.slack_enabled or False,
            "app_id": tenant.slack_app_id,
            "client_id": tenant.slack_client_id,
            "has_bot_token": bool(tenant.slack_bot_token),
            "has_signing_secret": bool(tenant.slack_signing_secret),
            "webhook_url": f"/api/slack/webhook/{tenant.id}"
        }
        
    except Exception as e:
        logger.error(f"Error getting Slack config: {e}")
        raise HTTPException(status_code=500, detail="Failed to get Slack configuration")

@router.put("/config")
async def update_slack_config(
    config: SlackConfigUpdate,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Update Slack configuration for a tenant"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        # Update only provided fields
        if config.bot_token is not None:
            tenant.slack_bot_token = config.bot_token
        if config.signing_secret is not None:
            tenant.slack_signing_secret = config.signing_secret
        if config.app_id is not None:
            tenant.slack_app_id = config.app_id
        if config.client_id is not None:
            tenant.slack_client_id = config.client_id
        if config.client_secret is not None:
            tenant.slack_client_secret = config.client_secret
        if config.enabled is not None:
            tenant.slack_enabled = config.enabled
        
        db.commit()
        
        # Update bot manager
        bot_manager = get_slack_bot_manager()
        await bot_manager.update_bot_for_tenant(tenant, db)
        
        return {
            "success": True,
            "message": "Slack configuration updated successfully",
            "enabled": tenant.slack_enabled
        }
        
    except Exception as e:
        logger.error(f"Error updating Slack config: {e}")
        raise HTTPException(status_code=500, detail="Failed to update Slack configuration")

@router.get("/status", response_model=SlackStatusResponse)
async def get_slack_status(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get Slack bot status for a tenant"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        bot_manager = get_slack_bot_manager()
        status_info = await bot_manager.get_bot_status(tenant.id)
        
        return SlackStatusResponse(**status_info)
        
    except Exception as e:
        logger.error(f"Error getting Slack status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get Slack status")

@router.get("/channels", response_model=List[SlackChannelResponse])
async def get_slack_channels(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get list of Slack channels the bot can access"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        bot_manager = get_slack_bot_manager()
        channels = await bot_manager.get_channels(tenant.id)
        
        return [SlackChannelResponse(**channel) for channel in channels]
        
    except Exception as e:
        logger.error(f"Error getting Slack channels: {e}")
        raise HTTPException(status_code=500, detail="Failed to get Slack channels")

@router.post("/test-message")
async def send_test_message(
    message_data: SlackTestMessage,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Send a test message to a Slack channel"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        bot_manager = get_slack_bot_manager()
        success = await bot_manager.send_message(
            tenant_id=tenant.id,
            channel=message_data.channel,
            text=message_data.message,
            thread_ts=message_data.thread_ts
        )
        
        if success:
            return {
                "success": True,
                "message": "Test message sent successfully"
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to send test message")
        
    except Exception as e:
        logger.error(f"Error sending test message: {e}")
        raise HTTPException(status_code=500, detail="Failed to send test message")

@router.post("/disable")
async def disable_slack(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Disable Slack integration for a tenant"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        tenant.slack_enabled = False
        db.commit()
        
        # Update bot manager
        bot_manager = get_slack_bot_manager()
        await bot_manager.update_bot_for_tenant(tenant, db)
        
        return {
            "success": True,
            "message": "Slack integration disabled successfully"
        }
        
    except Exception as e:
        logger.error(f"Error disabling Slack: {e}")
        raise HTTPException(status_code=500, detail="Failed to disable Slack integration")

@router.get("/webhook-info")
async def get_webhook_info(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get webhook information for Slack app configuration"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        # In production, you'd use your actual domain
        base_url = "https://your-domain.com"  # Replace with actual domain
        webhook_url = f"{base_url}/api/slack/webhook/{tenant.id}"
        
        return {
            "webhook_url": webhook_url,
            "tenant_id": tenant.id,
            "events_to_subscribe": [
                "message.channels",
                "message.groups",
                "message.im",
                "message.mpim",
                "app_mention"
            ],
            "oauth_scopes": [
                "chat:write",
                "channels:read",
                "groups:read",
                "im:read",
                "mpim:read",
                "users:read",
                "team:read"
            ]
        }
        
    except Exception as e:
        logger.error(f"Error getting webhook info: {e}")
        raise HTTPException(status_code=500, detail="Failed to get webhook information")

# Get the bot manager instance for use in main.py
def get_bot_manager():
    """Get the Slack bot manager instance"""
    return get_slack_bot_manager()


@router.get("/threads/analytics", response_model=ThreadAnalyticsResponse)
async def get_thread_analytics(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get thread analytics for a tenant"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        bot_manager = get_slack_bot_manager()
        result = await bot_manager.get_thread_analytics(tenant.id)
        
        if result.get("success"):
            analytics = result["thread_analytics"]
            return ThreadAnalyticsResponse(**analytics)
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to get analytics"))
        
    except Exception as e:
        logger.error(f"Error getting thread analytics: {e}")
        raise HTTPException(status_code=500, detail="Failed to get thread analytics")

@router.get("/threads/history/{channel_id}")
async def get_thread_history(
    channel_id: str,
    user_id: Optional[str] = None,
    thread_ts: Optional[str] = None,
    max_messages: int = 20,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get conversation history for a specific thread or channel"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        # Get thread manager
        bot_manager = get_slack_bot_manager()
        thread_manager = bot_manager.get_thread_manager(tenant.id)
        
        if not thread_manager:
            raise HTTPException(status_code=404, detail="Thread manager not found")
        
        if user_id:
            # Get specific user's thread history
            history = thread_manager.get_thread_conversation_history(
                channel_id=channel_id,
                user_id=user_id,
                thread_ts=thread_ts,
                max_messages=max_messages
            )
        else:
            # Get general channel statistics
            channel_context = thread_manager.get_channel_context(channel_id)
            if not channel_context:
                raise HTTPException(status_code=404, detail="Channel not found")
            
            return {
                "channel_id": channel_id,
                "channel_name": channel_context.channel_name,
                "channel_type": channel_context.channel_type,
                "topic": channel_context.topic,
                "message_count": len(history) if 'history' in locals() else 0
            }
        
        return {
            "channel_id": channel_id,
            "user_id": user_id,
            "thread_ts": thread_ts,
            "message_count": len(history),
            "messages": history
        }
        
    except Exception as e:
        logger.error(f"Error getting thread history: {e}")
        raise HTTPException(status_code=500, detail="Failed to get thread history")

@router.get("/channels/context")
async def get_all_channels_context(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get context information for all channels"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        # Query all channel contexts
        from app.slack.thread_memory import SlackChannelContext
        
        channels = db.query(SlackChannelContext).filter(
            SlackChannelContext.tenant_id == tenant.id
        ).all()
        
        channel_contexts = []
        for channel in channels:
            channel_contexts.append({
                "channel_id": channel.channel_id,
                "channel_name": channel.channel_name,
                "channel_type": channel.channel_type,
                "topic": channel.channel_topic,
                "personality": channel.channel_personality,
                "total_messages": channel.total_messages,
                "active_threads": channel.active_threads,
                "last_activity": channel.last_activity.isoformat() if channel.last_activity else None
            })
        
        return {
            "tenant_id": tenant.id,
            "total_channels": len(channel_contexts),
            "channels": channel_contexts
        }
        
    except Exception as e:
        logger.error(f"Error getting channels context: {e}")
        raise HTTPException(status_code=500, detail="Failed to get channels context")

@router.put("/channels/{channel_id}/personality")
async def update_channel_personality(
    channel_id: str,
    personality: str,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Update personality/tone for a specific channel"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        bot_manager = get_slack_bot_manager()
        thread_manager = bot_manager.get_thread_manager(tenant.id)
        
        if not thread_manager:
            raise HTTPException(status_code=404, detail="Thread manager not found")
        
        # Update channel context with new personality
        from app.slack.thread_memory import SlackChannelContext
        
        channel_context = db.query(SlackChannelContext).filter(
            SlackChannelContext.tenant_id == tenant.id,
            SlackChannelContext.channel_id == channel_id
        ).first()
        
        if channel_context:
            channel_context.channel_personality = personality
            db.commit()
        else:
            # Create new channel context
            new_context = SlackChannelContext(
                tenant_id=tenant.id,
                channel_id=channel_id,
                channel_personality=personality
            )
            db.add(new_context)
            db.commit()
        
        # Clear cache to force reload
        if hasattr(thread_manager, 'channel_cache') and channel_id in thread_manager.channel_cache:
            del thread_manager.channel_cache[channel_id]
        
        return {
            "success": True,
            "message": f"Updated personality for channel {channel_id}",
            "channel_id": channel_id,
            "personality": personality
        }
        
    except Exception as e:
        logger.error(f"Error updating channel personality: {e}")
        raise HTTPException(status_code=500, detail="Failed to update channel personality")

@router.post("/threads/cleanup")
async def cleanup_old_threads(
    days_old: int = 30,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Manually trigger cleanup of old thread memories"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        bot_manager = get_slack_bot_manager()
        thread_manager = bot_manager.get_thread_manager(tenant.id)
        
        if not thread_manager:
            raise HTTPException(status_code=404, detail="Thread manager not found")
        
        cleaned_count = thread_manager.cleanup_old_threads(days_old=days_old)
        
        return {
            "success": True,
            "message": f"Cleaned up {cleaned_count} old threads",
            "cleaned_threads": cleaned_count,
            "days_old": days_old
        }
        
    except Exception as e:
        logger.error(f"Error cleaning up threads: {e}")
        raise HTTPException(status_code=500, detail="Failed to cleanup threads")

@router.get("/threads/user-preferences/{user_id}")
async def get_user_preferences(
    user_id: str,
    channel_id: str,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get user preferences across all threads in a channel"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        bot_manager = get_slack_bot_manager()
        thread_manager = bot_manager.get_thread_manager(tenant.id)
        
        if not thread_manager:
            raise HTTPException(status_code=404, detail="Thread manager not found")
        
        preferences = thread_manager.get_user_preferences(user_id, channel_id)
        
        return {
            "user_id": user_id,
            "channel_id": channel_id,
            "preferences": preferences,
            "preferences_count": len(preferences)
        }
        
    except Exception as e:
        logger.error(f"Error getting user preferences: {e}")
        raise HTTPException(status_code=500, detail="Failed to get user preferences")

@router.post("/threads/{channel_id}/summary")
async def update_thread_summary(
    channel_id: str,
    summary: str,
    user_id: str,
    thread_ts: Optional[str] = None,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Update AI-generated summary for a thread"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        bot_manager = get_slack_bot_manager()
        thread_manager = bot_manager.get_thread_manager(tenant.id)
        
        if not thread_manager:
            raise HTTPException(status_code=404, detail="Thread manager not found")
        
        success = thread_manager.update_topic_summary(
            channel_id=channel_id,
            user_id=user_id,
            summary=summary,
            thread_ts=thread_ts
        )
        
        if success:
            return {
                "success": True,
                "message": "Thread summary updated successfully",
                "channel_id": channel_id,
                "thread_ts": thread_ts,
                "summary": summary
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to update thread summary")
        
    except Exception as e:
        logger.error(f"Error updating thread summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to update thread summary")