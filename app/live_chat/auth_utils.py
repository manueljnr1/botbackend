
from typing import Optional, Union
from fastapi import Header, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.live_chat.models import Agent
from app.tenants.models import Tenant


def get_current_agent_optional(db: Session = Depends(get_db)):
    """Optional agent dependency - returns None if no valid token"""
    from fastapi.security import OAuth2PasswordBearer
    from fastapi import Request
    
    oauth2_scheme = OAuth2PasswordBearer(tokenUrl="live-chat/auth/login", auto_error=False)
    
    def _get_agent(token: str = Depends(oauth2_scheme)):
        if not token:
            return None
        
        try:
            from app.core.security import verify_token
            from app.live_chat.models import AgentStatus
            
            payload = verify_token(token)
            agent_id = payload.get("sub")
            user_type = payload.get("type")
            
            if user_type != "agent":
                return None
            
            agent = db.query(Agent).filter(
                Agent.id == int(agent_id),
                Agent.status == AgentStatus.ACTIVE,
                Agent.is_active == True
            ).first()
            
            return agent
            
        except Exception:
            return None
    
    return _get_agent


def get_tenant_context(
    api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
) -> Tenant:
    """Universal tenant resolver - works with both API key and agent token"""
    
    # Try API key first
    if api_key:
        from app.tenants.router import get_tenant_from_api_key
        return get_tenant_from_api_key(api_key, db)
    
    # Try bearer token
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]  # Remove "Bearer " prefix
        
        try:
            from app.core.security import verify_token
            from app.live_chat.models import AgentStatus
            
            payload = verify_token(token)
            agent_id = payload.get("sub")
            user_type = payload.get("type")
            
            if user_type == "agent":
                agent = db.query(Agent).filter(
                    Agent.id == int(agent_id),
                    Agent.status == AgentStatus.ACTIVE,
                    Agent.is_active == True
                ).first()
                
                if agent:
                    tenant = db.query(Tenant).filter(Tenant.id == agent.tenant_id).first()
                    if tenant:
                        return tenant
                    raise HTTPException(status_code=404, detail="Agent's tenant not found")
                
        except Exception as e:
            pass
    
    raise HTTPException(status_code=401, detail="API key or agent authentication required")


def get_agent_or_tenant_context(
    api_key: Optional[str] = Header(None, alias="X-API-Key"),
    db: Session = Depends(get_db)
) -> tuple[Tenant, Optional[Agent]]:
    """
    Returns (tenant, agent) - agent is None for API key access
    """
    # Try API key first
    if api_key:
        from app.tenants.router import get_tenant_from_api_key
        tenant = get_tenant_from_api_key(api_key, db)
        return tenant, None
    
    # Try agent token
    from fastapi import Request
    from starlette.requests import Request as StarletteRequest
    import inspect
    
    # Get the current request context
    frame = inspect.currentframe()
    try:
        while frame:
            if 'request' in frame.f_locals and isinstance(frame.f_locals['request'], (Request, StarletteRequest)):
                request = frame.f_locals['request']
                break
            frame = frame.f_back
        else:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Extract token from Authorization header
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]  # Remove "Bearer " prefix
            
            try:
                from app.core.security import verify_token
                from app.live_chat.models import AgentStatus
                
                payload = verify_token(token)
                agent_id = payload.get("sub")
                user_type = payload.get("type")
                
                if user_type == "agent":
                    agent = db.query(Agent).filter(
                        Agent.id == int(agent_id),
                        Agent.status == AgentStatus.ACTIVE,
                        Agent.is_active == True
                    ).first()
                    
                    if agent:
                        tenant = db.query(Tenant).filter(Tenant.id == agent.tenant_id).first()
                        if tenant:
                            return tenant, agent
                        raise HTTPException(status_code=404, detail="Agent's tenant not found")
                    
            except Exception:
                pass
    finally:
        del frame
    
    raise HTTPException(status_code=401, detail="Authentication required")