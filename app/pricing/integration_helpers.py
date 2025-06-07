# app/pricing/integration_helpers.py
"""
Complete integration helpers for conversation-based pricing system
Includes ALL functions needed for proper operation
"""

from fastapi import HTTPException, status, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.pricing.service import PricingService
from app.database import get_db
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


# ============================================================================
# DEPENDENCY FUNCTIONS FOR FASTAPI ENDPOINTS
# ============================================================================

def check_message_limit_dependency(tenant_id: int, db: Session = Depends(get_db)):
    """Legacy function name - redirects to conversation limit check"""
    return check_conversation_limit_dependency(tenant_id, db)


def check_conversation_limit_dependency(tenant_id: int, db: Session = Depends(get_db)):
    """Dependency function to check conversation limits before processing"""
    logger.info(f"🔍 Checking conversation limit for tenant {tenant_id}")
    
    try:
        # Use the PricingService for consistency
        pricing_service = PricingService(db)
        
        if not pricing_service.check_message_limit(tenant_id):
            logger.warning(f"🚫 Conversation limit exceeded for tenant {tenant_id}")
            
            # Get more details for better error message
            try:
                usage_stats = pricing_service.get_usage_stats(tenant_id)
                subscription = pricing_service.get_tenant_subscription(tenant_id)
                plan_name = subscription.plan.name if subscription else "Unknown"
                
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "error": "Conversation limit exceeded",
                        "message": f"You have reached your monthly limit of {usage_stats.messages_limit} conversations on the {plan_name} plan. Please upgrade to continue.",
                        "current_usage": usage_stats.messages_used,
                        "limit": usage_stats.messages_limit,
                        "plan_name": plan_name,
                        "upgrade_required": True,
                        "conversation_definition": "A conversation is any length of interaction within 24 hours"
                    }
                )
            except:
                # Fallback error message
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "error": "Conversation limit exceeded",
                        "message": "You have reached your monthly conversation limit. Please upgrade your plan to continue.",
                        "upgrade_required": True,
                        "conversation_definition": "A conversation is any length of interaction within 24 hours"
                    }
                )
        
        logger.info(f"✅ Conversation limit check passed for tenant {tenant_id}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"💥 Error checking conversation limit for tenant {tenant_id}: {e}")
        # Don't block on database errors - log but continue
        pass


def check_integration_limit_dependency(tenant_id: int, db: Session = Depends(get_db)):
    """Dependency function to check integration limits before adding"""
    logger.info(f"🔍 Checking integration limit for tenant {tenant_id}")
    
    try:
        pricing_service = PricingService(db)
        
        if not pricing_service.check_integration_limit(tenant_id):
            logger.warning(f"🚫 Integration limit exceeded for tenant {tenant_id}")
            
            # Get plan details for better error message
            try:
                subscription = pricing_service.get_tenant_subscription(tenant_id)
                plan_name = subscription.plan.name if subscription else "Unknown"
                current_count = subscription.integrations_count if subscription else 0
                limit = subscription.plan.max_integrations if subscription else 0
                
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "error": "Integration limit exceeded",
                        "message": f"You have reached your integration limit of {limit} on the {plan_name} plan. Please upgrade to add more integrations.",
                        "current_usage": current_count,
                        "limit": limit,
                        "plan_name": plan_name,
                        "upgrade_required": True
                    }
                )
            except:
                # Fallback error message
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "error": "Integration limit exceeded",
                        "message": "You have reached your integration limit. Please upgrade your plan to add more integrations.",
                        "upgrade_required": True
                    }
                )
        
        logger.info(f"✅ Integration limit check passed for tenant {tenant_id}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"💥 Error checking integration limit for tenant {tenant_id}: {e}")


def check_feature_access_dependency(tenant_id: int, feature: str, db: Session = Depends(get_db)):
    """Dependency function to check feature access"""
    logger.info(f"🔍 Checking feature access for tenant {tenant_id}, feature: {feature}")
    
    # Temporarily block WhatsApp and Live Chat features
    if feature in ["whatsapp", "live_chat"]:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "Feature temporarily unavailable",
                "message": f"The {feature} feature is temporarily disabled while we prepare exciting updates. Please check back soon!",
                "feature": feature,
                "status": "coming_soon"
            }
        )
    
    try:
        pricing_service = PricingService(db)
        
        if not pricing_service.check_feature_access(tenant_id, feature):
            logger.warning(f"🚫 Feature {feature} not available for tenant {tenant_id}")
            
            # Get current plan for better error message
            try:
                subscription = pricing_service.get_tenant_subscription(tenant_id)
                current_plan = subscription.plan.name if subscription else "Unknown"
                
                # Suggest appropriate upgrade based on feature
                upgrade_suggestions = {
                    "advanced_analytics": "Basic plan or higher",
                    "priority_support": "Growth plan or higher",
                    "api_access": "Pro plan or higher",
                    "white_label": "Agency plan",
                    "custom_integrations": "Agency plan"
                }
                
                suggested_plan = upgrade_suggestions.get(feature, "a higher plan")
                
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "error": "Feature not available",
                        "message": f"The {feature} feature is not available on your current {current_plan} plan. Please upgrade to {suggested_plan} to access this feature.",
                        "feature": feature,
                        "current_plan": current_plan,
                        "suggested_plan": suggested_plan,
                        "upgrade_required": True
                    }
                )
            except:
                # Fallback error message
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
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"💥 Error checking feature access for tenant {tenant_id}: {e}")


