

# import logging
# import json
# from typing import Dict, Any, Optional, List
# from fastapi import APIRouter, Depends, HTTPException, Header, Request, status, BackgroundTasks
# from sqlalchemy.orm import Session
# from pydantic import BaseModel, Field, validator

# from app.database import get_db
# from app.tenants.router import get_tenant_from_api_key
# from app.instagram.models import InstagramIntegration, InstagramConversation, InstagramMessage
# from app.instagram.service import InstagramAPIService, InstagramWebhookProcessor, InstagramConversationManager
# from app.instagram.bot_manager import get_instagram_bot_manager
# from app.pricing.integration_helpers import (
#     check_integration_limit_dependency_with_super_tenant
# )

# logger = logging.getLogger(__name__)

# router = APIRouter()

# # Pydantic Models
# class InstagramIntegrationCreate(BaseModel):
#     meta_app_id: str = Field(..., min_length=1, description="Meta App ID")
#     meta_app_secret: str = Field(..., min_length=1, description="Meta App Secret")
#     facebook_page_id: str = Field(..., min_length=1, description="Facebook Page ID")
#     page_access_token: str = Field(..., min_length=1, description="Page Access Token")
#     instagram_business_account_id: str = Field(..., min_length=1, description="Instagram Business Account ID")
#     instagram_username: str = Field(..., min_length=1, description="Instagram Username")
#     webhook_verify_token: str = Field(..., min_length=8, description="Webhook Verify Token")
    
#     @validator('instagram_username')
#     def clean_username(cls, v):
#         return v.lstrip('@').lower()

# class InstagramIntegrationUpdate(BaseModel):
#     bot_enabled: Optional[bool] = None
#     auto_reply_enabled: Optional[bool] = None
#     webhook_verify_token: Optional[str] = None

# class InstagramIntegrationResponse(BaseModel):
#     id: int
#     tenant_id: int
#     instagram_username: str
#     facebook_page_id: str
#     bot_enabled: bool
#     bot_status: str
#     webhook_subscribed: bool
#     last_message_at: Optional[str] = None
#     error_count: int
#     created_at: str

# class InstagramTestMessageRequest(BaseModel):
#     instagram_user_id: str = Field(..., description="Instagram User ID to send test message to")
#     message: str = Field(..., min_length=1, max_length=1000, description="Test message content")

# class InstagramConversationResponse(BaseModel):
#     id: int
#     conversation_id: str
#     instagram_user_id: str
#     instagram_username: Optional[str] = None
#     user_profile_name: Optional[str] = None
#     is_active: bool
#     conversation_status: str
#     total_messages: int
#     last_message_at: Optional[str] = None
#     created_at: str

# class InstagramMessageResponse(BaseModel):
#     id: int
#     message_uuid: str
#     message_type: str
#     content: Optional[str] = None
#     is_from_user: bool
#     message_status: str
#     created_at: str

# # Setup Endpoints
# @router.post("/setup", response_model=InstagramIntegrationResponse)
# async def setup_instagram_integration(
#     integration_data: InstagramIntegrationCreate,
#     background_tasks: BackgroundTasks,
#     api_key: str = Header(..., alias="X-API-Key"),
#     db: Session = Depends(get_db)
# ):
#     """Set up Instagram integration for tenant"""
#     try:
        
#         tenant = get_tenant_from_api_key(api_key, db)
        
       
#         check_integration_limit_dependency_with_super_tenant(tenant.id, db)
        
        
#         existing = db.query(InstagramIntegration).filter(
#             InstagramIntegration.tenant_id == tenant.id
#         ).first()
        
#         if existing:
#             raise HTTPException(
#                 status_code=400,
#                 detail="Instagram integration already exists for this tenant"
#             )
        
       
#         integration = InstagramIntegration(
#             tenant_id=tenant.id,
#             meta_app_id=integration_data.meta_app_id,
#             meta_app_secret=integration_data.meta_app_secret,
#             facebook_page_id=integration_data.facebook_page_id,
#             page_access_token=integration_data.page_access_token,
#             instagram_business_account_id=integration_data.instagram_business_account_id,
#             instagram_username=integration_data.instagram_username,
#             webhook_verify_token=integration_data.webhook_verify_token,
#             bot_status="setup"
#         )
        
#         db.add(integration)
#         db.commit()
#         db.refresh(integration)
        
#         # Test API connection
#         api_service = InstagramAPIService(integration, db)
#         connection_success, connection_msg = api_service.test_api_connection()
        
#         if not connection_success:
#             integration.bot_status = "error"
#             integration.last_error = f"API connection failed: {connection_msg}"
#             db.commit()
            
#             raise HTTPException(
#                 status_code=400,
#                 detail=f"Instagram API connection failed: {connection_msg}"
#             )
        
        
#         webhook_success = api_service.subscribe_to_webhooks()
#         if webhook_success:
#             logger.info(f"✅ Webhooks subscribed for tenant {tenant.id}")
#         else:
#             logger.warning(f"⚠️ Webhook subscription failed for tenant {tenant.id}")
        
       
#         integration.bot_status = "active"
#         db.commit()
        
#         # Add to bot manager
#         background_tasks.add_task(
#             get_instagram_bot_manager().add_integration,
#             tenant.id
#         )
        
#         # Track integration creation
#         # track_integration_created(tenant.id, "instagram", db)
        
#         logger.info(f"✅ Instagram integration created for tenant {tenant.id}")
        
#         return InstagramIntegrationResponse(
#             id=integration.id,
#             tenant_id=integration.tenant_id,
#             instagram_username=integration.instagram_username,
#             facebook_page_id=integration.facebook_page_id,
#             bot_enabled=integration.bot_enabled,
#             bot_status=integration.bot_status,
#             webhook_subscribed=integration.webhook_subscribed,
#             last_message_at=integration.last_message_at.isoformat() if integration.last_message_at else None,
#             error_count=integration.error_count,
#             created_at=integration.created_at.isoformat()
#         )
        
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error setting up Instagram integration: {str(e)}")
#         raise HTTPException(status_code=500, detail="Failed to set up Instagram integration")

