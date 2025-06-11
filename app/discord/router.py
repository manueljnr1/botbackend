# Fixed app/discord/router.py

from fastapi import APIRouter, Depends, HTTPException, Header, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
from pydantic import BaseModel
import logging
import asyncio
import math
import json

from app.database import get_db, SessionLocal
from app.tenants.models import Tenant
from app.discord.discord_bot import DiscordBotManager

# 🔥 PRICING INTEGRATION - ADD THESE IMPORTS
from app.pricing.integration_helpers import (
    check_feature_access_dependency, 
    check_integration_limit_dependency,
    track_integration_added,
    track_integration_removed
)
from app.tenants.router import get_tenant_from_api_key

logger = logging.getLogger(__name__)
router = APIRouter()

# Global bot manager instance
bot_manager: Optional[DiscordBotManager] = None

def get_bot_manager():
    """Get or create the bot manager instance"""
    global bot_manager
    if bot_manager is None:
        # Create session factory function
        def session_factory():
            return SessionLocal()
        
        bot_manager = DiscordBotManager(db_session_factory=session_factory)
    return bot_manager

# Pydantic models
class DiscordConfig(BaseModel):
    bot_token: str
    application_id: str
    enabled: bool = True
    status_message: Optional[str] = "Chatting with customers"

class BotStatusResponse(BaseModel):
    tenant_id: int
    running: bool
    connected: bool
    guilds: int
    latency: Optional[float]
    features: list
    metrics: Dict[str, int]

