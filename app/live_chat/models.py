# app/live_chat/models.py - FIXED VERSION
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text, DateTime, Float, JSON, Table
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
from datetime import datetime
from enum import Enum





agent_tags_association = Table(
    'agent_tags_association',
    Base.metadata,
    Column('agent_id', Integer, ForeignKey('agents.id'), primary_key=True),
    Column('tag_id', Integer, ForeignKey('agent_tags.id'), primary_key=True),
    Column('proficiency_level', Integer, default=3),  # 1-5 scale
    Column('assigned_at', DateTime, default=datetime.utcnow),
    Column('assigned_by', Integer, ForeignKey('agents.id'), nullable=True)
)

class ConversationStatus(str, Enum):
    QUEUED = "queued"
    ASSIGNED = "assigned"
    ACTIVE = "active"
    CLOSED = "closed"
    ABANDONED = "abandoned"
    TRANSFERRED = "transferred"


class AgentStatus(str, Enum):
    INVITED = "invited"
    ACTIVE = "active"
    OFFLINE = "offline"
    BUSY = "busy"
    AWAY = "away"
    REVOKED = "revoked"


class MessageType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    SYSTEM = "system"
    HANDOFF = "handoff"


class SenderType(str, Enum):
    CUSTOMER = "customer"
    AGENT = "agent"
    SYSTEM = "system"