# @router.get("/status", response_model=InstagramIntegrationResponse)
# async def get_instagram_status(
#     api_key: str = Header(..., alias="X-API-Key"),
#     db: Session = Depends(get_db)
# ):
#     """Get Instagram integration status"""
#     try:
#         tenant = get_tenant_from_api_key(api_key, db)
        
#         integration = db.query(InstagramIntegration).filter(
#             InstagramIntegration.tenant_id == tenant.id
#         ).first()
        
#         if not integration:
#             raise HTTPException(
#                 status_code=404,
#                 detail="Instagram integration not found"
#             )
        
#         return InstagramIntegrationResponse(
#             id=integration.id,
#             tenant_id=integration.tenant_id,
#             instagram_username=integration.instagram_username,
#             facebook_page_id=integration.facebook_page_id,
#             bot_enabled=integration.bot_enabled,
#             bot_status=integration.bot_status,
#             webhook_subscribed=integration.webhook_subscribed,
#             last_message_at=integration.last_message_at.isoformat() if integration.last_message_at else None,
#             error_count=integration.error_count,
#             created_at=integration.created_at.isoformat()
#         )
        
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error getting Instagram status: {str(e)}")
#         raise HTTPException(status_code=500, detail="Failed to get Instagram status")

# @router.put("/settings", response_model=InstagramIntegrationResponse)
# async def update_instagram_settings(
#     settings_update: InstagramIntegrationUpdate,
#     api_key: str = Header(..., alias="X-API-Key"),
#     db: Session = Depends(get_db)
# ):
#     """Update Instagram integration settings"""
#     try:
#         tenant = get_tenant_from_api_key(api_key, db)
        
#         integration = db.query(InstagramIntegration).filter(
#             InstagramIntegration.tenant_id == tenant.id
#         ).first()
        
#         if not integration:
#             raise HTTPException(
#                 status_code=404,
#                 detail="Instagram integration not found"
#             )
        
#         # Update settings
#         update_data = settings_update.dict(exclude_unset=True)
#         for field, value in update_data.items():
#             setattr(integration, field, value)
        
#         db.commit()
#         db.refresh(integration)
        
#         # If bot was disabled, remove from manager
#         if settings_update.bot_enabled is False:
#             get_instagram_bot_manager().remove_integration(tenant.id)
        
#         # If bot was enabled, add to manager
#         elif settings_update.bot_enabled is True and integration.bot_status == "active":
#             await get_instagram_bot_manager().add_integration(tenant.id)
        
#         logger.info(f"✅ Instagram settings updated for tenant {tenant.id}")
        
#         return InstagramIntegrationResponse(
#             id=integration.id,
#             tenant_id=integration.tenant_id,
#             instagram_username=integration.instagram_username,
#             facebook_page_id=integration.facebook_page_id,
#             bot_enabled=integration.bot_enabled,
#             bot_status=integration.bot_status,
#             webhook_subscribed=integration.webhook_subscribed,
#             last_message_at=integration.last_message_at.isoformat() if integration.last_message_at else None,
#             error_count=integration.error_count,
#             created_at=integration.created_at.isoformat()
#         )
        
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error updating Instagram settings: {str(e)}")
#         raise HTTPException(status_code=500, detail="Failed to update Instagram settings")

# @router.delete("/integration")
# async def delete_instagram_integration(
#     api_key: str = Header(..., alias="X-API-Key"),
#     db: Session = Depends(get_db)
# ):
#     """Delete Instagram integration"""
#     try:
#         tenant = get_tenant_from_api_key(api_key, db)
        
#         integration = db.query(InstagramIntegration).filter(
#             InstagramIntegration.tenant_id == tenant.id
#         ).first()
        
#         if not integration:
#             raise HTTPException(
#                 status_code=404,
#                 detail="Instagram integration not found"
#             )
        
#         # Remove from bot manager
#         get_instagram_bot_manager().remove_integration(tenant.id)
        
#         # Delete from database
#         db.delete(integration)
#         db.commit()
        
#         logger.info(f"🗑️ Instagram integration deleted for tenant {tenant.id}")
        
#         return {"message": "Instagram integration deleted successfully"}
        
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error deleting Instagram integration: {str(e)}")
#         raise HTTPException(status_code=500, detail="Failed to delete Instagram integration")

# # Webhook Endpoints
# @router.get("/webhook")
# async def instagram_webhook_verify(request: Request):
#     """Verify Instagram webhook (challenge verification)"""
#     try:
#         params = dict(request.query_params)
        
#         webhook_processor = InstagramWebhookProcessor(next(get_db()))
#         challenge = webhook_processor.verify_webhook_challenge(params)
        
#         if challenge:
#             return int(challenge)
#         else:
#             raise HTTPException(status_code=403, detail="Webhook verification failed")
            
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error in webhook verification: {str(e)}")
#         raise HTTPException(status_code=500, detail="Webhook verification error")

# @router.post("/webhook")
# async def instagram_webhook_handler(
#     request: Request,
#     background_tasks: BackgroundTasks,
#     x_hub_signature_256: str = Header(None, alias="X-Hub-Signature-256"),
#     db: Session = Depends(get_db)
# ):
#     """Handle Instagram webhook events"""
#     try:
#         # Get raw body and headers
#         body = await request.body()
#         headers = dict(request.headers)
        
#         # Parse JSON payload
#         try:
#             payload = json.loads(body.decode('utf-8'))
#         except json.JSONDecodeError:
#             logger.error("Invalid JSON in webhook payload")
#             raise HTTPException(status_code=400, detail="Invalid JSON payload")
        
#         # Verify webhook signature (Meta requirement)
#         if x_hub_signature_256:
#             # Find the integration to verify signature
#             page_id = None
#             for entry in payload.get("entry", []):
#                 page_id = entry.get("id")
#                 break
            
