from sqlalchemy import Column, Integer, String, Text, DateTime, Float, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime

class ConversationAnalytics(Base):
    __tablename__ = "conversation_analytics"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("chat_sessions.session_id"), unique=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True)
    
    # Analytics fields
    conversation_category = Column(String, nullable=True)
    conversation_sentiment = Column(String, nullable=True)
    conversation_topics = Column(Text, nullable=True)  # JSON string
    user_rating = Column(Integer, nullable=True)  # 1-5 stars
    user_feedback = Column(Text, nullable=True)
    
    # Journey mapping
    user_journey_stage = Column(String, nullable=True)
    conversation_flow = Column(Text, nullable=True)  # JSON
    
    # Metadata
    analyzed_at = Column(DateTime, default=datetime.utcnow)
    analysis_version = Column(String, default="v1.0")
    
    # Relationships
    session = relationship("ChatSession", foreign_keys=[session_id])
    tenant = relationship("Tenant", foreign_keys=[tenant_id])