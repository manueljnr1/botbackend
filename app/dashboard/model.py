"""
Dashboard response models for tenant metrics and analytics
"""
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime

class TenantMetrics(BaseModel):
    """Metrics for tenant dashboard overview"""
    total_conversations: int
    total_messages: int
    knowledge_base_count: int
    faq_count: int
    active_sessions: int
    unique_users: int

class DailyMetric(BaseModel):
    """Metrics for a specific day"""
    date: str
    conversations: int
    messages: int

class PerformanceMetrics(BaseModel):
    """Performance metrics for tenant"""
    messages_per_conversation: float
    daily_metrics: List[DailyMetric]

class RecentConversation(BaseModel):
    """Information about a recent conversation"""
    session_id: str
    user_identifier: str
    started_at: str
    is_active: bool
    message_count: int
    first_message: Optional[str]
    last_message_time: Optional[str]

class CategoryCount(BaseModel):
    """Count for a specific category"""
    name: str
    count: int

class FAQMetrics(BaseModel):
    """Metrics about tenant FAQs"""
    total_count: int
    categories: List[CategoryCount]

class TypeCount(BaseModel):
    """Count for a specific document type"""
    type: str
    count: int

class KnowledgeBaseMetrics(BaseModel):
    """Metrics about tenant knowledge bases"""
    total_count: int
    by_type: List[TypeCount]