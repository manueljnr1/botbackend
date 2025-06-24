# app/instagram/models.py
"""
Instagram Integration Database Models
Handles Instagram business account connections and messaging
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON
from sqlalchemy.orm import relationship, validates
from sqlalchemy.sql import func
from app.database import Base
from datetime import datetime
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.tenants.models import Tenant

class InstagramIntegration(Base):
    """Instagram integration configuration for tenants"""
    __tablename__ = "instagram_integrations"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), unique=True, index=True)
    
    # Meta App Configuration
    meta_app_id = Column(String, nullable=False)
    meta_app_secret = Column(String, nullable=False)  # Encrypted in production
    
    # Instagram Business Account Info
    instagram_business_account_id = Column(String, nullable=False, index=True)
    instagram_username = Column(String, nullable=False)
    
    # Facebook Page Connection (Required for Instagram API)
    facebook_page_id = Column(String, nullable=False, index=True)
    facebook_page_name = Column(String, nullable=True)
    
    # Access Tokens
    page_access_token = Column(Text, nullable=False)  # Long-lived token
    token_expires_at = Column(DateTime, nullable=True)
    
    # Webhook Configuration
    webhook_verify_token = Column(String, nullable=False)
    webhook_subscribed = Column(Boolean, default=False)
    webhook_subscription_fields = Column(JSON, nullable=True)  # ['messages', 'message_reactions']
    
    # Bot Configuration
    bot_enabled = Column(Boolean, default=True)
    bot_status = Column(String, default="active")  # active, inactive, error, setup
    
    # Settings
    auto_reply_enabled = Column(Boolean, default=True)
    business_verification_required = Column(Boolean, default=True)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_message_at = Column(DateTime, nullable=True)
    
    # Error tracking
    last_error = Column(Text, nullable=True)
    error_count = Column(Integer, default=0)
    
    # Relationships
    # tenant = relationship("Tenant", back_populates="instagram_integration")
    tenant = relationship("Tenant")
    conversations = relationship("InstagramConversation", back_populates="integration", cascade="all, delete-orphan")
    
    @validates('instagram_username')
    def validate_username(self, key, username):
        """Validate Instagram username format"""
        if username:
            # Remove @ if present and validate format
            clean_username = username.lstrip('@').lower()
            if not re.match(r'^[a-zA-Z0-9._]{1,30}$', clean_username):
                raise ValueError("Invalid Instagram username format")
            return clean_username
        return username
    
    def is_token_expired(self) -> bool:
        """Check if access token is expired"""
        if not self.token_expires_at:
            return False
        return datetime.utcnow() >= self.token_expires_at
    
    def get_status_info(self) -> dict:
        """Get comprehensive status information"""
        return {
            "bot_enabled": self.bot_enabled,
            "bot_status": self.bot_status,
            "webhook_subscribed": self.webhook_subscribed,
            "token_expired": self.is_token_expired(),
            "last_message_at": self.last_message_at.isoformat() if self.last_message_at else None,
            "error_count": self.error_count,
            "last_error": self.last_error
        }


class InstagramConversation(Base):
    """Instagram conversation tracking"""
    __tablename__ = "instagram_conversations"
    
    id = Column(Integer, primary_key=True, index=True)
    integration_id = Column(Integer, ForeignKey("instagram_integrations.id"), index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True)
    
    # Instagram User Info
    instagram_user_id = Column(String, nullable=False, index=True)  # Instagram Scoped ID (IGSID)
    instagram_username = Column(String, nullable=True)
    user_profile_name = Column(String, nullable=True)
    user_profile_picture = Column(String, nullable=True)
    
    # Conversation Metadata
    conversation_id = Column(String, unique=True, index=True)  # Internal conversation ID
    thread_id = Column(String, nullable=True)  # Instagram thread ID if available
    
    # Status and State
    is_active = Column(Boolean, default=True)
    conversation_status = Column(String, default="open")  # open, closed, archived
    
    # Business Context
    conversation_source = Column(String, nullable=True)  # story_mention, direct_message, comment_reply
    initial_message_type = Column(String, nullable=True)  # text, media, story_reply
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_message_at = Column(DateTime, nullable=True)
    last_user_message_at = Column(DateTime, nullable=True)
    last_bot_message_at = Column(DateTime, nullable=True)
    
    # Metrics
    total_messages = Column(Integer, default=0)
    user_messages = Column(Integer, default=0)
    bot_messages = Column(Integer, default=0)
    
    # Relationships
    integration = relationship("InstagramIntegration", back_populates="conversations")
    tenant = relationship("Tenant")
    messages = relationship("InstagramMessage", back_populates="conversation", cascade="all, delete-orphan")
    
    def get_user_identifier(self) -> str:
        """Get consistent user identifier for memory system"""
        return f"instagram:{self.instagram_user_id}"
    
    def update_message_stats(self, is_from_user: bool):
        """Update conversation statistics"""
        self.total_messages += 1
        self.last_message_at = datetime.utcnow()
        
        if is_from_user:
            self.user_messages += 1
            self.last_user_message_at = datetime.utcnow()
        else:
            self.bot_messages += 1
            self.last_bot_message_at = datetime.utcnow()


class InstagramMessage(Base):
    """Individual Instagram messages"""
    __tablename__ = "instagram_messages"
    
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("instagram_conversations.id"), index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True)
    
    # Message Identification
    instagram_message_id = Column(String, nullable=True, index=True)  # Meta's message ID
    message_uuid = Column(String, unique=True, index=True)  # Our internal UUID
    
    # Message Content
    message_type = Column(String, default="text")  # text, image, video, audio, story_reply, unsupported
    content = Column(Text, nullable=True)  # Text content
    
    # Media handling
    media_url = Column(String, nullable=True)  # Media URL from Instagram
    media_type = Column(String, nullable=True)  # image, video, audio
    media_size = Column(Integer, nullable=True)  # File size in bytes
    
    # Message Direction and Status
    is_from_user = Column(Boolean, default=True)
    message_status = Column(String, default="received")  # received, sent, delivered, read, failed
    
    # Instagram-specific fields
    reply_to_story = Column(Boolean, default=False)
    story_id = Column(String, nullable=True)  # If replying to story
    quick_reply_payload = Column(String, nullable=True)  # Quick reply selection
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    instagram_timestamp = Column(DateTime, nullable=True)  # Timestamp from Instagram
    delivered_at = Column(DateTime, nullable=True)
    read_at = Column(DateTime, nullable=True)
    
    # Error handling
    send_error = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    
    # Metadata
    raw_webhook_data = Column(JSON, nullable=True)  # Store original webhook payload
    
    # Relationships
    conversation = relationship("InstagramConversation", back_populates="messages")
    tenant = relationship("Tenant")
    
    def get_display_content(self) -> str:
        """Get appropriate content for display"""
        if self.message_type == "text":
            return self.content or ""
        elif self.message_type in ["image", "video", "audio"]:
            return f"[{self.message_type.title()}]" + (f" {self.content}" if self.content else "")
        elif self.message_type == "story_reply":
            return f"[Story Reply] {self.content or ''}"
        else:
            return f"[{self.message_type.title()}]"
    
    def is_deliverable(self) -> bool:
        """Check if message can be delivered"""
        return self.message_status not in ["delivered", "failed"] and not self.is_from_user


class InstagramWebhookEvent(Base):
    """Log webhook events for debugging and analytics"""
    __tablename__ = "instagram_webhook_events"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    integration_id = Column(Integer, ForeignKey("instagram_integrations.id"), nullable=True, index=True)
    
    # Event Details
    event_type = Column(String, nullable=False, index=True)  # messages, message_reactions, etc.
    event_id = Column(String, nullable=True, index=True)  # Instagram's event ID
    instagram_user_id = Column(String, nullable=True, index=True)
    
    # Processing Status
    processing_status = Column(String, default="pending")  # pending, processed, failed, ignored
    processing_error = Column(Text, nullable=True)
    processed_at = Column(DateTime, nullable=True)
    
    # Raw Data
    raw_payload = Column(JSON, nullable=False)  # Full webhook payload
    headers = Column(JSON, nullable=True)  # Request headers
    
    # Timestamps
    received_at = Column(DateTime(timezone=True), server_default=func.now())
    instagram_timestamp = Column(DateTime, nullable=True)
    
    # Relationships
    tenant = relationship("Tenant")
    integration = relationship("InstagramIntegration")
    
    def mark_processed(self, error: str = None):
        """Mark event as processed"""
        self.processing_status = "failed" if error else "processed"
        self.processing_error = error
        self.processed_at = datetime.utcnow()
    
    def get_event_summary(self) -> dict:
        """Get event summary for logging"""
        return {
            "event_type": self.event_type,
            "event_id": self.event_id,
            "instagram_user_id": self.instagram_user_id,
            "processing_status": self.processing_status,
            "received_at": self.received_at.isoformat(),
            "processing_error": self.processing_error
        }