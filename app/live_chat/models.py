# app/live_chat/models.py - FINAL CLEAN VERSION
from sqlalchemy import Column, ForeignKey, Integer, String, Text, DateTime, Boolean, Enum, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
from datetime import datetime
import enum

class AgentStatus(str, enum.Enum):
    ONLINE = "online"
    BUSY = "busy"
    AWAY = "away"
    OFFLINE = "offline"

class ChatStatus(str, enum.Enum):
    WAITING = "waiting"
    ACTIVE = "active"
    RESOLVED = "resolved"
    ABANDONED = "abandoned"
    TRANSFERRED = "transferred"
    ESCALATED = "escalated"

class MessageType(str, enum.Enum):
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    SYSTEM = "system"
    HANDOFF = "handoff"

class Agent(Base):
    """Customer support agents for each tenant - NO USER RELATIONSHIP"""
    __tablename__ = "agents"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    
    # 🚫 REMOVED: user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Agent details
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    avatar_url = Column(String, nullable=True)
    department = Column(String, nullable=True, default="general")
    skills = Column(Text, nullable=True)
    
    # Status and availability
    status = Column(Enum(AgentStatus), default=AgentStatus.OFFLINE)
    is_active = Column(Boolean, default=True)
    max_concurrent_chats = Column(Integer, default=3)
    current_chat_count = Column(Integer, default=0)
    
    # Metrics
    total_chats_handled = Column(Integer, default=0)
    average_response_time = Column(Integer, default=0)
    customer_satisfaction_rating = Column(Float, default=0.0)
    
    # Timestamps
    last_seen = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 🚫 REMOVED: user = relationship("User", back_populates="agent", uselist=False)

    tenant = relationship("Tenant", back_populates="agents")
    
    # Safe relationships only
    live_chats = relationship("LiveChat", back_populates="agent")
    messages = relationship("LiveChatMessage", back_populates="agent")

class LiveChat(Base):
    """Live chat sessions between users and agents"""
    __tablename__ = "live_chats"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, unique=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    
    # User information
    user_identifier = Column(String, index=True, nullable=False)
    user_name = Column(String, nullable=True)
    user_email = Column(String, nullable=True)
    platform = Column(String, default="web")
    
    # Agent assignment
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    assigned_at = Column(DateTime(timezone=True), nullable=True)
    
    # Chat metadata
    status = Column(Enum(ChatStatus), default=ChatStatus.WAITING)
    subject = Column(String, nullable=True)
    priority = Column(String, default="normal")
    department = Column(String, nullable=True)
    
    # Bot integration
    chatbot_session_id = Column(String, nullable=True)
    handoff_reason = Column(Text, nullable=True)
    bot_context = Column(Text, nullable=True)
    
    # Timing and metrics
    queue_time = Column(Integer, default=0)
    first_response_time = Column(Integer, nullable=True)
    resolution_time = Column(Integer, nullable=True)
    customer_satisfaction = Column(Integer, nullable=True)
    
    # Timestamps
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    ended_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    tenant = relationship("Tenant", back_populates="live_chats")
    agent = relationship("Agent", back_populates="live_chats")
    messages = relationship("LiveChatMessage", back_populates="chat", cascade="all, delete-orphan")

class LiveChatMessage(Base):
    """Messages in live chat sessions"""
    __tablename__ = "live_chat_messages"
    
    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("live_chats.id"), nullable=False)
    
    # Message content
    content = Column(Text, nullable=False)
    message_type = Column(Enum(MessageType), default=MessageType.TEXT)
    file_url = Column(String, nullable=True)
    
    # Sender information
    is_from_user = Column(Boolean, default=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    sender_name = Column(String, nullable=True)
    
    # Message metadata
    is_internal = Column(Boolean, default=False)
    read_by_user = Column(Boolean, default=False)
    read_by_agent = Column(Boolean, default=False)
    read_at = Column(DateTime(timezone=True), nullable=True)
    
    # Platform-specific data
    platform_message_id = Column(String, nullable=True)
    platform_metadata = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    chat = relationship("LiveChat", back_populates="messages")
    agent = relationship("Agent", back_populates="messages")

class AgentSession(Base):
    """Track agent login sessions and availability"""
    __tablename__ = "agent_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    
    # Session details
    session_token = Column(String, unique=True, index=True)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    
    # Status tracking
    status = Column(Enum(AgentStatus), default=AgentStatus.ONLINE)
    last_activity = Column(DateTime(timezone=True), server_default=func.now())
    
    # Timestamps
    logged_in_at = Column(DateTime(timezone=True), server_default=func.now())
    logged_out_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    agent = relationship("Agent")

class ChatQueue(Base):
    """Queue management for incoming chats"""
    __tablename__ = "chat_queue"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    chat_id = Column(Integer, ForeignKey("live_chats.id"), nullable=False, unique=True)
    
    # Queue details
    position = Column(Integer, nullable=False)
    estimated_wait_time = Column(Integer, nullable=True)
    department = Column(String, nullable=True)
    priority = Column(String, default="normal")
    
    # Assignment preferences
    preferred_agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    required_skills = Column(Text, nullable=True)
    
    # Timestamps
    queued_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    chat = relationship("LiveChat")
    preferred_agent = relationship("Agent")