# app/admin/router.py
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.orm import Session
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

# Pydantic models
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

# Admin-only endpoints
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

@router.get("/tenants/overview")
async def get_tenant_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """
    Get overview of all tenants' usage (admin only)
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
        
        tenant_stats.append({
            "id": tenant.id,
            "name": tenant.name,
            "is_active": tenant.is_active,
            "kb_count": kb_count,
            "faq_count": faq_count,
            "session_count": session_count,
            "message_count": message_count,
            "active_users": active_users
        })
    
    return {
        "total_tenants": len(tenants),
        "active_tenants": sum(1 for t in tenants if t.is_active),
        "tenant_stats": tenant_stats
    }

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
    from app.knowledge_base.processor import DocumentProcessor
    processor = DocumentProcessor(kb.tenant_id)
    processor.delete_vector_store(kb.vector_store_id)
    
    # Delete the uploaded file
    import os
    if os.path.exists(kb.file_path):
        os.remove(kb.file_path)
    
    # Delete from database
    db.delete(kb)
    db.commit()
    
    return {"message": "Document deleted successfully"}

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