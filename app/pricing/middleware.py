from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.pricing.service import PricingService
from app.tenants.router import get_tenant_from_api_key
import logging

logger = logging.getLogger(__name__)


class PricingMiddleware:
    """Middleware to enforce pricing limits and track usage"""
    
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        request = Request(scope, receive)
        
        # Check if this is a chatbot endpoint that should count towards message limits
        if self.should_track_message_usage(request):
            try:
                await self.check_and_track_message_usage(request)
            except HTTPException as e:
                response = JSONResponse(
                    status_code=e.status_code,
                    content={"detail": e.detail}
                )
                await response(scope, receive, send)
                return
        
        # Check if this is an integration endpoint that should check integration limits
        if self.should_check_integration_limits(request):
            try:
                await self.check_integration_limits(request)
            except HTTPException as e:
                response = JSONResponse(
                    status_code=e.status_code,
                    content={"detail": e.detail}
                )
                await response(scope, receive, send)
                return
        
        await self.app(scope, receive, send)
    
    def should_track_message_usage(self, request: Request) -> bool:
        """Determine if this request should count towards message usage"""
        path = request.url.path
        method = request.method
        
        # Track message usage for chatbot endpoints
        message_endpoints = [
            "/chatbot/chat",
            "/chatbot/send-message",
            "/api/whatsapp/webhook"  # WhatsApp webhook
        ]
        
        return method == "POST" and any(endpoint in path for endpoint in message_endpoints)
    
    def should_check_integration_limits(self, request: Request) -> bool:
        """Determine if this request should check integration limits"""
        path = request.url.path
        method = request.method
        
        # Check integration limits for adding new integrations
        integration_endpoints = [
            "/discord/bot/create",
            "/api/whatsapp/setup",
            "/integrations/slack/setup"
        ]
        
        return method == "POST" and any(endpoint in path for endpoint in integration_endpoints)
    
    async def check_and_track_message_usage(self, request: Request):
        """Check message limits and track usage"""
        # Get API key from headers
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            # Skip if no API key (might be admin endpoint)
            return
        
        # Get database session
        db = next(get_db())
        try:
            # Get tenant from API key
            tenant = get_tenant_from_api_key(api_key, db)
            
            # Check and log message usage
            pricing_service = PricingService(db)
            
            # Check if tenant can send messages
            if not pricing_service.check_message_limit(tenant.id):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Message limit exceeded for your current plan. Please upgrade to continue."
                )
            
            # Log the message usage (this will be done after successful response)
            # We'll track this in the actual endpoint handlers
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error in pricing middleware: {e}")
            # Don't block the request for other errors
        finally:
            db.close()
    
    async def check_integration_limits(self, request: Request):
        """Check integration limits for new integrations"""
        # Get API key from headers
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            return
        
        # Get database session
        db = next(get_db())
        try:
            # Get tenant from API key
            tenant = get_tenant_from_api_key(api_key, db)
            
            # Check integration limits
            pricing_service = PricingService(db)
            
            if not pricing_service.check_integration_limit(tenant.id):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Integration limit exceeded for your current plan. Please upgrade to add more integrations."
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error checking integration limits: {e}")
        finally:
            db.close()


async def track_message_usage_decorator(tenant_id: int, db: Session, count: int = 1):
    """Decorator/helper function to track message usage after successful processing"""
    try:
        pricing_service = PricingService(db)
        success = pricing_service.log_message_usage(tenant_id, count)
        if not success:
            logger.warning(f"Failed to log message usage for tenant {tenant_id}")
    except Exception as e:
        logger.error(f"Error tracking message usage: {e}")


async def track_integration_usage_decorator(tenant_id: int, db: Session, integration_type: str, action: str = "added"):
    """Decorator/helper function to track integration usage"""
    try:
        pricing_service = PricingService(db)
        success = pricing_service.log_integration_usage(tenant_id, integration_type, action)
        if not success:
            logger.warning(f"Failed to log integration usage for tenant {tenant_id}")
    except Exception as e:
        logger.error(f"Error tracking integration usage: {e}")


def check_feature_access_decorator(tenant_id: int, db: Session, feature: str) -> bool:
    """Decorator/helper function to check feature access"""
    try:
        pricing_service = PricingService(db)
        return pricing_service.check_feature_access(tenant_id, feature)
    except Exception as e:
        logger.error(f"Error checking feature access: {e}")
        return False