#             if page_id:
#                 integration = db.query(InstagramIntegration).filter(
#                     InstagramIntegration.facebook_page_id == page_id
#                 ).first()
                
#                 if integration:
#                     api_service = InstagramAPIService(integration, db)
#                     signature_valid = api_service.verify_webhook_signature(
#                         body.decode('utf-8'), x_hub_signature_256
#                     )
                    
#                     if not signature_valid:
#                         logger.warning("Invalid webhook signature")
#                         raise HTTPException(status_code=403, detail="Invalid signature")
        
#         # Process webhook in background
#         background_tasks.add_task(
#             process_instagram_webhook_background,
#             payload,
#             headers
#         )
        
#         logger.info("📨 Instagram webhook received and queued for processing")
#         return {"status": "received"}
        
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error handling Instagram webhook: {str(e)}")
#         raise HTTPException(status_code=500, detail="Webhook processing error")

# async def process_instagram_webhook_background(payload: Dict, headers: Dict):
#     """Background task to process Instagram webhook"""
#     db = None
#     try:
#         db = next(get_db())
        
#         webhook_processor = InstagramWebhookProcessor(db)
#         success, message = webhook_processor.process_webhook_event(payload, headers)
        
#         if success:
#             logger.info(f"✅ Instagram webhook processed: {message}")
            
#             # Process any incoming messages with bot manager
#             bot_manager = get_instagram_bot_manager()
            
#             for entry in payload.get("entry", []):
#                 page_id = entry.get("id")
                
#                 # Find integration
#                 integration = db.query(InstagramIntegration).filter(
#                     InstagramIntegration.facebook_page_id == page_id,
#                     InstagramIntegration.bot_enabled == True
#                 ).first()
                
#                 if not integration:
#                     continue
                
#                 tenant_id = integration.tenant_id
                
#                 # Process messaging events
#                 for messaging in entry.get("messaging", []):
#                     sender_id = messaging.get("sender", {}).get("id")
                    
#                     # Skip if we're the sender
#                     if sender_id == page_id:
#                         continue
                    
#                     # Find conversation
#                     conversation = db.query(InstagramConversation).filter(
#                         InstagramConversation.integration_id == integration.id,
#                         InstagramConversation.instagram_user_id == sender_id,
#                         InstagramConversation.is_active == True
#                     ).first()
                    
#                     if conversation:
#                         # Get the latest message
#                         latest_message = db.query(InstagramMessage).filter(
#                             InstagramMessage.conversation_id == conversation.id,
#                             InstagramMessage.is_from_user == True
#                         ).order_by(InstagramMessage.created_at.desc()).first()
                        
#                         if latest_message:
#                             await bot_manager.process_incoming_message(
#                                 tenant_id, conversation, latest_message
#                             )
#         else:
#             logger.error(f"❌ Instagram webhook processing failed: {message}")
            
#     except Exception as e:
#         logger.error(f"💥 Error in background webhook processing: {str(e)}")
#     finally:
#         if db:
#             db.close()

# # Conversation Management
# @router.get("/conversations", response_model=List[InstagramConversationResponse])
# async def get_instagram_conversations(
#     limit: int = 20,
#     offset: int = 0,
#     status: Optional[str] = None,
#     api_key: str = Header(..., alias="X-API-Key"),
#     db: Session = Depends(get_db)
# ):
#     """Get Instagram conversations for tenant"""
#     try:
#         tenant = get_tenant_from_api_key(api_key, db)
        
#         integration = db.query(InstagramIntegration).filter(
#             InstagramIntegration.tenant_id == tenant.id
#         ).first()
        
#         if not integration:
#             raise HTTPException(
#                 status_code=404,
#                 detail="Instagram integration not found"
#             )
        
#         # Build query
#         query = db.query(InstagramConversation).filter(
#             InstagramConversation.integration_id == integration.id
#         )
        
#         if status:
#             query = query.filter(InstagramConversation.conversation_status == status)
        
#         conversations = query.order_by(
#             InstagramConversation.last_message_at.desc()
#         ).offset(offset).limit(limit).all()
        
#         return [
#             InstagramConversationResponse(
#                 id=conv.id,
#                 conversation_id=conv.conversation_id,
#                 instagram_user_id=conv.instagram_user_id,
#                 instagram_username=conv.instagram_username,
#                 user_profile_name=conv.user_profile_name,
#                 is_active=conv.is_active,
#                 conversation_status=conv.conversation_status,
#                 total_messages=conv.total_messages,
#                 last_message_at=conv.last_message_at.isoformat() if conv.last_message_at else None,
#                 created_at=conv.created_at.isoformat()
#             )
#             for conv in conversations
#         ]
        
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error getting Instagram conversations: {str(e)}")
#         raise HTTPException(status_code=500, detail="Failed to get conversations")

# @router.get("/conversations/{conversation_id}/messages", response_model=List[InstagramMessageResponse])
# async def get_conversation_messages(
#     conversation_id: str,
#     limit: int = 50,
#     offset: int = 0,
#     api_key: str = Header(..., alias="X-API-Key"),
#     db: Session = Depends(get_db)
# ):
#     """Get messages from a specific Instagram conversation"""
#     try:
#         tenant = get_tenant_from_api_key(api_key, db)
        
#         # Find conversation
#         conversation = db.query(InstagramConversation).filter(
#             InstagramConversation.conversation_id == conversation_id,
#             InstagramConversation.tenant_id == tenant.id
#         ).first()
        
#         if not conversation:
#             raise HTTPException(
#                 status_code=404,
#                 detail="Conversation not found"
#             )
        
#         # Get messages
#         messages = db.query(InstagramMessage).filter(
#             InstagramMessage.conversation_id == conversation.id
#         ).order_by(
#             InstagramMessage.created_at.desc()
#         ).offset(offset).limit(limit).all()
        