class Agent(Base):
    __tablename__ = "agents"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    
    # Basic Information
    email = Column(String, nullable=False, index=True)
    full_name = Column(String, nullable=False)
    display_name = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    
    # Authentication & Invitation
    password_hash = Column(String, nullable=True)
    invite_token = Column(String, unique=True, nullable=True, index=True)
    invited_by = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    invited_at = Column(DateTime, default=datetime.utcnow)
    password_set_at = Column(DateTime, nullable=True)
    
    # Status & Activity
    status = Column(String, default=AgentStatus.INVITED)
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime, nullable=True)
    last_seen = Column(DateTime, nullable=True)
    is_online = Column(Boolean, default=False)
    
    # Performance Tracking
    total_conversations = Column(Integer, default=0)
    total_messages_sent = Column(Integer, default=0)
    average_response_time = Column(Float, nullable=True)
    customer_satisfaction_avg = Column(Float, nullable=True)
    conversations_today = Column(Integer, default=0)
    
    # Preferences & Settings
    notification_settings = Column(Text, nullable=True)
    timezone = Column(String, default="UTC")
    max_concurrent_chats = Column(Integer, default=3)
    auto_assign = Column(Boolean, default=True)
    
    # Work Schedule
    work_hours_start = Column(String, nullable=True)
    work_hours_end = Column(String, nullable=True)
    work_days = Column(String, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 🔧 FIXED RELATIONSHIPS - No more overlaps!
    # Primary tenant relationship
    tenant = relationship("Tenant", foreign_keys=[tenant_id])
    invited_by_user = relationship("Tenant", foreign_keys=[invited_by])
    assigned_conversations = relationship("LiveChatConversation", foreign_keys="LiveChatConversation.assigned_agent_id", back_populates="assigned_agent")
    previous_conversations = relationship("LiveChatConversation", foreign_keys="LiveChatConversation.previous_agent_id", back_populates="previous_agent")
    sessions = relationship("AgentSession", back_populates="agent", cascade="all, delete-orphan")
    messages = relationship("LiveChatMessage", back_populates="agent")
    tags = relationship("AgentTag", secondary=agent_tags_association, foreign_keys=[agent_tags_association.c.agent_id, agent_tags_association.c.tag_id], back_populates="agents")
    tag_performances = relationship("AgentTagPerformance", back_populates="agent", cascade="all, delete-orphan")



    # Specialization settings
    primary_specialization = Column(String(50), nullable=True)  # Main area of expertise
    secondary_specializations = Column(JSON, nullable=True)  # Additional skills
    skill_level = Column(Integer, default=3)  # Overall skill level 1-5
    accepts_overflow = Column(Boolean, default=True)  # Take non-specialized conversations when needed


    def __repr__(self):
        return f"<Agent {self.full_name} ({self.email})>"


class LiveChatConversation(Base):
    __tablename__ = "live_chat_conversations"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    
    # Customer Information
    customer_identifier = Column(String, nullable=False, index=True)
    customer_email = Column(String, nullable=True)
    customer_name = Column(String, nullable=True)
    customer_phone = Column(String, nullable=True)
    customer_ip = Column(String, nullable=True)
    customer_user_agent = Column(Text, nullable=True)
    
    # Handoff Context
    chatbot_session_id = Column(String, nullable=True, index=True)
    handoff_reason = Column(String, nullable=True)
    handoff_trigger = Column(String, nullable=True)
    handoff_context = Column(Text, nullable=True)
    original_question = Column(Text, nullable=True)
    
    # Queue Management
    status = Column(String, default=ConversationStatus.QUEUED, index=True)
    queue_position = Column(Integer, nullable=True)
    priority_level = Column(Integer, default=1)
    queue_entry_time = Column(DateTime, default=datetime.utcnow)
    
    # Agent Assignment
    assigned_agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    assigned_at = Column(DateTime, nullable=True)
    assignment_method = Column(String, nullable=True)
    previous_agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    
    # Timing & Metrics
    created_at = Column(DateTime, default=datetime.utcnow)
    first_response_at = Column(DateTime, nullable=True)
    last_activity_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)
    
    # Calculated Metrics
    wait_time_seconds = Column(Integer, nullable=True)
    response_time_seconds = Column(Integer, nullable=True)
    conversation_duration_seconds = Column(Integer, nullable=True)
    message_count = Column(Integer, default=0)
    agent_message_count = Column(Integer, default=0)
    customer_message_count = Column(Integer, default=0)
    
    # Customer Satisfaction
    customer_satisfaction = Column(Integer, nullable=True)
    customer_feedback = Column(Text, nullable=True)
    satisfaction_submitted_at = Column(DateTime, nullable=True)
    
    # Closure Information
    closed_by = Column(String, nullable=True)
    closure_reason = Column(String, nullable=True)
    resolution_status = Column(String, nullable=True)
    agent_notes = Column(Text, nullable=True)
    internal_notes = Column(Text, nullable=True)
    
    # Tags & Categories
    tags = Column(Text, nullable=True)
    category = Column(String, nullable=True)
    department = Column(String, nullable=True)
    
    # Timestamps
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 🔧 FIXED RELATIONSHIPS - Clear and specific
    tenant = relationship("Tenant")
    
    # Currently assigned agent
    assigned_agent = relationship(
        "Agent",
        foreign_keys=[assigned_agent_id],
        back_populates="assigned_conversations"
    )
    
    # Previously assigned agent (for transfers)
    previous_agent = relationship(
        "Agent",
        foreign_keys=[previous_agent_id],
        back_populates="previous_conversations"
    )
    
    # Messages in this conversation
    messages = relationship(
        "LiveChatMessage", 
        back_populates="conversation", 
        cascade="all, delete-orphan"
    )
    
    # Queue entry
    queue_entry = relationship(
        "ChatQueue", 
        back_populates="conversation", 
        uselist=False
    )
    
    def __repr__(self):
        return f"<LiveChatConversation {self.id} - {self.status}>"


