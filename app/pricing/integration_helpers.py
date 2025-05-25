"""
Helper functions to integrate pricing checks into existing endpoints
"""

from fastapi import HTTPException, status, Depends
from sqlalchemy.orm import Session
from app.pricing.service import PricingService
from app.database import get_db
import logging

logger = logging.getLogger(__name__)


def check_message_limit_dependency(tenant_id: int, db: Session = Depends(get_db)):
    """Dependency function to check message limits before processing"""
    logger.info(f"🔍 Checking message limit for tenant {tenant_id}")
    pricing_service = PricingService(db)
    
    if not pricing_service.check_message_limit(tenant_id):
        logger.warning(f"🚫 Message limit exceeded for tenant {tenant_id}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "Message limit exceeded",
                "message": "You have reached your monthly message limit. Please upgrade your plan to continue.",
                "upgrade_required": True
            }
        )
    
    logger.info(f"✅ Message limit check passed for tenant {tenant_id}")


def check_integration_limit_dependency(tenant_id: int, db: Session = Depends(get_db)):
    """Dependency function to check integration limits before adding"""
    logger.info(f"🔍 Checking integration limit for tenant {tenant_id}")
    pricing_service = PricingService(db)
    
    if not pricing_service.check_integration_limit(tenant_id):
        logger.warning(f"🚫 Integration limit exceeded for tenant {tenant_id}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "Integration limit exceeded",
                "message": "You have reached your integration limit. Please upgrade your plan to add more integrations.",
                "upgrade_required": True
            }
        )
    
    logger.info(f"✅ Integration limit check passed for tenant {tenant_id}")


def check_feature_access_dependency(tenant_id: int, feature: str, db: Session = Depends(get_db)):
    """Dependency function to check feature access"""
    logger.info(f"🔍 Checking feature access for tenant {tenant_id}, feature: {feature}")
    pricing_service = PricingService(db)
    
    if not pricing_service.check_feature_access(tenant_id, feature):
        logger.warning(f"🚫 Feature {feature} not available for tenant {tenant_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "Feature not available",
                "message": f"The {feature} feature is not available on your current plan. Please upgrade to access this feature.",
                "feature": feature,
                "upgrade_required": True
            }
        )
    
    logger.info(f"✅ Feature access granted for tenant {tenant_id}, feature: {feature}")


# Usage tracking functions (call after successful operations)

