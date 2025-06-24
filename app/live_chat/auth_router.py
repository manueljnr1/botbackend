# app/live_chat/auth_router.py - FIXED ASYNC ISSUES
import secrets
from fastapi import APIRouter, Depends, HTTPException, status, Header, Request
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime, timedelta
import logging

from app.database import get_db
from app.live_chat.agent_service import AgentAuthService, AgentSessionService, LiveChatSettingsService
from app.live_chat.models import Agent, AgentStatus
from app.tenants.router import get_tenant_from_api_key
from app.tenants.models import Tenant

logger = logging.getLogger(__name__)
router = APIRouter()

# Pydantic Models
class AgentInviteRequest(BaseModel):
    email: EmailStr
    full_name: str

class AgentPasswordSetRequest(BaseModel):
    token: str
    password: str
    confirm_password: str

class AgentLoginResponse(BaseModel):
    access_token: str
    token_type: str
    agent_id: int
    agent_name: str
    display_name: str
    tenant_id: int
    email: str
    status: str
    expires_in: int

class AgentProfileUpdate(BaseModel):
    display_name: Optional[str] = None
    timezone: Optional[str] = None
    max_concurrent_chats: Optional[int] = None
    auto_assign: Optional[bool] = None
    work_hours_start: Optional[str] = None
    work_hours_end: Optional[str] = None
    work_days: Optional[str] = None

class AgentResponse(BaseModel):
    agent_id: int
    email: str
    full_name: str
    display_name: Optional[str]
    status: str
    is_active: bool
    is_online: bool
    invited_at: Optional[str]
    last_login: Optional[str]
    last_seen: Optional[str]
    total_conversations: int
    average_response_time: Optional[float]
    customer_satisfaction_avg: Optional[float]

class LiveChatSettingsResponse(BaseModel):
    is_enabled: bool
    welcome_message: Optional[str]
    offline_message: Optional[str]
    pre_chat_form_enabled: bool
    post_chat_survey_enabled: bool
    max_queue_size: int
    max_wait_time_minutes: int
    auto_assignment_enabled: bool
    assignment_method: str
    max_chats_per_agent: int
    business_hours_enabled: bool
    email_notifications_enabled: bool
    widget_color: str
    widget_position: str
    file_upload_enabled: bool
    file_size_limit_mb: int

class MessageResponse(BaseModel):
    success: bool
    message: str


# =============================================================================
# TENANT ENDPOINTS (Agent Management)
# =============================================================================

