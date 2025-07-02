

import secrets
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from fastapi import HTTPException
from pydantic import BaseModel, EmailStr, validator

from app.live_chat.permissions import (
    AgentRole, AgentPermission, PermissionService, 
    can_agent_invite_role, get_role_info
)
from app.live_chat.models import Agent, AgentStatus, AgentRoleHistory
from app.tenants.models import Tenant

logger = logging.getLogger(__name__)



class AgentInviteWithRoleRequest(BaseModel):
    email: EmailStr
    full_name: str
    role: AgentRole = AgentRole.MEMBER
    department: Optional[str] = None
    initial_tags: Optional[List[str]] = None
    max_concurrent_chats: Optional[int] = 3
    notes: Optional[str] = None
    
    @validator('role')
    def validate_role(cls, v):
        if v not in [AgentRole.MEMBER, AgentRole.SENIOR_AGENT, AgentRole.TEAM_CAPTAIN]:
            raise ValueError('Invalid agent role')
        return v
    
    @validator('max_concurrent_chats')
    def validate_concurrent_chats(cls, v):
        if v is not None and (v < 1 or v > 10):
            raise ValueError('Max concurrent chats must be between 1 and 10')
        return v

class AgentInviteResponse(BaseModel):
    success: bool
    agent_id: int
    email: str
    full_name: str
    role: str
    invite_token: str
    status: str
    invited_at: str
    email_sent: bool
    initial_permissions: List[str]
    role_info: Dict[str, Any]

class BulkInviteRequest(BaseModel):
    invitations: List[AgentInviteWithRoleRequest]
    send_welcome_email: bool = True

class AgentPromotionRequest(BaseModel):
    new_role: AgentRole
    reason: Optional[str] = None
    effective_date: Optional[datetime] = None




