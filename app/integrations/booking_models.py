# app/integrations/booking_models.py

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime

class BookingRequest(Base):
    """Track booking requests made through the chatbot"""
    __tablename__ = "booking_requests"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"))
    session_id = Column(String, ForeignKey("chat_sessions.session_id"))
    user_identifier = Column(String)
    user_email = Column(String, nullable=True)
    user_name = Column(String, nullable=True)
    
    # Calendly info
    calendly_event_uri = Column(String, nullable=True)
    calendly_event_uuid = Column(String, nullable=True)
    booking_url = Column(String)
    
    # Status tracking
    status = Column(String, default="pending")  # pending, booked, cancelled
    booking_message = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    booked_at = Column(DateTime, nullable=True)
    
    # Relationships
    tenant = relationship("Tenant")