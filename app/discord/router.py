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

@router.post("/configure")
async def configure_discord_bot(
    config: DiscordConfig,
    background_tasks: BackgroundTasks,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Configure Discord bot for a tenant"""
    
    # Get tenant
    tenant = db.query(Tenant).filter(
        Tenant.api_key == api_key,
        Tenant.is_active == True
    ).first()
    
    if not tenant:
        raise HTTPException(status_code=403, detail="Invalid API key")
    
    # Update tenant Discord configuration
    tenant.discord_bot_token = config.bot_token
    tenant.discord_application_id = config.application_id
    tenant.discord_enabled = config.enabled
    tenant.discord_status_message = config.status_message
    
    db.commit()
    
    # Start/restart bot in background
    if config.enabled:
        background_tasks.add_task(restart_bot_for_tenant, tenant.id)
    else:
        background_tasks.add_task(stop_bot_for_tenant, tenant.id)
    
    return {"message": "Discord configuration updated successfully"}

@router.post("/start")
async def start_discord_bot(
    background_tasks: BackgroundTasks,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Start Discord bot for a tenant"""
    
    tenant = db.query(Tenant).filter(
        Tenant.api_key == api_key,
        Tenant.is_active == True
    ).first()
    
    if not tenant:
        raise HTTPException(status_code=403, detail="Invalid API key")
    
    if not tenant.discord_bot_token:
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
    
    tenant = db.query(Tenant).filter(
        Tenant.api_key == api_key,
        Tenant.is_active == True
    ).first()
    
    if not tenant:
        raise HTTPException(status_code=403, detail="Invalid API key")
    
    background_tasks.add_task(stop_bot_for_tenant, tenant.id)
    
    return {"message": "Discord bot stop initiated"}

@router.get("/status")
async def get_discord_bot_status(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get Discord bot status for a tenant"""
    
    # Get tenant
    tenant = db.query(Tenant).filter(
        Tenant.api_key == api_key,
        Tenant.is_active == True
    ).first()
    
    if not tenant:
        raise HTTPException(status_code=403, detail="Invalid API key")
    
    # Default safe response
    safe_response = {
        "tenant_id": tenant.id,
        "running": False,
        "connected": False,
        "guilds": 0,
        "latency": None
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


# Background task functions - Fixed to handle async properly
async def start_bot_for_tenant(tenant_id: int):
    """Background task to start bot for tenant"""
    try:
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
    manager = get_bot_manager()
    
    total_bots = len(manager.active_bots)
    running_bots = sum(1 for bot in manager.active_bots.values() if bot.is_running)
    
    return {
        "status": "healthy" if running_bots == total_bots or total_bots == 0 else "degraded",
        "total_bots": total_bots,
        "running_bots": running_bots,
        "manager_initialized": bot_manager is not None
    }