class AgentInvitationService:
    """Service for handling role-based agent invitations"""
    
    def __init__(self, db: Session):
        self.db = db
        self.permission_service = PermissionService(db)
    
    async def invite_agent_with_role(
        self, 
        request: AgentInviteWithRoleRequest,
        tenant_id: int,
        invited_by_agent_id: Optional[int] = None
    ) -> AgentInviteResponse:
        """Invite a new agent with specific role assignment"""
        try:
            # Validate invitation permissions if invited by agent
            if invited_by_agent_id:
                await self._validate_invitation_permissions(
                    invited_by_agent_id, request.role
                )
            
            # Check if agent already exists
            existing_agent = await self._check_existing_agent(
                tenant_id, request.email
            )
            
            if existing_agent:
                if existing_agent.status == AgentStatus.REVOKED:
                    return await self._reactivate_agent_with_role(
                        existing_agent, request, invited_by_agent_id
                    )
                else:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Agent with email {request.email} already exists"
                    )
            
            # Create new agent with role
            agent = await self._create_agent_with_role(
                request, tenant_id, invited_by_agent_id
            )
            
            # Setup initial permissions and tags
            await self._setup_agent_permissions(agent, request)
            
            # Send role-specific invitation email
            email_sent = await self._send_role_invitation_email(agent, request.role)
            
            # Get role information
            role_info = get_role_info(request.role)
            
            # Get initial permissions
            initial_permissions = self.permission_service.get_agent_permissions(agent)
            
            logger.info(
                f"Agent invited with role {request.role}: {request.email} "
                f"for tenant {tenant_id}"
            )
            
            return AgentInviteResponse(
                success=True,
                agent_id=agent.id,
                email=agent.email,
                full_name=agent.full_name,
                role=agent.role,
                invite_token=agent.invite_token,
                status=agent.status,
                invited_at=agent.invited_at.isoformat(),
                email_sent=email_sent,
                initial_permissions=[p.value for p in initial_permissions],
                role_info=role_info
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error inviting agent with role: {str(e)}")
            self.db.rollback()
            raise HTTPException(status_code=500, detail="Failed to invite agent")
    
    async def bulk_invite_agents(
        self,
        request: BulkInviteRequest,
        tenant_id: int,
        invited_by_agent_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Bulk invite multiple agents with different roles"""
        try:
            results = []
            successful = 0
            failed = 0
            
            for invitation in request.invitations:
                try:
                    result = await self.invite_agent_with_role(
                        invitation, tenant_id, invited_by_agent_id
                    )
                    results.append({
                        "email": invitation.email,
                        "success": True,
                        "agent_id": result.agent_id,
                        "role": result.role
                    })
                    successful += 1
                    
                except Exception as e:
                    results.append({
                        "email": invitation.email,
                        "success": False,
                        "error": str(e)
                    })
                    failed += 1
            
            return {
                "success": True,
                "total_processed": len(request.invitations),
                "successful_invitations": successful,
                "failed_invitations": failed,
                "results": results
            }
            
        except Exception as e:
            logger.error(f"Error in bulk agent invitation: {str(e)}")
            raise HTTPException(status_code=500, detail="Bulk invitation failed")
    
    async def promote_agent(
        self,
        agent_id: int,
        request: AgentPromotionRequest,
        promoted_by_agent_id: int
    ) -> Dict[str, Any]:
        """Promote an agent to a new role"""
        try:
            # Validate promotion permissions
            promoting_agent = self.db.query(Agent).filter(
                Agent.id == promoted_by_agent_id
            ).first()
            
            if not promoting_agent:
                raise HTTPException(status_code=404, detail="Promoting agent not found")
            
            if not self.permission_service.has_permission(
                promoting_agent, AgentPermission.PROMOTE_AGENTS
            ):
                raise HTTPException(
                    status_code=403, 
                    detail="Permission denied: Cannot promote agents"
                )
            
            # Perform promotion
            success = self.permission_service.promote_agent(
                agent_id=agent_id,
                new_role=request.new_role,
                promoted_by_id=promoted_by_agent_id,
                reason=request.reason
            )
            
            if success:
                # Get updated agent
                agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
                
                # Send promotion notification email
                await self._send_promotion_notification(agent, request.new_role)
                
                return {
                    "success": True,
                    "message": f"Agent promoted to {request.new_role.value}",
                    "agent_id": agent_id,
                    "new_role": request.new_role.value,
                    "promoted_at": datetime.utcnow().isoformat()
                }
            else:
                raise HTTPException(status_code=400, detail="Promotion failed")
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error promoting agent: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to promote agent")
    
    async def get_available_roles_for_invitation(
        self, 
        inviter_agent_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get roles that can be assigned during invitation"""
        try:
            available_roles = []
            
            # If no inviter (tenant admin), all roles available
            if not inviter_agent_id:
                roles_to_check = [AgentRole.MEMBER, AgentRole.SENIOR_AGENT, AgentRole.TEAM_CAPTAIN]
            else:
                # Get inviter's role
                inviter = self.db.query(Agent).filter(
                    Agent.id == inviter_agent_id
                ).first()
                
                if not inviter:
                    raise HTTPException(status_code=404, detail="Inviter not found")
                
                # Determine available roles based on inviter's role
                if inviter.role == AgentRole.TEAM_CAPTAIN:
                    roles_to_check = [AgentRole.MEMBER, AgentRole.SENIOR_AGENT, AgentRole.TEAM_CAPTAIN]
                elif inviter.role == AgentRole.SENIOR_AGENT:
                    roles_to_check = [AgentRole.MEMBER]
                else:
                    roles_to_check = []  # Regular members cannot invite
            
            for role in roles_to_check:
                role_info = get_role_info(role)
                role_info["can_invite"] = True
                available_roles.append(role_info)
            
            return available_roles
            
        except Exception as e:
            logger.error(f"Error getting available roles: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to get available roles")
    
    # =============================================================================
    # PRIVATE HELPER METHODS
    # =============================================================================
    
    async def _validate_invitation_permissions(
        self, 
        inviter_agent_id: int, 
        target_role: AgentRole
    ):
        """Validate that inviter can invite to target role"""
        inviter = self.db.query(Agent).filter(
            Agent.id == inviter_agent_id
        ).first()
        
        if not inviter:
            raise HTTPException(status_code=404, detail="Inviter agent not found")
        
        # Check if inviter has invitation permission
        if not self.permission_service.has_permission(
            inviter, AgentPermission.INVITE_AGENTS
        ):
            raise HTTPException(
                status_code=403,
                detail="Permission denied: Cannot invite agents"
            )
        
        # Check if inviter can invite to this specific role
        if not can_agent_invite_role(inviter.role, target_role):
            raise HTTPException(
                status_code=403,
                detail=f"Cannot invite agents to role: {target_role.value}"
            )
    
    async def _check_existing_agent(self, tenant_id: int, email: str) -> Optional[Agent]:
        """Check if agent with email already exists"""
        return self.db.query(Agent).filter(
            Agent.tenant_id == tenant_id,
            Agent.email == email.lower().strip()
        ).first()
    
    # async def _create_agent_with_role(
    #     self,
    #     request: AgentInviteWithRoleRequest,
    #     tenant_id: int,
    #     invited_by_agent_id: Optional[int]
    # ) -> Agent:
    #     """Create new agent with role assignment"""
    #     # Generate secure invite token
    #     invite_token = secrets.token_urlsafe(32)
        
    #     # Create agent
    #     agent = Agent(
    #         tenant_id=tenant_id,
    #         email=request.email.lower().strip(),
    #         full_name=request.full_name,
    #         display_name=request.full_name.split()[0],
    #         invite_token=invite_token,
    #         invited_by=invited_by_agent_id or tenant_id,
    #         status=AgentStatus.INVITED,
    #         invited_at=datetime.utcnow(),
            
    #         # Role assignment
    #         role=request.role,
    #         max_concurrent_chats=request.max_concurrent_chats or 3,
            
    #         # Set role-based convenience flags
    #         can_assign_conversations=request.role in [AgentRole.SENIOR_AGENT, AgentRole.TEAM_CAPTAIN],
    #         can_manage_team=request.role == AgentRole.TEAM_CAPTAIN,
    #         can_access_analytics=request.role in [AgentRole.SENIOR_AGENT, AgentRole.TEAM_CAPTAIN],
    #     )
        
    #     self.db.add(agent)
    #     self.db.commit()
    #     self.db.refresh(agent)
        
    #     # Create role history record
    #     role_history = AgentRoleHistory(
    #         agent_id=agent.id,
    #         old_role=None,
    #         new_role=request.role,
    #         changed_by=invited_by_agent_id or tenant_id,
    #         reason=f"Initial invitation as {request.role.value}"
    #     )
    #     self.db.add(role_history)
    #     self.db.commit()
        
    #     return agent



    async def _create_agent_with_role(
        self,
        request: AgentInviteWithRoleRequest,
        tenant_id: int,
        invited_by_agent_id: Optional[int]
    ) -> Agent:
        """Create new agent with role assignment"""
        # Generate secure invite token
        invite_token = secrets.token_urlsafe(32)
        
        # Create agent
        agent = Agent(
            tenant_id=tenant_id,
            email=request.email.lower().strip(),
            full_name=request.full_name,
            display_name=request.full_name.split()[0],
            invite_token=invite_token,
            invited_by=invited_by_agent_id or tenant_id,
            status=AgentStatus.INVITED,
            invited_at=datetime.utcnow(),
            
            # Role assignment
            role=request.role,
            max_concurrent_chats=request.max_concurrent_chats or 3,
            
            # Set role-based convenience flags
            can_assign_conversations=request.role in [AgentRole.SENIOR_AGENT, AgentRole.TEAM_CAPTAIN],
            can_manage_team=request.role == AgentRole.TEAM_CAPTAIN,
            can_access_analytics=request.role in [AgentRole.SENIOR_AGENT, AgentRole.TEAM_CAPTAIN],
        )
        
        self.db.add(agent)
        self.db.commit()
        self.db.refresh(agent)
        
        # 🔧 FIXED: Only create role history if changed_by is an agent
        if invited_by_agent_id:  # Only create role history when invited by an agent
            role_history = AgentRoleHistory(
                agent_id=agent.id,
                old_role=None,
                new_role=request.role,
                changed_by=invited_by_agent_id,  # This is guaranteed to be an agent ID
                reason=f"Initial invitation as {request.role.value}"
            )
            self.db.add(role_history)
            self.db.commit()
        else:
            # When invited by tenant admin, we don't create role history
            # since changed_by must reference an agent, not a tenant
            logger.info(f"Agent {agent.id} invited by tenant admin - no role history created")
        
        return agent


    
    async def _setup_agent_permissions(
        self,
        agent: Agent,
        request: AgentInviteWithRoleRequest
    ):
        """Setup initial permissions and skill tags"""
        try:
            # Assign initial skill tags if provided
            if request.initial_tags:
                await self._assign_initial_tags(agent.id, request.initial_tags)
            
        except Exception as e:
            logger.error(f"Error setting up agent permissions: {str(e)}")
            # Don't fail the invitation for this
    
    async def _assign_initial_tags(self, agent_id: int, tag_names: List[str]):
        """Assign initial skill tags to newly invited agent"""
        try:
            from app.live_chat.models import AgentTag, AgentTagPerformance, agent_tags_association
            
            for tag_name in tag_names:
                # Find the tag
                tag = self.db.query(AgentTag).filter(
                    AgentTag.name == tag_name.lower(),
                    AgentTag.is_active == True
                ).first()
                
                if tag:
                    # Create tag assignment
                    self.db.execute(
                        agent_tags_association.insert().values(
                            agent_id=agent_id,
                            tag_id=tag.id,
                            proficiency_level=2,  # Beginner level for new agents
                            assigned_at=datetime.utcnow()
                        )
                    )
                    
                    # Create performance record
                    performance = AgentTagPerformance(
                        agent_id=agent_id,
                        tag_id=tag.id,
                        proficiency_level=2,
                        max_concurrent_for_tag=1  # Conservative for new agents
                    )
                    self.db.add(performance)
            
            self.db.commit()
            
        except Exception as e:
            logger.error(f"Error assigning initial tags: {str(e)}")
            self.db.rollback()
    
    async def _send_role_invitation_email(self, agent: Agent, role: AgentRole) -> bool:
        """Send role-specific invitation email"""
        try:
            from app.email.resend_service import email_service
            from app.config import settings
            
            # Get tenant info
            tenant = self.db.query(Tenant).filter(Tenant.id == agent.tenant_id).first()
            if not tenant:
                logger.error(f"Tenant not found for agent {agent.id}")
                return False
            
            frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
            invite_url = f"{frontend_url}/agent/accept-invite/{agent.invite_token}"
            
            # Role-specific email content
            role_messages = {
                AgentRole.MEMBER: {
                    "title": "Join Our Support Team",
                    "description": "You've been invited to join as a Support Member",
                    "responsibilities": [
                        "Handle customer conversations",
                        "Provide excellent customer service",
                        "Use our live chat system efficiently"
                    ]
                },
                AgentRole.SENIOR_AGENT: {
                    "title": "Join as Senior Support Agent",
                    "description": "You've been invited to join as a Senior Support Agent",
                    "responsibilities": [
                        "Handle complex customer issues",
                        "Mentor junior members",
                        "Assist with conversation assignment",
                        "Access team performance metrics"
                    ]
                },
                AgentRole.TEAM_CAPTAIN: {
                    "title": "Join as Team Captain",
                    "description": "You've been invited to lead our support team",
                    "responsibilities": [
                        "Manage the support team",
                        "Configure system settings",
                        "Monitor performance analytics",
                        "Handle escalated issues"
                    ]
                }
            }
            
            role_info = role_messages.get(role, role_messages[AgentRole.MEMBER])
            
            # Send invitation email (you'll need to implement this in your email service)
            result = await email_service.send_agent_invitation(
                to_email=agent.email,
                agent_name=agent.full_name,
                business_name=tenant.business_name or tenant.name,
                invite_url=invite_url,
                role_title=role_info["title"],
                role_description=role_info["description"],
                responsibilities=role_info["responsibilities"]
            )
            
            return result.get("success", False)
            
        except Exception as e:
            logger.error(f"Error sending role invitation email: {str(e)}")
            return False
    
    # async def _reactivate_agent_with_role(
    #     self,
    #     agent: Agent,
    #     request: AgentInviteWithRoleRequest,
    #     invited_by_agent_id: Optional[int]
    # ) -> AgentInviteResponse:
    #     """Reactivate a previously revoked agent with new role"""
    #     try:
    #         # Generate new invite token
    #         agent.invite_token = secrets.token_urlsafe(32)
    #         agent.status = AgentStatus.INVITED
    #         agent.is_active = True
    #         agent.invited_at = datetime.utcnow()
    #         agent.password_hash = None
    #         agent.password_set_at = None
            
    #         # Update role
    #         old_role = agent.role
    #         agent.role = request.role
    #         agent.can_assign_conversations = request.role in [AgentRole.SENIOR_AGENT, AgentRole.TEAM_CAPTAIN]
    #         agent.can_manage_team = request.role == AgentRole.TEAM_CAPTAIN
    #         agent.can_access_analytics = request.role in [AgentRole.SENIOR_AGENT, AgentRole.TEAM_CAPTAIN]
            
    #         # Create role history
    #         role_history = AgentRoleHistory(
    #             agent_id=agent.id,
    #             old_role=old_role,
    #             new_role=request.role,
    #             changed_by=invited_by_agent_id or agent.tenant_id,
    #             reason=f"Reactivation with role {request.role.value}"
    #         )
    #         self.db.add(role_history)
    #         self.db.commit()
            
    #         # Send invitation
    #         email_sent = await self._send_role_invitation_email(agent, request.role)
            
    #         # Get role info and permissions
    #         role_info = get_role_info(request.role)
    #         initial_permissions = self.permission_service.get_agent_permissions(agent)
            
    #         logger.info(f"Agent reactivated with role {request.role}: {agent.email}")
            
    #         return AgentInviteResponse(
    #             success=True,
    #             agent_id=agent.id,
    #             email=agent.email,
    #             full_name=agent.full_name,
    #             role=agent.role,
    #             invite_token=agent.invite_token,
    #             status="reactivated",
    #             invited_at=agent.invited_at.isoformat(),
    #             email_sent=email_sent,
    #             initial_permissions=[p.value for p in initial_permissions],
    #             role_info=role_info
    #         )
            
    #     except Exception as e:
    #         logger.error(f"Error reactivating agent: {str(e)}")
    #         self.db.rollback()
    #         raise HTTPException(status_code=500, detail="Failed to reactivate agent")





    async def _reactivate_agent_with_role(
        self,
        agent: Agent,
        request: AgentInviteWithRoleRequest,
        invited_by_agent_id: Optional[int]
    ) -> AgentInviteResponse:
        """Reactivate a previously revoked agent with new role"""
        try:
            # Generate new invite token
            agent.invite_token = secrets.token_urlsafe(32)
            agent.status = AgentStatus.INVITED
            agent.is_active = True
            agent.invited_at = datetime.utcnow()
            agent.password_hash = None
            agent.password_set_at = None
            
            # Update role
            old_role = agent.role
            agent.role = request.role
            agent.can_assign_conversations = request.role in [AgentRole.SENIOR_AGENT, AgentRole.TEAM_CAPTAIN]
            agent.can_manage_team = request.role == AgentRole.TEAM_CAPTAIN
            agent.can_access_analytics = request.role in [AgentRole.SENIOR_AGENT, AgentRole.TEAM_CAPTAIN]
            
            # 🔧 FIXED: Only create role history if changed_by is an agent
            if invited_by_agent_id:  # Only when reactivated by an agent
                role_history = AgentRoleHistory(
                    agent_id=agent.id,
                    old_role=old_role,
                    new_role=request.role,
                    changed_by=invited_by_agent_id,  # This is guaranteed to be an agent ID
                    reason=f"Reactivation with role {request.role.value}"
                )
                self.db.add(role_history)
            else:
                # When reactivated by tenant admin, we don't create role history
                # since changed_by must reference an agent, not a tenant
                logger.info(f"Agent {agent.id} reactivated by tenant admin - no role history created")
            
            self.db.commit()
            
            # Send invitation
            email_sent = await self._send_role_invitation_email(agent, request.role)
            
            # Get role info and permissions
            role_info = get_role_info(request.role)
            initial_permissions = self.permission_service.get_agent_permissions(agent)
            
            logger.info(f"Agent reactivated with role {request.role}: {agent.email}")
            
            return AgentInviteResponse(
                success=True,
                agent_id=agent.id,
                email=agent.email,
                full_name=agent.full_name,
                role=agent.role,
                invite_token=agent.invite_token,
                status="reactivated",
                invited_at=agent.invited_at.isoformat(),
                email_sent=email_sent,
                initial_permissions=[p.value for p in initial_permissions],
                role_info=role_info
            )
            
        except Exception as e:
            logger.error(f"Error reactivating agent: {str(e)}")
            self.db.rollback()
            raise HTTPException(status_code=500, detail="Failed to reactivate agent")



    
    async def _send_promotion_notification(self, agent: Agent, new_role: AgentRole):
        """Send email notification about promotion"""
        try:
            from app.email.resend_service import email_service
            
            tenant = self.db.query(Tenant).filter(Tenant.id == agent.tenant_id).first()
            
            await email_service.send_promotion_notification(
                to_email=agent.email,
                agent_name=agent.full_name,
                business_name=tenant.business_name or tenant.name,
                new_role=new_role.value,
                new_permissions=self.permission_service.get_agent_permissions(agent)
            )
            
        except Exception as e:
            logger.error(f"Error sending promotion notification: {str(e)}")
            # Don't fail promotion for email failure