#         # Return in chronological order (oldest first)
#         return [
#             InstagramMessageResponse(
#                 id=msg.id,
#                 message_uuid=msg.message_uuid,
#                 message_type=msg.message_type,
#                 content=msg.content,
#                 is_from_user=msg.is_from_user,
#                 message_status=msg.message_status,
#                 created_at=msg.created_at.isoformat()
#             )
#             for msg in reversed(messages)
#         ]
        
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error getting conversation messages: {str(e)}")
#         raise HTTPException(status_code=500, detail="Failed to get messages")

# # Testing and Management
# @router.post("/test-message")
# async def send_test_instagram_message(
#     test_request: InstagramTestMessageRequest,
#     api_key: str = Header(..., alias="X-API-Key"),
#     db: Session = Depends(get_db)
# ):
#     """Send test message via Instagram (for testing purposes)"""
#     try:
#         tenant = get_tenant_from_api_key(api_key, db)
        
#         integration = db.query(InstagramIntegration).filter(
#             InstagramIntegration.tenant_id == tenant.id
#         ).first()
        
#         if not integration:
#             raise HTTPException(
#                 status_code=404,
#                 detail="Instagram integration not found"
#             )
        
#         if not integration.bot_enabled:
#             raise HTTPException(
#                 status_code=400,
#                 detail="Instagram bot is disabled"
#             )
        
#         # Send via bot manager
#         bot_manager = get_instagram_bot_manager()
#         success = await bot_manager.send_message(
#             tenant.id,
#             test_request.instagram_user_id,
#             test_request.message
#         )
        
#         if success:
#             return {"message": "Test message sent successfully"}
#         else:
#             raise HTTPException(
#                 status_code=500,
#                 detail="Failed to send test message"
#             )
            
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error sending test message: {str(e)}")
#         raise HTTPException(status_code=500, detail="Failed to send test message")

# @router.get("/health")
# async def instagram_health_check(
#     api_key: str = Header(..., alias="X-API-Key"),
#     db: Session = Depends(get_db)
# ):
#     """Health check for Instagram integration"""
#     try:
#         tenant = get_tenant_from_api_key(api_key, db)
        
#         integration = db.query(InstagramIntegration).filter(
#             InstagramIntegration.tenant_id == tenant.id
#         ).first()
        
#         if not integration:
#             return {
#                 "status": "not_configured",
#                 "message": "Instagram integration not found"
#             }
        
#         # Test API connection
#         api_service = InstagramAPIService(integration, db)
#         connection_success, connection_msg = api_service.test_api_connection()
        
#         # Get bot manager status
#         bot_manager = get_instagram_bot_manager()
#         manager_status = bot_manager.get_integration_status(tenant.id)
        
#         return {
#             "status": "healthy" if connection_success else "unhealthy",
#             "api_connection": connection_success,
#             "connection_message": connection_msg,
#             "integration_status": integration.get_status_info(),
#             "bot_manager_status": manager_status,
#             "webhook_subscribed": integration.webhook_subscribed
#         }
        
#     except Exception as e:
#         logger.error(f"Error in Instagram health check: {str(e)}")
#         return {
#             "status": "error",
#             "message": str(e)
#         }

# @router.get("/analytics")
# async def get_instagram_analytics(
#     days: int = 30,
#     api_key: str = Header(..., alias="X-API-Key"),
#     db: Session = Depends(get_db)
# ):
#     """Get Instagram integration analytics"""
#     try:
#         tenant = get_tenant_from_api_key(api_key, db)
        
#         integration = db.query(InstagramIntegration).filter(
#             InstagramIntegration.tenant_id == tenant.id
#         ).first()
        
#         if not integration:
#             raise HTTPException(
#                 status_code=404,
#                 detail="Instagram integration not found"
#             )
        
#         from datetime import datetime, timedelta
#         start_date = datetime.utcnow() - timedelta(days=days)
        
#         # Get conversation stats
#         total_conversations = db.query(InstagramConversation).filter(
#             InstagramConversation.integration_id == integration.id,
#             InstagramConversation.created_at >= start_date
#         ).count()
        
#         active_conversations = db.query(InstagramConversation).filter(
#             InstagramConversation.integration_id == integration.id,
#             InstagramConversation.is_active == True,
#             InstagramConversation.last_message_at >= start_date
#         ).count()
        
#         # Get message stats
#         total_messages = db.query(InstagramMessage).filter(
#             InstagramMessage.tenant_id == tenant.id,
#             InstagramMessage.created_at >= start_date
#         ).count()
        
#         user_messages = db.query(InstagramMessage).filter(
#             InstagramMessage.tenant_id == tenant.id,
#             InstagramMessage.is_from_user == True,
#             InstagramMessage.created_at >= start_date
#         ).count()
        
#         bot_messages = total_messages - user_messages
        
#         return {
#             "period_days": days,
#             "integration_id": integration.id,
#             "conversations": {
#                 "total": total_conversations,
#                 "active": active_conversations
#             },
#             "messages": {
#                 "total": total_messages,
#                 "from_users": user_messages,
#                 "from_bot": bot_messages
#             },
#             "integration_info": {
#                 "instagram_username": integration.instagram_username,
#                 "bot_enabled": integration.bot_enabled,
#                 "webhook_subscribed": integration.webhook_subscribed,
#                 "created_at": integration.created_at.isoformat()
#             }
#         }
        
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error getting Instagram analytics: {str(e)}")
#         raise HTTPException(status_code=500, detail="Failed to get analytics")

# # Admin endpoints (for debugging and management)
# @router.get("/admin/all-integrations")
# async def get_all_instagram_integrations(
#     current_user = Depends(lambda: None)  # Add proper admin auth when available
# ):
#     """Get all Instagram integrations (admin only)"""
#     try:
#         bot_manager = get_instagram_bot_manager()
#         return {
#             "integrations": bot_manager.get_all_integrations_status(),
#             "manager_stats": bot_manager.get_stats()
#         }
        
#     except Exception as e:
#         logger.error(f"Error getting all integrations: {str(e)}")
#         raise HTTPException(status_code=500, detail="Failed to get integrations")

