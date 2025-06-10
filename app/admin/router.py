# app/admin/router.py
from fastapi import APIRouter, Depends, HTTPException, Header, Query
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