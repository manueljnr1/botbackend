from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from decimal import Decimal
from enum import Enum


class PlanType(str, Enum):
    FREE = "free"
    BASIC = "basic"
    PRO = "pro"


class BillingCycle(str, Enum):
    MONTHLY = "monthly"
    YEARLY = "yearly"


class PricingPlanBase(BaseModel):
    name: str
    plan_type: PlanType
    price_monthly: Decimal = Field(default=0.00, ge=0)
    price_yearly: Decimal = Field(default=0.00, ge=0)
    max_integrations: int = Field(default=1, ge=-1)  # -1 for unlimited
    max_messages_monthly: int = Field(default=100, ge=0)
    custom_prompt_allowed: bool = False
    website_api_allowed: bool = True
    slack_allowed: bool = False
    discord_allowed: bool = False
    whatsapp_allowed: bool = False
    features: Optional[str] = None
    is_active: bool = True


class PricingPlanCreate(PricingPlanBase):
    pass


class PricingPlanUpdate(BaseModel):
    name: Optional[str] = None
    price_monthly: Optional[Decimal] = None
    price_yearly: Optional[Decimal] = None
    max_integrations: Optional[int] = None
    max_messages_monthly: Optional[int] = None
    custom_prompt_allowed: Optional[bool] = None
    website_api_allowed: Optional[bool] = None
    slack_allowed: Optional[bool] = None
    discord_allowed: Optional[bool] = None
    whatsapp_allowed: Optional[bool] = None
    features: Optional[str] = None
    is_active: Optional[bool] = None


class PricingPlanOut(PricingPlanBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SubscriptionBase(BaseModel):
    plan_id: int
    billing_cycle: BillingCycle = BillingCycle.MONTHLY


class SubscriptionCreate(SubscriptionBase):
    pass


class SubscriptionUpdate(BaseModel):
    plan_id: Optional[int] = None
    billing_cycle: Optional[BillingCycle] = None
    is_active: Optional[bool] = None


class SubscriptionOut(SubscriptionBase):
    id: int
    tenant_id: int
    is_active: bool
    current_period_start: datetime
    current_period_end: datetime
    messages_used_current_period: int
    integrations_count: int
    status: str
    stripe_subscription_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    plan: PricingPlanOut

    class Config:
        from_attributes = True


class UsageLogOut(BaseModel):
    id: int
    usage_type: str
    count: int
    integration_type: Optional[str] = None
    extra_data: Optional[str] = None  # Changed from 'metadata' to 'extra_data'
    created_at: datetime

    class Config:
        from_attributes = True


class UsageStatsOut(BaseModel):
    messages_used: int
    messages_limit: int
    integrations_used: int
    integrations_limit: int
    period_start: datetime
    period_end: datetime
    can_send_messages: bool
    can_add_integrations: bool


class BillingHistoryOut(BaseModel):
    id: int
    amount: Decimal
    currency: str
    billing_period_start: datetime
    billing_period_end: datetime
    payment_status: str
    payment_date: Optional[datetime] = None
    stripe_invoice_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class PlanComparisonOut(BaseModel):
    plans: List[PricingPlanOut]
    current_plan: Optional[PricingPlanOut] = None
    current_usage: Optional[UsageStatsOut] = None


class UpgradeRequest(BaseModel):
    plan_id: int
    billing_cycle: BillingCycle = BillingCycle.MONTHLY


class MessageResponse(BaseModel):
    message: str
    success: bool = True