class LiveChatMessage(Base):
    __tablename__ = "live_chat_messages"
    
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("live_chat_conversations.id"), nullable=False)
    
    # Message Content
    content = Column(Text, nullable=False)
    message_type = Column(String, default=MessageType.TEXT)
    raw_content = Column(Text, nullable=True)
    
    # Sender Information
    sender_type = Column(String, nullable=False)
    sender_id = Column(String, nullable=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    sender_name = Column(String, nullable=True)
    sender_avatar = Column(String, nullable=True)
    
    # Message Status & Timing
    sent_at = Column(DateTime, default=datetime.utcnow)
    delivered_at = Column(DateTime, nullable=True)
    read_at = Column(DateTime, nullable=True)
    edited_at = Column(DateTime, nullable=True)
    
    # Message Properties
    is_internal = Column(Boolean, default=False)
    is_edited = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)
    deleted_at = Column(DateTime, nullable=True)
    
    # File Attachments
    attachment_url = Column(String, nullable=True)
    attachment_name = Column(String, nullable=True)
    attachment_type = Column(String, nullable=True)
    attachment_size = Column(Integer, nullable=True)
    
    # System Messages
    system_event_type = Column(String, nullable=True)
    system_event_data = Column(Text, nullable=True)
    
    # Message Metadata
    client_message_id = Column(String, nullable=True)
    reply_to_message_id = Column(Integer, ForeignKey("live_chat_messages.id"), nullable=True)
    thread_id = Column(String, nullable=True)
    
    # 🔧 FIXED RELATIONSHIPS
    conversation = relationship("LiveChatConversation", back_populates="messages")
    agent = relationship("Agent", back_populates="messages")
    reply_to = relationship("LiveChatMessage", remote_side=[id])
    
    def __repr__(self):
        return f"<LiveChatMessage {self.id} from {self.sender_type}>"


class AgentSession(Base):
    __tablename__ = "agent_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    
    # Session Information
    session_id = Column(String, unique=True, nullable=False, index=True)
    status = Column(String, default=AgentStatus.OFFLINE)
    login_at = Column(DateTime, default=datetime.utcnow)
    logout_at = Column(DateTime, nullable=True)
    last_activity = Column(DateTime, default=datetime.utcnow)
    
    # Current Load & Capacity
    active_conversations = Column(Integer, default=0)
    max_concurrent_chats = Column(Integer, default=3)
    is_accepting_chats = Column(Boolean, default=True)
    
    # Performance Metrics
    messages_sent = Column(Integer, default=0)
    conversations_handled = Column(Integer, default=0)
    average_response_time = Column(Float, nullable=True)
    total_online_time = Column(Integer, default=0)
    
    # Technical Details
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    websocket_id = Column(String, nullable=True, unique=True)
    device_type = Column(String, nullable=True)
    browser = Column(String, nullable=True)
    
    # Status Messages
    status_message = Column(String, nullable=True)
    away_message = Column(String, nullable=True)
    
    # 🔧 FIXED RELATIONSHIP
    agent = relationship("Agent", back_populates="sessions")
    
    def __repr__(self):
        return f"<AgentSession {self.agent_id} - {self.status}>"


class ChatQueue(Base):
    __tablename__ = "chat_queue"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    conversation_id = Column(Integer, ForeignKey("live_chat_conversations.id"), nullable=False, unique=True)
    
    # Queue Management
    position = Column(Integer, nullable=False, index=True)
    priority = Column(Integer, default=1, index=True)
    estimated_wait_time = Column(Integer, nullable=True)
    
    # Assignment Rules
    preferred_agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    assignment_criteria = Column(Text, nullable=True)
    skills_required = Column(Text, nullable=True)
    language_preference = Column(String, nullable=True)
    
    # Queue Entry Details
    entry_reason = Column(String, nullable=True)
    queue_source = Column(String, nullable=True)
    
    # Timing
    queued_at = Column(DateTime, default=datetime.utcnow)
    assigned_at = Column(DateTime, nullable=True)
    removed_at = Column(DateTime, nullable=True)
    
    # Status
    status = Column(String, default="waiting")
    abandon_reason = Column(String, nullable=True)
    
    # Customer Context
    customer_message_preview = Column(Text, nullable=True)
    urgency_indicators = Column(Text, nullable=True)
    
    # 🔧 FIXED RELATIONSHIPS
    conversation = relationship("LiveChatConversation", back_populates="queue_entry")
    preferred_agent = relationship("Agent")
    
    def __repr__(self):
        return f"<ChatQueue position {self.position} for conversation {self.conversation_id}>"


