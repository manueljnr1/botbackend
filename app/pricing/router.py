# app/pricing/router.py
from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.database import get_db
from app.pricing.models import PricingPlan, TenantSubscription, UsageLog, BillingHistory
from app.pricing.schemas import (
    PricingPlanOut, PricingPlanCreate, PricingPlanUpdate,
    SubscriptionOut, SubscriptionCreate, SubscriptionUpdate,
    UsageStatsOut, UsageLogOut, BillingHistoryOut,
    PlanComparisonOut, PlanComparisonDetailOut, PlanFeaturesDetail,
    UpgradeRequest, MessageResponse, PlanType
)
from app.pricing.service import PricingService
from app.tenants.router import get_tenant_from_api_key, get_current_tenant
from app.auth.router import get_admin_user
from app.auth.models import User

router = APIRouter()


@router.post("/plans", response_model=PricingPlanOut)
async def create_pricing_plan(
    plan_data: PricingPlanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """Create a new pricing plan (Admin only)"""
    # Check if plan with same name exists
    existing_plan = db.query(PricingPlan).filter(PricingPlan.name == plan_data.name).first()
    if existing_plan:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Plan with this name already exists"
        )
    
    plan = PricingPlan(**plan_data.model_dump())
    db.add(plan)
    db.commit()
    db.refresh(plan)
    
    return plan


@router.get("/plans", response_model=List[PricingPlanOut])
async def list_pricing_plans(
    db: Session = Depends(get_db),
    include_inactive: bool = False,
    exclude_addons: bool = False
):
    """List all pricing plans"""
    query = db.query(PricingPlan)
    if not include_inactive:
        query = query.filter(PricingPlan.is_active == True)
    
    if exclude_addons:
        query = query.filter(PricingPlan.plan_type != "livechat_addon")
    
    return query.all()


@router.get("/plans/detailed", response_model=List[PlanFeaturesDetail])
async def get_detailed_plans(
    db: Session = Depends(get_db),
    include_addons: bool = True
):
    """Get detailed plan information with features breakdown"""
    plans = db.query(PricingPlan).filter(PricingPlan.is_active == True).all()
    
    if not include_addons:
        plans = [p for p in plans if p.plan_type != "livechat_addon"]
    
    detailed_plans = []
    
    for plan in plans:
        # Parse features from JSON string
        import json
        try:
            features_list = json.loads(plan.features) if plan.features else []
        except:
            features_list = []
        
        # Build integrations list
        integrations = []
        if plan.website_api_allowed:
            integrations.append("Web Integration")
        if plan.slack_allowed:
            integrations.append("Slack Integration")
        if plan.discord_allowed:
            integrations.append("Discord Integration")
        if plan.whatsapp_allowed:
            integrations.append("WhatsApp Integration")
        
        # Determine if plan is popular (Growth plan)
        is_popular = plan.plan_type == "growth"
        is_addon = plan.plan_type == "livechat_addon"
        
        detailed_plan = PlanFeaturesDetail(
            plan_name=plan.name,
            plan_type=plan.plan_type,
            price_monthly=plan.price_monthly,
            price_yearly=plan.price_yearly,
            conversations_limit=plan.max_messages_monthly,
            features=features_list,
            integrations=integrations,
            is_popular=is_popular,
            is_addon=is_addon
        )
        
        detailed_plans.append(detailed_plan)
    
    # Sort plans by price (excluding add-ons)
    main_plans = [p for p in detailed_plans if not p.is_addon]
    addon_plans = [p for p in detailed_plans if p.is_addon]
    
    main_plans.sort(key=lambda x: x.price_monthly)
    
    return main_plans + addon_plans


