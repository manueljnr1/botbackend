from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import json
from app.database import get_db
from app.tenants.router import get_tenant_from_api_key
from app.analytics.analytics_service import AnalyticsService
from app.analytics.schemas import *

router = APIRouter()

# 1. CHAT TRACKING WITH FILTERS
@router.get("/conversations/filtered")
async def get_filtered_conversations(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get conversations with advanced filtering"""
    tenant = get_tenant_from_api_key(api_key, db)
    service = AnalyticsService(db)
    
    filters = {
        "start_date": datetime.fromisoformat(start_date) if start_date else None,
        "end_date": datetime.fromisoformat(end_date) if end_date else None,
        "session_id": session_id,
        "category": category
    }
    
    conversations = service.get_filtered_conversations(tenant.id, filters)
    
    return {
        "success": True,
        "total": len(conversations),
        "conversations": conversations,
        "filters_applied": {k: v for k, v in filters.items() if v is not None}
    }

# 2. LOCATION ANALYTICS
@router.get("/locations")
async def get_location_analytics(
    days: int = Query(30, ge=1, le=365),
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get user location analytics"""
    tenant = get_tenant_from_api_key(api_key, db)
    service = AnalyticsService(db)
    
    analytics = service.get_location_analytics(tenant.id, days)
    
    return {
        "success": True,
        "tenant_id": tenant.id,
        "period_days": days,
        "location_analytics": analytics
    }

# 3. TOPICS ANALYTICS
@router.get("/topics")
async def get_topics_analytics(
    days: int = Query(30, ge=1, le=365),
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get conversation topics analytics"""
    tenant = get_tenant_from_api_key(api_key, db)
    service = AnalyticsService(db)
    
    # Get recent sessions with analytics
    from app.analytics.models import ConversationAnalytics
    from sqlalchemy import func
    
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    analytics = db.query(ConversationAnalytics).filter(
        ConversationAnalytics.tenant_id == tenant.id,
        ConversationAnalytics.analyzed_at >= start_date,
        ConversationAnalytics.conversation_topics.isnot(None)
    ).all()
    
    # Aggregate topics
    all_topics = []
    for record in analytics:
        try:
            topics = json.loads(record.conversation_topics)
            all_topics.extend(topics)
        except:
            continue
    
    from collections import Counter
    topic_counts = Counter(all_topics)
    
    return {
        "success": True,
        "period_days": days,
        "total_conversations_analyzed": len(analytics),
        "top_topics": [
            {"topic": topic, "count": count}
            for topic, count in topic_counts.most_common(20)
        ]
    }

# 4. CATEGORIES ANALYTICS
@router.get("/categories")
async def get_categories_analytics(
    days: int = Query(30, ge=1, le=365),
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get conversation categories analytics"""
    tenant = get_tenant_from_api_key(api_key, db)
    
    from app.analytics.models import ConversationAnalytics
    from sqlalchemy import func
    
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    categories = db.query(
        ConversationAnalytics.conversation_category,
        func.count(ConversationAnalytics.id).label('count'),
        func.avg(ConversationAnalytics.user_rating).label('avg_rating')
    ).filter(
        ConversationAnalytics.tenant_id == tenant.id,
        ConversationAnalytics.analyzed_at >= start_date
    ).group_by(ConversationAnalytics.conversation_category).all()
    
    category_data = [
        {
            "category": cat.conversation_category or "uncategorized",
            "count": cat.count,
            "avg_rating": round(cat.avg_rating, 2) if cat.avg_rating else None
        }
        for cat in categories
    ]
    
    return {
        "success": True,
        "period_days": days,
        "categories": category_data
    }

# 5. CONVERSATION RATINGS
@router.post("/conversations/{session_id}/rate")
async def rate_conversation(
    session_id: str,
    rating: int = Query(..., ge=1, le=5),
    feedback: Optional[str] = None,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Submit conversation rating"""
    tenant = get_tenant_from_api_key(api_key, db)
    service = AnalyticsService(db)
    
    success = service.submit_conversation_rating(session_id, rating, feedback)
    
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {
        "success": True,
        "message": "Rating submitted successfully",
        "session_id": session_id,
        "rating": rating
    }

# 6. CUSTOMER JOURNEY
@router.get("/journey/{user_identifier}")
async def get_customer_journey(
    user_identifier: str,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get customer journey mapping"""
    tenant = get_tenant_from_api_key(api_key, db)
    service = AnalyticsService(db)
    
    journey = service.analyze_customer_journey(user_identifier, tenant.id)
    
    return {
        "success": True,
        "customer_journey": journey
    }

# 7. SENTIMENT ANALYTICS
@router.get("/sentiment")
async def get_sentiment_analytics(
    days: int = Query(30, ge=1, le=365),
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get sentiment analytics"""
    tenant = get_tenant_from_api_key(api_key, db)
    
    from app.analytics.models import ConversationAnalytics
    from sqlalchemy import func
    
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    sentiments = db.query(
        ConversationAnalytics.conversation_sentiment,
        func.count(ConversationAnalytics.id).label('count')
    ).filter(
        ConversationAnalytics.tenant_id == tenant.id,
        ConversationAnalytics.analyzed_at >= start_date,
        ConversationAnalytics.conversation_sentiment.isnot(None)
    ).group_by(ConversationAnalytics.conversation_sentiment).all()
    
    sentiment_data = [
        {"sentiment": sent.conversation_sentiment, "count": sent.count}
        for sent in sentiments
    ]
    
    return {
        "success": True,
        "period_days": days,
        "sentiment_distribution": sentiment_data
    }

# BATCH ANALYSIS TRIGGER
@router.post("/analyze-sessions")
async def trigger_batch_analysis(
    limit: int = Query(50, ge=1, le=100),
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Trigger batch analysis for sessions without analytics"""
    tenant = get_tenant_from_api_key(api_key, db)
    service = AnalyticsService(db)
    
    service.analyze_all_sessions(tenant.id, limit)
    
    return {
        "success": True,
        "message": f"Batch analysis triggered for up to {limit} sessions"
    }