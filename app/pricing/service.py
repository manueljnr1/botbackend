from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import HTTPException, status

from app.pricing.models import PricingPlan, TenantSubscription, UsageLog, BillingHistory
from app.pricing.schemas import (
    PricingPlanCreate, SubscriptionCreate, UsageStatsOut, PlanType
)
from app.tenants.models import Tenant


class PricingService:
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_default_plans(self):
        """Create default pricing plans if they don't exist"""
        
        # Check if plans already exist
        existing_plans = self.db.query(PricingPlan).count()
        if existing_plans > 0:
            return
        
        plans = [
            {
                "name": "Free",
                "plan_type": PlanType.FREE,
                "price_monthly": 0.00,
                "price_yearly": 0.00,
                "max_integrations": 1,
                "max_messages_monthly": 100,
                "custom_prompt_allowed": False,
                "website_api_allowed": True,
                "slack_allowed": False,
                "discord_allowed": False,
                "whatsapp_allowed": False,
                "features": '["Website API integration", "Basic support"]'
            },
            {
                "name": "Basic",
                "plan_type": PlanType.BASIC,
                "price_monthly": 29.00,
                "price_yearly": 290.00,  # 10 months price for yearly
                "max_integrations": 3,
                "max_messages_monthly": 3000,
                "custom_prompt_allowed": True,
                "website_api_allowed": True,
                "slack_allowed": True,
                "discord_allowed": True,
                "whatsapp_allowed": False,
                "features": '["Website API", "Slack integration", "Discord integration", "Custom prompts", "Email support"]'
            },
            {
                "name": "Pro",
                "plan_type": PlanType.PRO,
                "price_monthly": 99.00,
                "price_yearly": 990.00,  # 10 months price for yearly
                "max_integrations": -1,  # Unlimited
                "max_messages_monthly": 10000,
                "custom_prompt_allowed": True,
                "website_api_allowed": True,
                "slack_allowed": True,
                "discord_allowed": True,
                "whatsapp_allowed": True,
                "features": '["All integrations", "Unlimited integrations", "Custom prompts", "Priority support", "Advanced analytics"]'
            }
        ]
        
        for plan_data in plans:
            plan = PricingPlan(**plan_data)
            self.db.add(plan)
        
        self.db.commit()
    
    def get_plan_by_type(self, plan_type: PlanType) -> Optional[PricingPlan]:
        """Get plan by type"""
        return self.db.query(PricingPlan).filter(
            PricingPlan.plan_type == plan_type,
            PricingPlan.is_active == True
        ).first()
    
    def create_free_subscription_for_tenant(self, tenant_id: int) -> TenantSubscription:
        """Create a free subscription for a new tenant"""
        free_plan = self.get_plan_by_type(PlanType.FREE)
        if not free_plan:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Free plan not found"
            )
        
        # Check if subscription already exists
        existing_subscription = self.db.query(TenantSubscription).filter(
            TenantSubscription.tenant_id == tenant_id,
            TenantSubscription.is_active == True
        ).first()
        
        if existing_subscription:
            return existing_subscription
        
        # Create new subscription
        subscription = TenantSubscription(
            tenant_id=tenant_id,
            plan_id=free_plan.id,
            is_active=True,
            billing_cycle="monthly",
            current_period_start=datetime.utcnow(),
            current_period_end=datetime.utcnow() + timedelta(days=30),
            status="active"
        )
        
        self.db.add(subscription)
        self.db.commit()
        self.db.refresh(subscription)
        
        return subscription
    
    def get_tenant_subscription(self, tenant_id: int) -> Optional[TenantSubscription]:
        """Get active subscription for tenant"""
        return self.db.query(TenantSubscription).filter(
            TenantSubscription.tenant_id == tenant_id,
            TenantSubscription.is_active == True
        ).first()
    
    def check_message_limit(self, tenant_id: int) -> bool:
        """Check if tenant can send more messages"""
        subscription = self.get_tenant_subscription(tenant_id)
        if not subscription:
            return False
        
        # Check if current period is valid
        now = datetime.utcnow()
        if now > subscription.current_period_end:
            self.reset_usage_for_new_period(subscription)
        
        return subscription.messages_used_current_period < subscription.plan.max_messages_monthly
    
    def check_integration_limit(self, tenant_id: int) -> bool:
        """Check if tenant can add more integrations"""
        subscription = self.get_tenant_subscription(tenant_id)
        if not subscription:
            return False
        
        # -1 means unlimited
        if subscription.plan.max_integrations == -1:
            return True
        
        return subscription.integrations_count < subscription.plan.max_integrations
    
    def log_message_usage(self, tenant_id: int, count: int = 1) -> bool:
        """Log message usage and check if limit is exceeded"""
        subscription = self.get_tenant_subscription(tenant_id)
        if not subscription:
            return False
        
        # Check if current period is valid
        now = datetime.utcnow()
        if now > subscription.current_period_end:
            self.reset_usage_for_new_period(subscription)
        
        # Check limit before incrementing
        if not self.check_message_limit(tenant_id):
            return False
        
        # Increment usage
        subscription.messages_used_current_period += count
        
        # Log the usage
        usage_log = UsageLog(
            subscription_id=subscription.id,
            tenant_id=tenant_id,
            usage_type="message",
            count=count
        )
        
        self.db.add(usage_log)
        self.db.commit()
        
        return True
    
    def log_integration_usage(self, tenant_id: int, integration_type: str, action: str = "added") -> bool:
        """Log integration addition/removal"""
        subscription = self.get_tenant_subscription(tenant_id)
        if not subscription:
            return False
        
        if action == "added":
            if not self.check_integration_limit(tenant_id):
                return False
            subscription.integrations_count += 1
        elif action == "removed":
            subscription.integrations_count = max(0, subscription.integrations_count - 1)
        
        # Log the usage
        usage_log = UsageLog(
            subscription_id=subscription.id,
            tenant_id=tenant_id,
            usage_type=f"integration_{action}",
            count=1,
            integration_type=integration_type
        )
        
        self.db.add(usage_log)
        self.db.commit()
        
        return True
    
    def reset_usage_for_new_period(self, subscription: TenantSubscription):
        """Reset usage counters for new billing period"""
        subscription.messages_used_current_period = 0
        subscription.current_period_start = datetime.utcnow()
        
        if subscription.billing_cycle == "monthly":
            subscription.current_period_end = subscription.current_period_start + timedelta(days=30)
        else:  # yearly
            subscription.current_period_end = subscription.current_period_start + timedelta(days=365)
        
        self.db.commit()
    
    def get_usage_stats(self, tenant_id: int) -> UsageStatsOut:
        """Get current usage statistics for tenant"""
        subscription = self.get_tenant_subscription(tenant_id)
        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active subscription found"
            )
        
        # Check if current period is valid
        now = datetime.utcnow()
        if now > subscription.current_period_end:
            self.reset_usage_for_new_period(subscription)
        
        return UsageStatsOut(
            messages_used=subscription.messages_used_current_period,
            messages_limit=subscription.plan.max_messages_monthly,
            integrations_used=subscription.integrations_count,
            integrations_limit=subscription.plan.max_integrations,
            period_start=subscription.current_period_start,
            period_end=subscription.current_period_end,
            can_send_messages=subscription.messages_used_current_period < subscription.plan.max_messages_monthly,
            can_add_integrations=subscription.plan.max_integrations == -1 or subscription.integrations_count < subscription.plan.max_integrations
        )
    
    def upgrade_subscription(self, tenant_id: int, new_plan_id: int, billing_cycle: str = "monthly") -> TenantSubscription:
        """Upgrade tenant subscription to a new plan"""
        current_subscription = self.get_tenant_subscription(tenant_id)
        new_plan = self.db.query(PricingPlan).filter(PricingPlan.id == new_plan_id).first()
        
        if not new_plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Plan not found"
            )
        
        if current_subscription:
            # Deactivate current subscription
            current_subscription.is_active = False
            current_subscription.status = "canceled"
        
        # Create new subscription
        new_subscription = TenantSubscription(
            tenant_id=tenant_id,
            plan_id=new_plan_id,
            is_active=True,
            billing_cycle=billing_cycle,
            current_period_start=datetime.utcnow(),
            current_period_end=datetime.utcnow() + timedelta(days=30 if billing_cycle == "monthly" else 365),
            status="active",
            messages_used_current_period=0,
            integrations_count=current_subscription.integrations_count if current_subscription else 0
        )
        
        self.db.add(new_subscription)
        self.db.commit()
        self.db.refresh(new_subscription)
        
        return new_subscription
    
    def check_feature_access(self, tenant_id: int, feature: str) -> bool:
        """Check if tenant has access to a specific feature"""
        subscription = self.get_tenant_subscription(tenant_id)
        if not subscription:
            return False
        
        plan = subscription.plan
        
        feature_mapping = {
            "custom_prompt": plan.custom_prompt_allowed,
            "slack": plan.slack_allowed,
            "discord": plan.discord_allowed,
            "whatsapp": plan.whatsapp_allowed,
            "website_api": plan.website_api_allowed
        }
        
        return feature_mapping.get(feature, False)
    
    def get_plan_recommendations(self, tenant_id: int) -> dict:
        """Get plan recommendations based on current usage"""
        subscription = self.get_tenant_subscription(tenant_id)
        if not subscription:
            return {"recommended_plan": None, "reason": "No subscription found"}
        
        usage_stats = self.get_usage_stats(tenant_id)
        current_plan = subscription.plan
        
        # Calculate usage percentages
        message_usage_percent = (usage_stats.messages_used / usage_stats.messages_limit) * 100
        integration_usage_percent = (usage_stats.integrations_used / max(usage_stats.integrations_limit, 1)) * 100 if usage_stats.integrations_limit != -1 else 0
        
        recommendations = []
        
        # Check if user is approaching limits
        if message_usage_percent > 80:
            recommendations.append({
                "type": "upgrade",
                "reason": f"You've used {message_usage_percent:.1f}% of your message limit",
                "suggested_plan": "Basic" if current_plan.plan_type == "free" else "Pro"
            })
        
        if integration_usage_percent > 80 and usage_stats.integrations_limit != -1:
            recommendations.append({
                "type": "upgrade",
                "reason": f"You've used {integration_usage_percent:.1f}% of your integration limit",
                "suggested_plan": "Pro"
            })
        
        return {
            "current_plan": current_plan.name,
            "usage_stats": usage_stats,
            "recommendations": recommendations
        }
    
    def get_billing_summary(self, tenant_id: int) -> dict:
        """Get billing summary for tenant"""
        subscription = self.get_tenant_subscription(tenant_id)
        if not subscription:
            return {"error": "No subscription found"}
        
        # Calculate days remaining in current period
        now = datetime.utcnow()
        days_remaining = (subscription.current_period_end - now).days
        
        # Get usage logs for current period
        usage_logs = self.db.query(UsageLog).filter(
            UsageLog.tenant_id == tenant_id,
            UsageLog.created_at >= subscription.current_period_start
        ).all()
        
        # Calculate total usage
        total_messages = sum(log.count for log in usage_logs if log.usage_type == "message")
        integration_changes = [log for log in usage_logs if "integration" in log.usage_type]
        
        return {
            "current_plan": subscription.plan.name,
            "billing_cycle": subscription.billing_cycle,
            "current_period_start": subscription.current_period_start,
            "current_period_end": subscription.current_period_end,
            "days_remaining": days_remaining,
            "usage_summary": {
                "messages_used": subscription.messages_used_current_period,
                "messages_limit": subscription.plan.max_messages_monthly,
                "integrations_count": subscription.integrations_count,
                "integrations_limit": subscription.plan.max_integrations
            },
            "cost_this_period": float(subscription.plan.price_monthly),
            "next_billing_date": subscription.current_period_end
        }