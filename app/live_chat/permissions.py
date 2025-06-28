# app/live_chat/permissions.py - SINGLE PERMISSION FILE
"""
Complete permission system for Live Chat
Handles roles, permissions, decorators, and services in one coordinated file
"""

import logging
from functools import wraps
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum
from sqlalchemy.orm import Session
from sqlalchemy import and_
from fastapi import HTTPException, status, Depends

logger = logging.getLogger(__name__)

# =============================================================================
# ENUMS & CONSTANTS
# =============================================================================

class AgentRole(str, Enum):
    MEMBER = "member"
    SENIOR_AGENT = "senior_agent"
    TEAM_CAPTAIN = "team_captain"

class AgentPermission(str, Enum):
    # Basic Agent permissions
    HANDLE_CONVERSATIONS = "handle_conversations"
    VIEW_PERSONAL_ANALYTICS = "view_personal_analytics"
    SEND_TRANSCRIPTS = "send_transcripts"
    
    # Senior Agent permissions
    ASSIGN_CONVERSATIONS = "assign_conversations"
    TRANSFER_CONVERSATIONS = "transfer_conversations"
    VIEW_TEAM_ANALYTICS = "view_team_analytics"
    VIEW_ROUTING_INSIGHTS = "view_routing_insights"
    MENTOR_AGENTS = "mentor_agents"
    
    # Team Captain permissions
    MANAGE_AGENT_TAGS = "manage_agent_tags"
    CONFIGURE_ROUTING = "configure_routing"
    MANAGE_AGENTS = "manage_agents"
    ACCESS_SYSTEM_SETTINGS = "access_system_settings"
    BULK_ASSIGN_CONVERSATIONS = "bulk_assign_conversations"
    VIEW_TENANT_ANALYTICS = "view_tenant_analytics"
    INVITE_AGENTS = "invite_agents"
    PROMOTE_AGENTS = "promote_agents"

# Role hierarchy for permission inheritance
ROLE_HIERARCHY = {
    AgentRole.MEMBER: 1,
    AgentRole.SENIOR_AGENT: 2,
    AgentRole.TEAM_CAPTAIN: 3
}

# Default permissions per role
ROLE_PERMISSIONS = {
    AgentRole.MEMBER: [
        AgentPermission.HANDLE_CONVERSATIONS,
        AgentPermission.VIEW_PERSONAL_ANALYTICS,
        AgentPermission.SEND_TRANSCRIPTS,
    ],
    AgentRole.SENIOR_AGENT: [
        # Inherit all Member permissions
        AgentPermission.HANDLE_CONVERSATIONS,
        AgentPermission.VIEW_PERSONAL_ANALYTICS,
        AgentPermission.SEND_TRANSCRIPTS,
        # Senior specific permissions
        AgentPermission.ASSIGN_CONVERSATIONS,
        AgentPermission.TRANSFER_CONVERSATIONS,
        AgentPermission.VIEW_TEAM_ANALYTICS,
        AgentPermission.VIEW_ROUTING_INSIGHTS,
        AgentPermission.MENTOR_AGENTS,
    ],
    AgentRole.TEAM_CAPTAIN: [
        # Inherit all previous permissions
        AgentPermission.HANDLE_CONVERSATIONS,
        AgentPermission.VIEW_PERSONAL_ANALYTICS,
        AgentPermission.SEND_TRANSCRIPTS,
        AgentPermission.ASSIGN_CONVERSATIONS,
        AgentPermission.TRANSFER_CONVERSATIONS,
        AgentPermission.VIEW_TEAM_ANALYTICS,
        AgentPermission.VIEW_ROUTING_INSIGHTS,
        AgentPermission.MENTOR_AGENTS,
        # Captain specific permissions
        AgentPermission.MANAGE_AGENT_TAGS,
        AgentPermission.CONFIGURE_ROUTING,
        AgentPermission.MANAGE_AGENTS,
        AgentPermission.ACCESS_SYSTEM_SETTINGS,
        AgentPermission.BULK_ASSIGN_CONVERSATIONS,
        AgentPermission.VIEW_TENANT_ANALYTICS,
        AgentPermission.INVITE_AGENTS,
        AgentPermission.PROMOTE_AGENTS,
    ]
}