# @router.post("/admin/restart-integration/{tenant_id}")
# async def restart_instagram_integration(
#     tenant_id: int,
#     current_user = Depends(lambda: None)  # Add proper admin auth when available
# ):
#     """Restart Instagram integration for specific tenant (admin only)"""
#     try:
#         bot_manager = get_instagram_bot_manager()
        
#         # Remove and re-add integration
#         bot_manager.remove_integration(tenant_id)
#         success = await bot_manager.add_integration(tenant_id)
        
#         if success:
#             return {"message": f"Instagram integration restarted for tenant {tenant_id}"}
#         else:
#             raise HTTPException(
#                 status_code=500,
#                 detail=f"Failed to restart integration for tenant {tenant_id}"
#             )
            
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error restarting integration: {str(e)}")
#         raise HTTPException(status_code=500, detail="Failed to restart integration")









import logging
import json
from typing import Dict, Any, Optional, List
# MODIFIED: Added Query and RedirectResponse
from fastapi import APIRouter, Depends, HTTPException, Header, Request, status, BackgroundTasks, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, validator
import hashlib
import hmac
from fastapi import Cookie

from app.database import get_db
from app.tenants.router import get_tenant_from_api_key
from app.instagram.models import InstagramIntegration, InstagramConversation, InstagramMessage
from app.instagram.service import InstagramAPIService, InstagramWebhookProcessor, InstagramConversationManager
from app.instagram.bot_manager import get_instagram_bot_manager
from app.pricing.integration_helpers import (
    check_integration_limit_dependency_with_super_tenant
)
# NEW: Import settings to get env variables
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# --- REMOVED: InstagramIntegrationCreate model ---
# Users no longer submit this data.

class InstagramIntegrationUpdate(BaseModel):
    bot_enabled: Optional[bool] = None
    auto_reply_enabled: Optional[bool] = None
    webhook_verify_token: Optional[str] = None

class InstagramIntegrationResponse(BaseModel):
    id: int
    tenant_id: int
    instagram_username: str
    facebook_page_id: str
    bot_enabled: bool
    bot_status: str
    webhook_subscribed: bool
    last_message_at: Optional[str] = None
    error_count: int
    created_at: str

class InstagramTestMessageRequest(BaseModel):
    instagram_user_id: str = Field(..., description="Instagram User ID to send test message to")
    message: str = Field(..., min_length=1, max_length=1000, description="Test message content")

class InstagramConversationResponse(BaseModel):
    id: int
    conversation_id: str
    instagram_user_id: str
    instagram_username: Optional[str] = None
    user_profile_name: Optional[str] = None
    is_active: bool
    conversation_status: str
    total_messages: int
    last_message_at: Optional[str] = None
    created_at: str

class InstagramMessageResponse(BaseModel):
    id: int
    message_uuid: str
    message_type: str
    content: Optional[str] = None
    is_from_user: bool
    message_status: str
    created_at: str




@router.get("/auth/login")
async def instagram_auth_login(
    request: Request,
    db: Session = Depends(get_db),
    tenant_api_key: Optional[str] = Cookie(None, alias="tenant_api_key"),
    access_token: Optional[str] = Cookie(None, alias="access_token")
):
    """
    Step 1: Redirect user to Facebook for OAuth.
    Uses the platform's Meta App ID from environment settings.
    """
    try:
        # Try to get API key from cookie or header
        api_key = tenant_api_key
        if not api_key:
            # Fallback to header
            api_key = request.headers.get("X-API-Key")
        
        if not api_key:
            raise HTTPException(
                status_code=401,
                detail="API key not found. Please log in."
            )
        
        tenant = get_tenant_from_api_key(api_key, db)
        
        # Check if integration limit is hit
        check_integration_limit_dependency_with_super_tenant(tenant.id, db)
        
        # Get App ID from environment settings
        meta_app_id = settings.INSTAGRAM_META_APP_ID
        if not meta_app_id:
            raise HTTPException(
                status_code=500,
                detail="Instagram App ID is not configured on the server."
            )

        # This MUST match the URL in your Meta App settings
        redirect_uri = settings.INSTAGRAM_REDIRECT_URI
        if not redirect_uri:
             raise HTTPException(
                status_code=500,
                detail="Instagram Redirect URI is not configured on the server."
            )
        
        # Scopes needed for messaging and account info
        scopes = [
            "pages_manage_metadata",
            "pages_messaging", 
            "instagram_basic",
            "instagram_manage_messages"
        ]
        
        # Pass tenant_id in state to identify user on callback
        state = str(tenant.id)
        
        auth_url = (
            f"https://www.facebook.com/v18.0/dialog/oauth?"
            f"client_id={meta_app_id}"
            f"&redirect_uri={redirect_uri}"
            f"&state={state}"
            f"&scope={','.join(scopes)}"
            f"&response_type=code"
        )
        
        logger.info(f"Redirecting tenant {tenant.id} to Facebook for auth.")
        return RedirectResponse(url=auth_url)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating auth redirect: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to initiate authentication")
    



