from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text, DateTime, Float, event
from sqlalchemy.orm import relationship
from sqlalchemy.orm import relationship, validates
from sqlalchemy.sql import func
from app.database import Base
from datetime import datetime, timedelta
import secrets
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.live_chat.models import Agent, Conversation

class Tenant(Base):
    __tablename__ = "tenants"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    business_name = Column(String, nullable=False, index=True) 
    description = Column(Text, nullable=True)
    api_key = Column(String, unique=True, index=True)
    is_active = Column(Boolean, default=True)
    email = Column(String, nullable=False, unique=True, index=True)  # ← Just 'email'
    supabase_user_id = Column(String, nullable=True, index=True)

    # 🆕 NEW: Subscription details
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now()) # Added server_default for creation as well, often useful
    
    #Email settings
    feedback_email = Column(String, nullable=True)      # Where tenant receives feedback emails
    from_email = Column(String, nullable=True)          # What users see as sender
    enable_feedback_system = Column(Boolean, default=True)
    feedback_notification_enabled = Column(Boolean, default=True)

     #  Super tenant 
    is_super_tenant = Column(Boolean, default=False)
    # 🆕 NEW: Can impersonate other tenants
    can_impersonate = Column(Boolean, default=False)
    # 🆕 NEW: Current impersonated tenant (if any)
    impersonating_tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True)

    # Integration fields
    discord_bot_token = Column(String, nullable=True)
    discord_application_id = Column(String, nullable=True)
    discord_enabled = Column(Boolean, default=False)
    discord_status_message = Column(String, nullable=True, default="Chatting with customers")

    slack_bot_token = Column(String, nullable=True)
    slack_signing_secret = Column(String, nullable=True)
    slack_app_id = Column(String, nullable=True)
    slack_client_id = Column(String, nullable=True)
    slack_client_secret = Column(String, nullable=True)
    slack_enabled = Column(Boolean, default=False)
    slack_team_id = Column(String, nullable=True)  # Slack workspace ID
    slack_bot_user_id = Column(String, nullable=True)  # Bot user ID in Slack

    # 🔒 NEW: Custom prompt management
    system_prompt = Column(Text, nullable=True)  # Custom system prompt
    system_prompt_validated = Column(Boolean, default=False)  # Has prompt been validated?
    system_prompt_updated_at = Column(DateTime, nullable=True)  # When was prompt last updated?
    
    # 🔒 NEW: Security settings
    security_level = Column(String(20), default="standard")  # standard, strict, custom
    allow_custom_prompts = Column(Boolean, default=True)  # Can tenant customize prompts?
    security_notifications_enabled = Column(Boolean, default=True)  # Send security alerts?

    # ===== RELATIONSHIPS (consolidated - no duplicates) =====
    
    # Core relationships
    users = relationship("User", back_populates="tenant")
    knowledge_bases = relationship("KnowledgeBase", back_populates="tenant", cascade="all, delete-orphan")
    faqs = relationship("FAQ", back_populates="tenant", cascade="all, delete-orphan")
    chat_sessions = relationship("ChatSession", back_populates="tenant", cascade="all, delete-orphan")
    
    # Credentials and subscription
    tenant_credentials = relationship("TenantCredentials", back_populates="tenant", uselist=False, overlaps="credentials", cascade="all, delete-orphan")
    credentials = relationship("TenantCredentials", back_populates="tenant", uselist=False, cascade="all, delete-orphan", overlaps="tenant_credentials")
    subscription = relationship("TenantSubscription", back_populates="tenant", uselist=False)
    
    # Live chat relationships (FIXED - no duplicates)
    agents = relationship("Agent", back_populates="tenant", cascade="all, delete-orphan")
    conversations = relationship("LiveChatConversation", back_populates="tenant", cascade="all, delete-orphan")
    live_chat_settings = relationship("LiveChatSettings", back_populates="tenant", uselist=False, cascade="all, delete-orphan")
    
    # Self-referential relationship for impersonation
    impersonating_tenant = relationship("Tenant", remote_side=[id], foreign_keys=[impersonating_tenant_id])

    @validates('email')
    def normalize_email(self, key, email):
        """Automatically normalize email to lowercase"""
        if email:
            return email.lower().strip()
        return email

# ADD this event listener AFTER your Tenant class definition
@event.listens_for(Tenant.email, 'set')
def normalize_tenant_email(target, value, oldvalue, initiator):
    """Event listener to normalize email before setting"""
    if value:
        return value.lower().strip()
    return value

class TenantPasswordReset(Base):
    __tablename__ = "tenant_password_resets"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    token = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    is_used = Column(Boolean, default=False)

    @classmethod
    def create_token(cls, tenant_id: int):
        """Create a new password reset token"""
        token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(hours=24)
        return cls(
            tenant_id=tenant_id,
            token=token,
            expires_at=expires_at
        )
    
    def is_valid(self):
        """Check if token is valid (not used and not expired)"""
        return not self.is_used and datetime.utcnow() < self.expires_at