"""
API endpoints for managing tenant knowledge mapping
"""
from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from app.database import get_db
from app.auth.router import get_current_user, get_admin_user
from app.auth.models import User
from app.tenants.models import Tenant
from app.knowledge_base.models import KnowledgeBase, FAQ
from app.context.tenant_context import tenant_context_manager

router = APIRouter()

# Pydantic models
class TenantMapInfo(BaseModel):
    """Information about a tenant's knowledge mapping"""
    tenant_id: int
    tenant_name: str
    knowledge_base_count: int
    faq_count: int
    has_active_context: bool

class KnowledgeBaseInfo(BaseModel):
    """Information about a knowledge base"""
    id: int
    name: str
    description: Optional[str] = None
    document_type: str
    
    class Config:
        from_attributes = True

class FAQInfo(BaseModel):
    """Information about a FAQ"""
    id: int
    question: str
    answer: str
    
    class Config:
        from_attributes = True

# Helper function
async def get_admin_or_own_tenant(tenant_id: int, current_user: User = Depends(get_current_user)):
    """
    Ensure user is either an admin or accessing their own tenant
    
    Args:
        tenant_id: ID of the tenant to access
        current_user: Current authenticated user
        
    Returns:
        User if authorized
        
    Raises:
        HTTPException if not authorized
    """
    if current_user.is_admin or current_user.tenant_id == tenant_id:
        return current_user
    
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Not authorized to access this tenant"
    )

# Endpoints
@router.get("/tenants", response_model=List[TenantMapInfo])
async def list_tenant_knowledge_maps(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """
    List all tenants with their knowledge mapping information (admin only)
    """
    # Get all active tenants
    tenants = db.query(Tenant).filter(Tenant.is_active == True).all()
    
    result = []
    for tenant in tenants:
        # Count knowledge bases
        kb_count = db.query(KnowledgeBase).filter(KnowledgeBase.tenant_id == tenant.id).count()
        
        # Count FAQs
        faq_count = db.query(FAQ).filter(FAQ.tenant_id == tenant.id).count()
        
        # Check if tenant has active context
        has_context = tenant.id in tenant_context_manager.tenant_contexts
        
        result.append({
            "tenant_id": tenant.id,
            "tenant_name": tenant.name,
            "knowledge_base_count": kb_count,
            "faq_count": faq_count,
            "has_active_context": has_context
        })
    
    return result

@router.get("/tenants/{tenant_id}", response_model=TenantMapInfo)
async def get_tenant_knowledge_map(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_or_own_tenant)
):
    """
    Get knowledge mapping information for a specific tenant
    """
    # Get tenant
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id, Tenant.is_active == True).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    # Count knowledge bases
    kb_count = db.query(KnowledgeBase).filter(KnowledgeBase.tenant_id == tenant_id).count()
    
    # Count FAQs
    faq_count = db.query(FAQ).filter(FAQ.tenant_id == tenant_id).count()
    
    # Check if tenant has active context
    has_context = tenant_id in tenant_context_manager.tenant_contexts
    
    return {
        "tenant_id": tenant.id,
        "tenant_name": tenant.name,
        "knowledge_base_count": kb_count,
        "faq_count": faq_count,
        "has_active_context": has_context
    }

@router.get("/tenants/{tenant_id}/knowledge-bases", response_model=List[KnowledgeBaseInfo])
async def list_tenant_knowledge_bases(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_or_own_tenant)
):
    """
    List all knowledge bases for a specific tenant
    """
    # Get tenant
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id, Tenant.is_active == True).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    # Get knowledge bases
    knowledge_bases = db.query(KnowledgeBase).filter(KnowledgeBase.tenant_id == tenant_id).all()
    
    return knowledge_bases

@router.get("/tenants/{tenant_id}/faqs", response_model=List[FAQInfo])
async def list_tenant_faqs(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_or_own_tenant)
):
    """
    List all FAQs for a specific tenant
    """
    # Get tenant
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id, Tenant.is_active == True).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    # Get FAQs
    faqs = db.query(FAQ).filter(FAQ.tenant_id == tenant_id).all()
    
    return faqs

@router.post("/tenants/{tenant_id}/refresh")
async def refresh_tenant_context(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_or_own_tenant)
):
    """
    Refresh a tenant's context to reload knowledge bases and FAQs
    """
    # Get tenant
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id, Tenant.is_active == True).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    # Invalidate and reload tenant context
    tenant_context_manager.invalidate_tenant_context(tenant_id)
    context = tenant_context_manager.get_tenant_context(tenant_id, db)
    
    if not context:
        raise HTTPException(status_code=500, detail="Failed to refresh tenant context")
    
    return {
        "message": "Tenant context refreshed successfully",
        "tenant_id": tenant_id,
        "knowledge_base_count": len(context.knowledge_bases),
        "faq_count": len(context.faqs)
    }

@router.post("/tenants/{tenant_id}/test")
async def test_tenant_chatbot(
    tenant_id: int,
    message: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_or_own_tenant)
):
    """
    Test the chatbot for a specific tenant with a sample message
    """
    # Get tenant
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id, Tenant.is_active == True).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    # Import here to avoid circular imports
    from app.chatbot.engine import ChatbotEngine
    
    # Initialize engine
    engine = ChatbotEngine(db)
    
    # Process the message
    result = engine.process_message(
        api_key=tenant.api_key,
        user_message=message,
        user_identifier=f"test-user-{current_user.id}"
    )
    
    if not result.get("success"):
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to process message: {result.get('error', 'Unknown error')}"
        )
    
    return {
        "message": message,
        "response": result.get("response"),
        "session_id": result.get("session_id")
    }