# app/fine_tuning/models.py
"""
Lightweight models for autonomous fine-tuning system
Zero complexity, maximum performance
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Float, Boolean, JSON, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class LearningPattern(Base):
    """Stores learned conversation patterns for continuous improvement"""
    __tablename__ = "learning_patterns"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True)
    pattern_type = Column(String(50), index=True)  # 'failed_response', 'successful_resolution', 'escalation_trigger'
    user_message_pattern = Column(Text)  # What users say
    bot_response_pattern = Column(Text, nullable=True)  # What bot said
    improved_response = Column(Text, nullable=True)  # Better response learned
    success_rate = Column(Float, default=0.0)  # How well this pattern works
    usage_count = Column(Integer, default=0)  # How many times applied
    confidence_score = Column(Float, default=0.0)  # Confidence in this learning
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    last_used = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True, index=True)
    
    # Relationships
    tenant = relationship("Tenant")

class TrainingMetrics(Base):
    """Tracks training performance and system improvement"""
    __tablename__ = "training_metrics"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True)
    training_cycle = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    conversations_analyzed = Column(Integer, default=0)
    patterns_learned = Column(Integer, default=0)
    responses_improved = Column(Integer, default=0)
    escalation_rate_before = Column(Float, nullable=True)  # Before training
    escalation_rate_after = Column(Float, nullable=True)   # After training
    feedback_score_improvement = Column(Float, default=0.0)
    processing_time_seconds = Column(Float, default=0.0)
    errors_encountered = Column(Integer, default=0)
    training_data = Column(JSON, nullable=True)  # Store additional metrics
    
    # Relationships
    tenant = relationship("Tenant")

class AutoImprovement(Base):
    """Tracks automatic improvements made to the system"""
    __tablename__ = "auto_improvements"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True)
    improvement_type = Column(String(50), index=True)  # 'faq_created', 'response_updated', 'pattern_added'
    trigger_pattern = Column(Text)  # What triggered this improvement
    old_response = Column(Text, nullable=True)  # Previous response
    new_response = Column(Text)  # Improved response
    effectiveness_score = Column(Float, default=0.0)  # How effective the improvement is
    conversations_affected = Column(Integer, default=0)  # How many conversations this impacts
    applied_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    is_active = Column(Boolean, default=True, index=True)
    rollback_data = Column(JSON, nullable=True)  # Data needed to rollback if improvement fails
    
    # Relationships
    tenant = relationship("Tenant")


class ConversationAnalysis(Base):
    """Tracks conversation sentiment and confusion signals"""
    __tablename__ = "conversation_analysis"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True)
    session_id = Column(String(50), index=True)
    message_id = Column(Integer, ForeignKey("chat_messages.id"))
    sentiment_score = Column(Float, default=0.0)  # -1 to 1
    confusion_detected = Column(Boolean, default=False)
    satisfaction_level = Column(String(20))  # 'positive', 'neutral', 'negative'
    confidence_signals = Column(JSON, nullable=True)  # Store detected signals
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    tenant = relationship("Tenant")

class ResponseConfidence(Base):
    """Tracks bot response confidence scores"""
    __tablename__ = "response_confidence"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True)
    session_id = Column(String(50), index=True)
    message_id = Column(Integer, ForeignKey("chat_messages.id"))
    bot_response = Column(Text)
    confidence_score = Column(Float, default=0.0)  # 0 to 1
    uncertainty_reasons = Column(JSON, nullable=True)  # Why confidence is low
    needs_improvement = Column(Boolean, default=False, index=True)
    improved_response = Column(Text, nullable=True)
    improvement_applied = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    tenant = relationship("Tenant")

class ProactiveLearning(Base):
    """Tracks A/B testing and proactive improvements"""
    __tablename__ = "proactive_learning"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True)
    pattern_trigger = Column(Text, index=True)
    response_a = Column(Text)  # Original response
    response_b = Column(Text)  # Alternative response
    a_success_count = Column(Integer, default=0)
    b_success_count = Column(Integer, default=0)
    a_failure_count = Column(Integer, default=0)
    b_failure_count = Column(Integer, default=0)
    winner_response = Column(Text, nullable=True)
    test_status = Column(String(20), default='active')  # 'active', 'completed'
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    tenant = relationship("Tenant")