def track_message_sent(tenant_id: int, db: Session, count: int = 1):
    """Track message usage after successful send"""
    try:
        logger.info(f"📊 Starting to track message usage for tenant {tenant_id}, count: {count}")
        pricing_service = PricingService(db)
        success = pricing_service.log_message_usage(tenant_id, count)
        
        if success:
            logger.info(f"✅ Successfully tracked {count} message(s) for tenant {tenant_id}")
        else:
            logger.warning(f"⚠️ Failed to track message usage for tenant {tenant_id} - might have hit limit")
        
        return success
    except Exception as e:
        logger.error(f"💥 Error tracking message usage for tenant {tenant_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def track_integration_added(tenant_id: int, db: Session, integration_type: str):
    """Track integration addition after successful setup"""
    try:
        logger.info(f"📊 Tracking integration addition for tenant {tenant_id}, type: {integration_type}")
        pricing_service = PricingService(db)
        success = pricing_service.log_integration_usage(tenant_id, integration_type, "added")
        
        if success:
            logger.info(f"✅ Successfully tracked integration addition for tenant {tenant_id}")
        else:
            logger.warning(f"⚠️ Failed to track integration addition for tenant {tenant_id}")
        
        return success
    except Exception as e:
        logger.error(f"💥 Error tracking integration addition: {e}")
        return False


def track_integration_removed(tenant_id: int, db: Session, integration_type: str):
    """Track integration removal"""
    try:
        logger.info(f"📊 Tracking integration removal for tenant {tenant_id}, type: {integration_type}")
        pricing_service = PricingService(db)
        success = pricing_service.log_integration_usage(tenant_id, integration_type, "removed")
        
        if success:
            logger.info(f"✅ Successfully tracked integration removal for tenant {tenant_id}")
        else:
            logger.warning(f"⚠️ Failed to track integration removal for tenant {tenant_id}")
        
        return success
    except Exception as e:
        logger.error(f"💥 Error tracking integration removal: {e}")
        return False


def get_tenant_usage_summary(tenant_id: int, db: Session):
    """Get a summary of tenant's current usage and limits"""
    try:
        logger.info(f"📈 Getting usage summary for tenant {tenant_id}")
        pricing_service = PricingService(db)
        usage_stats = pricing_service.get_usage_stats(tenant_id)
        subscription = pricing_service.get_tenant_subscription(tenant_id)
        
        return {
            "usage_stats": usage_stats,
            "subscription": {
                "plan_name": subscription.plan.name if subscription else "No Plan",
                "billing_cycle": subscription.billing_cycle if subscription else None,
                "next_billing_date": subscription.current_period_end if subscription else None
            },
            "warnings": []
        }
    except Exception as e:
        logger.error(f"💥 Error getting usage summary: {e}")
        return None


def check_and_warn_usage_limits(tenant_id: int, db: Session):
    """Check usage and return warnings if approaching limits"""
    try:
        pricing_service = PricingService(db)
        usage_stats = pricing_service.get_usage_stats(tenant_id)
        
        warnings = []
        
        # Check message usage
        message_percent = (usage_stats.messages_used / usage_stats.messages_limit) * 100
        if message_percent >= 90:
            warnings.append({
                "type": "message_limit",
                "severity": "critical",
                "message": f"You've used {message_percent:.1f}% of your message limit"
            })
        elif message_percent >= 75:
            warnings.append({
                "type": "message_limit",
                "severity": "warning",
                "message": f"You've used {message_percent:.1f}% of your message limit"
            })
        
        # Check integration usage
        if usage_stats.integrations_limit != -1:
            integration_percent = (usage_stats.integrations_used / usage_stats.integrations_limit) * 100
            if integration_percent >= 90:
                warnings.append({
                    "type": "integration_limit",
                    "severity": "critical",
                    "message": f"You've used {integration_percent:.1f}% of your integration limit"
                })
        
        return warnings
    except Exception as e:
        logger.error(f"💥 Error checking usage limits: {e}")
        return []


# Decorator functions for easy integration

def require_feature_access(feature: str):
    """Decorator to require feature access for an endpoint"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            # This would need to be customized based on how you extract tenant_id
            # from your endpoint parameters
            tenant_id = kwargs.get('tenant_id') or args[0] if args else None
            db = kwargs.get('db') or next(get_db())
            
            if tenant_id:
                check_feature_access_dependency(tenant_id, feature, db)
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


def track_message_usage(count: int = 1):
    """Decorator to automatically track message usage after successful endpoint execution"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            
            # Extract tenant_id and db from function parameters
            tenant_id = kwargs.get('tenant_id') or args[0] if args else None
            db = kwargs.get('db') or next(get_db())
            
            if tenant_id:
                track_message_sent(tenant_id, db, count)
            
            return result
        return wrapper
    return decorator


# Example usage in your existing endpoints:
"""
# In your chatbot router - before processing message
@router.post("/chat")
async def chat_endpoint(
    message_data: ChatRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    tenant = get_tenant_from_api_key(api_key, db)
    
    # Check message limit before processing
    check_message_limit_dependency(tenant.id, db)
    
    # Process the chat message
    response = await process_chat_message(message_data, tenant)
    
    # Track usage after successful processing
    track_message_sent(tenant.id, db, count=1)
    
    return response


# In your discord router - before creating bot
@router.post("/bot/create")
async def create_discord_bot(
    bot_data: DiscordBotCreate,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    tenant = get_tenant_from_api_key(api_key, db)
    
    # Check feature access
    check_feature_access_dependency(tenant.id, "discord", db)
    
    # Check integration limit
    check_integration_limit_dependency(tenant.id, db)
    
    # Create the bot
    bot = await create_bot(bot_data, tenant)
    
    # Track integration addition
    track_integration_added(tenant.id, db, "discord")
    
    return bot


# In your tenant router - before updating system prompt
@router.put("/{tenant_id}/prompt")
async def update_tenant_prompt(
    tenant_id: int,
    prompt_data: dict,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    tenant = get_tenant_from_api_key(api_key, db)
    
    # Check custom prompt feature access
    check_feature_access_dependency(tenant.id, "custom_prompt", db)
    
    # Update the prompt
    tenant.system_prompt = prompt_data.get("system_prompt")
    db.commit()
    
    return tenant
"""