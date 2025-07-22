# app/admin/router.py
from fastapi import APIRouter, Depends, HTTPException, Header, Query
import logging
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel

from app.database import get_db
from app.auth.models import User
from app.tenants.models import Tenant
from app.knowledge_base.models import KnowledgeBase, FAQ
from app.chatbot.models import ChatSession, ChatMessage
from app.auth.router import get_current_user, get_admin_user
from app.core.security import get_password_hash
from app.tenants.api_key_service import EnhancedAPIKeyResetService, get_enhanced_api_key_reset_service

from app.tenants.secure_id_service import get_secure_tenant_id_service, SecureTenantIDService
from app.auth.models import TenantCredentials

router = APIRouter()

# Initialize logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
router = APIRouter()

# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class UserUpdate(BaseModel):
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None
    tenant_id: Optional[int] = None

class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    is_active: bool
    is_admin: bool
    tenant_id: Optional[int]
    created_at: datetime
    
    class Config:
        from_attributes = True

class TenantUpdateAdmin(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    system_prompt: Optional[str] = None
    email: Optional[str] = None
    feedback_email: Optional[str] = None
    from_email: Optional[str] = None
    enable_feedback_system: Optional[bool] = None
    feedback_notification_enabled: Optional[bool] = None

class TenantResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    is_active: bool
    system_prompt: Optional[str] = None
    email: Optional[str] = None
    feedback_email: Optional[str] = None
    from_email: Optional[str] = None
    enable_feedback_system: bool
    feedback_notification_enabled: bool
    api_key: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class FAQCreate(BaseModel):
    question: str
    answer: str
    tenant_id: int

class FAQUpdate(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None

class FAQResponse(BaseModel):
    id: int
    question: str
    answer: str
    tenant_id: int
    created_at: datetime
    
    class Config:
        from_attributes = True

class DocumentResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    tenant_id: int
    document_type: str
    file_path: str
    created_at: datetime
    
    class Config:
        from_attributes = True



class TenantStatsResponse(BaseModel):
    id: int
    name: str
    is_active: bool
    kb_count: int
    faq_count: int
    session_count: int
    message_count: int
    active_users: int
    # Add subscription info safely
    subscription_plan: Optional[str] = None
    subscription_status: Optional[str] = None

class TenantOverviewResponse(BaseModel):
    total_tenants: int
    active_tenants: int
    tenant_stats: List[TenantStatsResponse]


class AdminAPIKeyResetRequest(BaseModel):
    reason: Optional[str] = None

class AdminAPIKeyResetResponse(BaseModel):
    success: bool
    message: str
    tenant_id: int
    tenant_name: Optional[str] = None
    new_api_key: Optional[str] = None
    old_api_key_masked: Optional[str] = None
    reset_timestamp: Optional[str] = None
    reset_by: str
    verification_method: Optional[str] = None
    error: Optional[str] = None

class BulkAPIKeyResetRequest(BaseModel):
    tenant_ids: List[int]
    reason: Optional[str] = None

class BulkAPIKeyResetResponse(BaseModel):
    success: bool
    message: str
    total_requested: int
    successful_resets: int
    failed_resets: int
    results: List[Dict[str, Any]]
    errors: List[Dict[str, Any]] = []

class SecurityAuditResponse(BaseModel):
    success: bool
    audit_period_days: int
    total_tenants: int
    security_summary: Dict[str, Any]
    recent_resets: List[Dict[str, Any]]
    recommendations: List[str]
    error: Optional[str] = None


class MigrationAuditResponse(BaseModel):
    success: bool
    audit_timestamp: Optional[str] = None
    summary: Dict[str, Any]
    duplicate_details: List[Dict[str, Any]]
    invalid_key_details: List[Dict[str, Any]]
    recommendations: List[str]
    error: Optional[str] = None

class MigrationFixRequest(BaseModel):
    dry_run: bool = True
    fix_duplicates: bool = True
    fix_invalid: bool = True

class MigrationFixResponse(BaseModel):
    success: bool
    migration_type: str
    total_fixes: int
    duplicate_fixes: Dict[str, Any]
    invalid_fixes: Dict[str, Any]
    initial_audit: Dict[str, Any]
    final_audit: Dict[str, Any]
    error: Optional[str] = None






class TenantIDSecurityAuditResponse(BaseModel):
    success: bool
    audit_timestamp: Optional[str] = None
    summary: Dict[str, Any]
    secure_tenants: List[Dict[str, Any]]
    insecure_tenants: List[Dict[str, Any]]
    recommendations: List[str]
    next_steps: List[str] = []
    error: Optional[str] = None

class TenantIDResetRequest(BaseModel):
    reason: Optional[str] = None

class TenantIDResetResponse(BaseModel):
    success: bool
    message: str
    old_tenant_id: Optional[int] = None
    new_tenant_id: Optional[int] = None
    tenant_name: Optional[str] = None
    business_name: Optional[str] = None
    tenant_email: Optional[str] = None
    reason: Optional[str] = None
    timestamp: Optional[str] = None
    error: Optional[str] = None

class BulkTenantIDResetRequest(BaseModel):
    dry_run: bool = True
    batch_size: int = 10
    reason: Optional[str] = None

class BulkTenantIDResetResponse(BaseModel):
    success: bool
    message: str
    total_tenants: int
    reset_count: int
    failed_count: int
    successful_resets: List[Dict[str, Any]]
    failed_resets: List[Dict[str, Any]]
    dry_run: bool
    error: Optional[str] = None

class TenantIDMigrationPreview(BaseModel):
    success: bool
    preview_type: str
    total_insecure_tenants: int
    would_reset_count: int
    preview_resets: List[Dict[str, Any]]
    estimated_time_minutes: Optional[float] = None
    warning: str
    next_step: str
    error: Optional[str] = None




# =============================================================================
# USER MANAGEMENT ENDPOINTS
# =============================================================================

@router.get("/users", response_model=List[UserResponse])
async def list_all_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """
    Get a list of all users (admin only)
    """
    users = db.query(User).all()
    return users

@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_update: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """
    Update a user's status or role (admin only)
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Prevent self-deactivation
    if current_user.id == user_id and user_update.is_active is False:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")
    
    # Prevent removing own admin privileges
    if current_user.id == user_id and user_update.is_admin is False:
        raise HTTPException(status_code=400, detail="You cannot remove your own admin privileges")
    
    # Update user fields
    if user_update.is_active is not None:
        user.is_active = user_update.is_active
    
    if user_update.is_admin is not None:
        user.is_admin = user_update.is_admin
    
    if user_update.tenant_id is not None:
        # Verify tenant exists
        tenant = db.query(Tenant).filter(Tenant.id == user_update.tenant_id).first()
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        user.tenant_id = user_update.tenant_id
    
    db.commit()
    db.refresh(user)
    return user

@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """
    Delete a user (admin only)
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Prevent self-deletion
    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    
    db.delete(user)
    db.commit()
    
    return {"message": "User deleted successfully"}

# =============================================================================
# TENANT MANAGEMENT ENDPOINTS
# =============================================================================

@router.get("/tenants", response_model=List[TenantResponse])
async def admin_list_tenants(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """
    Get list of all tenants with full details (admin only)
    """
    tenants = db.query(Tenant).all()
    return tenants



@router.get("/tenants/overview", response_model=TenantOverviewResponse)
async def get_tenant_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """
    Get overview of all tenants' usage with subscription info (admin only)
    """
    tenants = db.query(Tenant).all()
    
    tenant_stats = []
    for tenant in tenants:
        # Knowledge base count
        kb_count = db.query(KnowledgeBase).filter(
            KnowledgeBase.tenant_id == tenant.id
        ).count()
        
        # FAQ count
        faq_count = db.query(FAQ).filter(
            FAQ.tenant_id == tenant.id
        ).count()
        
        # Session count
        session_count = db.query(ChatSession).filter(
            ChatSession.tenant_id == tenant.id
        ).count()
        
        # Message count
        message_count = db.query(ChatMessage).join(
            ChatSession, ChatMessage.session_id == ChatSession.id
        ).filter(
            ChatSession.tenant_id == tenant.id
        ).count()
        
        # Active users (unique user identifiers from sessions)
        active_users = db.query(ChatSession.user_identifier).filter(
            ChatSession.tenant_id == tenant.id
        ).distinct().count()
        
        # Get subscription info safely
        subscription_plan = None
        subscription_status = None
        try:
            # Import here to avoid circular imports
            from app.pricing.models import TenantSubscription
            subscription = db.query(TenantSubscription).filter(
                TenantSubscription.tenant_id == tenant.id,
                TenantSubscription.is_active == True
            ).first()
            
            if subscription and subscription.plan:
                subscription_plan = subscription.plan.name
                subscription_status = subscription.status
            else:
                subscription_plan = "No Plan"
                subscription_status = "inactive"
        except Exception as e:
            # If there's any issue with subscription data, use defaults
            subscription_plan = "Unknown"
            subscription_status = "unknown"
        
        tenant_stats.append(TenantStatsResponse(
            id=tenant.id,
            name=tenant.name,
            is_active=tenant.is_active,
            kb_count=kb_count,
            faq_count=faq_count,
            session_count=session_count,
            message_count=message_count,
            active_users=active_users,
            subscription_plan=subscription_plan,
            subscription_status=subscription_status
        ))
    
    return TenantOverviewResponse(
        total_tenants=len(tenants),
        active_tenants=sum(1 for t in tenants if t.is_active),
        tenant_stats=tenant_stats
    )




@router.get("/tenants/{tenant_id}", response_model=TenantResponse)
async def admin_get_tenant(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """
    Get detailed tenant information (admin only)
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant







@router.put("/tenants/{tenant_id}", response_model=TenantResponse)
async def admin_update_tenant(
    tenant_id: int,
    tenant_update: TenantUpdateAdmin,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """
    Update tenant details including system prompt (admin only)
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    # Update tenant fields
    update_data = tenant_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(tenant, key, value)
    
    db.commit()
    db.refresh(tenant)
    return tenant






@router.delete("/tenants/{tenant_id}")
async def admin_delete_tenant(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """
    Deactivate a tenant (admin only)
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    tenant.is_active = False
    db.commit()
    return {"message": "Tenant deactivated successfully"}



# =============================================================================
# SYSTEM PROMPT MANAGEMENT
# =============================================================================

@router.get("/tenants/{tenant_id}/prompt")
async def admin_get_tenant_prompt(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """
    Get tenant's system prompt (admin only)
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    return {
        "tenant_id": tenant.id,
        "tenant_name": tenant.name,
        "system_prompt": tenant.system_prompt
    }

@router.put("/tenants/{tenant_id}/prompt")
async def admin_update_tenant_prompt(
    tenant_id: int,
    prompt_data: dict,  # Expects {"system_prompt": "new prompt"}
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """
    Update tenant's system prompt (admin only)
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    new_system_prompt = prompt_data.get("system_prompt")
    if new_system_prompt is None:
        raise HTTPException(status_code=400, detail="system_prompt field is required")
    
    tenant.system_prompt = new_system_prompt
    db.commit()
    db.refresh(tenant)
    
    return {
        "message": "System prompt updated successfully",
        "tenant_id": tenant.id,
        "tenant_name": tenant.name,
        "system_prompt": tenant.system_prompt
    }

# =============================================================================
# DOCUMENT MANAGEMENT ENDPOINTS
# =============================================================================

@router.get("/documents")
async def list_all_documents(
    tenant_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """
    List all knowledge base documents (admin only)
    """
    query = db.query(KnowledgeBase)
    
    if tenant_id:
        query = query.filter(KnowledgeBase.tenant_id == tenant_id)
    
    documents = query.all()
    
    result = []
    for doc in documents:
        # Get tenant name
        tenant = db.query(Tenant).filter(Tenant.id == doc.tenant_id).first()
        tenant_name = tenant.name if tenant else "Unknown"
        
        result.append({
            "id": doc.id,
            "name": doc.name,
            "description": doc.description,
            "tenant_id": doc.tenant_id,
            "tenant_name": tenant_name,
            "document_type": doc.document_type.value,
            "created_at": doc.created_at.isoformat()
        })
    
    return result

@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def admin_get_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """
    Get detailed document information (admin only)
    """
    document = db.query(KnowledgeBase).filter(KnowledgeBase.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Convert enum to string for response
    doc_response = DocumentResponse(
        id=document.id,
        name=document.name,
        description=document.description,
        tenant_id=document.tenant_id,
        document_type=document.document_type.value,
        file_path=document.file_path,
        created_at=document.created_at
    )
    return doc_response

@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """
    Delete a knowledge base document (admin only)
    """
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == document_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Delete the vector store
    try:
        from app.knowledge_base.processor import DocumentProcessor
        processor = DocumentProcessor(kb.tenant_id)
        processor.delete_vector_store(kb.vector_store_id)
    except Exception as e:
        # Log the error but don't fail the deletion
        print(f"Warning: Could not delete vector store: {e}")
    
    # Delete the uploaded file
    import os
    try:
        if kb.file_path and os.path.exists(kb.file_path):
            os.remove(kb.file_path)
    except Exception as e:
        # Log the error but don't fail the deletion
        print(f"Warning: Could not delete file: {e}")
    
    # Delete from database
    db.delete(kb)
    db.commit()
    
    return {"message": "Document deleted successfully"}

# =============================================================================
# FAQ MANAGEMENT ENDPOINTS
# =============================================================================

@router.get("/faqs")
async def list_all_faqs(
    tenant_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """
    List all FAQs (admin only)
    """
    query = db.query(FAQ)
    
    if tenant_id:
        query = query.filter(FAQ.tenant_id == tenant_id)
    
    faqs = query.all()
    
    result = []
    for faq in faqs:
        # Get tenant name
        tenant = db.query(Tenant).filter(Tenant.id == faq.tenant_id).first()
        tenant_name = tenant.name if tenant else "Unknown"
        
        result.append({
            "id": faq.id,
            "question": faq.question,
            "answer": faq.answer,
            "tenant_id": faq.tenant_id,
            "tenant_name": tenant_name,
            "created_at": faq.created_at.isoformat()
        })
    
    return result

@router.get("/faqs/{faq_id}", response_model=FAQResponse)
async def admin_get_faq(
    faq_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """
    Get detailed FAQ information (admin only)
    """
    faq = db.query(FAQ).filter(FAQ.id == faq_id).first()
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found")
    return faq

@router.post("/faqs", response_model=FAQResponse)
async def admin_create_faq(
    faq: FAQCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """
    Create a new FAQ for any tenant (admin only)
    """
    # Verify tenant exists
    tenant = db.query(Tenant).filter(Tenant.id == faq.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    db_faq = FAQ(
        question=faq.question,
        answer=faq.answer,
        tenant_id=faq.tenant_id
    )
    
    db.add(db_faq)
    db.commit()
    db.refresh(db_faq)
    
    return db_faq

@router.put("/faqs/{faq_id}", response_model=FAQResponse)
async def admin_update_faq(
    faq_id: int,
    faq_update: FAQUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """
    Update FAQ content (admin only)
    """
    faq = db.query(FAQ).filter(FAQ.id == faq_id).first()
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found")
    
    # Update FAQ fields
    update_data = faq_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(faq, key, value)
    
    db.commit()
    db.refresh(faq)
    return faq

@router.delete("/faqs/{faq_id}")
async def delete_faq(
    faq_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """
    Delete an FAQ (admin only)
    """
    faq = db.query(FAQ).filter(FAQ.id == faq_id).first()
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found")
    
    db.delete(faq)
    db.commit()
    
    return {"message": "FAQ deleted successfully"}

# =============================================================================
# USAGE STATISTICS
# =============================================================================

@router.get("/usage-statistics")
async def get_usage_statistics(
    days: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """
    Get global usage statistics (admin only)
    """
    # Calculate date range
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    # Total messages in time period
    total_messages = db.query(ChatMessage).join(
        ChatSession, ChatMessage.session_id == ChatSession.id
    ).filter(
        ChatMessage.created_at >= start_date,
        ChatMessage.created_at <= end_date
    ).count()
    
    # Total sessions in time period
    total_sessions = db.query(ChatSession).filter(
        ChatSession.created_at >= start_date,
        ChatSession.created_at <= end_date
    ).count()
    
    # Active users in time period (unique user identifiers)
    active_users = db.query(ChatSession.user_identifier).filter(
        ChatSession.created_at >= start_date,
        ChatSession.created_at <= end_date
    ).distinct().count()
    
    # Daily session counts
    daily_query = db.query(
        func.date(ChatSession.created_at).label('date'),
        func.count().label('count')
    ).filter(
        ChatSession.created_at >= start_date,
        ChatSession.created_at <= end_date
    ).group_by(
        func.date(ChatSession.created_at)
    ).all()
    
    daily_sessions = {str(date): count for date, count in daily_query}
    
    # Fill in missing days
    current_date = start_date.date()
    while current_date <= end_date.date():
        day_str = str(current_date)
        if day_str not in daily_sessions:
            daily_sessions[day_str] = 0
        current_date += timedelta(days=1)
    
    # Messages per tenant
    tenant_messages = db.query(
        Tenant.name,
        func.count(ChatMessage.id).label('count')
    ).join(
        ChatSession, ChatSession.tenant_id == Tenant.id
    ).join(
        ChatMessage, ChatMessage.session_id == ChatSession.id
    ).filter(
        ChatMessage.created_at >= start_date,
        ChatMessage.created_at <= end_date
    ).group_by(
        Tenant.name
    ).all()
    
    tenant_message_counts = [
        {"tenant": name, "count": count}
        for name, count in tenant_messages
    ]
    
    return {
        "period_days": days,
        "total_messages": total_messages,
        "total_sessions": total_sessions,
        "active_users": active_users,
        "daily_sessions": [
            {"date": k, "count": v}
            for k, v in sorted(daily_sessions.items())
        ],
        "tenant_message_counts": tenant_message_counts,
        "resources": {
            "total_tenants": db.query(Tenant).count(),
            "total_knowledge_bases": db.query(KnowledgeBase).count(),
            "total_faqs": db.query(FAQ).count(),
            "total_users": db.query(User).count()
        }
    }

# =============================================================================
# SESSION MANAGEMENT
# =============================================================================

@router.get("/session-details/{session_id}")
async def get_admin_session_details(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """
    Get details of any chat session (admin only)
    """
    session = db.query(ChatSession).filter(
        ChatSession.session_id == session_id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Get tenant info
    tenant = db.query(Tenant).filter(Tenant.id == session.tenant_id).first()
    tenant_name = tenant.name if tenant else "Unknown"
    
    # Get messages
    messages = db.query(ChatMessage).filter(
        ChatMessage.session_id == session.id
    ).order_by(ChatMessage.created_at.asc()).all()
    
    # Format messages
    formatted_messages = [
        {
            "content": msg.content,
            "is_from_user": msg.is_from_user,
            "created_at": msg.created_at.isoformat()
        }
        for msg in messages
    ]
    
    return {
        "session_id": session.session_id,
        "tenant_id": session.tenant_id,
        "tenant_name": tenant_name,
        "user_identifier": session.user_identifier,
        "is_active": session.is_active,
        "created_at": session.created_at.isoformat(),
        "messages": formatted_messages,
        "message_count": len(messages)
    }

# =============================================================================
# BULK OPERATIONS
# =============================================================================

@router.post("/tenants/bulk-action")
async def admin_bulk_tenant_action(
    action_data: dict,  # {"action": "activate|deactivate", "tenant_ids": [1,2,3]}
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """
    Perform bulk actions on multiple tenants (admin only)
    """
    action = action_data.get("action")
    tenant_ids = action_data.get("tenant_ids", [])
    
    if action not in ["activate", "deactivate"]:
        raise HTTPException(status_code=400, detail="Invalid action. Use 'activate' or 'deactivate'")
    
    if not tenant_ids:
        raise HTTPException(status_code=400, detail="No tenant IDs provided")
    
    # Update tenants
    is_active = action == "activate"
    updated_count = db.query(Tenant).filter(
        Tenant.id.in_(tenant_ids)
    ).update(
        {"is_active": is_active},
        synchronize_session=False
    )
    
    db.commit()
    
    return {
        "message": f"Successfully {action}d {updated_count} tenants",
        "action": action,
        "affected_tenants": updated_count
    }



# =============================================================================# API KEY RESET ENDPOINTS

@router.post("/tenants/{tenant_id}/reset-api-key", response_model=AdminAPIKeyResetResponse)
async def admin_reset_tenant_api_key(
    tenant_id: int,
    reset_request: AdminAPIKeyResetRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """
    Admin endpoint to reset any tenant's API key (bypasses password verification)
    Enhanced with better audit logging
    """
    try:
        # Get admin identifier for audit
        admin_identifier = getattr(current_user, 'username', None) or getattr(current_user, 'email', f'admin_{current_user.id}')
        
        # Initialize the enhanced service
        api_service = get_enhanced_api_key_reset_service(db)
        
        # Perform admin reset (bypasses password validation)
        result = await api_service.admin_reset_tenant_api_key(
            tenant_id=tenant_id,
            reason=reset_request.reason
        )
        
        if result["success"]:
            # Enhanced audit with security context
            api_service.audit_api_key_reset(
                tenant_id=tenant_id,
                reset_by=f"admin:{admin_identifier}",
                reason=reset_request.reason or "Admin-initiated reset",
                verification_method="admin_override"
            )
            
            logger.info(
                f"🔧 Admin {admin_identifier} reset API key for tenant {tenant_id} "
                f"(bypassed password verification)"
            )
            
            # Add admin info to response
            result["reset_by"] = admin_identifier
            result["verification_method"] = "admin_override"
        
        return AdminAPIKeyResetResponse(**result)
        
    except Exception as e:
        logger.error(f"❌ Admin API key reset failed for tenant {tenant_id}: {str(e)}")
        return AdminAPIKeyResetResponse(
            success=False,
            error=f"Admin API key reset failed: {str(e)}",
            tenant_id=tenant_id,
            reset_by=getattr(current_user, 'username', 'unknown_admin'),
            verification_method="admin_override"
        )

@router.get("/tenants/{tenant_id}/api-key-info")
async def admin_get_tenant_api_key_info(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """
    Admin endpoint to get API key information for any tenant
    Enhanced with authentication method details
    """
    try:
        api_service = get_enhanced_api_key_reset_service(db)
        result = api_service.get_tenant_api_key_info(tenant_id)
        
        if result["success"]:
            # Add admin-specific info
            tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
            if tenant:
                # Check for recent password verification attempts (security monitoring)
                has_supabase = bool(tenant.supabase_user_id)
                has_local_creds = bool(
                    db.query(TenantCredentials).filter(
                        TenantCredentials.tenant_id == tenant_id
                    ).first()
                )
                
                result.update({
                    "admin_view": True,
                    "created_at": tenant.created_at.isoformat() if tenant.created_at else None,
                    "is_active": tenant.is_active,
                    "business_name": tenant.business_name,
                    "email": tenant.email,
                    "supabase_user_id": tenant.supabase_user_id,
                    "security_status": {
                        "has_supabase_auth": has_supabase,
                        "has_local_credentials": has_local_creds,
                        "authentication_methods_count": sum([has_supabase, has_local_creds])
                    }
                })
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Admin failed to get API key info for tenant {tenant_id}: {str(e)}")
        return {
            "success": False,
            "error": f"Failed to get API key info: {str(e)}"
        }

@router.post("/tenants/bulk-reset-api-keys", response_model=BulkAPIKeyResetResponse)
async def admin_bulk_reset_api_keys(
    bulk_request: BulkAPIKeyResetRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """
    Admin endpoint to reset API keys for multiple tenants at once
    Enhanced with better error handling and security logging
    """
    try:
        admin_identifier = getattr(current_user, 'username', None) or getattr(current_user, 'email', f'admin_{current_user.id}')
        api_service = get_enhanced_api_key_reset_service(db)
        
        successful_resets = []
        failed_resets = []
        errors = []
        
        logger.info(
            f"🔧 Admin {admin_identifier} starting bulk API key reset for "
            f"{len(bulk_request.tenant_ids)} tenants (SECURITY OPERATION)"
        )
        
        for tenant_id in bulk_request.tenant_ids:
            try:
                # Reset API key for this tenant
                result = await api_service.admin_reset_tenant_api_key(
                    tenant_id=tenant_id,
                    reason=bulk_request.reason or "Bulk admin reset"
                )
                
                if result["success"]:
                    successful_resets.append({
                        "tenant_id": tenant_id,
                        "tenant_name": result.get("tenant_name"),
                        "new_api_key": result.get("new_api_key"),
                        "old_api_key_masked": result.get("old_api_key_masked"),
                        "verification_method": "admin_override"
                    })
                    
                    # Enhanced audit for each successful reset
                    api_service.audit_api_key_reset(
                        tenant_id=tenant_id,
                        reset_by=f"admin_bulk:{admin_identifier}",
                        reason=bulk_request.reason or "Bulk admin reset",
                        verification_method="admin_override"
                    )
                else:
                    failed_resets.append({
                        "tenant_id": tenant_id,
                        "error": result.get("error", "Unknown error")
                    })
                    errors.append({
                        "tenant_id": tenant_id,
                        "error": result.get("error", "Unknown error")
                    })
                    
            except Exception as e:
                error_msg = f"Exception during reset: {str(e)}"
                failed_resets.append({
                    "tenant_id": tenant_id,
                    "error": error_msg
                })
                errors.append({
                    "tenant_id": tenant_id,
                    "error": error_msg
                })
                logger.error(f"❌ Failed to reset API key for tenant {tenant_id}: {e}")
        
        total_requested = len(bulk_request.tenant_ids)
        successful_count = len(successful_resets)
        failed_count = len(failed_resets)
        
        # Enhanced security logging for bulk operations
        logger.info(
            f"✅ BULK API KEY RESET COMPLETED: "
            f"Admin: {admin_identifier} | "
            f"Success: {successful_count}/{total_requested} | "
            f"Reason: {bulk_request.reason or 'Not specified'} | "
            f"Tenant IDs: {bulk_request.tenant_ids}"
        )
        
        return BulkAPIKeyResetResponse(
            success=successful_count > 0,
            message=f"Bulk reset completed: {successful_count} successful, {failed_count} failed",
            total_requested=total_requested,
            successful_resets=successful_count,
            failed_resets=failed_count,
            results=successful_resets,
            errors=errors
        )
        
    except Exception as e:
        logger.error(f"❌ Bulk API key reset failed: {str(e)}")
        return BulkAPIKeyResetResponse(
            success=False,
            message=f"Bulk reset failed: {str(e)}",
            total_requested=len(bulk_request.tenant_ids),
            successful_resets=0,
            failed_resets=len(bulk_request.tenant_ids),
            results=[],
            errors=[{"error": str(e)}]
        )

@router.get("/tenants/api-key-security-audit", response_model=SecurityAuditResponse)
async def get_api_key_security_audit(
    days: int = Query(30, description="Number of days to look back for audit"),
    include_auth_methods: bool = Query(True, description="Include authentication method analysis"),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """
    Enhanced security audit of API keys with authentication method analysis
    Provides insights into tenant security posture
    """
    try:
        admin_identifier = getattr(current_user, 'username', None) or getattr(current_user, 'email', f'admin_{current_user.id}')
        
        # Get all active tenants
        tenants = db.query(Tenant).filter(Tenant.is_active == True).all()
        
        # Security analysis
        security_summary = {
            "total_active_tenants": len(tenants),
            "tenants_with_supabase_auth": 0,
            "tenants_with_local_auth": 0,
            "tenants_with_both_auth": 0,
            "tenants_with_no_auth": 0,
            "tenants_with_api_keys": 0,
            "tenants_missing_api_keys": 0
        }
        
        tenant_details = []
        auth_method_breakdown = {
            "supabase_only": 0,
            "local_only": 0,
            "both_methods": 0,
            "no_methods": 0
        }
        
        for tenant in tenants:
            # Check authentication methods
            has_supabase = bool(tenant.supabase_user_id)
            has_local_creds = bool(
                db.query(TenantCredentials).filter(
                    TenantCredentials.tenant_id == tenant.id
                ).first()
            )
            has_api_key = bool(tenant.api_key)
            
            # Update counters
            if has_supabase:
                security_summary["tenants_with_supabase_auth"] += 1
            if has_local_creds:
                security_summary["tenants_with_local_auth"] += 1
            if has_supabase and has_local_creds:
                security_summary["tenants_with_both_auth"] += 1
                auth_method_breakdown["both_methods"] += 1
            elif has_supabase and not has_local_creds:
                auth_method_breakdown["supabase_only"] += 1
            elif has_local_creds and not has_supabase:
                auth_method_breakdown["local_only"] += 1
            else:
                security_summary["tenants_with_no_auth"] += 1
                auth_method_breakdown["no_methods"] += 1
            
            if has_api_key:
                security_summary["tenants_with_api_keys"] += 1
            else:
                security_summary["tenants_missing_api_keys"] += 1
            
            # Detailed tenant info for admin
            if include_auth_methods:
                tenant_details.append({
                    "tenant_id": tenant.id,
                    "tenant_name": tenant.name,
                    "business_name": tenant.business_name,
                    "email": tenant.email,
                    "api_key_masked": f"{tenant.api_key[:8]}...{tenant.api_key[-4:]}" if tenant.api_key else "Missing",
                    "has_supabase_auth": has_supabase,
                    "has_local_credentials": has_local_creds,
                    "auth_method_count": sum([has_supabase, has_local_creds]),
                    "security_score": calculate_tenant_security_score(has_supabase, has_local_creds, has_api_key),
                    "last_updated": tenant.updated_at.isoformat() if tenant.updated_at else None
                })
        
        # Generate security recommendations
        recommendations = generate_security_recommendations(security_summary, auth_method_breakdown)
        
        # Mock recent resets (in production, you'd have a proper audit log table)
        recent_resets = [
            {
                "info": "This is a simplified audit view. Consider implementing a dedicated audit log table for production use.",
                "recommendation": "Store detailed reset logs with timestamps, IP addresses, and verification methods"
            }
        ]
        
        # Log admin access to security audit
        logger.info(
            f"🔍 SECURITY AUDIT ACCESSED: "
            f"Admin: {admin_identifier} | "
            f"Period: {days} days | "
            f"Tenants analyzed: {len(tenants)}"
        )
        
        return SecurityAuditResponse(
            success=True,
            audit_period_days=days,
            total_tenants=len(tenants),
            security_summary={
                **security_summary,
                "auth_method_breakdown": auth_method_breakdown,
                "tenant_details": tenant_details if include_auth_methods else []
            },
            recent_resets=recent_resets,
            recommendations=recommendations
        )
        
    except Exception as e:
        logger.error(f"❌ Security audit failed: {str(e)}")
        return SecurityAuditResponse(
            success=False,
            audit_period_days=days,
            total_tenants=0,
            security_summary={},
            recent_resets=[],
            recommendations=[],
            error=f"Security audit failed: {str(e)}"
        )

def calculate_tenant_security_score(has_supabase: bool, has_local_creds: bool, has_api_key: bool) -> int:
    """
    Calculate a simple security score for a tenant (0-100)
    """
    score = 0
    
    # API key existence (40 points)
    if has_api_key:
        score += 40
    
    # Authentication methods (60 points total)
    if has_supabase and has_local_creds:
        score += 60  # Best: both methods available
    elif has_supabase or has_local_creds:
        score += 40  # Good: one method available
    # else: 0 points for no auth methods
    
    return score

def generate_security_recommendations(security_summary: Dict[str, Any], auth_breakdown: Dict[str, Any]) -> List[str]:
    """
    Generate security recommendations based on audit findings
    """
    recommendations = []
    
    if security_summary["tenants_missing_api_keys"] > 0:
        recommendations.append(
            f"🚨 {security_summary['tenants_missing_api_keys']} tenants are missing API keys. "
            "Use the migration utility to fix this."
        )
    
    if security_summary["tenants_with_no_auth"] > 0:
        recommendations.append(
            f"⚠️ {security_summary['tenants_with_no_auth']} tenants have no authentication methods. "
            "These tenants cannot reset their API keys safely."
        )
    
    if auth_breakdown["local_only"] > auth_breakdown["supabase_only"]:
        recommendations.append(
            "💡 Consider migrating local-only tenants to Supabase for better security and management."
        )
    
    if security_summary["tenants_with_both_auth"] < security_summary["total_active_tenants"] * 0.8:
        recommendations.append(
            "🔐 Consider enabling multiple authentication methods for better security redundancy."
        )
    
    # Always recommend regular rotation
    recommendations.append(
        "🔄 Implement regular API key rotation (every 90 days) for enhanced security."
    )
    
    recommendations.append(
        "📊 Consider implementing a dedicated audit log table for detailed security monitoring."
    )
    
    return recommendations

@router.post("/tenants/{tenant_id}/force-password-verification")
async def admin_test_tenant_password_verification(
    tenant_id: int,
    password_data: dict,  # {"password": "test_password"}
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """
    Admin endpoint to test tenant password verification
    Useful for troubleshooting authentication issues
    """
    try:
        admin_identifier = getattr(current_user, 'username', None) or getattr(current_user, 'email', f'admin_{current_user.id}')
        
        password = password_data.get("password")
        if not password:
            raise HTTPException(status_code=400, detail="Password is required")
        
        # Initialize the service
        api_service = get_enhanced_api_key_reset_service(db)
        
        # Test password verification
        verification_result = await api_service.verify_tenant_password(tenant_id, password)
        
        # Log admin testing activity
        logger.info(
            f"🔧 Admin {admin_identifier} tested password verification for tenant {tenant_id}: "
            f"Result: {verification_result['success']} | "
            f"Method: {verification_result.get('method', 'unknown')}"
        )
        
        return {
            "success": True,
            "admin_test": True,
            "tenant_id": tenant_id,
            "password_verification": verification_result,
            "tested_by": admin_identifier
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Admin password verification test failed: {str(e)}")
        return {
            "success": False,
            "error": f"Password verification test failed: {str(e)}"
        }
    


@router.get("/api-key-migration/audit", response_model=MigrationAuditResponse)
async def admin_audit_api_keys(
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """
    Admin endpoint to audit all tenant API keys for issues
    Shows duplicates, invalid formats, and missing keys
    """
    try:
        admin_identifier = getattr(current_user, 'username', None) or getattr(current_user, 'email', f'admin_{current_user.id}')
        
        # Initialize migration service
        from app.tenants.api_key_service import APIKeyMigrationService
        migration_service = APIKeyMigrationService(db)
        
        # Run comprehensive audit
        audit_result = migration_service.comprehensive_api_key_audit()
        
        # Log admin access
        logger.info(
            f"🔍 API Key Migration Audit: "
            f"Admin: {admin_identifier} | "
            f"Total tenants: {audit_result.get('summary', {}).get('total_tenants', 0)} | "
            f"Issues found: {len(audit_result.get('duplicate_details', [])) + len(audit_result.get('invalid_key_details', []))}"
        )
        
        if audit_result["success"]:
            return MigrationAuditResponse(**audit_result)
        else:
            return MigrationAuditResponse(
                success=False,
                summary={},
                duplicate_details=[],
                invalid_key_details=[],
                recommendations=[],
                error=audit_result.get("error")
            )
        
    except Exception as e:
        logger.error(f"❌ API key migration audit failed: {str(e)}")
        return MigrationAuditResponse(
            success=False,
            summary={},
            duplicate_details=[],
            invalid_key_details=[],
            recommendations=[],
            error=f"Audit failed: {str(e)}"
        )




@router.post("/tenant-security/bulk-reset", response_model=BulkTenantIDResetResponse)
async def bulk_reset_tenant_ids(
    bulk_request: BulkTenantIDResetRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """
    Admin endpoint to bulk reset all insecure tenant IDs
    ⚠️ DANGER: This operation modifies ALL foreign key references
    🔒 REQUIRES: Database backup before running with dry_run=false
    """
    try:
        admin_identifier = getattr(current_user, 'username', None) or getattr(current_user, 'email', f'admin_{current_user.id}')
        
        # Critical security warning for actual changes
        if not bulk_request.dry_run:
            logger.critical(
                f"🚨🚨🚨 CRITICAL DATABASE OPERATION: "
                f"Admin {admin_identifier} is performing BULK TENANT ID RESET! "
                f"This will modify ALL foreign key references in the database!"
            )
        else:
            logger.info(
                f"🔍 Bulk tenant ID reset preview: Admin {admin_identifier} (dry_run=true)"
            )
        
        # Initialize secure ID service
        secure_id_service = get_secure_tenant_id_service(db)
        
        # Perform bulk reset
        result = secure_id_service.bulk_reset_insecure_ids(
            dry_run=bulk_request.dry_run,
            batch_size=bulk_request.batch_size
        )
        
        # Enhanced logging based on result
        if result["success"]:
            action_type = "DRY RUN PREVIEW" if bulk_request.dry_run else "ACTUAL RESET"
            logger.info(
                f"✅ Bulk tenant ID reset {action_type} completed: "
                f"Admin: {admin_identifier} | "
                f"Total: {result['total_tenants']} | "
                f"Reset: {result['reset_count']} | "
                f"Failed: {result['failed_count']} | "
                f"Reason: {bulk_request.reason or 'Security upgrade'}"
            )
            
            # Add audit info to result
            result.update({
                "admin_who_performed": admin_identifier,
                "operation_reason": bulk_request.reason or "Bulk security upgrade"
            })
        else:
            logger.error(
                f"❌ Bulk tenant ID reset failed: "
                f"Admin: {admin_identifier} | "
                f"Error: {result.get('error')}"
            )
        
        return BulkTenantIDResetResponse(**result)
        
    except Exception as e:
        logger.error(f"❌ Bulk tenant ID reset failed: {str(e)}")
        return BulkTenantIDResetResponse(
            success=False,
            message=f"Bulk reset failed: {str(e)}",
            total_tenants=0,
            reset_count=0,
            failed_count=0,
            successful_resets=[],
            failed_resets=[],
            dry_run=bulk_request.dry_run,
            error=str(e)
        )

@router.get("/tenant-security/status")
async def get_tenant_security_status(
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """
    Admin endpoint to get quick tenant ID security status
    Lightweight version of the full audit
    """
    try:
        secure_id_service = get_secure_tenant_id_service(db)
        
        # Quick counts
        total_tenants = db.query(Tenant).count()
        active_tenants = db.query(Tenant).filter(Tenant.is_active == True).count()
        
        # Quick security check
        insecure_tenants = secure_id_service.find_insecure_tenant_ids()
        insecure_count = len(insecure_tenants)
        secure_count = total_tenants - insecure_count
        
        # Security percentage
        security_percentage = (secure_count / total_tenants * 100) if total_tenants > 0 else 100
        
        # Status determination
        if insecure_count == 0:
            status = "secure"
            message = "All tenant IDs are secure"
            priority = "low"
        elif insecure_count <= 5:
            status = "minor_issues"
            message = f"{insecure_count} tenants need ID security upgrade"
            priority = "medium"
        else:
            status = "needs_attention"
            message = f"{insecure_count} tenants have insecure sequential IDs"
            priority = "high"
        
        # Risk assessment
        high_risk_tenants = [t for t in insecure_tenants if t["tenant_id"] < 1000]
        
        return {
            "success": True,
            "status": status,
            "priority": priority,
            "message": message,
            "summary": {
                "total_tenants": total_tenants,
                "active_tenants": active_tenants,
                "secure_tenants": secure_count,
                "insecure_tenants": insecure_count,
                "security_percentage": round(security_percentage, 2),
                "high_risk_tenants": len(high_risk_tenants)
            },
            "recommendations": [
                "All tenant IDs are secure" if insecure_count == 0 else f"Upgrade {insecure_count} insecure tenant IDs",
                "Run full audit for detailed analysis" if insecure_count > 0 else None,
                "Use preview mode before applying changes" if insecure_count > 0 else None
            ],
            "next_actions": [
                "GET /admin/tenant-security/audit - Full security audit",
                "GET /admin/tenant-security/preview-reset - Preview changes",
                "POST /admin/tenant-security/bulk-reset - Apply security upgrade"
            ] if insecure_count > 0 else [],
            "security_score": {
                "score": round(security_percentage),
                "grade": "A" if security_percentage >= 95 else "B" if security_percentage >= 80 else "C" if security_percentage >= 60 else "D",
                "description": "Excellent" if security_percentage >= 95 else "Good" if security_percentage >= 80 else "Fair" if security_percentage >= 60 else "Poor"
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Tenant security status check failed: {str(e)}")
        return {
            "success": False,
            "status": "error",
            "message": f"Status check failed: {str(e)}",
            "summary": {},
            "recommendations": ["Contact system administrator"],
            "next_actions": []
        }

@router.get("/tenant-security/insecure-tenants")
async def list_insecure_tenants(
    limit: int = Query(50, description="Maximum number of results"),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """
    Admin endpoint to list tenants with insecure sequential IDs
    Useful for targeted security upgrades
    """
    try:
        admin_identifier = getattr(current_user, 'username', None) or getattr(current_user, 'email', f'admin_{current_user.id}')
        
        secure_id_service = get_secure_tenant_id_service(db)
        insecure_tenants = secure_id_service.find_insecure_tenant_ids()
        
        # Apply limit
        limited_tenants = insecure_tenants[:limit] if limit > 0 else insecure_tenants
        
        # Add additional security context
        for tenant in limited_tenants:
            tenant_id = tenant["tenant_id"]
            
            # Risk assessment
            if tenant_id < 100:
                tenant["risk_level"] = "critical"
                tenant["risk_description"] = "Extremely predictable ID"
            elif tenant_id < 1000:
                tenant["risk_level"] = "high"
                tenant["risk_description"] = "Highly predictable ID"
            elif tenant_id < 10000:
                tenant["risk_level"] = "medium"
                tenant["risk_description"] = "Moderately predictable ID"
            else:
                tenant["risk_level"] = "low"
                tenant["risk_description"] = "Somewhat predictable ID"
            
            # Security recommendations
            tenant["recommended_action"] = "Immediate ID reset required"
            tenant["can_be_reset"] = True
        
        logger.info(
            f"📋 Insecure tenants list accessed: "
            f"Admin: {admin_identifier} | "
            f"Found: {len(insecure_tenants)} | "
            f"Returned: {len(limited_tenants)}"
        )
        
        return {
            "success": True,
            "total_insecure": len(insecure_tenants),
            "returned_count": len(limited_tenants),
            "limit_applied": limit,
            "tenants": limited_tenants,
            "security_summary": {
                "critical_risk": len([t for t in insecure_tenants if t["tenant_id"] < 100]),
                "high_risk": len([t for t in insecure_tenants if 100 <= t["tenant_id"] < 1000]),
                "medium_risk": len([t for t in insecure_tenants if 1000 <= t["tenant_id"] < 10000]),
                "low_risk": len([t for t in insecure_tenants if t["tenant_id"] >= 10000])
            },
            "recommendations": [
                "Reset critical and high-risk tenant IDs immediately",
                "Schedule bulk reset for all insecure IDs",
                "Consider implementing additional security measures for low-ID tenants"
            ]
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to list insecure tenants: {str(e)}")
        return {
            "success": False,
            "error": f"Failed to list insecure tenants: {str(e)}",
            "tenants": []
        }

@router.post("/tenant-security/generate-test-id")
async def generate_test_secure_id(
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """
    Admin endpoint to test secure ID generation
    Useful for verifying the system works before bulk operations
    """
    try:
        secure_id_service = get_secure_tenant_id_service(db)
        
        # Generate multiple test IDs
        test_ids = []
        generation_times = []
        
        for i in range(5):
            import time
            start_time = time.time()
            
            test_id = secure_id_service.generate_unique_tenant_id()
            
            end_time = time.time()
            generation_time = (end_time - start_time) * 1000  # Convert to milliseconds
            
            test_ids.append({
                "test_number": i + 1,
                "generated_id": test_id,
                "is_9_digits": 100000000 <= test_id <= 999999999,
                "is_unique": secure_id_service.is_id_available(test_id),
                "generation_time_ms": round(generation_time, 2)
            })
            generation_times.append(generation_time)
        
        avg_generation_time = sum(generation_times) / len(generation_times)
        
        # Validation summary
        all_valid = all(t["is_9_digits"] and t["is_unique"] for t in test_ids)
        
        return {
            "success": True,
            "test_results": {
                "all_ids_valid": all_valid,
                "generated_count": len(test_ids),
                "average_generation_time_ms": round(avg_generation_time, 2),
                "system_performance": "excellent" if avg_generation_time < 10 else "good" if avg_generation_time < 50 else "slow"
            },
            "test_ids": test_ids,
            "validation": {
                "format_valid": all(t["is_9_digits"] for t in test_ids),
                "uniqueness_valid": all(t["is_unique"] for t in test_ids),
                "performance_acceptable": avg_generation_time < 100
            },
            "recommendation": "System ready for bulk operations" if all_valid and avg_generation_time < 100 else "Review system performance before bulk operations"
        }
        
    except Exception as e:
        logger.error(f"❌ Secure ID generation test failed: {str(e)}")
        return {
            "success": False,
            "error": f"Test failed: {str(e)}",
            "recommendation": "Fix issues before proceeding with bulk operations"
        }