from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text, DateTime, Float, event
from sqlalchemy.orm import relationship
from sqlalchemy.orm import relationship, validates
from sqlalchemy.sql import func
from app.database import Base
from datetime import datetime, timedelta
import secrets
from typing import TYPE_CHECKING
from sqlalchemy.orm import validates
import re




if TYPE_CHECKING:
    # from app.pricing.models import TenantSubscription
    from app.live_chat.models import Agent, LiveChatConversation, LiveChatSettings
    from app.telegram.models import TelegramIntegration
    
    


from app.instagram.models import InstagramIntegration

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
    subscription = relationship("TenantSubscription", uselist=False)
    instagram_integration = relationship("InstagramIntegration", uselist=False, cascade="all, delete-orphan", overlaps="tenant")
    telegram_integration = relationship("TelegramIntegration", uselist=False, cascade="all, delete-orphan")

    

    # Branding and customization fields
    primary_color = Column(String(7), default="#007bff")  # Hex color
    secondary_color = Column(String(7), default="#f0f4ff")
    text_color = Column(String(7), default="#222222")
    background_color = Column(String(7), default="#ffffff")
    user_bubble_color = Column(String(7), default="#007bff")
    bot_bubble_color = Column(String(7), default="#f0f4ff")
    border_color = Column(String(7), default="#e0e0e0")
    
    # Logo options
    logo_image_url = Column(String, nullable=True)  # URL to uploaded logo
    logo_text = Column(String(10), nullable=True)   # Fallback text (e.g., "SB")
    
    # Advanced customization
    border_radius = Column(String(10), default="12px")
    widget_position = Column(String(20), default="bottom-right")
    font_family = Column(String(100), default="Inter, sans-serif")
    
    # Custom CSS for power users
    custom_css = Column(Text, nullable=True)
    
    # Branding validation
    branding_updated_at = Column(DateTime, nullable=True)
    branding_version = Column(Integer, default=1, nullable=True)  # For cache invalidation



    # Telegram Integration fields
    telegram_bot_token = Column(String, nullable=True)
    telegram_enabled = Column(Boolean, default=False)
    telegram_username = Column(String, nullable=True)  # @botusername
    telegram_webhook_url = Column(String, nullable=True)




    # 📧 NEW: Email confirmation fields
    email_confirmed = Column(Boolean, default=False, nullable=False)
    email_confirmation_sent_at = Column(DateTime(timezone=True), nullable=True)
    registration_completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # You might also want to add these for better tracking
    email_confirmation_token = Column(String, nullable=True)  # Optional: store token for reference
    confirmation_attempts = Column(Integer, default=0, nullable=False)  # Track attempts
    last_confirmation_attempt = Column(DateTime(timezone=True), nullable=True)






    # Live chat relationships (FIXED - no duplicates)
    agents = relationship("Agent", foreign_keys="Agent.tenant_id", cascade="all, delete-orphan")
    conversations = relationship("LiveChatConversation", cascade="all, delete-orphan") 
    live_chat_settings = relationship("LiveChatSettings", uselist=False, cascade="all, delete-orphan")
    
    # Self-referential relationship for impersonation
    impersonating_tenant = relationship("Tenant", remote_side=[id], foreign_keys=[impersonating_tenant_id])

    allowed_origins = Column(String, nullable=True)

    @validates('email')
    def normalize_email(self, key, email):
        """Automatically normalize email to lowercase"""
        if email:
            return email.lower().strip()
        return email


    @validates('primary_color', 'secondary_color', 'text_color', 'background_color', 
              'user_bubble_color', 'bot_bubble_color', 'border_color')
    def validate_color(self, key, color):
        """Validate hex color format"""
        if color is None:
            return color
        
        # Remove any whitespace
        color = color.strip()
        
        # Check hex format
        if not re.match(r'^#[0-9A-Fa-f]{6}$', color):
            raise ValueError(f"Invalid color format for {key}. Must be hex format like #007bff")
        
        return color.upper()  # Normalize to uppercase
    
    @validates('widget_position')
    def validate_position(self, key, position):
        """Validate widget position"""
        if position is None:
            return position
            
        valid_positions = ['bottom-right', 'bottom-left', 'top-right', 'top-left']
        if position not in valid_positions:
            raise ValueError(f"Invalid widget position. Must be one of: {valid_positions}")
        
        return position
    
    @validates('logo_text')
    def validate_logo_text(self, key, logo_text):
        """Validate logo text length"""
        if logo_text is None:
            return logo_text
            
        if len(logo_text) > 3:
            return logo_text[:3]  # Truncate to 3 characters
        
        return logo_text.upper()  # Normalize to uppercase
    
    @validates('border_radius')
    def validate_border_radius(self, key, radius):
        """Validate border radius CSS format"""
        if radius is None:
            return radius
            
        # Basic validation for CSS units
        if not re.match(r'^\d+(\.\d+)?(px|rem|em|%)$', radius):
            return '12px'  # Default fallback
        
        return radius




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