@router.post("/invite-agent")
async def invite_agent(
    request: AgentInviteRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Tenant invites a new agent to their support team"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        # TODO: Check if tenant has permission to add more agents (pricing limits)
        
        service = AgentAuthService(db)
        # FIXED: Now properly awaiting the async function
        result = await service.invite_agent(
            tenant_id=tenant.id,
            email=request.email,
            full_name=request.full_name,
            invited_by_id=tenant.id
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in invite_agent endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to invite agent")


@router.get("/agents", response_model=List[AgentResponse])
async def get_tenant_agents(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get all agents for the tenant"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        service = AgentAuthService(db)
        agents = service.get_tenant_agents(tenant.id)
        
        return agents
        
    except Exception as e:
        logger.error(f"Error getting tenant agents: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get agents")


@router.post("/agents/{agent_id}/revoke")
async def revoke_agent(
    agent_id: int,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Revoke an agent's access"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        service = AgentAuthService(db)
        # FIXED: Now properly awaiting the async function
        result = await service.revoke_agent(
            tenant_id=tenant.id,
            agent_id=agent_id,
            revoked_by_id=tenant.id
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error revoking agent: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to revoke agent")


@router.get("/active-agents")
async def get_active_agents(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get all currently active agents"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        session_service = AgentSessionService(db)
        active_agents = session_service.get_active_agents(tenant.id)
        
        return {
            "success": True,
            "active_agents": active_agents,
            "total_active": len(active_agents)
        }
        
    except Exception as e:
        logger.error(f"Error getting active agents: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get active agents")


# =============================================================================
# PUBLIC ENDPOINTS (Agent Registration & Login)
# =============================================================================

@router.get("/verify-invite/{token}")
async def verify_invitation(token: str, db: Session = Depends(get_db)):
    """Verify invitation token (public endpoint)"""
    try:
        service = AgentAuthService(db)
        agent = service.verify_invite_token(token)
        
        return {
            "valid": True,
            "agent_name": agent.full_name,
            "agent_email": agent.email,
            "business_name": agent.tenant.business_name or agent.tenant.name,
            "tenant_name": agent.tenant.name
        }
        
    except HTTPException as e:
        return {
            "valid": False,
            "error": e.detail
        }
    except Exception as e:
        logger.error(f"Error verifying invitation: {str(e)}")
        return {
            "valid": False,
            "error": "Verification failed"
        }


@router.post("/set-password", response_model=MessageResponse)
async def set_agent_password(
    request: AgentPasswordSetRequest,
    db: Session = Depends(get_db)
):
    """Agent sets their password after invitation (public endpoint)"""
    try:
        # Validate password confirmation
        if request.password != request.confirm_password:
            raise HTTPException(
                status_code=400, 
                detail="Passwords do not match"
            )
        
        # Validate password strength
        if len(request.password) < 8:
            raise HTTPException(
                status_code=400, 
                detail="Password must be at least 8 characters long"
            )
        
        service = AgentAuthService(db)
        # FIXED: Now properly awaiting the async function
        result = await service.set_agent_password(request.token, request.password)
        
        return {
            "success": True,
            "message": "Password set successfully. You can now log in."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting agent password: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to set password")


@router.post("/login", response_model=AgentLoginResponse)
async def agent_login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """Agent login (public endpoint)"""
    try:
        service = AgentAuthService(db)
        result = service.authenticate_agent(form_data.username, form_data.password)
        
        # Create agent session
        session_service = AgentSessionService(db)
        session_data = {
            "tenant_id": result["tenant_id"],
            "ip_address": request.client.host if request else None,
            "user_agent": request.headers.get("user-agent") if request else None,
            "device_type": "unknown",  # Could be enhanced with user-agent parsing
            "browser": "unknown"
        }
        
        session = session_service.create_session(result["agent_id"], session_data)
        result["session_id"] = session.session_id
        
        logger.info(f"Agent login successful: {result['email']}")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in agent login: {str(e)}")
        raise HTTPException(status_code=500, detail="Login failed")


# =============================================================================
# AUTHENTICATED AGENT ENDPOINTS
# =============================================================================

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="live-chat/auth/login")

def get_current_agent(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """Dependency to get current authenticated agent"""
    try:
        from app.core.security import verify_token
        
        # Decode and verify JWT token
        payload = verify_token(token)
        agent_id = payload.get("sub")
        user_type = payload.get("type")
        
        if user_type != "agent":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid user type"
            )
        
        # Get agent from database
        agent = db.query(Agent).filter(
            Agent.id == int(agent_id),
            Agent.status == AgentStatus.ACTIVE,
            Agent.is_active == True
        ).first()
        
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found or inactive"
            )
        
        return agent
        
    except Exception as e:
        logger.error(f"Error verifying agent token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.get("/profile")
async def get_agent_profile(
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """Get current agent's profile"""
    try:
        return {
            "agent_id": current_agent.id,
            "email": current_agent.email,
            "full_name": current_agent.full_name,
            "display_name": current_agent.display_name,
            "status": current_agent.status,
            "timezone": current_agent.timezone,
            "max_concurrent_chats": current_agent.max_concurrent_chats,
            "auto_assign": current_agent.auto_assign,
            "work_hours_start": current_agent.work_hours_start,
            "work_hours_end": current_agent.work_hours_end,
            "work_days": current_agent.work_days,
            "total_conversations": current_agent.total_conversations,
            "average_response_time": current_agent.average_response_time,
            "customer_satisfaction_avg": current_agent.customer_satisfaction_avg
        }
        
    except Exception as e:
        logger.error(f"Error getting agent profile: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get profile")


@router.put("/profile")
async def update_agent_profile(
    update_data: AgentProfileUpdate,
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """Update agent profile"""
    try:
        service = AgentAuthService(db)
        result = service.update_agent_profile(
            agent_id=current_agent.id,
            tenant_id=current_agent.tenant_id,
            update_data=update_data.dict(exclude_unset=True)
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating agent profile: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to update profile")


@router.post("/logout")
async def agent_logout(
    session_id: str,
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """Agent logout"""
    try:
        session_service = AgentSessionService(db)
        success = session_service.end_session(session_id)
        
        if success:
            return {
                "success": True,
                "message": "Logged out successfully"
            }
        else:
            return {
                "success": False,
                "message": "Session not found"
            }
            
    except Exception as e:
        logger.error(f"Error in agent logout: {str(e)}")
        raise HTTPException(status_code=500, detail="Logout failed")


# =============================================================================
# LIVE CHAT SETTINGS ENDPOINTS
# =============================================================================

@router.get("/settings", response_model=LiveChatSettingsResponse)
async def get_live_chat_settings(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get live chat settings for tenant"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        settings_service = LiveChatSettingsService(db)
        settings = settings_service.get_or_create_settings(tenant.id)
        
        return settings
        
    except Exception as e:
        logger.error(f"Error getting live chat settings: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get settings")


@router.put("/settings")
async def update_live_chat_settings(
    update_data: dict,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Update live chat settings"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        settings_service = LiveChatSettingsService(db)
        settings = settings_service.update_settings(tenant.id, update_data)
        
        return {
            "success": True,
            "message": "Settings updated successfully",
            "settings": settings
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating live chat settings: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to update settings")


# =============================================================================
# EMAIL SERVICE TESTING ENDPOINTS
# =============================================================================

@router.post("/test-email")
async def test_email_service(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Test if email service is working (Admin endpoint)"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        from app.email.resend_service import email_service
        result = await email_service.test_email_connection()
        
        return {
            "tenant_id": tenant.id,
            "email_service_status": result,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error testing email service: {str(e)}")
        raise HTTPException(status_code=500, detail="Email service test failed")


@router.post("/resend-invitation/{agent_id}")
async def resend_agent_invitation(
    agent_id: int,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Resend invitation email to an agent"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        # Get agent
        agent = db.query(Agent).filter(
            Agent.id == agent_id,
            Agent.tenant_id == tenant.id,
            Agent.status == "invited"
        ).first()
        
        if not agent:
            raise HTTPException(
                status_code=404, 
                detail="Agent not found or not in invited status"
            )
        
        # Generate new invite token if expired
        if agent.invited_at < datetime.utcnow() - timedelta(days=7):
            agent.invite_token = secrets.token_urlsafe(32)
            agent.invited_at = datetime.utcnow()
            db.commit()
        
        # Resend invitation
        from app.email.resend_service import email_service
        from app.config import settings
        
        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
        invite_url = f"{frontend_url}/agent/accept-invite/{agent.invite_token}"
        
        result = await email_service.send_agent_invitation(
            to_email=agent.email,
            agent_name=agent.full_name,
            business_name=tenant.business_name or tenant.name,
            invite_url=invite_url
        )
        
        if result["success"]:
            return {
                "success": True,
                "message": f"Invitation resent to {agent.email}",
                "email_id": result.get("email_id"),
                "agent_id": agent_id
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to resend invitation: {result.get('error')}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resending invitation: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to resend invitation")


# =============================================================================
# HEALTH CHECK & STATUS ENDPOINTS
# =============================================================================

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        from app.email.resend_service import email_service
        
        return {
            "status": "healthy",
            "service": "live_chat_auth",
            "email_service_enabled": email_service.enabled,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception:
        return {
            "status": "healthy",
            "service": "live_chat_auth",
            "email_service_enabled": False,
            "timestamp": datetime.utcnow().isoformat()
        }


@router.get("/stats/{tenant_id}")
async def get_tenant_live_chat_stats(
    tenant_id: int,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get live chat statistics for tenant"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        if tenant.id != tenant_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Get basic stats
        total_agents = db.query(Agent).filter(
            Agent.tenant_id == tenant_id,
            Agent.is_active == True
        ).count()
        
        active_agents = db.query(Agent).filter(
            Agent.tenant_id == tenant_id,
            Agent.is_online == True
        ).count()
        
        invited_agents = db.query(Agent).filter(
            Agent.tenant_id == tenant_id,
            Agent.status == AgentStatus.INVITED
        ).count()
        
        return {
            "tenant_id": tenant_id,
            "total_agents": total_agents,
            "active_agents": active_agents,
            "invited_agents": invited_agents,
            "live_chat_enabled": True  # TODO: Get from settings
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting live chat stats: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get statistics")