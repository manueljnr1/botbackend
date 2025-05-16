"""
Dashboard router for tenant metrics and analytics
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, distinct
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import datetime

from app.database import get_db
from app.auth.router import get_current_user
from app.auth.models import User
from app.tenants.models import Tenant
from app.knowledge_base.models import KnowledgeBase, FAQ
from app.chatbot.models import ChatSession, ChatMessage

router = APIRouter()

async def get_tenant_id_from_user(current_user: User) -> int:
    """Get tenant ID from the current user"""
    if current_user.is_admin and not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin user must specify tenant_id parameter"
        )
    return current_user.tenant_id

@router.get("/metrics")
async def get_tenant_metrics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get key metrics for the tenant dashboard
    
    Returns:
        - total_conversations: Number of chat sessions
        - total_messages: Number of messages exchanged
        - knowledge_base_count: Number of knowledge bases
        - knowledge_base_size: Total size of knowledge bases (document count)
        - faq_count: Number of FAQs
        - active_sessions: Number of active chat sessions
    """
    tenant_id = await get_tenant_id_from_user(current_user)
    
    # Get total conversations (chat sessions)
    total_conversations = db.query(func.count(ChatSession.id)) \
        .filter(ChatSession.tenant_id == tenant_id) \
        .scalar() or 0
    
    # Get total messages
    total_messages = db.query(func.count(ChatMessage.id)) \
        .join(ChatSession, ChatSession.id == ChatMessage.session_id) \
        .filter(ChatSession.tenant_id == tenant_id) \
        .scalar() or 0
    
    # Get knowledge base metrics
    knowledge_base_count = db.query(func.count(KnowledgeBase.id)) \
        .filter(KnowledgeBase.tenant_id == tenant_id) \
        .scalar() or 0
    
    # Get FAQ count
    faq_count = db.query(func.count(FAQ.id)) \
        .filter(FAQ.tenant_id == tenant_id) \
        .scalar() or 0
    
    # Get active sessions
    active_sessions = db.query(func.count(ChatSession.id)) \
        .filter(ChatSession.tenant_id == tenant_id, ChatSession.is_active == True) \
        .scalar() or 0
    
    # Get unique users
    unique_users = db.query(func.count(distinct(ChatSession.user_identifier))) \
        .filter(ChatSession.tenant_id == tenant_id) \
        .scalar() or 0
    
    return {
        "total_conversations": total_conversations,
        "total_messages": total_messages,
        "knowledge_base_count": knowledge_base_count,
        "faq_count": faq_count,
        "active_sessions": active_sessions,
        "unique_users": unique_users
    }

