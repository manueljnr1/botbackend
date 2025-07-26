from sqlalchemy import Column, ForeignKey, Integer, String, Text, DateTime, Boolean, JSON, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum








class ChatSession(Base):
    __tablename__ = "chat_sessions"

    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, unique=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True)
    user_identifier = Column(String, index=True)  # Could be email, phone, etc.
    language_code = Column(String(10), default="en")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)  # Add index
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), index=True)
    user_email = Column(String, nullable=True) 
    session_metadata = Column(JSON, nullable=True)
    
    # === FIX START ===
    # Add the missing fields for the smart feedback system
    email_captured_at = Column(DateTime, nullable=True)
    email_expires_at = Column(DateTime, nullable=True)
    # === FIX END ===

    # Relationships
    tenant = relationship("Tenant", back_populates="chat_sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")

    # Discord integration fields
    discord_channel_id = Column(String, nullable=True)
    discord_user_id = Column(String, nullable=True)
    discord_guild_id = Column(String, nullable=True)
    platform = Column(String, default="web")  # web, discord, etc.


    user_country = Column(String, nullable=True)
    user_city = Column(String, nullable=True) 
    user_region = Column(String, nullable=True)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), index=True)
    content = Column(Text)
    translated_content = Column(Text, nullable=True)  # Add translated content
    source_language = Column(String(10), nullable=True)  # Source language code
    target_language = Column(String(10), nullable=True)  # Target language code (if translated)
    is_from_user = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Relationships
    session = relationship("ChatSession", back_populates="messages")







class EscalationStatus(enum.Enum):
    PENDING = "pending"
    ACTIVE = "active" 
    RESOLVED = "resolved"
    CLOSED = "closed"



class Escalation(Base):
    __tablename__ = "escalations"
    
    id = Column(Integer, primary_key=True, index=True)
    escalation_id = Column(String, unique=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"))
    session_id = Column(String, ForeignKey("chat_sessions.session_id"))
    user_identifier = Column(String, index=True)
    
    # Context & details
    reason = Column(String(100))
    original_issue = Column(Text)
    conversation_summary = Column(Text)
    
    # Status & communication
    status = Column(String(20), default="pending")
    team_notified = Column(Boolean, default=False)
    team_email_id = Column(String, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime, nullable=True)
    
    # Relationships
    tenant = relationship("Tenant")
    session = relationship("ChatSession")
    messages = relationship("EscalationMessage", back_populates="escalation", cascade="all, delete-orphan")

class EscalationMessage(Base):
    __tablename__ = "escalation_messages"
    
    id = Column(Integer, primary_key=True, index=True)
    escalation_id = Column(Integer, ForeignKey("escalations.id"))
    content = Column(Text)
    from_team = Column(Boolean, default=False)
    sent_to_customer = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    escalation = relationship("Escalation", back_populates="messages")