# ============================================================================
# CONVERSATION TRACKING FUNCTIONS
# ============================================================================

def track_conversation_started(tenant_id: int, user_identifier: str, platform: str, db: Session) -> bool:
    """
    Track when a new conversation starts - PRIMARY CONVERSATION TRACKING FUNCTION
    This implements the 24-hour conversation window logic
    """
    try:
        logger.info(f"📊 Tracking conversation start for tenant {tenant_id}, user: {user_identifier}, platform: {platform}")
        
        # Check if ConversationSession model exists, if not use fallback
        try:
            from app.pricing.models import ConversationSession
            model_available = True
        except ImportError:
            logger.warning("ConversationSession model not available, using fallback tracking")
            model_available = False
        
        if model_available:
            # Use full conversation tracking with ConversationSession model
            last_24_hours = datetime.utcnow() - timedelta(hours=24)
            existing_conversation = db.query(ConversationSession).filter(
                ConversationSession.tenant_id == tenant_id,
                ConversationSession.user_identifier == user_identifier,
                ConversationSession.platform == platform,
                ConversationSession.last_activity > last_24_hours,
                ConversationSession.is_active == True
            ).first()
            
            if existing_conversation:
                # Update existing conversation activity
                existing_conversation.last_activity = datetime.utcnow()
                existing_conversation.message_count += 1
                
                # Update duration
                duration = (existing_conversation.last_activity - existing_conversation.started_at).total_seconds() / 60
                existing_conversation.duration_minutes = int(duration)
                
                db.commit()
                logger.info(f"✅ Updated existing conversation for tenant {tenant_id}")
                return True
            else:
                # Start new conversation and log usage
                pricing_service = PricingService(db)
                success = pricing_service.log_message_usage(tenant_id, 1)
                
                if success:
                    # Create conversation session record
                    new_conversation = ConversationSession(
                        tenant_id=tenant_id,
                        user_identifier=user_identifier,
                        platform=platform,
                        started_at=datetime.utcnow(),
                        last_activity=datetime.utcnow(),
                        message_count=1,
                        counted_for_billing=True
                    )
                    db.add(new_conversation)
                    db.commit()
                    
                    logger.info(f"✅ Started new conversation and logged usage for tenant {tenant_id}")
                    return True
                else:
                    logger.warning(f"⚠️ Failed to start conversation - limit exceeded for tenant {tenant_id}")
                    return False
        else:
            # Fallback to simple usage tracking without conversation sessions
            pricing_service = PricingService(db)
            success = pricing_service.log_message_usage(tenant_id, 1)
            
            if success:
                logger.info(f"✅ Logged message usage (fallback) for tenant {tenant_id}")
            else:
                logger.warning(f"⚠️ Failed to log message usage for tenant {tenant_id}")
            
            return success
        
    except Exception as e:
        logger.error(f"💥 Error tracking conversation for tenant {tenant_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def track_message_sent(tenant_id: int, db: Session, count: int = 1, user_identifier: str = None, platform: str = "web") -> bool:
    """
    Track individual message usage (updated for conversation-based model)
    This now focuses on updating conversation activity rather than counting individual messages
    """
    try:
        logger.info(f"📊 Tracking message for tenant {tenant_id}, count: {count}, platform: {platform}")
        
        if user_identifier:
            # Use conversation tracking
            return track_conversation_started(tenant_id, user_identifier, platform, db)
        else:
            # Fallback for when user_identifier is not provided
            pricing_service = PricingService(db)
            success = pricing_service.log_message_usage(tenant_id, count)
            
            if success:
                logger.info(f"✅ Logged message usage (fallback) for tenant {tenant_id}")
            else:
                logger.warning(f"⚠️ Failed to log message usage for tenant {tenant_id}")
            
            return success
        
    except Exception as e:
        logger.error(f"💥 Error tracking message for tenant {tenant_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


# ============================================================================
# INTEGRATION TRACKING FUNCTIONS
# ============================================================================

def track_integration_added(tenant_id: int, db: Session, integration_type: str) -> bool:
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


def track_integration_removed(tenant_id: int, db: Session, integration_type: str) -> bool:
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


# ============================================================================
# USAGE SUMMARY AND ANALYTICS FUNCTIONS
# ============================================================================

def get_tenant_usage_summary(tenant_id: int, db: Session) -> Dict[str, Any]:
    """Get a summary of tenant's current usage and limits"""
    try:
        logger.info(f"📈 Getting usage summary for tenant {tenant_id}")
        pricing_service = PricingService(db)
        
        # Get basic usage stats
        usage_stats = pricing_service.get_usage_stats(tenant_id)
        subscription = pricing_service.get_tenant_subscription(tenant_id)
        
        # Try to get conversation statistics if model is available
        conversation_details = {}
        try:
            from app.pricing.models import ConversationSession
            
            current_period_start = subscription.current_period_start if subscription else datetime.utcnow() - timedelta(days=30)
            
            active_conversations = db.query(ConversationSession).filter(
                ConversationSession.tenant_id == tenant_id,
                ConversationSession.started_at >= current_period_start,
                ConversationSession.counted_for_billing == True
            ).count()
            
            conversation_details = {
                "active_conversations_this_period": active_conversations,
                "conversation_definition": "A conversation is any length of interaction within 24 hours"
            }
        except ImportError:
            conversation_details = {
                "conversation_definition": "A conversation is any length of interaction within 24 hours"
            }
        
        return {
            "usage_stats": usage_stats,
            "subscription": {
                "plan_name": subscription.plan.name if subscription else "No Plan",
                "billing_cycle": subscription.billing_cycle if subscription else None,
                "next_billing_date": subscription.current_period_end if subscription else None
            },
            "conversation_details": conversation_details,
            "warnings": check_and_warn_usage_limits(tenant_id, db)
        }
    except Exception as e:
        logger.error(f"💥 Error getting usage summary: {e}")
        return {"error": str(e)}


def check_and_warn_usage_limits(tenant_id: int, db: Session) -> List[Dict[str, Any]]:
    """Check usage and return warnings if approaching limits"""
    try:
        pricing_service = PricingService(db)
        usage_stats = pricing_service.get_usage_stats(tenant_id)
        
        warnings = []
        
        # Check conversation usage
        if usage_stats.messages_limit > 0:  # Avoid division by zero
            conversation_percent = (usage_stats.messages_used / usage_stats.messages_limit) * 100
            
            if conversation_percent >= 90:
                warnings.append({
                    "type": "conversation_limit",
                    "severity": "critical",
                    "message": f"You've used {conversation_percent:.1f}% of your conversation limit",
                    "current_usage": usage_stats.messages_used,
                    "limit": usage_stats.messages_limit,
                    "definition": "A conversation is any length of interaction within 24 hours"
                })
            elif conversation_percent >= 75:
                warnings.append({
                    "type": "conversation_limit",
                    "severity": "warning",
                    "message": f"You've used {conversation_percent:.1f}% of your conversation limit",
                    "current_usage": usage_stats.messages_used,
                    "limit": usage_stats.messages_limit,
                    "definition": "A conversation is any length of interaction within 24 hours"
                })
        
        # Check integration usage (though most plans now have unlimited integrations)
        if usage_stats.integrations_limit != -1 and usage_stats.integrations_limit > 0:
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


# ============================================================================
# ADVANCED ANALYTICS FUNCTIONS
# ============================================================================

def end_conversation_session(tenant_id: int, user_identifier: str, platform: str, db: Session) -> bool:
    """
    Manually end a conversation session
    Useful for explicit session termination
    """
    try:
        from app.pricing.models import ConversationSession
        
        # Find active conversation
        conversation = db.query(ConversationSession).filter(
            ConversationSession.tenant_id == tenant_id,
            ConversationSession.user_identifier == user_identifier,
            ConversationSession.platform == platform,
            ConversationSession.is_active == True
        ).first()
        
        if conversation:
            conversation.is_active = False
            
            # Calculate final duration
            duration = (datetime.utcnow() - conversation.started_at).total_seconds() / 60
            conversation.duration_minutes = int(duration)
            
            db.commit()
            logger.info(f"✅ Ended conversation session for tenant {tenant_id}")
            return True
        else:
            logger.info(f"ℹ️ No active conversation found to end for tenant {tenant_id}")
            return False
            
    except Exception as e:
        logger.error(f"💥 Error ending conversation session: {e}")
        return False


def get_conversation_analytics(tenant_id: int, db: Session, days: int = 30) -> Dict[str, Any]:
    """
    Get conversation analytics for the tenant
    Useful for advanced analytics feature
    """
    try:
        from app.pricing.models import ConversationSession
        
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Get conversation statistics
        conversations = db.query(ConversationSession).filter(
            ConversationSession.tenant_id == tenant_id,
            ConversationSession.started_at >= start_date
        ).all()
        
        if not conversations:
            return {
                "total_conversations": 0,
                "total_messages": 0,
                "average_duration": 0,
                "platform_breakdown": {},
                "daily_breakdown": {},
                "period_days": days
            }
        
        # Platform breakdown
        platform_stats = {}
        for conv in conversations:
            platform = conv.platform or "unknown"
            if platform not in platform_stats:
                platform_stats[platform] = {
                    "count": 0,
                    "total_messages": 0,
                    "total_duration": 0
                }
            platform_stats[platform]["count"] += 1
            platform_stats[platform]["total_messages"] += conv.message_count or 0
            platform_stats[platform]["total_duration"] += conv.duration_minutes or 0
        
        # Daily breakdown
        daily_stats = {}
        for conv in conversations:
            day = conv.started_at.date().isoformat()
            if day not in daily_stats:
                daily_stats[day] = 0
            daily_stats[day] += 1
        
        total_conversations = len(conversations)
        total_messages = sum(conv.message_count or 0 for conv in conversations)
        total_duration = sum(conv.duration_minutes or 0 for conv in conversations)
        average_duration = total_duration / total_conversations if total_conversations > 0 else 0
        
        return {
            "total_conversations": total_conversations,
            "total_messages": total_messages,
            "average_duration": round(average_duration, 2),
            "platform_breakdown": platform_stats,
            "daily_breakdown": daily_stats,
            "period_days": days
        }
        
    except Exception as e:
        logger.error(f"💥 Error getting conversation analytics: {e}")
        return {"error": str(e)}


# ============================================================================
# DECORATOR FUNCTIONS
# ============================================================================

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


def track_conversation_usage(user_identifier: str = None, platform: str = "web"):
    """Decorator to automatically track conversation usage after successful endpoint execution"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            
            # Extract tenant_id and db from function parameters
            tenant_id = kwargs.get('tenant_id') or args[0] if args else None
            db = kwargs.get('db') or next(get_db())
            
            if tenant_id and user_identifier:
                track_conversation_started(tenant_id, user_identifier, platform, db)
            
            return result
        return wrapper
    return decorator