# =============================================================================
# PERMISSION SERVICE
# =============================================================================

class PermissionService:
    """Centralized permission management service"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def has_permission(self, agent, permission: AgentPermission) -> bool:
        """Check if agent has specific permission"""
        try:
            # Import here to avoid circular imports
            from app.live_chat.models import AgentPermissionOverride
            
            # Check role-based permissions first
            role_permissions = ROLE_PERMISSIONS.get(agent.role, [])
            if permission in role_permissions:
                return True
            
            # Check custom permission overrides
            override = self.db.query(AgentPermissionOverride).filter(
                and_(
                    AgentPermissionOverride.agent_id == agent.id,
                    AgentPermissionOverride.permission == permission
                )
            ).first()
            
            if override:
                return override.granted
            
            return False
            
        except Exception as e:
            logger.error(f"Permission check error for agent {agent.id}: {str(e)}")
            return False
    
    def has_role(self, agent, required_role: AgentRole) -> bool:
        """Check if agent has required role or higher"""
        agent_level = ROLE_HIERARCHY.get(agent.role, 0)
        required_level = ROLE_HIERARCHY.get(required_role, 999)
        return agent_level >= required_level
    
    def get_agent_permissions(self, agent) -> List[AgentPermission]:
        """Get all permissions for an agent"""
        try:
            from app.live_chat.models import AgentPermissionOverride
            
            # Start with role-based permissions
            permissions = set(ROLE_PERMISSIONS.get(agent.role, []))
            
            # Apply custom overrides
            overrides = self.db.query(AgentPermissionOverride).filter(
                AgentPermissionOverride.agent_id == agent.id
            ).all()
            
            for override in overrides:
                if override.granted:
                    permissions.add(override.permission)
                else:
                    permissions.discard(override.permission)
            
            return list(permissions)
            
        except Exception as e:
            logger.error(f"Error getting permissions for agent {agent.id}: {str(e)}")
            return list(ROLE_PERMISSIONS.get(agent.role, []))
    
    def promote_agent(self, agent_id: int, new_role: AgentRole, 
                     promoted_by_id: int, reason: str = None) -> bool:
        """Promote agent to new role"""
        try:
            from app.live_chat.models import Agent, AgentRoleHistory
            
            agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
            if not agent:
                logger.error(f"Agent {agent_id} not found for promotion")
                return False
            
            old_role = agent.role
            
            # Validate promotion path
            if not self._can_promote_to_role(old_role, new_role):
                logger.error(f"Invalid promotion from {old_role} to {new_role}")
                return False
            
            # Create role history record
            role_history = AgentRoleHistory(
                agent_id=agent_id,
                old_role=old_role,
                new_role=new_role,
                changed_by=promoted_by_id,
                reason=reason or f"Promoted from {old_role} to {new_role}"
            )
            self.db.add(role_history)
            
            # Update agent role and convenience flags
            agent.role = new_role
            agent.promoted_at = datetime.utcnow()
            agent.promoted_by = promoted_by_id
            self._update_agent_flags(agent, new_role)
            
            self.db.commit()
            logger.info(f"Agent {agent_id} promoted from {old_role} to {new_role}")
            return True
            
        except Exception as e:
            logger.error(f"Agent promotion error: {str(e)}")
            self.db.rollback()
            return False
    
    def grant_custom_permission(self, agent_id: int, permission: AgentPermission,
                              granted_by_id: int, reason: str = None) -> bool:
        """Grant custom permission to agent"""
        try:
            from app.live_chat.models import AgentPermissionOverride
            
            # Remove existing override if any
            existing = self.db.query(AgentPermissionOverride).filter(
                and_(
                    AgentPermissionOverride.agent_id == agent_id,
                    AgentPermissionOverride.permission == permission
                )
            ).first()
            
            if existing:
                self.db.delete(existing)
            
            # Create new override
            override = AgentPermissionOverride(
                agent_id=agent_id,
                permission=permission,
                granted=True,
                granted_by=granted_by_id,
                reason=reason or f"Custom permission granted: {permission}"
            )
            self.db.add(override)
            self.db.commit()
            
            logger.info(f"Custom permission {permission} granted to agent {agent_id}")
            return True
            
        except Exception as e:
            logger.error(f"Permission grant error: {str(e)}")
            self.db.rollback()
            return False
    
    def revoke_custom_permission(self, agent_id: int, permission: AgentPermission,
                               revoked_by_id: int, reason: str = None) -> bool:
        """Revoke custom permission from agent"""
        try:
            from app.live_chat.models import AgentPermissionOverride
            
            # Remove existing override if any
            existing = self.db.query(AgentPermissionOverride).filter(
                and_(
                    AgentPermissionOverride.agent_id == agent_id,
                    AgentPermissionOverride.permission == permission
                )
            ).first()
            
            if existing:
                self.db.delete(existing)
            
            # Create revocation record
            override = AgentPermissionOverride(
                agent_id=agent_id,
                permission=permission,
                granted=False,
                granted_by=revoked_by_id,
                reason=reason or f"Permission revoked: {permission}"
            )
            self.db.add(override)
            self.db.commit()
            
            logger.info(f"Permission {permission} revoked from agent {agent_id}")
            return True
            
        except Exception as e:
            logger.error(f"Permission revoke error: {str(e)}")
            self.db.rollback()
            return False
    
    def _can_promote_to_role(self, current_role: AgentRole, new_role: AgentRole) -> bool:
        """Check if promotion is valid"""
        current_level = ROLE_HIERARCHY.get(current_role, 0)
        new_level = ROLE_HIERARCHY.get(new_role, 0)
        
        # Can promote to same level or higher, but not skip levels
        if new_level <= current_level:
            return False
        
        # Don't allow skipping levels (e.g., Agent -> Team Captain)
        if new_level - current_level > 1:
            return False
        
        return True
    
    def _update_agent_flags(self, agent, role: AgentRole):
        """Update agent convenience flags based on role"""
        agent.can_assign_conversations = role in [AgentRole.SENIOR_AGENT, AgentRole.TEAM_CAPTAIN]
        agent.can_manage_team = role == AgentRole.TEAM_CAPTAIN
        agent.can_access_analytics = role in [AgentRole.SENIOR_AGENT, AgentRole.TEAM_CAPTAIN]

# =============================================================================
# DECORATORS
# =============================================================================

def require_permission(permission: AgentPermission):
    """Decorator to require specific permission"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract current_agent from kwargs
            current_agent = kwargs.get('current_agent')
            if not current_agent:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required"
                )
            
            # Get database session
            db = kwargs.get('db')
            if not db:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Database session not available"
                )
            
            # Check permission
            permission_service = PermissionService(db)
            if not permission_service.has_permission(current_agent, permission):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: {permission.value} required"
                )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator

