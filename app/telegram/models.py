# app/telegram/models.py
"""
Telegram Integration Database Models
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.tenants.models import Tenant

class TelegramIntegration(Base):
    """
    Telegram integration configuration per tenant
    Stores bot credentials and settings
    """
    __tablename__ = "telegram_integrations"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), unique=True, index=True)
    
    # Bot Configuration
    bot_token = Column(String, nullable=False)  # Bot API token from @BotFather
    bot_username = Column(String, nullable=True)  # @botusername
    bot_name = Column(String, nullable=True)  # Display name
    
    # Webhook Configuration
    webhook_url = Column(String, nullable=True)  # Registered webhook URL
    webhook_secret = Column(String, nullable=True)  # Webhook secret token
    
    # Status and Settings
    is_active = Column(Boolean, default=False)
    is_webhook_set = Column(Boolean, default=False)
    
    # Bot Features
    enable_groups = Column(Boolean, default=False)  # Allow bot in groups
    enable_privacy_mode = Column(Boolean, default=True)  # Privacy mode setting
    enable_inline_mode = Column(Boolean, default=False)  # Inline queries
    
    # Message Settings
    welcome_message = Column(Text, nullable=True)  # Custom welcome message
    help_message = Column(Text, nullable=True)  # Custom help message
    enable_typing_indicator = Column(Boolean, default=True)  # Show typing...
    
    # Rate Limiting
    max_messages_per_minute = Column(Integer, default=30)  # Per user rate limit
    
    # Analytics and Monitoring
    last_webhook_received = Column(DateTime, nullable=True)
    last_message_sent = Column(DateTime, nullable=True)
    total_messages_received = Column(Integer, default=0)
    total_messages_sent = Column(Integer, default=0)
    
    # Error Tracking
    last_error = Column(Text, nullable=True)
    error_count = Column(Integer, default=0)
    last_error_at = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    activated_at = Column(DateTime, nullable=True)
    
    # Relationships
    # tenant = relationship("Tenant", back_populates="telegram_integration")
    tenant = relationship("Tenant")
    
    def is_configured(self) -> bool:
        """Check if integration is properly configured"""
        return bool(self.bot_token and self.bot_username and self.is_active)
    
    def get_webhook_endpoint(self) -> str:
        """Get the webhook endpoint for this bot"""
        return f"/api/telegram/webhook/{self.tenant_id}"
    
    def get_bot_info_summary(self) -> dict:
        """Get bot information summary for admin dashboard"""
        return {
            "bot_username": self.bot_username,
            "bot_name": self.bot_name,
            "is_active": self.is_active,
            "is_webhook_set": self.is_webhook_set,
            "total_messages": self.total_messages_received + self.total_messages_sent,
            "last_activity": max(
                self.last_webhook_received or self.created_at,
                self.last_message_sent or self.created_at
            ),
            "error_count": self.error_count
        }

class TelegramChat(Base):
    """
    Telegram chat sessions for analytics and memory
    """
    __tablename__ = "telegram_chats"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True)
    telegram_integration_id = Column(Integer, ForeignKey("telegram_integrations.id"))
    
    # Telegram Chat Information
    chat_id = Column(String, nullable=False, index=True)  # Telegram chat ID
    chat_type = Column(String, nullable=False)  # private, group, supergroup, channel
    
    # User Information
    user_id = Column(String, nullable=True, index=True)  # Telegram user ID
    username = Column(String, nullable=True)  # @username
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    
    # Chat Settings
    is_active = Column(Boolean, default=True)
    language_code = Column(String, default="en")
    
    # Analytics
    first_message_at = Column(DateTime, server_default=func.now())
    last_message_at = Column(DateTime, server_default=func.now())
    total_messages = Column(Integer, default=0)
    
    # Relationships
    tenant = relationship("Tenant")
    integration = relationship("TelegramIntegration")
    
    @property
    def user_identifier(self) -> str:
        """Get user identifier for memory system"""
        return f"telegram:{self.user_id}"
    
    @property
    def display_name(self) -> str:
        """Get display name for user"""
        if self.username:
            return f"@{self.username}"
        elif self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        elif self.first_name:
            return self.first_name
        else:
            return f"User {self.user_id}"