# --- MODIFIED: /auth/callback Endpoint ---
@router.get("/auth/callback")
async def instagram_auth_callback(
    background_tasks: BackgroundTasks,
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db)
):
    """
    Step 2: Handle callback from Facebook, exchange code for tokens,
    and create/update the integration.
    """
    try:
        tenant_id = int(state)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    # Get or create the integration record for this tenant
    integration = db.query(InstagramIntegration).filter(
        InstagramIntegration.tenant_id == tenant_id
    ).first()

    if not integration:
        integration = InstagramIntegration(tenant_id=tenant_id)
        db.add(integration)

    # This MUST match the URL from the /auth/login step
    redirect_uri = settings.INSTAGRAM_REDIRECT_URI

    try:
        # Pass the placeholder (or existing) integration to the service
        api_service = InstagramAPIService(integration, db)
        
        # Call the modified function in service.py
        # It will use env settings for app_id and secret
        success, token_data = await api_service.exchange_code_for_tokens(code, redirect_uri)
        
        if not success:
            error_msg = token_data.get("error", "Token exchange failed")
            integration.bot_status = "error"
            integration.last_error = f"OAuth Error: {error_msg}"
            db.commit()
            raise HTTPException(status_code=400, detail=f"OAuth failed: {error_msg}")

        # Save all the new data from OAuth to the integration record
        integration.page_access_token = token_data["page_access_token"]
        integration.token_expires_at = token_data["expires_at"]
        integration.facebook_page_id = token_data["page_id"]
        integration.instagram_business_account_id = token_data["ig_id"]
        integration.instagram_username = token_data["username"]
        
        # Save credentials from .env to the record (optional, but good for refresh logic)
        integration.meta_app_id = settings.INSTAGRAM_META_APP_ID
        integration.meta_app_secret = settings.INSTAGRAM_META_APP_SECRET
        
        # Generate a secure verify token for them
        from .utils import generate_webhook_verify_token
        if not integration.webhook_verify_token:
            integration.webhook_verify_token = generate_webhook_verify_token()
        
        db.commit() # Commit token data first

        # Now, finish the setup (subscribe, test, activate)
        webhook_success = api_service.subscribe_to_webhooks()
        if not webhook_success:
            logger.warning(f"⚠️ Webhook subscription failed for tenant {tenant_id}")
            # Don't fail the whole setup, but log it
        
        connection_success, connection_msg = api_service.test_api_connection()
        
        if connection_success:
            integration.bot_status = "active"
            integration.last_error = None
            logger.info(f"✅ Instagram integration fully activated for tenant {tenant_id}")
        else:
            integration.bot_status = "error"
            integration.last_error = f"API connection failed post-auth: {connection_msg}"
            logger.error(f"❌ Post-auth connection failed for tenant {tenant_id}: {connection_msg}")
        
        db.commit()
        
        # Add to bot manager
        if integration.bot_status == "active":
            background_tasks.add_task(
                get_instagram_bot_manager().add_integration,
                tenant_id
            )
        
        # Redirect user to a "success" page on your frontend
        return RedirectResponse(url=settings.INSTAGRAM_FRONTEND_SUCCESS_URL)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in auth callback: {str(e)}")
        integration.bot_status = "error"
        integration.last_error = f"Callback exception: {str(e)}"
        db.commit()
        raise HTTPException(status_code=500, detail="Failed to finalize authentication")