class ConversationTransfer(Base):
    __tablename__ = "conversation_transfers"
    
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("live_chat_conversations.id"), nullable=False)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    
    # Transfer Details
    from_agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    to_agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    transfer_reason = Column(String, nullable=True)
    transfer_notes = Column(Text, nullable=True)
    
    # Transfer Status
    status = Column(String, default="pending")
    initiated_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    # Context
    conversation_summary = Column(Text, nullable=True)
    customer_context = Column(Text, nullable=True)
    
    # 🔧 FIXED RELATIONSHIPS
    conversation = relationship("LiveChatConversation")
    from_agent = relationship("Agent", foreign_keys=[from_agent_id])
    to_agent = relationship("Agent", foreign_keys=[to_agent_id])


class ConversationTag(Base):
    __tablename__ = "conversation_tags"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    name = Column(String, nullable=False)
    color = Column(String, nullable=True)
    description = Column(String, nullable=True)
    
    # Usage Stats
    usage_count = Column(Integer, default=0)
    created_by_agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 🔧 FIXED RELATIONSHIP
    created_by = relationship("Agent")


class LiveChatSettings(Base):
    __tablename__ = "live_chat_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, unique=True)
    
    # General Settings
    is_enabled = Column(Boolean, default=True)
    welcome_message = Column(Text, nullable=True)
    offline_message = Column(Text, nullable=True)
    pre_chat_form_enabled = Column(Boolean, default=False)
    post_chat_survey_enabled = Column(Boolean, default=True)
    
    # Queue Settings
    max_queue_size = Column(Integer, default=50)
    max_wait_time_minutes = Column(Integer, default=30)
    queue_timeout_message = Column(Text, nullable=True)
    
    # Auto-Assignment Settings
    auto_assignment_enabled = Column(Boolean, default=True)
    assignment_method = Column(String, default="round_robin")
    max_chats_per_agent = Column(Integer, default=3)
    
    # Business Hours
    business_hours_enabled = Column(Boolean, default=False)
    business_hours = Column(Text, nullable=True)
    timezone = Column(String, default="UTC")
    
    # Notification Settings
    email_notifications_enabled = Column(Boolean, default=True)
    escalation_email = Column(String, nullable=True)
    notification_triggers = Column(Text, nullable=True)
    
    # Branding
    widget_color = Column(String, default="#6d28d9")
    widget_position = Column(String, default="bottom-right")
    company_logo_url = Column(String, nullable=True)
    
    # Features
    file_upload_enabled = Column(Boolean, default=True)
    file_size_limit_mb = Column(Integer, default=10)
    allowed_file_types = Column(Text, nullable=True)
    
    # Security
    customer_info_retention_days = Column(Integer, default=365)
    require_email_verification = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 🔧 FIXED RELATIONSHIP
    tenant = relationship("Tenant")


class CustomerProfile(Base):
    """Customer profile for tracking returning visitors"""
    __tablename__ = "customer_profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    customer_identifier = Column(String, nullable=False, index=True)
    
    # Basic Information
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)
    total_conversations = Column(Integer, default=0)
    total_sessions = Column(Integer, default=0)
    
    # Preferences
    preferred_language = Column(String, nullable=True)
    time_zone = Column(String, nullable=True)
    preferred_contact_method = Column(String, nullable=True)
    
    # Analytics
    customer_satisfaction_avg = Column(Float, nullable=True)
    average_session_duration = Column(Integer, nullable=True)  # seconds
    total_messages_sent = Column(Integer, default=0)
    
    # Privacy & Compliance
    data_collection_consent = Column(Boolean, default=False)
    marketing_consent = Column(Boolean, default=False)
    last_consent_update = Column(DateTime, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class CustomerSession(Base):
    """Individual customer session tracking"""
    __tablename__ = "customer_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    customer_profile_id = Column(Integer, ForeignKey("customer_profiles.id"), nullable=False)
    session_id = Column(String, unique=True, nullable=False)
    
    # Session Details
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    
    # Technical Details
    ip_address = Column(String, nullable=True)
    user_agent = Column(Text, nullable=True)
    device_fingerprint = Column(String, nullable=True)
    
    # Geolocation
    country = Column(String, nullable=True)
    region = Column(String, nullable=True)
    city = Column(String, nullable=True)
    
    # Activity
    page_views = Column(Integer, default=0)
    conversations_started = Column(Integer, default=0)

class CustomerDevice(Base):
    """Device information for fingerprinting"""
    __tablename__ = "customer_devices"
    
    id = Column(Integer, primary_key=True, index=True)
    customer_profile_id = Column(Integer, ForeignKey("customer_profiles.id"), nullable=False)
    device_fingerprint = Column(String, nullable=False, index=True)
    
    # Device Details
    device_type = Column(String, nullable=True)  # mobile, tablet, desktop
    browser_name = Column(String, nullable=True)
    browser_version = Column(String, nullable=True)
    operating_system = Column(String, nullable=True)
    screen_resolution = Column(String, nullable=True)
    
    # Capabilities
    supports_websockets = Column(Boolean, default=True)
    supports_file_upload = Column(Boolean, default=True)
    supports_notifications = Column(Boolean, default=False)
    
    # Tracking
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)
    total_sessions = Column(Integer, default=1)