@router.get("/performance")
async def get_performance_metrics(
    days: int = 7,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get performance metrics for the tenant
    
    Args:
        days: Number of days to include in the metrics (default: 7)
        
    Returns:
        - average_response_time: Average time to generate a response
        - messages_per_conversation: Average number of messages per conversation
        - daily_metrics: Daily breakdown of conversations and messages
    """
    tenant_id = await get_tenant_id_from_user(current_user)
    
    # Calculate date range
    end_date = datetime.datetime.now()
    start_date = end_date - datetime.timedelta(days=days)
    
    # Get message count per session
    session_messages = db.query(
        ChatSession.id,
        func.count(ChatMessage.id).label('message_count')
    ).join(
        ChatMessage, ChatMessage.session_id == ChatSession.id
    ).filter(
        ChatSession.tenant_id == tenant_id,
        ChatSession.created_at >= start_date
    ).group_by(
        ChatSession.id
    ).all()
    
    # Calculate average messages per conversation
    if session_messages:
        messages_per_conversation = sum(sm.message_count for sm in session_messages) / len(session_messages)
    else:
        messages_per_conversation = 0
    
    # Get daily metrics
    daily_metrics = []
    for day_offset in range(days):
        day_date = end_date - datetime.timedelta(days=day_offset)
        day_start = day_date.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + datetime.timedelta(days=1)
        
        # Count conversations started on this day
        conversations = db.query(func.count(ChatSession.id)) \
            .filter(
                ChatSession.tenant_id == tenant_id,
                ChatSession.created_at >= day_start,
                ChatSession.created_at < day_end
            ) \
            .scalar() or 0
        
        # Count messages sent on this day
        messages = db.query(func.count(ChatMessage.id)) \
            .join(ChatSession, ChatSession.id == ChatMessage.session_id) \
            .filter(
                ChatSession.tenant_id == tenant_id,
                ChatMessage.created_at >= day_start,
                ChatMessage.created_at < day_end
            ) \
            .scalar() or 0
        
        daily_metrics.append({
            "date": day_start.strftime("%Y-%m-%d"),
            "conversations": conversations,
            "messages": messages
        })
    
    # Reverse to get chronological order
    daily_metrics.reverse()
    
    return {
        "messages_per_conversation": round(messages_per_conversation, 2),
        "daily_metrics": daily_metrics
    }

@router.get("/recent-conversations")
async def get_recent_conversations(
    limit: int = 5,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get recent conversations for the tenant
    
    Args:
        limit: Maximum number of conversations to return (default: 5)
    
    Returns:
        List of recent conversations with basic info
    """
    tenant_id = await get_tenant_id_from_user(current_user)
    
    # Get recent sessions
    recent_sessions = db.query(ChatSession) \
        .filter(ChatSession.tenant_id == tenant_id) \
        .order_by(ChatSession.created_at.desc()) \
        .limit(limit) \
        .all()
    
    result = []
    for session in recent_sessions:
        # Count messages in this session
        message_count = db.query(func.count(ChatMessage.id)) \
            .filter(ChatMessage.session_id == session.id) \
            .scalar() or 0
        
        # Get first and last message
        first_message = db.query(ChatMessage) \
            .filter(ChatMessage.session_id == session.id, ChatMessage.is_from_user == True) \
            .order_by(ChatMessage.created_at.asc()) \
            .first()
        
        last_message = db.query(ChatMessage) \
            .filter(ChatMessage.session_id == session.id) \
            .order_by(ChatMessage.created_at.desc()) \
            .first()
        
        result.append({
            "session_id": session.session_id,
            "user_identifier": session.user_identifier,
            "started_at": session.created_at.isoformat(),
            "is_active": session.is_active,
            "message_count": message_count,
            "first_message": first_message.content if first_message else None,
            "last_message_time": last_message.created_at.isoformat() if last_message else None
        })
    
    return result

@router.get("/faq-metrics")
async def get_faq_metrics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get metrics about tenant FAQs
    
    Returns:
        FAQ metrics including categories and counts
    """
    tenant_id = await get_tenant_id_from_user(current_user)
    
    # Get total FAQ count
    faq_count = db.query(func.count(FAQ.id)) \
        .filter(FAQ.tenant_id == tenant_id) \
        .scalar() or 0
    
    # Get FAQ categories (simple implementation - uses first word of question)
    faqs = db.query(FAQ.question) \
        .filter(FAQ.tenant_id == tenant_id) \
        .all()
    
    # Simple categorization by first word
    categories = {}
    for faq in faqs:
        # Use first word as a simple category
        if faq.question:
            category = faq.question.split()[0].lower() if faq.question.split() else "other"
            categories[category] = categories.get(category, 0) + 1
    
    # Convert to list for output
    category_list = [{"name": k, "count": v} for k, v in categories.items()]
    # Sort by count descending
    category_list.sort(key=lambda x: x["count"], reverse=True)
    
    return {
        "total_count": faq_count,
        "categories": category_list[:10]  # Return top 10 categories
    }

@router.get("/knowledge-base-metrics")
async def get_knowledge_base_metrics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get metrics about tenant knowledge bases
    
    Returns:
        Knowledge base metrics including types and counts
    """
    tenant_id = await get_tenant_id_from_user(current_user)
    
    # Get knowledge base count by document type
    kb_types = db.query(
        KnowledgeBase.document_type, 
        func.count(KnowledgeBase.id).label('count')
    ).filter(
        KnowledgeBase.tenant_id == tenant_id
    ).group_by(
        KnowledgeBase.document_type
    ).all()
    
    # Format the result
    result = {
        "total_count": sum(kb.count for kb in kb_types),
        "by_type": [{"type": kb.document_type.value, "count": kb.count} for kb in kb_types]
    }
    
    return result