# app/pricing/service.py
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import HTTPException, status
import logging

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
                "plan_type": "free",
                "price_monthly": 0.00,
                "price_yearly": 0.00,
                "max_integrations": -1,  # Unlimited integrations
                "max_messages_monthly": 50,  # 50 conversations
                "custom_prompt_allowed": True,
                "website_api_allowed": True,
                "slack_allowed": True,
                "discord_allowed": True,
                "whatsapp_allowed": False,  # Temporarily removed
                "features": '["Custom Prompt", "Slack Integration", "Discord Integration", "Web Integration", "Bot Memory"]',
                "is_active": True,
                "is_addon": False,
                "is_popular": False,
                "display_order": 1
            },
            {
                "name": "Basic",
                "plan_type": "basic",
                "price_monthly": 9.99,  # UPDATED PRICE
                "price_yearly": 99.00,  # UPDATED PRICE
                "max_integrations": -1,  # Unlimited integrations
                "max_messages_monthly": 2000,  # UPDATED: 2,000 conversations
                "custom_prompt_allowed": True,
                "website_api_allowed": True,
                "slack_allowed": True,
                "discord_allowed": True,
                "whatsapp_allowed": False,  # Temporarily removed
                "features": '["Custom Prompt", "Slack Integration", "Discord Integration", "Web Integration", "Advanced Analytics", "Bot Memory"]',
                "is_active": True,
                "is_addon": False,
                "is_popular": False,
                "display_order": 2
            },
            {
                "name": "Growth",
                "plan_type": "growth",
                "price_monthly": 29.00,  # UPDATED PRICE
                "price_yearly": 290.00,  # UPDATED PRICE
                "max_integrations": -1,  # Unlimited integrations
                "max_messages_monthly": 5000,  # 5,000 conversations
                "custom_prompt_allowed": True,
                "website_api_allowed": True,
                "slack_allowed": True,
                "discord_allowed": True,
                "whatsapp_allowed": False,  # Temporarily removed
                "features": '["Custom Prompt", "Slack Integration", "Discord Integration", "Web Integration", "Advanced Analytics", "Priority Support", "Bot Memory"]',
                "is_active": True,
                "is_addon": False,
                "is_popular": True,  # Popular plan
                "display_order": 3
            },
            {
                "name": "Pro",  # NEW PLAN
                "plan_type": "pro",
                "price_monthly": 59.00,
                "price_yearly": 590.00,
                "max_integrations": -1,  # Unlimited integrations
                "max_messages_monthly": 20000,  # 20,000 conversations
                "custom_prompt_allowed": True,
                "website_api_allowed": True,
                "slack_allowed": True,
                "discord_allowed": True,
                "whatsapp_allowed": False,  # Temporarily removed
                "features": '["Custom Prompt", "Slack Integration", "Discord Integration", "Web Integration", "Advanced Analytics", "Priority Support", "Enhanced Bot Memory", "API Access"]',
                "is_active": True,
                "is_addon": False,
                "is_popular": False,
                "display_order": 4
            },
            {
                "name": "Agency", 
                "plan_type": "agency",
                "price_monthly": 99.00,
                "price_yearly": 990.00,
                "max_integrations": -1,  # Unlimited integrations
                "max_messages_monthly": 50000,  # 50,000 conversations
                "custom_prompt_allowed": True,
                "website_api_allowed": True,
                "slack_allowed": True,
                "discord_allowed": True,
                "whatsapp_allowed": False,  # Temporarily removed
                "features": '["Custom Prompt", "Slack Integration", "Discord Integration", "Web Integration", "Advanced Analytics", "Priority Support", "Enhanced Bot Memory", "API Access", "White Label", "Custom Integrations"]',
                "is_active": True,
                "is_addon": False,
                "is_popular": False,
                "display_order": 5
            }
        ]
        
        for plan_data in plans:
            plan = PricingPlan(**plan_data)
            self.db.add(plan)
        
        self.db.commit()
    
    def get_plan_by_type(self, plan_type: str) -> Optional[PricingPlan]:
        """Get plan by type"""
        return self.db.query(PricingPlan).filter(
            PricingPlan.plan_type == plan_type,
            PricingPlan.is_active == True
        ).first()
    

    def get_all_plans(self) -> List[PricingPlan]:
        """Get all active plans"""
        return self.db.query(PricingPlan).filter(
            PricingPlan.is_active == True
        ).all()

    
    def create_free_subscription_for_tenant(self, tenant_id: int) -> Optional[TenantSubscription]:
        """
        Create a free subscription for a new tenant - ENHANCED VERSION
        """
        try:
            # Ensure default plans exist first
            self.create_default_plans()
            
            # Get the free plan
            free_plan = self.get_plan_by_type("free")
            if not free_plan:
                logger.error("❌ Free plan not found - cannot create subscription")
                return None
            
            # Check if subscription already exists
            existing_subscription = self.db.query(TenantSubscription).filter(
                TenantSubscription.tenant_id == tenant_id,
                TenantSubscription.is_active == True
            ).first()
            
            if existing_subscription:
                logger.info(f"ℹ️ Subscription already exists for tenant {tenant_id}")
                return existing_subscription
            
            # Create new subscription with proper defaults
            subscription = TenantSubscription(
                tenant_id=tenant_id,
                plan_id=free_plan.id,
                is_active=True,
                billing_cycle="monthly",
                current_period_start=datetime.utcnow(),
                current_period_end=datetime.utcnow() + timedelta(days=30),
                status="active",
                messages_used_current_period=0,
                integrations_count=0
            )
            
            self.db.add(subscription)
            self.db.commit()
            self.db.refresh(subscription)
            
            # Verify the subscription was created with plan relationship
            if not subscription.plan:
                logger.error(f"❌ Subscription created but plan relationship is None for tenant {tenant_id}")
                return None
            
            logger.info(f"✅ Created free subscription for tenant {tenant_id} with plan {subscription.plan.name}")
            return subscription
            
        except Exception as e:
            logger.error(f"💥 Error creating free subscription for tenant {tenant_id}: {e}")
            self.db.rollback()
            return None

    
    def get_tenant_subscription(self, tenant_id: int) -> Optional[TenantSubscription]:
        """Get active subscription for tenant"""
        return self.db.query(TenantSubscription).filter(
            TenantSubscription.tenant_id == tenant_id,
            TenantSubscription.is_active == True
        ).first()
    
    def check_message_limit(self, tenant_id: int) -> bool:
        """
        Check if tenant can send more messages (conversations) - WITH PROPER NULL CHECKS
        """
        try:
            subscription = self.get_tenant_subscription(tenant_id)
            
            if not subscription:
                # Try to create a free subscription if none exists
                subscription = self.create_free_subscription_for_tenant(tenant_id)
                if not subscription:
                    return True  # Allow messages if can't create subscription
            
            # CRITICAL FIX: Check if plan exists
            if not subscription.plan:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"🚨 No plan found for tenant {tenant_id} subscription ID {subscription.id}")
                
                # Try to assign free plan
                free_plan = self.get_plan_by_type("free")
                if free_plan:
                    subscription.plan_id = free_plan.id
                    self.db.commit()
                    self.db.refresh(subscription)
                    logger.info(f"✅ Assigned free plan to tenant {tenant_id}")
                else:
                    logger.error(f"❌ No free plan available for tenant {tenant_id}")
                    return True  # Allow messages if no free plan exists
            
            # CRITICAL FIX: Check if plan has the required attribute
            if not hasattr(subscription.plan, 'max_messages_monthly'):
                logger.warning(f"Plan for tenant {tenant_id} missing max_messages_monthly attribute")
                return True  # Allow messages if plan is malformed
            
            if subscription.plan.max_messages_monthly is None:
                logger.warning(f"Plan for tenant {tenant_id} has null max_messages_monthly")
                return True  # Allow unlimited if max is None
            
            # Check if current period is valid
            now = datetime.utcnow()
            if now > subscription.current_period_end:
                self.reset_usage_for_new_period(subscription)
            
            # Now safe to check the limit
            return subscription.messages_used_current_period < subscription.plan.max_messages_monthly
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"💥 Error checking message limit for tenant {tenant_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return True  # Allow messages on error to avoid breaking chat
    
    def check_integration_limit(self, tenant_id: int) -> bool:
        """Check if tenant can add more integrations"""
        subscription = self.get_tenant_subscription(tenant_id)
        if not subscription:
            return False
        
        # -1 means unlimited (all plans now have unlimited integrations)
        if subscription.plan.max_integrations == -1:
            return True
        
        return subscription.integrations_count < subscription.plan.max_integrations
    
    def log_message_usage(self, tenant_id: int, count: int = 1) -> bool:
        """
        Log message usage and check if limit is exceeded - WITH PROPER NULL CHECKS
        Note: A conversation is any length of interaction within 24 hours
        """
        try:
            subscription = self.get_tenant_subscription(tenant_id)
            
            if not subscription:
                # Try to create free subscription
                subscription = self.create_free_subscription_for_tenant(tenant_id)
                if not subscription:
                    return False
            
            # CRITICAL FIX: Ensure plan exists
            if not subscription.plan:
                free_plan = self.get_plan_by_type("free")
                if free_plan:
                    subscription.plan_id = free_plan.id
                    self.db.commit()
                    self.db.refresh(subscription)
                else:
                    return False
            
            # Check if current period is valid
            now = datetime.utcnow()
            if now > subscription.current_period_end:
                self.reset_usage_for_new_period(subscription)
            
            # Check if this is a new conversation (within 24 hours)
            last_24_hours = now - timedelta(hours=24)
            recent_usage = self.db.query(UsageLog).filter(
                UsageLog.tenant_id == tenant_id,
                UsageLog.usage_type == "conversation",
                UsageLog.created_at > last_24_hours
            ).first()
            
            # If no recent conversation usage, this counts as a new conversation
            if not recent_usage:
                # Check limit before incrementing
                if not self.check_message_limit(tenant_id):
                    return False
                
                # Increment usage for new conversation
                subscription.messages_used_current_period += 1
                
                # Log the conversation usage
                usage_log = UsageLog(
                    subscription_id=subscription.id,
                    tenant_id=tenant_id,
                    usage_type="conversation",
                    count=1
                )
                
                self.db.add(usage_log)
            
            # Always log individual message for tracking
            message_log = UsageLog(
                subscription_id=subscription.id,
                tenant_id=tenant_id,
                usage_type="message",
                count=count
            )
            
            self.db.add(message_log)
            self.db.commit()
            
            return True
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"💥 Error logging message usage for tenant {tenant_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
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
            "whatsapp": False,  # Temporarily disabled for all plans
            "live_chat": False,  # Completely removed
            "website_api": plan.website_api_allowed,
            "advanced_analytics": "Advanced Analytics" in (plan.features or ""),
            "priority_support": "Priority Support" in (plan.features or ""),
            "bot_memory": "Bot Memory" in (plan.features or ""),
            "enhanced_bot_memory": "Enhanced Bot Memory" in (plan.features or ""),
            "api_access": "API Access" in (plan.features or ""),
            "white_label": "White Label" in (plan.features or ""),
            "custom_integrations": "Custom Integrations" in (plan.features or "")
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
        
        recommendations = []
        
        # Check if user is approaching limits and suggest appropriate upgrades
        if message_usage_percent > 80:
            if current_plan.plan_type == "free":
                recommendations.append({
                    "type": "upgrade",
                    "reason": f"You've used {message_usage_percent:.1f}% of your conversation limit",
                    "suggested_plan": "Basic"
                })
            elif current_plan.plan_type == "basic":
                recommendations.append({
                    "type": "upgrade", 
                    "reason": f"You've used {message_usage_percent:.1f}% of your conversation limit",
                    "suggested_plan": "Growth"
                })
            elif current_plan.plan_type == "growth":
                recommendations.append({
                    "type": "upgrade",
                    "reason": f"You've used {message_usage_percent:.1f}% of your conversation limit", 
                    "suggested_plan": "Agency"
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
        
        # Calculate conversation count and individual messages
        conversation_count = len([log for log in usage_logs if log.usage_type == "conversation"])
        message_count = sum(log.count for log in usage_logs if log.usage_type == "message")
        integration_changes = [log for log in usage_logs if "integration" in log.usage_type]
        
        return {
            "current_plan": subscription.plan.name,
            "billing_cycle": subscription.billing_cycle,
            "current_period_start": subscription.current_period_start,
            "current_period_end": subscription.current_period_end,
            "days_remaining": days_remaining,
            "usage_summary": {
                "conversations_used": subscription.messages_used_current_period,
                "conversations_limit": subscription.plan.max_messages_monthly,
                "total_messages": message_count,
                "integrations_count": subscription.integrations_count,
                "integrations_limit": subscription.plan.max_integrations
            },
            "cost_this_period": float(subscription.plan.price_monthly),
            "next_billing_date": subscription.current_period_end,
            "conversation_definition": "A conversation is any length of interaction within 24 hours"
        }
    
    def check_message_limit_with_super_tenant(self, tenant_id: int) -> bool:
        """
        Enhanced message limit check that bypasses for super tenants
        """
        try:
            # Check if super tenant first
            from app.tenants.super_tenant_service import SuperTenantService
            super_service = SuperTenantService(self.db)
            
            if super_service.is_super_tenant(tenant_id):
                logger.info(f"🔓 Super tenant {tenant_id} - unlimited message access")
                return True  # Super tenants have unlimited access
            
            # Otherwise use normal limit checking
            return self.check_message_limit(tenant_id)
            
        except Exception as e:
            logger.error(f"Error checking message limit with super tenant: {e}")
            return self.check_message_limit(tenant_id)  # Fallback to normal check

    def check_integration_limit_with_super_tenant(self, tenant_id: int) -> bool:
        """
        Enhanced integration limit check that bypasses for super tenants
        """
        try:
            # Check if super tenant first
            from app.tenants.super_tenant_service import SuperTenantService
            super_service = SuperTenantService(self.db)
            
            if super_service.is_super_tenant(tenant_id):
                logger.info(f"🔓 Super tenant {tenant_id} - unlimited integration access")
                return True  # Super tenants have unlimited access
            
            # Otherwise use normal limit checking
            return self.check_integration_limit(tenant_id)
            
        except Exception as e:
            logger.error(f"Error checking integration limit with super tenant: {e}")
            return self.check_integration_limit(tenant_id)  # Fallback to normal check