# 🔥 MODIFIED WITH PRICING CHECKS
@router.post("/configure")
async def configure_discord_bot(
    config: DiscordConfig,
    background_tasks: BackgroundTasks,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Configure Discord bot for a tenant"""
    
    # Get tenant
    tenant = get_tenant_from_api_key(api_key, db)
    
    # 🔒 PRICING CHECK - Can tenant use Discord?
    check_feature_access_dependency(tenant.id, "discord", db)
    
    # 🔒 PRICING CHECK - Can tenant add integrations? (only if enabling)
    if config.enabled and not getattr(tenant, 'discord_enabled', False):
        # This is a new integration being added
        check_integration_limit_dependency(tenant.id, db)
    
    # Update tenant Discord configuration
    was_enabled = getattr(tenant, 'discord_enabled', False)
    tenant.discord_bot_token = config.bot_token
    tenant.discord_application_id = config.application_id
    tenant.discord_enabled = config.enabled
    tenant.discord_status_message = config.status_message
    
    db.commit()
    
    # 📊 PRICING TRACK - Track integration changes
    if config.enabled and not was_enabled:
        # New integration added
        track_integration_added(tenant.id, db, "discord")
    elif not config.enabled and was_enabled:
        # Integration removed
        track_integration_removed(tenant.id, db, "discord")
    
    # Start/restart bot in background with longer delay for rate limiting
    if config.enabled:
        background_tasks.add_task(restart_bot_for_tenant, tenant.id)
    else:
        background_tasks.add_task(stop_bot_for_tenant, tenant.id)
    
    return {"message": "Discord configuration updated successfully"}

# 🔥 MODIFIED WITH PRICING CHECKS
@router.post("/start")
async def start_discord_bot(
    background_tasks: BackgroundTasks,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Start Discord bot for a tenant"""
    
    tenant = get_tenant_from_api_key(api_key, db)
    
    # 🔒 PRICING CHECK - Can tenant use Discord?
    check_feature_access_dependency(tenant.id, "discord", db)
    
    if not getattr(tenant, 'discord_bot_token', None):
        raise HTTPException(status_code=400, detail="Discord bot not configured")
    
    background_tasks.add_task(start_bot_for_tenant, tenant.id)
    
    return {"message": "Discord bot start initiated"}

@router.post("/stop")
async def stop_discord_bot(
    background_tasks: BackgroundTasks,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Stop Discord bot for a tenant"""
    
    tenant = get_tenant_from_api_key(api_key, db)
    
    background_tasks.add_task(stop_bot_for_tenant, tenant.id)
    
    return {"message": "Discord bot stop initiated"}

@router.get("/status")
async def get_discord_bot_status(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get Discord bot status for a tenant"""
    
    # Get tenant
    tenant = get_tenant_from_api_key(api_key, db)
    
    # Default safe response
    safe_response = {
        "tenant_id": tenant.id,
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
    
    try:
        manager = get_bot_manager()
        if manager is None:
            return safe_response
        
        status = manager.get_bot_status(tenant.id)
        
        # Safely extract values
        safe_response["running"] = bool(status.get("running", False))
        safe_response["connected"] = bool(status.get("connected", False))
        safe_response["guilds"] = int(status.get("guilds", 0))
        safe_response["features"] = status.get("features", ["rate_limiting", "simple_memory", "human_delays"])
        safe_response["metrics"] = status.get("metrics", safe_response["metrics"])
        
        # Handle latency safely
        latency = status.get("latency")
        if latency is not None:
            try:
                latency_num = float(latency)
                # Check for invalid values
                if not (math.isinf(latency_num) or math.isnan(latency_num)):
                    if 0 <= latency_num <= 30000:  # Reasonable range
                        safe_response["latency"] = round(latency_num, 2)
            except (ValueError, TypeError, OverflowError):
                pass  # Keep latency as None
        
        return safe_response
        
    except Exception as e:
        logger.error(f"Error in status endpoint: {e}", exc_info=True)
        return safe_response

@router.get("/metrics/{tenant_id}")
async def get_discord_bot_metrics(
    tenant_id: int,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get detailed metrics for Discord bot"""
    
    # Get tenant and verify access
    tenant = get_tenant_from_api_key(api_key, db)
    if tenant.id != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    try:
        manager = get_bot_manager()
        if manager is None or tenant_id not in manager.active_bots:
            return {
                "tenant_id": tenant_id,
                "metrics": {
                    "messages_processed": 0,
                    "rate_limit_hits": 0,
                    "api_errors": 0,
                    "last_rate_limit": None
                }
            }
        
        bot = manager.active_bots[tenant_id]
        metrics = bot.metrics
        
        return {
            "tenant_id": tenant_id,
            "metrics": {
                "messages_processed": metrics.messages_processed,
                "rate_limit_hits": metrics.rate_limit_hits,
                "api_errors": metrics.api_errors,
                "last_rate_limit": metrics.last_rate_limit
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error retrieving metrics")

# Background task functions - Fixed to handle async properly with longer delays
async def start_bot_for_tenant(tenant_id: int):
    """Background task to start bot for tenant"""
    try:
        # Add delay to help with rate limiting
        await asyncio.sleep(2)
        
        manager = get_bot_manager()
        success = await manager.start_tenant_bot(tenant_id)
        logger.info(f"Bot start for tenant {tenant_id}: {'success' if success else 'failed'}")
    except Exception as e:
        logger.error(f"Error starting bot for tenant {tenant_id}: {e}", exc_info=True)

async def stop_bot_for_tenant(tenant_id: int):
    """Background task to stop bot for tenant"""
    try:
        manager = get_bot_manager()
        success = await manager.stop_tenant_bot(tenant_id)
        logger.info(f"Bot stop for tenant {tenant_id}: {'success' if success else 'failed'}")
    except Exception as e:
        logger.error(f"Error stopping bot for tenant {tenant_id}: {e}", exc_info=True)

async def restart_bot_for_tenant(tenant_id: int):
    """Background task to restart bot for tenant"""
    try:
        # Add longer delay for restarts to help with rate limiting
        await asyncio.sleep(5)
        
        manager = get_bot_manager()
        success = await manager.restart_tenant_bot(tenant_id)
        logger.info(f"Bot restart for tenant {tenant_id}: {'success' if success else 'failed'}")
    except Exception as e:
        logger.error(f"Error restarting bot for tenant {tenant_id}: {e}", exc_info=True)

# Add CORS support for local testing
@router.options("/{path:path}")
async def options_handler():
    """Handle OPTIONS requests for CORS"""
    return {"message": "OK"}

# Add health check endpoint
@router.get("/health")
async def discord_health_check():
    """Health check for Discord integration"""
    try:
        manager = get_bot_manager()
        
        total_bots = len(manager.active_bots)
        running_bots = sum(1 for bot in manager.active_bots.values() if bot.is_running)
        
        # Calculate total metrics across all bots
        total_messages = sum(bot.metrics.messages_processed for bot in manager.active_bots.values())
        total_rate_limits = sum(bot.metrics.rate_limit_hits for bot in manager.active_bots.values())
        total_errors = sum(bot.metrics.api_errors for bot in manager.active_bots.values())
        
        status = "healthy"
        if total_rate_limits > 0:
            status = "warning"
        if running_bots < total_bots and total_bots > 0:
            status = "degraded"
        
        return {
            "status": status,
            "total_bots": total_bots,
            "running_bots": running_bots,
            "manager_initialized": bot_manager is not None,
            "aggregate_metrics": {
                "total_messages_processed": total_messages,
                "total_rate_limit_hits": total_rate_limits,
                "total_api_errors": total_errors
            },
            "features": ["rate_limiting", "message_queueing", "exponential_backoff"]
        }
        
    except Exception as e:
        logger.error(f"Health check error: {e}", exc_info=True)
        return {
            "status": "error",
            "total_bots": 0,
            "running_bots": 0,
            "manager_initialized": False,
            "error": str(e)
        }