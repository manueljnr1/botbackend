from sqlalchemy import Column, ForeignKey, Integer, String, Text, DateTime, Boolean, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, unique=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"))
    user_identifier = Column(String, index=True)  # Could be email, phone, etc.
    language_code = Column(String(10), default="en")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
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


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"))
    content = Column(Text)
    translated_content = Column(Text, nullable=True)  # Add translated content
    source_language = Column(String(10), nullable=True)  # Source language code
    target_language = Column(String(10), nullable=True)  # Target language code (if translated)
    is_from_user = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    session = relationship("ChatSession", back_populates="messages")
