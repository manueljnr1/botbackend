# app/live_chat/agent_service.py - FIXED VERSION
import secrets
import uuid
import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from typing import Optional, Dict, List
import json

from app.core.security import get_password_hash, verify_password, create_access_token
from app.live_chat.models import (
    Agent, AgentStatus, LiveChatConversation, AgentSession, 
    LiveChatSettings, ConversationStatus
)
from app.tenants.models import Tenant

logger = logging.getLogger(__name__)


class AgentAuthService:
    def __init__(self, db: Session):
        self.db = db
    
    def invite_agent(self, tenant_id: int, email: str, full_name: str, invited_by_id: int) -> Dict:
        """Send invitation to new agent"""
        try:
            # Normalize email
            email = email.lower().strip()
            
            # Check if agent already exists
            existing_agent = self.db.query(Agent).filter(
                Agent.tenant_id == tenant_id,
                Agent.email == email
            ).first()
            
            if existing_agent:
                if existing_agent.status == AgentStatus.REVOKED:
                    return self._reactivate_agent(existing_agent)
                else:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Agent with email {email} already exists"
                    )
            
            # Generate secure invite token
            invite_token = secrets.token_urlsafe(32)
            
            # Create agent record
            agent = Agent(
                tenant_id=tenant_id,
                email=email,
                full_name=full_name,
                display_name=full_name.split()[0],  # First name as default display
                invite_token=invite_token,
                invited_by=invited_by_id,
                status=AgentStatus.INVITED
            )
            
            self.db.add(agent)
            self.db.commit()
            self.db.refresh(agent)
            
            # Send invitation email
            self._send_invitation_email(agent)
            
            logger.info(f"Agent invited: {email} for tenant {tenant_id}")
            
            return {
                "success": True,
                "agent_id": agent.id,
                "email": agent.email,
                "full_name": agent.full_name,
                "invite_token": invite_token,
                "status": agent.status,
                "invited_at": agent.invited_at.isoformat()
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error inviting agent: {str(e)}")
            self.db.rollback()
            raise HTTPException(status_code=500, detail="Failed to invite agent")
    
    def _reactivate_agent(self, agent: Agent) -> Dict:
        """Reactivate a previously revoked agent"""
        # Generate new invite token
        agent.invite_token = secrets.token_urlsafe(32)
        agent.status = AgentStatus.INVITED
        agent.is_active = True
        agent.invited_at = datetime.utcnow()
        agent.password_hash = None  # Clear old password
        agent.password_set_at = None
        
        self.db.commit()
        
        # Send new invitation
        self._send_invitation_email(agent)
        
        logger.info(f"Agent reactivated: {agent.email}")
        
        return {
            "success": True,
            "agent_id": agent.id,
            "email": agent.email,
            "status": "reactivated",
            "invite_token": agent.invite_token
        }
    
    async def _send_invitation_email(self, agent: Agent):
        """Send invitation email to agent using Resend"""
        try:
            # Get tenant info
            tenant = self.db.query(Tenant).filter(Tenant.id == agent.tenant_id).first()
            if not tenant:
                logger.error(f"Tenant not found for agent {agent.id}")
                return False
            
            # Create invitation URL
            from app.config import settings
            frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
            invite_url = f"{frontend_url}/agent/accept-invite/{agent.invite_token}"
            
            # Send email via Resend
            from app.email.resend_service import email_service
            
            result = await email_service.send_agent_invitation(
                to_email=agent.email,
                agent_name=agent.full_name,
                business_name=tenant.business_name or tenant.name,
                invite_url=invite_url
            )
            
            if result["success"]:
                logger.info(f"✅ Invitation email sent to {agent.email}, ID: {result.get('email_id')}")
                return True
            else:
                logger.error(f"❌ Failed to send invitation email: {result.get('error')}")
                return False
            
        except Exception as e:
            logger.error(f"Error sending invitation email: {str(e)}")
            return False
    
    def verify_invite_token(self, token: str) -> Agent:
        """Verify invitation token and return agent"""
        agent = self.db.query(Agent).filter(
            Agent.invite_token == token,
            Agent.status == AgentStatus.INVITED,
            Agent.is_active == True
        ).first()
        
        if not agent:
            raise HTTPException(
                status_code=400, 
                detail="Invalid or expired invitation token"
            )
        
        # Check if invitation is expired (7 days)
        if agent.invited_at < datetime.utcnow() - timedelta(days=7):
            raise HTTPException(
                status_code=400, 
                detail="Invitation has expired. Please request a new invitation."
            )
        
        return agent
    
    async def set_agent_password(self, token: str, password: str) -> Dict:
        """Set password for invited agent and activate account"""
        try:
            # Verify token
            agent = self.verify_invite_token(token)
            
            # Validate password
            if len(password) < 8:
                raise HTTPException(
                    status_code=400, 
                    detail="Password must be at least 8 characters long"
                )
            
            # Set password and activate
            agent.password_hash = get_password_hash(password)
            agent.status = AgentStatus.ACTIVE
            agent.password_set_at = datetime.utcnow()
            agent.invite_token = None  # Clear token for security
            
            self.db.commit()
            
            # Send welcome email
            tenant = self.db.query(Tenant).filter(Tenant.id == agent.tenant_id).first()
            if tenant:
                from app.email.resend_service import email_service
                await email_service.send_password_reset_notification(
                    to_email=agent.email,
                    agent_name=agent.full_name,
                    business_name=tenant.business_name or tenant.name
                )
            
            logger.info(f"Agent password set and activated: {agent.email}")
            
            return {
                "success": True,
                "agent_id": agent.id,
                "email": agent.email,
                "full_name": agent.full_name,
                "status": agent.status,
                "activated_at": agent.password_set_at.isoformat()
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error setting agent password: {str(e)}")
            self.db.rollback()
            raise HTTPException(status_code=500, detail="Failed to set password")
    
    def authenticate_agent(self, email: str, password: str) -> Dict:
        """Authenticate agent login"""
        try:
            # Normalize email
            email = email.lower().strip()
            
            # Find agent
            agent = self.db.query(Agent).filter(
                Agent.email == email,
                Agent.status == AgentStatus.ACTIVE,
                Agent.is_active == True
            ).first()
            
            if not agent:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid email or password"
                )
            
            # Verify password
            if not agent.password_hash or not verify_password(password, agent.password_hash):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid email or password"
                )
            
            # Update last login
            agent.last_login = datetime.utcnow()
            agent.last_seen = datetime.utcnow()
            self.db.commit()
            
            # Create access token
            access_token = create_access_token(
                data={
                    "sub": str(agent.id),
                    "type": "agent",
                    "tenant_id": agent.tenant_id,
                    "email": agent.email
                },
                expires_delta=timedelta(hours=8)
            )
            
            logger.info(f"Agent authenticated: {agent.email}")
            
            return {
                "access_token": access_token,
                "token_type": "bearer",
                "agent_id": agent.id,
                "agent_name": agent.full_name,
                "display_name": agent.display_name,
                "tenant_id": agent.tenant_id,
                "email": agent.email,
                "status": agent.status,
                "expires_in": 28800  # 8 hours in seconds
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error authenticating agent: {str(e)}")
            raise HTTPException(status_code=500, detail="Authentication failed")
    
    async def revoke_agent(self, tenant_id: int, agent_id: int, revoked_by_id: int) -> Dict:
        """Revoke agent access"""
        try:
            agent = self.db.query(Agent).filter(
                Agent.id == agent_id,
                Agent.tenant_id == tenant_id
            ).first()
            
            if not agent:
                raise HTTPException(status_code=404, detail="Agent not found")
            
            # Update agent status
            agent.status = AgentStatus.REVOKED
            agent.is_active = False
            agent.updated_at = datetime.utcnow()
            
            # End any active sessions
            active_sessions = self.db.query(AgentSession).filter(
                AgentSession.agent_id == agent_id,
                AgentSession.logout_at.is_(None)
            ).all()
            
            for session in active_sessions:
                session.logout_at = datetime.utcnow()
                session.status = AgentStatus.OFFLINE
            
            self.db.commit()
            
            # Send revocation notification email
            tenant = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()
            if tenant:
                from app.email.resend_service import email_service
                await email_service.send_agent_revoked_notification(
                    to_email=agent.email,
                    agent_name=agent.full_name,
                    business_name=tenant.business_name or tenant.name
                )
            
            logger.info(f"Agent revoked: {agent.email} by user {revoked_by_id}")
            
            return {
                "success": True,
                "agent_id": agent.id,
                "email": agent.email,
                "status": "revoked",
                "revoked_at": datetime.utcnow().isoformat()
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error revoking agent: {str(e)}")
            self.db.rollback()
            raise HTTPException(status_code=500, detail="Failed to revoke agent")
    
    def get_tenant_agents(self, tenant_id: int) -> List[Dict]:
        """Get all agents for a tenant"""
        try:
            agents = self.db.query(Agent).filter(
                Agent.tenant_id == tenant_id
            ).order_by(Agent.created_at.desc()).all()
            
            agent_list = []
            for agent in agents:
                agent_data = {
                    "agent_id": agent.id,
                    "email": agent.email,
                    "full_name": agent.full_name,
                    "display_name": agent.display_name,
                    "status": agent.status,
                    "is_active": agent.is_active,
                    "is_online": agent.is_online,
                    "invited_at": agent.invited_at.isoformat() if agent.invited_at else None,
                    "last_login": agent.last_login.isoformat() if agent.last_login else None,
                    "last_seen": agent.last_seen.isoformat() if agent.last_seen else None,
                    "total_conversations": agent.total_conversations,
                    "average_response_time": agent.average_response_time,
                    "customer_satisfaction_avg": agent.customer_satisfaction_avg
                }
                agent_list.append(agent_data)
            
            return agent_list
            
        except Exception as e:
            logger.error(f"Error getting tenant agents: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to get agents")
    
    def update_agent_profile(self, agent_id: int, tenant_id: int, update_data: Dict) -> Dict:
        """Update agent profile information"""
        try:
            agent = self.db.query(Agent).filter(
                Agent.id == agent_id,
                Agent.tenant_id == tenant_id
            ).first()
            
            if not agent:
                raise HTTPException(status_code=404, detail="Agent not found")
            
            # Update allowed fields
            allowed_fields = [
                'display_name', 'timezone', 'max_concurrent_chats', 
                'auto_assign', 'notification_settings', 'work_hours_start',
                'work_hours_end', 'work_days'
            ]
            
            for field, value in update_data.items():
                if field in allowed_fields and hasattr(agent, field):
                    setattr(agent, field, value)
            
            agent.updated_at = datetime.utcnow()
            self.db.commit()
            
            logger.info(f"Agent profile updated: {agent.email}")
            
            return {
                "success": True,
                "agent_id": agent.id,
                "message": "Profile updated successfully"
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating agent profile: {str(e)}")
            self.db.rollback()
            raise HTTPException(status_code=500, detail="Failed to update profile")


class AgentSessionService:
    def __init__(self, db: Session):
        self.db = db
    
    def create_session(self, agent_id: int, session_data: Dict) -> AgentSession:
        """Create new agent session"""
        try:
            # End any existing active sessions
            self._end_active_sessions(agent_id)
            
            # Create new session
            session = AgentSession(
                agent_id=agent_id,
                tenant_id=session_data.get('tenant_id'),
                session_id=str(uuid.uuid4()),
                status=AgentStatus.ACTIVE,
                ip_address=session_data.get('ip_address'),
                user_agent=session_data.get('user_agent'),
                device_type=session_data.get('device_type'),
                browser=session_data.get('browser')
            )
            
            self.db.add(session)
            
            # Update agent online status
            agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
            if agent:
                agent.is_online = True
                agent.last_seen = datetime.utcnow()
            
            self.db.commit()
            self.db.refresh(session)
            
            logger.info(f"Agent session created: {agent_id}")
            return session
            
        except Exception as e:
            logger.error(f"Error creating agent session: {str(e)}")
            self.db.rollback()
            raise HTTPException(status_code=500, detail="Failed to create session")
    
    def _end_active_sessions(self, agent_id: int):
        """End all active sessions for agent"""
        active_sessions = self.db.query(AgentSession).filter(
            AgentSession.agent_id == agent_id,
            AgentSession.logout_at.is_(None)
        ).all()
        
        for session in active_sessions:
            session.logout_at = datetime.utcnow()
            session.status = AgentStatus.OFFLINE
    
    def update_session_status(self, session_id: str, status: str, websocket_id: str = None) -> bool:
        """Update agent session status"""
        try:
            session = self.db.query(AgentSession).filter(
                AgentSession.session_id == session_id
            ).first()
            
            if not session:
                return False
            
            session.status = status
            session.last_activity = datetime.utcnow()
            
            if websocket_id:
                session.websocket_id = websocket_id
            
            # Update agent online status
            agent = self.db.query(Agent).filter(Agent.id == session.agent_id).first()
            if agent:
                agent.is_online = (status in [AgentStatus.ACTIVE, AgentStatus.BUSY])
                agent.last_seen = datetime.utcnow()
            
            self.db.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error updating session status: {str(e)}")
            return False
    
    def end_session(self, session_id: str) -> bool:
        """End agent session"""
        try:
            session = self.db.query(AgentSession).filter(
                AgentSession.session_id == session_id
            ).first()
            
            if not session:
                return False
            
            # Calculate session duration
            if session.login_at:
                total_time = (datetime.utcnow() - session.login_at).total_seconds()
                session.total_online_time = int(total_time)
            
            session.logout_at = datetime.utcnow()
            session.status = AgentStatus.OFFLINE
            session.websocket_id = None
            
            # Update agent offline status
            agent = self.db.query(Agent).filter(Agent.id == session.agent_id).first()
            if agent:
                agent.is_online = False
                agent.last_seen = datetime.utcnow()
            
            self.db.commit()
            
            logger.info(f"Agent session ended: {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error ending session: {str(e)}")
            return False
    
    def get_active_agents(self, tenant_id: int) -> List[Dict]:
        """Get all active agents for tenant"""
        try:
            active_sessions = self.db.query(AgentSession).join(Agent).filter(
                Agent.tenant_id == tenant_id,
                AgentSession.logout_at.is_(None),
                AgentSession.status.in_([AgentStatus.ACTIVE, AgentStatus.BUSY])
            ).all()
            
            agents_data = []
            for session in active_sessions:
                agent = session.agent
                agent_data = {
                    "agent_id": agent.id,
                    "session_id": session.session_id,
                    "display_name": agent.display_name,
                    "email": agent.email,
                    "status": session.status,
                    "active_conversations": session.active_conversations,
                    "max_concurrent_chats": session.max_concurrent_chats,
                    "is_accepting_chats": session.is_accepting_chats,
                    "last_activity": session.last_activity.isoformat(),
                    "online_duration": int((datetime.utcnow() - session.login_at).total_seconds()) if session.login_at else 0
                }
                agents_data.append(agent_data)
            
            return agents_data
            
        except Exception as e:
            logger.error(f"Error getting active agents: {str(e)}")
            return []


class LiveChatSettingsService:
    def __init__(self, db: Session):
        self.db = db
    
    def get_or_create_settings(self, tenant_id: int) -> LiveChatSettings:
        """Get existing settings or create default ones"""
        settings = self.db.query(LiveChatSettings).filter(
            LiveChatSettings.tenant_id == tenant_id
        ).first()
        
        if not settings:
            settings = self._create_default_settings(tenant_id)
        
        return settings
    
    def _create_default_settings(self, tenant_id: int) -> LiveChatSettings:
        """Create default live chat settings"""
        tenant = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()
        business_name = tenant.business_name if tenant else "Our Team"
        
        settings = LiveChatSettings(
            tenant_id=tenant_id,
            is_enabled=True,
            welcome_message=f"Hi! How can {business_name} help you today?",
            offline_message=f"We're currently offline. Please leave a message and {business_name} will get back to you soon!",
            pre_chat_form_enabled=False,
            post_chat_survey_enabled=True,
            max_queue_size=50,
            max_wait_time_minutes=30,
            queue_timeout_message="Sorry for the wait! We're experiencing high volume. Please try again later or leave your email for a callback.",
            auto_assignment_enabled=True,
            assignment_method="round_robin",
            max_chats_per_agent=3,
            business_hours_enabled=False,
            email_notifications_enabled=True,
            widget_color="#6d28d9",
            widget_position="bottom-right",
            file_upload_enabled=True,
            file_size_limit_mb=10,
            allowed_file_types='["jpg", "jpeg", "png", "gif", "pdf", "doc", "docx"]',
            customer_info_retention_days=365,
            require_email_verification=False
        )
        
        self.db.add(settings)
        self.db.commit()
        self.db.refresh(settings)
        
        return settings
    
    def update_settings(self, tenant_id: int, update_data: Dict) -> LiveChatSettings:
        """Update live chat settings"""
        try:
            settings = self.get_or_create_settings(tenant_id)
            
            # Update allowed fields
            for field, value in update_data.items():
                if hasattr(settings, field):
                    setattr(settings, field, value)
            
            settings.updated_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(settings)
            
            return settings
            
        except Exception as e:
            logger.error(f"Error updating live chat settings: {str(e)}")
            self.db.rollback()
            raise HTTPException(status_code=500, detail="Failed to update settings")