@router.get("/plans/{plan_id}", response_model=PricingPlanOut)
async def get_pricing_plan(
    plan_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific pricing plan"""
    plan = db.query(PricingPlan).filter(PricingPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found"
        )
    return plan


@router.put("/plans/{plan_id}", response_model=PricingPlanOut)
async def update_pricing_plan(
    plan_id: int,
    plan_update: PricingPlanUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """Update a pricing plan (Admin only)"""
    plan = db.query(PricingPlan).filter(PricingPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found"
        )
    
    update_data = plan_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(plan, key, value)
    
    db.commit()
    db.refresh(plan)
    return plan


@router.delete("/plans/{plan_id}")
async def delete_pricing_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """Deactivate a pricing plan (Admin only)"""
    plan = db.query(PricingPlan).filter(PricingPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found"
        )
    
    # Don't actually delete, just deactivate
    plan.is_active = False
    db.commit()
    
    return {"message": "Plan deactivated successfully"}


@router.get("/subscription", response_model=SubscriptionOut)
async def get_my_subscription(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get current tenant's subscription details"""
    tenant = get_tenant_from_api_key(api_key, db)
    pricing_service = PricingService(db)
    
    subscription = pricing_service.get_tenant_subscription(tenant.id)
    if not subscription:
        # Create free subscription if none exists
        subscription = pricing_service.create_free_subscription_for_tenant(tenant.id)
    
    return subscription


@router.get("/usage", response_model=UsageStatsOut)
async def get_usage_stats(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get current tenant's usage statistics"""
    tenant = get_tenant_from_api_key(api_key, db)
    pricing_service = PricingService(db)
    
    return pricing_service.get_usage_stats(tenant.id)


@router.get("/usage/logs", response_model=List[UsageLogOut])
async def get_usage_logs(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db),
    limit: int = 100
):
    """Get tenant's recent usage logs"""
    tenant = get_tenant_from_api_key(api_key, db)
    
    usage_logs = db.query(UsageLog).filter(
        UsageLog.tenant_id == tenant.id
    ).order_by(UsageLog.created_at.desc()).limit(limit).all()
    
    return usage_logs


@router.post("/upgrade", response_model=SubscriptionOut)
async def upgrade_subscription(
    upgrade_request: UpgradeRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Upgrade tenant's subscription to a new plan"""
    tenant = get_tenant_from_api_key(api_key, db)
    pricing_service = PricingService(db)
    
    # Validate the new plan exists and is active
    new_plan = db.query(PricingPlan).filter(
        PricingPlan.id == upgrade_request.plan_id,
        PricingPlan.is_active == True
    ).first()
    
    if not new_plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found or inactive"
        )
    
    # For now, we'll just update the subscription
    # In production, you'd integrate with payment processor (Stripe)
    new_subscription = pricing_service.upgrade_subscription(
        tenant_id=tenant.id,
        new_plan_id=upgrade_request.plan_id,
        billing_cycle=upgrade_request.billing_cycle
    )
    
    return new_subscription


@router.get("/compare", response_model=PlanComparisonDetailOut)
async def compare_plans(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get enhanced plan comparison with current tenant's plan and usage"""
    tenant = get_tenant_from_api_key(api_key, db)
    pricing_service = PricingService(db)
    
    # Get all active plans (excluding add-ons for main comparison)
    plans = db.query(PricingPlan).filter(
        PricingPlan.is_active == True,
        PricingPlan.plan_type != "livechat_addon"
    ).all()
    
    # Get current subscription and usage
    subscription = pricing_service.get_tenant_subscription(tenant.id)
    current_plan_detail = None
    current_usage = pricing_service.get_usage_stats(tenant.id) if subscription else None
    
    # Convert plans to detailed format
    detailed_plans = []
    
    for plan in plans:
        # Parse features from JSON string
        import json
        try:
            features_list = json.loads(plan.features) if plan.features else []
        except:
            features_list = []
        
        # Build integrations list
        integrations = []
        if plan.website_api_allowed:
            integrations.append("Web Integration")
        if plan.slack_allowed:
            integrations.append("Slack Integration")
        if plan.discord_allowed:
            integrations.append("Discord Integration")
        if plan.whatsapp_allowed:
            integrations.append("WhatsApp Integration")
        
        # Determine if plan is popular (Growth plan)
        is_popular = plan.plan_type == "growth"
        
        detailed_plan = PlanFeaturesDetail(
            plan_name=plan.name,
            plan_type=plan.plan_type,
            price_monthly=plan.price_monthly,
            price_yearly=plan.price_yearly,
            conversations_limit=plan.max_messages_monthly,
            features=features_list,
            integrations=integrations,
            is_popular=is_popular,
            is_addon=False
        )
        
        detailed_plans.append(detailed_plan)
        
        # Set current plan if it matches
        if subscription and subscription.plan.id == plan.id:
            current_plan_detail = detailed_plan
    
    # Sort plans by price
    detailed_plans.sort(key=lambda x: x.price_monthly)
    
    return PlanComparisonDetailOut(
        plans=detailed_plans,
        current_plan=current_plan_detail,
        current_usage=current_usage
    )


@router.get("/billing/history", response_model=List[BillingHistoryOut])
async def get_billing_history(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db),
    limit: int = 12
):
    """Get tenant's billing history"""
    tenant = get_tenant_from_api_key(api_key, db)
    
    billing_history = db.query(BillingHistory).filter(
        BillingHistory.tenant_id == tenant.id
    ).order_by(BillingHistory.created_at.desc()).limit(limit).all()
    
    return billing_history


@router.post("/check-limits")
async def check_limits(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Check if tenant can perform actions based on their plan limits"""
    tenant = get_tenant_from_api_key(api_key, db)
    pricing_service = PricingService(db)
    
    can_send_messages = pricing_service.check_message_limit(tenant.id)
    can_add_integrations = pricing_service.check_integration_limit(tenant.id)
    
    return {
        "can_start_conversations": can_send_messages,
        "can_add_integrations": can_add_integrations,
        "usage_stats": pricing_service.get_usage_stats(tenant.id),
        "conversation_definition": "A conversation is any length of interaction within 24 hours"
    }


@router.post("/log-usage/conversation")
async def log_conversation_usage(
    count: int = 1,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Log conversation usage for tenant (replaces message usage)"""
    tenant = get_tenant_from_api_key(api_key, db)
    pricing_service = PricingService(db)
    
    success = pricing_service.log_message_usage(tenant.id, count)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Conversation limit exceeded for current billing period"
        )
    
    return {"message": "Conversation usage logged successfully", "success": True}


@router.post("/log-usage/integration")
async def log_integration_usage(
    integration_type: str,
    action: str = "added",  # "added" or "removed"
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Log integration usage for tenant"""
    tenant = get_tenant_from_api_key(api_key, db)
    pricing_service = PricingService(db)
    
    if action not in ["added", "removed"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Action must be 'added' or 'removed'"
        )
    
    success = pricing_service.log_integration_usage(tenant.id, integration_type, action)
    
    if not success and action == "added":
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Integration limit exceeded for current plan"
        )
    
    return {"message": f"Integration {action} logged successfully", "success": True}


@router.get("/feature-access/{feature}")
async def check_feature_access(
    feature: str,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Check if tenant has access to a specific feature"""
    tenant = get_tenant_from_api_key(api_key, db)
    pricing_service = PricingService(db)
    
    has_access = pricing_service.check_feature_access(tenant.id, feature)
    
    return {
        "feature": feature,
        "has_access": has_access,
        "tenant_id": tenant.id
    }


@router.get("/recommendations")
async def get_plan_recommendations(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get personalized plan recommendations based on usage"""
    tenant = get_tenant_from_api_key(api_key, db)
    pricing_service = PricingService(db)
    
    recommendations = pricing_service.get_plan_recommendations(tenant.id)
    
    return recommendations


@router.get("/billing/summary")
async def get_billing_summary(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get comprehensive billing summary for tenant"""
    tenant = get_tenant_from_api_key(api_key, db)
    pricing_service = PricingService(db)
    
    summary = pricing_service.get_billing_summary(tenant.id)
    
    return summary


@router.post("/initialize-defaults")
async def initialize_default_plans(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """Initialize default pricing plans (Admin only)"""
    pricing_service = PricingService(db)
    pricing_service.create_default_plans()
    
    return {"message": "Default pricing plans created successfully"}


@router.get("/plans/by-type/{plan_type}")
async def get_plan_by_type(
    plan_type: PlanType,
    db: Session = Depends(get_db)
):
    """Get plan details by plan type"""
    pricing_service = PricingService(db)
    plan = pricing_service.get_plan_by_type(plan_type.value)
    
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan of type {plan_type} not found"
        )
    
    return plan


@router.post("/add-addon/{addon_type}")
async def add_addon_to_subscription(
    addon_type: str,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Add an addon (like Live Chat) to current subscription"""
    tenant = get_tenant_from_api_key(api_key, db)
    pricing_service = PricingService(db)
    
    # Get the addon plan
    addon_plan = db.query(PricingPlan).filter(
        PricingPlan.plan_type == addon_type,
        PricingPlan.is_active == True
    ).first()
    
    if not addon_plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Addon type {addon_type} not found"
        )
    
    # For now, just return the addon details
    # In production, you'd handle payment and subscription modification
    return {
        "message": f"Addon {addon_plan.name} can be added to your subscription",
        "addon_details": {
            "name": addon_plan.name,
            "price_monthly": addon_plan.price_monthly,
            "features": addon_plan.features
        },
        "note": "Payment integration required for actual addon activation"
    }