def require_role(required_role: AgentRole):
    """Decorator to require specific role or higher"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_agent = kwargs.get('current_agent')
            if not current_agent:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required"
                )
            
            db = kwargs.get('db')
            permission_service = PermissionService(db)
            
            if not permission_service.has_role(current_agent, required_role):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Role {required_role.value} or higher required"
                )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator

# =============================================================================
# ENHANCED AUTHENTICATION DEPENDENCY
# =============================================================================

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

# OAuth2 scheme for Bearer token
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="live-chat/auth/login", auto_error=False)

def get_current_agent_with_permissions(
    token: str = Depends(oauth2_scheme)
):
    """
    Enhanced agent dependency with permission loading
    This replaces get_current_agent for permission-aware endpoints
    """
    # Import here to avoid circular imports
    from app.database import get_db
    from sqlalchemy.orm import Session
    
    # Get database session
    db_gen = get_db()
    db: Session = next(db_gen)
    
    try:
        from app.core.security import verify_token
        from app.live_chat.models import Agent
        
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication token required"
            )
        
        # Decode and verify JWT token
        payload = verify_token(token)
        agent_id = payload.get("sub")
        user_type = payload.get("type")
        
        if user_type != "agent":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid user type - agent token required"
            )
        
        # Get agent from database
        agent = db.query(Agent).filter(
            Agent.id == int(agent_id),
            Agent.status == "active",  # Using string for now
            Agent.is_active == True
        ).first()
        
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found or inactive"
            )
        
        # Load permissions using PermissionService
        permission_service = PermissionService(db)
        agent.permissions = permission_service.get_agent_permissions(agent)
        agent.can_promote = permission_service.has_permission(agent, AgentPermission.PROMOTE_AGENTS)
        agent.can_invite = permission_service.has_permission(agent, AgentPermission.INVITE_AGENTS)
        
        return agent
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying agent token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )
    finally:
        db.close()

# Backward compatibility function
def get_current_agent(token: str = Depends(oauth2_scheme)):
    """
    Basic agent authentication without permission loading
    For backward compatibility with existing endpoints
    """
    # Import here to avoid circular imports
    from app.database import get_db
    from sqlalchemy.orm import Session
    
    # Get database session
    db_gen = get_db()
    db: Session = next(db_gen)
    
    try:
        from app.core.security import verify_token
        from app.live_chat.models import Agent
        
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication token required"
            )
        
        # Decode and verify JWT token
        payload = verify_token(token)
        agent_id = payload.get("sub")
        user_type = payload.get("type")
        
        if user_type != "agent":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid user type - agent token required"
            )
        
        # Get agent from database
        agent = db.query(Agent).filter(
            Agent.id == int(agent_id),
            Agent.status == "active",
            Agent.is_active == True
        ).first()
        
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found or inactive"
            )
        
        return agent
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying agent token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )
    finally:
        db.close()

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_role_info(role: AgentRole) -> Dict[str, Any]:
    """Get role information including permissions and descriptions"""
    role_descriptions = {
        AgentRole.MEMBER: {
            "title": "Member",
            "description": "Handle customer conversations and provide support",
            "can_be_promoted_to": [AgentRole.SENIOR_AGENT]
        },
        AgentRole.SENIOR_AGENT: {
            "title": "Senior Agent", 
            "description": "Handle complex issues, mentor members, access team analytics",
            "can_be_promoted_to": [AgentRole.TEAM_CAPTAIN]
        },
        AgentRole.TEAM_CAPTAIN: {
            "title": "Team Captain",
            "description": "Lead the team, manage settings, full system access",
            "can_be_promoted_to": []
        }
    }
    
    info = role_descriptions.get(role, {})
    info.update({
        "value": role,
        "permissions": ROLE_PERMISSIONS.get(role, []),
        "permissions_count": len(ROLE_PERMISSIONS.get(role, [])),
        "hierarchy_level": ROLE_HIERARCHY.get(role, 0)
    })
    
    return info

def can_agent_invite_role(inviter_role: AgentRole, target_role: AgentRole) -> bool:
    """Check if an agent can invite someone to a specific role"""
    inviter_level = ROLE_HIERARCHY.get(inviter_role, 0)
    target_level = ROLE_HIERARCHY.get(target_role, 0)
    
    # Team Captains can invite anyone
    if inviter_role == AgentRole.TEAM_CAPTAIN:
        return True
    
    # Senior Agents can only invite Members
    if inviter_role == AgentRole.SENIOR_AGENT:
        return target_role == AgentRole.MEMBER
    
    # Regular Members cannot invite anyone
    return False

def validate_role_transition(current_role: AgentRole, new_role: AgentRole) -> Dict[str, Any]:
    """Validate if a role transition is allowed"""
    current_level = ROLE_HIERARCHY.get(current_role, 0)
    new_level = ROLE_HIERARCHY.get(new_role, 0)
    
    result = {
        "valid": False,
        "reason": "",
        "current_level": current_level,
        "new_level": new_level
    }
    
    if new_level <= current_level:
        result["reason"] = "Cannot demote or assign same role"
        return result
    
    if new_level - current_level > 1:
        result["reason"] = "Cannot skip role levels"
        return result
    
    result["valid"] = True
    result["reason"] = "Valid promotion"
    return result