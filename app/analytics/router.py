# app/analytics/router.py
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from datetime import datetime, timedelta
from collections import Counter
import json

from app.database import get_db
from app.tenants.models import Tenant
from app.chatbot.models import ChatSession, ChatMessage

router = APIRouter()

# Helper function to get tenant from API key
def get_tenant_from_api_key(api_key: str, db: Session):
    tenant = db.query(Tenant).filter(Tenant.api_key == api_key, Tenant.is_active == True).first()
    if not tenant:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return tenant

@router.get("/overview")
async def get_analytics_overview(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Get an overview of chatbot metrics for the tenant
    """
    # Get tenant from API key
    tenant = get_tenant_from_api_key(api_key, db)
    tenant_id = tenant.id
    
    # Get total number of sessions
    total_sessions = db.query(ChatSession).filter(
        ChatSession.tenant_id == tenant_id
    ).count()
    
    # Get active sessions
    active_sessions = db.query(ChatSession).filter(
        ChatSession.tenant_id == tenant_id,
        ChatSession.is_active == True
    ).count()
    
    # Get total messages
    total_messages = db.query(ChatMessage).join(
        ChatSession, ChatMessage.session_id == ChatSession.id
    ).filter(
        ChatSession.tenant_id == tenant_id
    ).count()
    
    # Get user messages count
    user_messages = db.query(ChatMessage).join(
        ChatSession, ChatMessage.session_id == ChatSession.id
    ).filter(
        ChatSession.tenant_id == tenant_id,
        ChatMessage.is_from_user == True
    ).count()
    
    # Get bot messages count
    bot_messages = db.query(ChatMessage).join(
        ChatSession, ChatMessage.session_id == ChatSession.id
    ).filter(
        ChatSession.tenant_id == tenant_id,
        ChatMessage.is_from_user == False
    ).count()
    
    # Get average messages per session
    avg_messages_per_session = total_messages / total_sessions if total_sessions > 0 else 0
    
    return {
        "total_sessions": total_sessions,
        "active_sessions": active_sessions,
        "total_messages": total_messages,
        "user_messages": user_messages,
        "bot_messages": bot_messages,
        "avg_messages_per_session": round(avg_messages_per_session, 2)
    }

@router.get("/sessions")
async def get_chat_sessions(
    limit: int = 10,
    offset: int = 0,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Get list of chat sessions with basic metrics
    """
    # Get tenant from API key
    tenant = get_tenant_from_api_key(api_key, db)
    tenant_id = tenant.id
    
    # Get sessions with message counts
    sessions = []
    query = db.query(ChatSession).filter(
        ChatSession.tenant_id == tenant_id
    ).order_by(
        ChatSession.created_at.desc()
    ).offset(offset).limit(limit).all()
    
    for session in query:
        # Count messages
        message_count = db.query(ChatMessage).filter(
            ChatMessage.session_id == session.id
        ).count()
        
        # Get first and last message time
        first_message = db.query(ChatMessage).filter(
            ChatMessage.session_id == session.id
        ).order_by(ChatMessage.created_at.asc()).first()
        
        last_message = db.query(ChatMessage).filter(
            ChatMessage.session_id == session.id
        ).order_by(ChatMessage.created_at.desc()).first()
        
        # Calculate session duration
        duration = None
        if first_message and last_message:
            duration_seconds = (last_message.created_at - first_message.created_at).total_seconds()
            duration = str(timedelta(seconds=int(duration_seconds)))
        
        sessions.append({
            "session_id": session.session_id,
            "user_identifier": session.user_identifier,
            "is_active": session.is_active,
            "created_at": session.created_at.isoformat(),
            "message_count": message_count,
            "duration": duration
        })
    
    # Get total count for pagination
    total_sessions = db.query(ChatSession).filter(
        ChatSession.tenant_id == tenant_id
    ).count()
    
    return {
        "total": total_sessions,
        "limit": limit,
        "offset": offset,
        "sessions": sessions
    }

@router.get("/time-analysis")
async def get_time_analysis(
    days: int = 7,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Get time-based analysis of chat activity
    """
    # Get tenant from API key
    tenant = get_tenant_from_api_key(api_key, db)
    tenant_id = tenant.id
    
    # Calculate date range
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    # Get sessions in date range
    sessions = db.query(ChatSession).filter(
        ChatSession.tenant_id == tenant_id,
        ChatSession.created_at >= start_date,
        ChatSession.created_at <= end_date
    ).all()
    
    # Prepare data structures
    daily_sessions = {}
    hourly_distribution = [0] * 24
    
    for session in sessions:
        # Daily count
        day = session.created_at.date().isoformat()
        if day not in daily_sessions:
            daily_sessions[day] = 0
        daily_sessions[day] += 1
        
        # Hourly distribution
        hour = session.created_at.hour
        hourly_distribution[hour] += 1
    
    # Fill in missing days
    current_date = start_date.date()
    while current_date <= end_date.date():
        day_str = current_date.isoformat()
        if day_str not in daily_sessions:
            daily_sessions[day_str] = 0
        current_date += timedelta(days=1)
    
    # Convert to sorted list for the response
    daily_data = [{"date": k, "count": v} for k, v in sorted(daily_sessions.items())]
    hourly_data = [{"hour": i, "count": hourly_distribution[i]} for i in range(24)]
    
    return {
        "daily_sessions": daily_data,
        "hourly_distribution": hourly_data
    }

@router.get("/common-questions")
async def get_common_questions(
    limit: int = 10,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Get most common user questions/messages
    """
    # Get tenant from API key
    tenant = get_tenant_from_api_key(api_key, db)
    tenant_id = tenant.id
    
    # Get all user messages
    messages = db.query(ChatMessage).join(
        ChatSession, ChatMessage.session_id == ChatSession.id
    ).filter(
        ChatSession.tenant_id == tenant_id,
        ChatMessage.is_from_user == True
    ).all()
    
    # Simple frequency analysis (could be improved with NLP for clustering similar questions)
    message_texts = [msg.content for msg in messages]
    counter = Counter(message_texts)
    
    # Get most common
    common_questions = [{"text": text, "count": count} 
                      for text, count in counter.most_common(limit)]
    
    return {
        "common_questions": common_questions
    }

@router.get("/session/{session_id}")
async def get_session_details(
    session_id: str,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific chat session
    """
    # Get tenant from API key
    tenant = get_tenant_from_api_key(api_key, db)
    tenant_id = tenant.id
    
    # Get session
    session = db.query(ChatSession).filter(
        ChatSession.session_id == session_id,
        ChatSession.tenant_id == tenant_id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Get messages
    messages = db.query(ChatMessage).filter(
        ChatMessage.session_id == session.id
    ).order_by(ChatMessage.created_at.asc()).all()
    
    # Calculate metrics
    first_message_time = messages[0].created_at if messages else None
    last_message_time = messages[-1].created_at if messages else None
    
    duration = None
    if first_message_time and last_message_time:
        duration_seconds = (last_message_time - first_message_time).total_seconds()
        duration = str(timedelta(seconds=int(duration_seconds)))
    
    user_message_count = sum(1 for msg in messages if msg.is_from_user)
    bot_message_count = sum(1 for msg in messages if not msg.is_from_user)
    
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
        "user_identifier": session.user_identifier,
        "is_active": session.is_active,
        "created_at": session.created_at.isoformat(),
        "message_count": len(messages),
        "user_message_count": user_message_count,
        "bot_message_count": bot_message_count,
        "duration": duration,
        "messages": formatted_messages
    }