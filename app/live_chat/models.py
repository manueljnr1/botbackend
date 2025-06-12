from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Enum, Float, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum

class AgentStatus(str, enum.Enum):
    ONLINE = "online"
    BUSY = "busy"
    AWAY = "away"
    OFFLINE = "offline"

class ConversationStatus(str, enum.Enum):
    QUEUED = "queued"
    ACTIVE = "active"
    RESOLVED = "resolved"
    ABANDONED = "abandoned"

class MessageType(str, enum.Enum):
    TEXT = "text"
    SYSTEM = "system"
    HANDOFF = "handoff"

class Agent(Base):
    """Simplified agent model"""
    __tablename__ = "agents"
    
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    department = Column(String, default="general")
    status = Column(Enum(AgentStatus), default=AgentStatus.OFFLINE)
    is_active = Column(Boolean, default=True)
    max_concurrent_chats = Column(Integer, default=3)
    
    # Simple metrics
    total_conversations = Column(Integer, default=0)
    avg_response_time_seconds = Column(Integer, default=0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_seen = Column(DateTime(timezone=True))
    
    # Relationships
    tenant = relationship("Tenant", back_populates="agents")
    conversations = relationship("Conversation", back_populates="agent")

class Conversation(Base):
    """Live chat conversation session"""
    __tablename__ = "conversations"
    
    id = Column(Integer, primary_key=True)
    session_id = Column(String, unique=True, index=True)  # user-facing ID
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    
    # Customer info
    customer_id = Column(String, index=True)  # user_identifier
    customer_name = Column(String)
    customer_email = Column(String)
    platform = Column(String, default="web")
    
    # Assignment
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    
    # Status and timing
    status = Column(Enum(ConversationStatus), default=ConversationStatus.QUEUED)
    department = Column(String, default="general")
    subject = Column(String)
    
    # Bot context (JSON string)
    bot_session_id = Column(String)
    handoff_reason = Column(Text)
    bot_context = Column(Text)
    
    # Metrics
    queue_time_seconds = Column(Integer, default=0)
    first_response_time_seconds = Column(Integer)
    resolution_time_seconds = Column(Integer)
    satisfaction_rating = Column(Integer)  # 1-5
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    assigned_at = Column(DateTime(timezone=True))
    resolved_at = Column(DateTime(timezone=True))
    
    # Relationships
    tenant = relationship("Tenant", back_populates="conversations")
    agent = relationship("Agent", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")

class Message(Base):
    """Chat messages"""
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    
    content = Column(Text, nullable=False)
    message_type = Column(Enum(MessageType), default=MessageType.TEXT)
    
    # Sender info
    from_agent = Column(Boolean, default=False)  # True = agent, False = customer
    sender_name = Column(String)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    read_at = Column(DateTime(timezone=True))
    
    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    agent = relationship("Agent")