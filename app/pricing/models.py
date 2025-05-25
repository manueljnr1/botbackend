from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text, DateTime, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
from datetime import datetime
from enum import Enum


class PlanType(str, Enum):
    FREE = "free"
    BASIC = "basic"
    PRO = "pro"


class PricingPlan(Base):
    __tablename__ = "pricing_plans"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)  # "Free", "Basic", "Pro"
    plan_type = Column(String, index=True)  # "free", "basic", "pro"
    price_monthly = Column(Numeric(10, 2), default=0.00)
    price_yearly = Column(Numeric(10, 2), default=0.00)
    
    # Plan limits
    max_integrations = Column(Integer, default=1)  # -1 for unlimited
    max_messages_monthly = Column(Integer, default=100)
    custom_prompt_allowed = Column(Boolean, default=False)
    
    # Available integrations
    website_api_allowed = Column(Boolean, default=True)
    slack_allowed = Column(Boolean, default=False)
    discord_allowed = Column(Boolean, default=False)
    whatsapp_allowed = Column(Boolean, default=False)
    
    # Plan features
    features = Column(Text, nullable=True)  # JSON string of additional features
    is_active = Column(Boolean, default=True)
    
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
    
    # Usage tracking
    messages_used_current_period = Column(Integer, default=0)
    integrations_count = Column(Integer, default=0)
    
    # Payment details
    stripe_subscription_id = Column(String, nullable=True)
    status = Column(String, default="active")  # active, canceled, past_due, etc.
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    plan = relationship("PricingPlan", back_populates="subscriptions")
    tenant = relationship("Tenant", back_populates="subscription")
    usage_logs = relationship("UsageLog", back_populates="subscription")


class UsageLog(Base):
    __tablename__ = "usage_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    subscription_id = Column(Integer, ForeignKey("tenant_subscriptions.id"), nullable=False)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    
    # Usage details
    usage_type = Column(String, nullable=False)  # "message", "integration_added", etc.
    count = Column(Integer, default=1)
    integration_type = Column(String, nullable=True)  # "slack", "discord", "whatsapp", etc.
    
    # Changed from 'metadata' to 'extra_data' to avoid SQLAlchemy reserved word
    extra_data = Column(Text, nullable=True)  # JSON string for additional data
    
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
    
    # Payment details
    stripe_invoice_id = Column(String, nullable=True)
    payment_status = Column(String, default="pending")  # pending, paid, failed
    payment_date = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())