@router.get("/status", response_model=InstagramIntegrationResponse)
async def get_instagram_status(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get Instagram integration status"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        integration = db.query(InstagramIntegration).filter(
            InstagramIntegration.tenant_id == tenant.id
        ).first()
        
        if not integration:
            raise HTTPException(
                status_code=404,
                detail="Instagram integration not found"
            )
        
        return InstagramIntegrationResponse(
            id=integration.id,
            tenant_id=integration.tenant_id,
            instagram_username=integration.instagram_username,
            facebook_page_id=integration.facebook_page_id,
            bot_enabled=integration.bot_enabled,
            bot_status=integration.bot_status,
            webhook_subscribed=integration.webhook_subscribed,
            last_message_at=integration.last_message_at.isoformat() if integration.last_message_at else None,
            error_count=integration.error_count,
            created_at=integration.created_at.isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting Instagram status: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get Instagram status")

@router.put("/settings", response_model=InstagramIntegrationResponse)
async def update_instagram_settings(
    settings_update: InstagramIntegrationUpdate,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Update Instagram integration settings"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        integration = db.query(InstagramIntegration).filter(
            InstagramIntegration.tenant_id == tenant.id
        ).first()
        
        if not integration:
            raise HTTPException(
                status_code=404,
                detail="Instagram integration not found"
            )
        
        # Update settings
        update_data = settings_update.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(integration, field, value)
        
        db.commit()
        db.refresh(integration)
        
        # If bot was disabled, remove from manager
        if settings_update.bot_enabled is False:
            get_instagram_bot_manager().remove_integration(tenant.id)
        
        # If bot was enabled, add to manager
        elif settings_update.bot_enabled is True and integration.bot_status == "active":
            await get_instagram_bot_manager().add_integration(tenant.id)
        
        logger.info(f"✅ Instagram settings updated for tenant {tenant.id}")
        
        return InstagramIntegrationResponse(
            id=integration.id,
            tenant_id=integration.tenant_id,
            instagram_username=integration.instagram_username,
            facebook_page_id=integration.facebook_page_id,
            bot_enabled=integration.bot_enabled,
            bot_status=integration.bot_status,
            webhook_subscribed=integration.webhook_subscribed,
            last_message_at=integration.last_message_at.isoformat() if integration.last_message_at else None,
            error_count=integration.error_count,
            created_at=integration.created_at.isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating Instagram settings: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to update Instagram settings")

@router.delete("/integration")
async def delete_instagram_integration(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Delete Instagram integration"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        integration = db.query(InstagramIntegration).filter(
            InstagramIntegration.tenant_id == tenant.id
        ).first()
        
        if not integration:
            raise HTTPException(
                status_code=404,
                detail="Instagram integration not found"
            )
        
        # Remove from bot manager
        get_instagram_bot_manager().remove_integration(tenant.id)
        
        # Delete from database
        db.delete(integration)
        db.commit()
        
        logger.info(f"🗑️ Instagram integration deleted for tenant {tenant.id}")
        
        return {"message": "Instagram integration deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting Instagram integration: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to delete Instagram integration")

# Webhook Endpoints
@router.get("/webhook")
async def instagram_webhook_verify(request: Request):
    """Verify Instagram webhook (challenge verification)"""
    try:
        params = dict(request.query_params)
        
        webhook_processor = InstagramWebhookProcessor(next(get_db()))
        challenge = webhook_processor.verify_webhook_challenge(params)
        
        if challenge:
            return int(challenge)
        else:
            raise HTTPException(status_code=403, detail="Webhook verification failed")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in webhook verification: {str(e)}")
        raise HTTPException(status_code=500, detail="Webhook verification error")

@router.post("/webhook")
async def instagram_webhook_handler(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: str = Header(None, alias="X-Hub-Signature-256"),
    db: Session = Depends(get_db)
):
    """Handle Instagram webhook events"""
    try:
        # Get raw body and headers
        body = await request.body()
        headers = dict(request.headers)
        
        # Parse JSON payload
        try:
            payload = json.loads(body.decode('utf-8'))
        except json.JSONDecodeError:
            logger.error("Invalid JSON in webhook payload")
            raise HTTPException(status_code=400, detail="Invalid JSON payload")
        
        # Verify webhook signature (Meta requirement)
        if x_hub_signature_256:
            # We must use the app_secret from settings to verify
            app_secret = settings.INSTAGRAM_META_APP_SECRET
            if app_secret:
                expected_signature = hmac.new(
                    app_secret.encode('utf-8'),
                    body, # Use raw body
                    hashlib.sha256
                ).hexdigest()
                
                signature = x_hub_signature_256[7:] # Remove 'sha256='
                
                if not hmac.compare_digest(signature, expected_signature):
                    logger.warning("Invalid webhook signature")
                    raise HTTPException(status_code=403, detail="Invalid signature")
            else:
                logger.warning("No App Secret in settings, skipping signature verification")

        
        # Process webhook in background
        background_tasks.add_task(
            process_instagram_webhook_background,
            payload,
            headers
        )
        
        logger.info("📨 Instagram webhook received and queued for processing")
        return {"status": "received"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error handling Instagram webhook: {str(e)}")
        raise HTTPException(status_code=500, detail="Webhook processing error")

async def process_instagram_webhook_background(payload: Dict, headers: Dict):
    """Background task to process Instagram webhook"""
    db = None
    try:
        db = next(get_db())
        
        webhook_processor = InstagramWebhookProcessor(db)
        success, message = webhook_processor.process_webhook_event(payload, headers)
        
        if success:
            logger.info(f"✅ Instagram webhook processed: {message}")
            
            # Process any incoming messages with bot manager
            bot_manager = get_instagram_bot_manager()
            
            for entry in payload.get("entry", []):
                page_id = entry.get("id")
                
                # Find integration
                integration = db.query(InstagramIntegration).filter(
                    InstagramIntegration.facebook_page_id == page_id,
                    InstagramIntegration.bot_enabled == True
                ).first()
                
                if not integration:
                    continue
                
                tenant_id = integration.tenant_id
                
                # Process messaging events
                for messaging in entry.get("messaging", []):
                    sender_id = messaging.get("sender", {}).get("id")
                    
                    # Skip if we're the sender
                    if sender_id == page_id:
                        continue
                    
                    # Find conversation
                    conversation = db.query(InstagramConversation).filter(
                        InstagramConversation.integration_id == integration.id,
                        InstagramConversation.instagram_user_id == sender_id,
                        InstagramConversation.is_active == True
                    ).first()
                    
                    if conversation:
                        # Get the latest message
                        latest_message = db.query(InstagramMessage).filter(
                            InstagramMessage.conversation_id == conversation.id,
                            InstagramMessage.is_from_user == True
                        ).order_by(InstagramMessage.created_at.desc()).first()
                        
                        if latest_message:
                            await bot_manager.process_incoming_message(
                                tenant_id, conversation, latest_message
                            )
        else:
            logger.error(f"❌ Instagram webhook processing failed: {message}")
            
    except Exception as e:
        logger.error(f"💥 Error in background webhook processing: {str(e)}")
    finally:
        if db:
            db.close()

# Conversation Management
@router.get("/conversations", response_model=List[InstagramConversationResponse])
async def get_instagram_conversations(
    limit: int = 20,
    offset: int = 0,
    status: Optional[str] = None,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get Instagram conversations for tenant"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        integration = db.query(InstagramIntegration).filter(
            InstagramIntegration.tenant_id == tenant.id
        ).first()
        
        if not integration:
            raise HTTPException(
                status_code=404,
                detail="Instagram integration not found"
            )
        
        # Build query
        query = db.query(InstagramConversation).filter(
            InstagramConversation.integration_id == integration.id
        )
        
        if status:
            query = query.filter(InstagramConversation.conversation_status == status)
        
        conversations = query.order_by(
            InstagramConversation.last_message_at.desc()
        ).offset(offset).limit(limit).all()
        
        return [
            InstagramConversationResponse(
                id=conv.id,
                conversation_id=conv.conversation_id,
                instagram_user_id=conv.instagram_user_id,
                instagram_username=conv.instagram_username,
                user_profile_name=conv.user_profile_name,
                is_active=conv.is_active,
                conversation_status=conv.conversation_status,
                total_messages=conv.total_messages,
                last_message_at=conv.last_message_at.isoformat() if conv.last_message_at else None,
                created_at=conv.created_at.isoformat()
            )
            for conv in conversations
        ]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting Instagram conversations: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get conversations")

@router.get("/conversations/{conversation_id}/messages", response_model=List[InstagramMessageResponse])
async def get_conversation_messages(
    conversation_id: str,
    limit: int = 50,
    offset: int = 0,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get messages from a specific Instagram conversation"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        # Find conversation
        conversation = db.query(InstagramConversation).filter(
            InstagramConversation.conversation_id == conversation_id,
            InstagramConversation.tenant_id == tenant.id
        ).first()
        
        if not conversation:
            raise HTTPException(
                status_code=404,
                detail="Conversation not found"
            )
        
        # Get messages
        messages = db.query(InstagramMessage).filter(
            InstagramMessage.conversation_id == conversation.id
        ).order_by(
            InstagramMessage.created_at.desc()
        ).offset(offset).limit(limit).all()
        
        # Return in chronological order (oldest first)
        return [
            InstagramMessageResponse(
                id=msg.id,
                message_uuid=msg.message_uuid,
                message_type=msg.message_type,
                content=msg.content,
                is_from_user=msg.is_from_user,
                message_status=msg.message_status,
                created_at=msg.created_at.isoformat()
            )
            for msg in reversed(messages)
        ]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting conversation messages: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get messages")

# Testing and Management
@router.post("/test-message")
async def send_test_instagram_message(
    test_request: InstagramTestMessageRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Send test message via Instagram (for testing purposes)"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        integration = db.query(InstagramIntegration).filter(
            InstagramIntegration.tenant_id == tenant.id
        ).first()
        
        if not integration:
            raise HTTPException(
                status_code=404,
                detail="Instagram integration not found"
            )
        
        if not integration.bot_enabled:
            raise HTTPException(
                status_code=400,
                detail="Instagram bot is disabled"
            )
        
        # Send via bot manager
        bot_manager = get_instagram_bot_manager()
        success = await bot_manager.send_message(
            tenant.id,
            test_request.instagram_user_id,
            test_request.message
        )
        
        if success:
            return {"message": "Test message sent successfully"}
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to send test message"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending test message: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to send test message")

@router.get("/health")
async def instagram_health_check(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Health check for Instagram integration"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        integration = db.query(InstagramIntegration).filter(
            InstagramIntegration.tenant_id == tenant.id
        ).first()
        
        if not integration:
            return {
                "status": "not_configured",
                "message": "Instagram integration not found"
            }
        
        # Test API connection
        api_service = InstagramAPIService(integration, db)
        connection_success, connection_msg = api_service.test_api_connection()
        
        # Get bot manager status
        bot_manager = get_instagram_bot_manager()
        manager_status = bot_manager.get_integration_status(tenant.id)
        
        return {
            "status": "healthy" if connection_success else "unhealthy",
            "api_connection": connection_success,
            "connection_message": connection_msg,
            "integration_status": integration.get_status_info(),
            "bot_manager_status": manager_status,
            "webhook_subscribed": integration.webhook_subscribed
        }
        
    except Exception as e:
        logger.error(f"Error in Instagram health check: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }

@router.get("/analytics")
async def get_instagram_analytics(
    days: int = 30,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get Instagram integration analytics"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        integration = db.query(InstagramIntegration).filter(
            InstagramIntegration.tenant_id == tenant.id
        ).first()
        
        if not integration:
            raise HTTPException(
                status_code=404,
                detail="Instagram integration not found"
            )
        
        from datetime import datetime, timedelta
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Get conversation stats
        total_conversations = db.query(InstagramConversation).filter(
            InstagramConversation.integration_id == integration.id,
            InstagramConversation.created_at >= start_date
        ).count()
        
        active_conversations = db.query(InstagramConversation).filter(
            InstagramConversation.integration_id == integration.id,
            InstagramConversation.is_active == True,
            InstagramConversation.last_message_at >= start_date
        ).count()
        
        # Get message stats
        total_messages = db.query(InstagramMessage).filter(
            InstagramMessage.tenant_id == tenant.id,
            InstagramMessage.created_at >= start_date
        ).count()
        
        user_messages = db.query(InstagramMessage).filter(
            InstagramMessage.tenant_id == tenant.id,
            InstagramMessage.is_from_user == True,
            InstagramMessage.created_at >= start_date
        ).count()
        
        bot_messages = total_messages - user_messages
        
        return {
            "period_days": days,
            "integration_id": integration.id,
            "conversations": {
                "total": total_conversations,
                "active": active_conversations
            },
            "messages": {
                "total": total_messages,
                "from_users": user_messages,
                "from_bot": bot_messages
            },
            "integration_info": {
                "instagram_username": integration.instagram_username,
                "bot_enabled": integration.bot_enabled,
                "webhook_subscribed": integration.webhook_subscribed,
                "created_at": integration.created_at.isoformat()
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting Instagram analytics: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get analytics")

# Admin endpoints (for debugging and management)
@router.get("/admin/all-integrations")
async def get_all_instagram_integrations(
    current_user = Depends(lambda: None)  # Add proper admin auth when available
):
    """Get all Instagram integrations (admin only)"""
    try:
        bot_manager = get_instagram_bot_manager()
        return {
            "integrations": bot_manager.get_all_integrations_status(),
            "manager_stats": bot_manager.get_stats()
        }
        
    except Exception as e:
        logger.error(f"Error getting all integrations: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get integrations")

@router.post("/admin/restart-integration/{tenant_id}")
async def restart_instagram_integration(
    tenant_id: int,
    current_user = Depends(lambda: None)  # Add proper admin auth when available
):
    """Restart Instagram integration for specific tenant (admin only)"""
    try:
        bot_manager = get_instagram_bot_manager()
        
        # Remove and re-add integration
        bot_manager.remove_integration(tenant_id)
        success = await bot_manager.add_integration(tenant_id)
        
        if success:
            return {"message": f"Instagram integration restarted for tenant {tenant_id}"}
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to restart integration for tenant {tenant_id}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error restarting integration: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to restart integration")


@router.get("/webhook")
async def instagram_webhook_verify(request: Request):
    """Verify Instagram webhook"""
    try:
        params = dict(request.query_params)
        webhook_processor = InstagramWebhookProcessor(next(get_db()))
        challenge = webhook_processor.verify_webhook_challenge(params)
        
        if challenge:
            return int(challenge)
        else:
            raise HTTPException(status_code=403, detail="Verification failed")
    except Exception as e:
        logger.error(f"Webhook verification error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/webhook")
async def instagram_webhook_handler(request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Handle Instagram webhook events"""
    try:
        body = await request.body()
        payload = json.loads(body.decode('utf-8'))
        
        background_tasks.add_task(process_webhook, payload)
        return {"status": "received"}
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

async def process_webhook(payload: Dict):
    """Process webhook in background"""
    db = next(get_db())
    webhook_processor = InstagramWebhookProcessor(db)
    webhook_processor.process_webhook_event(payload, {})