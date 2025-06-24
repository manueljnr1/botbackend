# app/pricing/models.py
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text, DateTime, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
from datetime import datetime
from enum import Enum


class PlanType(str, Enum):
    FREE = "free"
    BASIC = "basic"
    GROWTH = "growth"
    PRO = "pro"  # NEW PLAN TYPE
    AGENCY = "agency"


class Allplans(str):
    FREE = "Free"
    BASIC = "Basic"
    GROWTH = "Growth"
    PRO = "Pro"  
    AGENCY = "Agency"
    


class PricingPlan(Base):
    __tablename__ = "pricing_plans"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)  # "Free", "Basic", "Growth", "Agency", "Live Chat Add-on"
    plan_type = Column(String, index=True)  # "free", "basic", "growth", "agency", "livechat_addon"
    price_monthly = Column(Numeric(10, 2), default=0.00)
    price_yearly = Column(Numeric(10, 2), default=0.00)
    
    # Plan limits
    max_integrations = Column(Integer, default=-1)  # -1 for unlimited (default for all new plans)
    max_messages_monthly = Column(Integer, default=50)  # Now represents conversations, not individual messages
    custom_prompt_allowed = Column(Boolean, default=True)  # Now allowed in all plans
    
    # Available integrations - all now allowed by default except WhatsApp
    website_api_allowed = Column(Boolean, default=True)
    slack_allowed = Column(Boolean, default=True)  # Now allowed in all plans
    discord_allowed = Column(Boolean, default=True)  # Now allowed in all plans
    whatsapp_allowed = Column(Boolean, default=False)  # Only in Agency and Live Chat Add-on
    
    # Plan features
    features = Column(Text, nullable=True)  # JSON string of additional features
    is_active = Column(Boolean, default=True)
    
    # New fields for better plan management
    is_addon = Column(Boolean, default=False)  # True for add-on plans like Live Chat
    is_popular = Column(Boolean, default=False)  # For highlighting recommended plans
    display_order = Column(Integer, default=0)  # For ordering plans in UI
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    subscriptions = relationship("TenantSubscription", back_populates="plan")


class TenantSubscription(Base):
    __tablename__ = "tenant_subscriptions"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    plan_id = Column(Integer, ForeignKey("pricing_plans.id"), nullable=False)
    
    # Subscription details
    is_active = Column(Boolean, default=True)
    billing_cycle = Column(String, default="monthly")  # "monthly" or "yearly"
    
    # Current period
    current_period_start = Column(DateTime, nullable=False)
    current_period_end = Column(DateTime, nullable=False)
    
    # Usage tracking - conversations instead of individual messages
    messages_used_current_period = Column(Integer, default=0)  # Actually conversations used
    integrations_count = Column(Integer, default=0)
    
    # Add-on tracking
    active_addons = Column(Text, nullable=True)  # JSON string of active add-on plan IDs
    
    # Payment details
    stripe_subscription_id = Column(String, nullable=True)
    stripe_customer_id = Column(String, nullable=True)  # Added for better Stripe integration
    status = Column(String, default="active")  # active, canceled, past_due, etc.


        # Flutterwave payment tracking
    flutterwave_tx_ref = Column(String, nullable=True)
    flutterwave_flw_ref = Column(String, nullable=True)
    flutterwave_customer_id = Column(String, nullable=True)
        
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    plan = relationship("PricingPlan", back_populates="subscriptions")
    # tenant = relationship("Tenant", back_populates="subscription")
    tenant = relationship("Tenant")
    usage_logs = relationship("UsageLog", back_populates="subscription")


class UsageLog(Base):
    __tablename__ = "usage_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    subscription_id = Column(Integer, ForeignKey("tenant_subscriptions.id"), nullable=False)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    
    # Usage details - enhanced for conversation tracking
    usage_type = Column(String, nullable=False)  # "conversation", "message", "integration_added", etc.
    count = Column(Integer, default=1)
    integration_type = Column(String, nullable=True)  # "slack", "discord", "whatsapp", etc.
    
    # Enhanced metadata for better tracking
    extra_data = Column(Text, nullable=True)  # JSON string for additional data
    session_id = Column(String, nullable=True)  # Link to chat session if applicable
    user_identifier = Column(String, nullable=True)  # User who triggered the usage
    platform = Column(String, nullable=True)  # "web", "slack", "discord", etc.
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    subscription = relationship("TenantSubscription", back_populates="usage_logs")


class BillingHistory(Base):
    __tablename__ = "billing_history"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    subscription_id = Column(Integer, ForeignKey("tenant_subscriptions.id"), nullable=False)
    
    # Invoice details
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String, default="USD")
    billing_period_start = Column(DateTime, nullable=False)
    billing_period_end = Column(DateTime, nullable=False)
    
    # Enhanced billing details
    plan_name = Column(String, nullable=True)  # Plan name at time of billing
    conversations_included = Column(Integer, nullable=True)  # Conversations limit for this period
    conversations_used = Column(Integer, nullable=True)  # Conversations actually used
    addons_included = Column(Text, nullable=True)  # JSON string of add-ons included
    
    # Payment details
    stripe_invoice_id = Column(String, nullable=True)
    stripe_charge_id = Column(String, nullable=True)  # Added for charge tracking
    payment_status = Column(String, default="pending")  # pending, paid, failed, refunded
    payment_date = Column(DateTime, nullable=True)
    payment_method = Column(String, nullable=True)  # "card", "ach", etc.
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ConversationSession(Base):
    """
    New model to track conversation sessions for billing purposes
    A conversation is any length of interaction within 24 hours
    """
    __tablename__ = "conversation_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    user_identifier = Column(String, nullable=False)  # User who started the conversation
    platform = Column(String, nullable=False)  # "web", "slack", "discord", etc.
    
    # Conversation tracking
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_activity = Column(DateTime, nullable=False, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # Metrics
    message_count = Column(Integer, default=0)  # Total messages in this conversation
    duration_minutes = Column(Integer, default=0)  # Duration of conversation
    
    # Billing
    counted_for_billing = Column(Boolean, default=False)  # Whether this conversation was counted towards usage
    billing_period_start = Column(DateTime, nullable=True)  # Which billing period this belongs to
    
    # Metadata
    extra_data = Column(Text, nullable=True)  # JSON for additional conversation data
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())