class CustomerPreferences(Base):
    """Customer preferences and settings"""
    __tablename__ = "customer_preferences"
    
    id = Column(Integer, primary_key=True, index=True)
    customer_profile_id = Column(Integer, ForeignKey("customer_profiles.id"), nullable=False)
    
    # Communication Preferences
    preferred_language = Column(String, default="en")
    preferred_agent_gender = Column(String, nullable=True)
    preferred_communication_style = Column(String, nullable=True)  # formal, casual, technical
    
    # Notification Preferences
    email_notifications = Column(Boolean, default=False)
    sms_notifications = Column(Boolean, default=False)
    browser_notifications = Column(Boolean, default=False)
    
    # Accessibility
    requires_accessibility_features = Column(Boolean, default=False)
    accessibility_preferences = Column(JSON, nullable=True)
    
    # Privacy
    data_retention_preference = Column(String, default="standard")  # minimal, standard, extended
    third_party_sharing_consent = Column(Boolean, default=False)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)



class AgentTag(Base):
    """Tags for agent skills and specializations"""
    __tablename__ = "agent_tags"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    
    # Tag Information
    name = Column(String(50), nullable=False, index=True)  # e.g., "billing", "refunds"
    display_name = Column(String(100), nullable=False)  # e.g., "Billing & Payments"
    category = Column(String(50), nullable=False, index=True)  # e.g., "financial", "technical", "general"
    description = Column(Text, nullable=True)
    
    # Visual Properties
    color = Column(String(7), default="#6366f1")  # Hex color code
    icon = Column(String(50), nullable=True)  # Icon identifier
    
    # Priority and Routing
    priority_weight = Column(Float, default=1.0)  # Higher = more important for routing
    is_active = Column(Boolean, default=True)
    
    # Auto-assignment Rules
    keywords = Column(JSON, nullable=True)  # Keywords that trigger this tag
    routing_rules = Column(JSON, nullable=True)  # Complex routing logic
    
    # Statistics
    total_conversations = Column(Integer, default=0)
    success_rate = Column(Float, default=0.0)
    average_satisfaction = Column(Float, default=0.0)
    
    # Metadata
    created_by = Column(Integer, ForeignKey("agents.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    tenant = relationship("Tenant")
    created_by_agent = relationship("Agent", foreign_keys=[created_by])
    
    # Many-to-many with agents
    agents = relationship("Agent", secondary=agent_tags_association, foreign_keys=[agent_tags_association.c.agent_id, agent_tags_association.c.tag_id], back_populates="tags")
    
    def __repr__(self):
        return f"<AgentTag {self.name} ({self.category})>"


class ConversationTagging(Base):
    """Track which tags were identified for conversations"""
    __tablename__ = "conversation_tagging"
    
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("live_chat_conversations.id"), nullable=False)
    tag_id = Column(Integer, ForeignKey("agent_tags.id"), nullable=False)
    
    # Detection Information
    confidence_score = Column(Float, default=0.0)  # 0.0 - 1.0
    detection_method = Column(String(50), nullable=False)  # "keyword", "ml", "manual"
    detected_keywords = Column(JSON, nullable=True)
    
    # Context
    message_text = Column(Text, nullable=True)  # Text that triggered detection
    message_id = Column(Integer, ForeignKey("live_chat_messages.id"), nullable=True)
    
    # Assignment Impact
    influenced_routing = Column(Boolean, default=False)
    routing_weight = Column(Float, default=0.0)
    
    # Validation
    human_verified = Column(Boolean, default=False)
    verified_by = Column(Integer, ForeignKey("agents.id"), nullable=True)
    verified_at = Column(DateTime, nullable=True)
    
    # Timestamps
    detected_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    conversation = relationship("LiveChatConversation")
    tag = relationship("AgentTag")
    message = relationship("LiveChatMessage")
    verified_by_agent = relationship("Agent", foreign_keys=[verified_by])


class AgentTagPerformance(Base):
    """Track agent performance for specific tags"""
    __tablename__ = "agent_tag_performance"
    
    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    tag_id = Column(Integer, ForeignKey("agent_tags.id"), nullable=False)
    
    # Performance Metrics
    total_conversations = Column(Integer, default=0)
    successful_resolutions = Column(Integer, default=0)
    average_resolution_time = Column(Float, default=0.0)  # in minutes
    customer_satisfaction_avg = Column(Float, default=0.0)
    
    # Time-based Performance
    conversations_last_30_days = Column(Integer, default=0)
    satisfaction_last_30_days = Column(Float, default=0.0)
    
    # Skill Development
    proficiency_level = Column(Integer, default=3)  # 1-5 scale
    improvement_trend = Column(Float, default=0.0)  # positive = improving
    
    # Training and Certification
    certified = Column(Boolean, default=False)
    certification_date = Column(DateTime, nullable=True)
    last_training_date = Column(DateTime, nullable=True)
    
    # Availability
    is_available_for_tag = Column(Boolean, default=True)
    max_concurrent_for_tag = Column(Integer, default=2)
    current_active_conversations = Column(Integer, default=0)
    
    # Metadata
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_conversation_date = Column(DateTime, nullable=True)
    
    # Relationships
    agent = relationship("Agent")
    tag = relationship("AgentTag")
    
    # Unique constraint
    __table_args__ = (
        {"extend_existing": True},
    )


class SmartRoutingLog(Base):
    """Log smart routing decisions for analysis and improvement"""
    __tablename__ = "smart_routing_log"
    
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("live_chat_conversations.id"), nullable=False)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    
    # Routing Decision
    assigned_agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    routing_method = Column(String(50), nullable=False)  # "smart_tags", "fallback", "manual"
    confidence_score = Column(Float, default=0.0)
    
    # Detected Tags and Context
    detected_tags = Column(JSON, nullable=True)  # [{tag_id, confidence, keywords}]
    customer_context = Column(JSON, nullable=True)  # Previous history, location, etc.
    available_agents = Column(JSON, nullable=True)  # Agents considered
    
    # Routing Logic
    scoring_breakdown = Column(JSON, nullable=True)  # How scores were calculated
    fallback_reason = Column(String(200), nullable=True)
    alternative_agents = Column(JSON, nullable=True)  # Other good options
    
    # Outcome Tracking
    customer_satisfaction = Column(Integer, nullable=True)  # 1-5 rating
    resolution_time_minutes = Column(Integer, nullable=True)
    was_transferred = Column(Boolean, default=False)
    transfer_reason = Column(String(200), nullable=True)
    
    # Analysis
    routing_accuracy = Column(Float, nullable=True)  # Calculated post-conversation
    success_factors = Column(JSON, nullable=True)
    improvement_suggestions = Column(JSON, nullable=True)
    
    # Timestamps
    routed_at = Column(DateTime, default=datetime.utcnow)
    conversation_ended_at = Column(DateTime, nullable=True)
    
    # Relationships
    conversation = relationship("LiveChatConversation")
    assigned_agent = relationship("Agent")
    tenant = relationship("Tenant")







