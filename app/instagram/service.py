# app/instagram/service.py

import logging
import requests
import json
import uuid
import hashlib
import hmac
import asyncio
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.instagram.models import (
    InstagramIntegration, 
    InstagramConversation, 
    InstagramMessage,
    InstagramWebhookEvent
)
from app.config import settings

logger = logging.getLogger(__name__)

class InstagramAPIService:
    """Core Instagram API service for messaging operations"""
    
    def __init__(self, integration: InstagramIntegration, db: Session):
        self.integration = integration
        self.db = db
        self.api_version = "v18.0"
        self.base_url = f"https://graph.facebook.com/{self.api_version}"
        
    def _get_headers(self) -> Dict[str, str]:
        """Get API request headers"""
        return {
            "Authorization": f"Bearer {self.integration.page_access_token}",
            "Content-Type": "application/json"
        }
    
    def _make_request(self, method: str, endpoint: str, data: Dict = None, params: Dict = None) -> Tuple[bool, Dict]:
        """Make authenticated request to Instagram API"""
        url = f"{self.base_url}/{endpoint}"
        
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self._get_headers(),
                json=data,
                params=params,
                timeout=30
            )
            
            response_data = response.json()
            
            if response.status_code == 200:
                return True, response_data
            else:
                error_msg = response_data.get('error', {}).get('message', 'Unknown error')
                logger.error(f"Instagram API error: {error_msg}")
                return False, response_data
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Instagram API request failed: {str(e)}")
            return False, {"error": {"message": str(e)}}
    
    def send_message(self, instagram_user_id: str, message_content: str, 
                    message_type: str = "text", quick_replies: List[Dict] = None) -> Tuple[bool, Optional[str]]:
        """
        Send message to Instagram user
        
        Args:
            instagram_user_id: Instagram Scoped ID (IGSID)
            message_content: Message content
            message_type: Type of message (text, image, etc.)
            quick_replies: Optional quick reply buttons
            
        Returns:
            (success, message_id)
        """
        try:
            # Prepare message payload
            message_data = {
                "recipient": {
                    "id": instagram_user_id
                },
                "message": {}
            }
            
            if message_type == "text":
                message_data["message"]["text"] = message_content
            elif message_type == "image":
                message_data["message"]["attachment"] = {
                    "type": "image",
                    "payload": {
                        "url": message_content,
                        "is_reusable": True
                    }
                }
            
            # Add quick replies if provided
            if quick_replies:
                message_data["message"]["quick_replies"] = quick_replies
            
            # Send message
            success, response = self._make_request(
                "POST",
                f"{self.integration.facebook_page_id}/messages",
                message_data
            )
            
            if success:
                message_id = response.get("message_id")
                logger.info(f"✅ Instagram message sent: {message_id}")
                return True, message_id
            else:
                error_msg = response.get("error", {}).get("message", "Unknown error")
                logger.error(f"❌ Failed to send Instagram message: {error_msg}")
                return False, None
                
        except Exception as e:
            logger.error(f"💥 Error sending Instagram message: {str(e)}")
            return False, None
    
    def get_user_profile(self, instagram_user_id: str) -> Optional[Dict]:
        """Get Instagram user profile information"""
        try:
            success, response = self._make_request(
                "GET",
                instagram_user_id,
                params={
                    "fields": "name,username,profile_pic"
                }
            )
            
            if success:
                return {
                    "name": response.get("name"),
                    "username": response.get("username"),
                    "profile_picture": response.get("profile_pic")
                }
            else:
                logger.error(f"Failed to get user profile: {response}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting user profile: {str(e)}")
            return None
    
    def verify_webhook_signature(self, payload: str, signature: str) -> bool:
        """Verify webhook signature from Meta"""
        try:
            # Meta sends signature as 'sha256=<signature>'
            if not signature.startswith('sha256='):
                return False
            
            signature = signature[7:]  # Remove 'sha256=' prefix
            
            # Calculate expected signature
            expected_signature = hmac.new(
                self.integration.meta_app_secret.encode('utf-8'),
                payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(signature, expected_signature)
            
        except Exception as e:
            logger.error(f"Error verifying webhook signature: {str(e)}")
            return False
    
    def subscribe_to_webhooks(self) -> bool:
        """Subscribe page to Instagram webhook events"""
        try:
            subscription_data = {
                "subscribed_fields": ["messages", "message_reactions"]
            }
            
            success, response = self._make_request(
                "POST",
                f"{self.integration.facebook_page_id}/subscribed_apps",
                subscription_data
            )
            
            if success:
                self.integration.webhook_subscribed = True
                self.integration.webhook_subscription_fields = subscription_data["subscribed_fields"]
                self.db.commit()
                logger.info(f"✅ Instagram webhooks subscribed for page {self.integration.facebook_page_id}")
                return True
            else:
                logger.error(f"❌ Failed to subscribe to webhooks: {response}")
                return False
                
        except Exception as e:
            logger.error(f"💥 Error subscribing to webhooks: {str(e)}")
            return False
    
    def refresh_access_token(self) -> bool:
        """Refresh long-lived access token"""
        try:
            # For page tokens, we typically exchange short-lived for long-lived
            # This is usually done during initial setup, but can be refreshed
            params = {
                "grant_type": "fb_exchange_token",
                "client_id": self.integration.meta_app_id,
                "client_secret": self.integration.meta_app_secret,
                "fb_exchange_token": self.integration.page_access_token
            }
            
            response = requests.get(
                f"{self.base_url}/oauth/access_token",
                params=params,
                timeout=30
            )
            
            if response.status_code == 200:
                token_data = response.json()
                
                self.integration.page_access_token = token_data["access_token"]
                
                # Set expiration if provided
                if "expires_in" in token_data:
                    expires_in = int(token_data["expires_in"])
                    self.integration.token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
                
                self.db.commit()
                logger.info(f"✅ Instagram access token refreshed")
                return True
            else:
                logger.error(f"❌ Failed to refresh token: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"💥 Error refreshing access token: {str(e)}")
            return False
    
    def test_api_connection(self) -> Tuple[bool, str]:
        """Test API connection and permissions"""
        try:
            # Test by getting page info
            success, response = self._make_request(
                "GET",
                self.integration.facebook_page_id,
                params={"fields": "name,id"}
            )
            
            if success:
                page_name = response.get("name", "Unknown")
                return True, f"Connected to page: {page_name}"
            else:
                error_msg = response.get("error", {}).get("message", "Connection failed")
                return False, error_msg
                
        except Exception as e:
            return False, f"Connection test failed: {str(e)}"


class InstagramWebhookProcessor:
    """Process Instagram webhook events"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def process_webhook_event(self, payload: Dict, headers: Dict) -> Tuple[bool, str]:
        """Process incoming webhook event"""
        try:
            # Log the webhook event
            webhook_event = InstagramWebhookEvent(
                event_type="webhook",
                raw_payload=payload,
                headers=dict(headers),
                received_at=datetime.utcnow()
            )
            self.db.add(webhook_event)
            
            # Process each entry in the webhook
            for entry in payload.get("entry", []):
                page_id = entry.get("id")
                
                # Find integration by page ID
                integration = self.db.query(InstagramIntegration).filter(
                    InstagramIntegration.facebook_page_id == page_id,
                    InstagramIntegration.bot_enabled == True
                ).first()
                
                if not integration:
                    logger.warning(f"No integration found for page ID: {page_id}")
                    continue
                
                # Update webhook event with integration info
                webhook_event.integration_id = integration.id
                webhook_event.tenant_id = integration.tenant_id
                
                # Process messaging events
                for messaging in entry.get("messaging", []):
                    success = self._process_messaging_event(integration, messaging)
                    if not success:
                        webhook_event.processing_status = "failed"
            
            # Mark as processed if we get here
            if webhook_event.processing_status == "pending":
                webhook_event.processing_status = "processed"
            
            webhook_event.processed_at = datetime.utcnow()
            self.db.commit()
            
            return True, "Webhook processed successfully"
            
        except Exception as e:
            logger.error(f"💥 Error processing webhook: {str(e)}")
            return False, str(e)
    
    def _process_messaging_event(self, integration: InstagramIntegration, messaging: Dict) -> bool:
        """Process individual messaging event"""
        try:
            sender_id = messaging.get("sender", {}).get("id")
            recipient_id = messaging.get("recipient", {}).get("id")
            timestamp = messaging.get("timestamp")
            
            # Skip if we're the sender
            if sender_id == integration.facebook_page_id:
                return True
            
            # Get or create conversation
            conversation = self._get_or_create_conversation(
                integration, sender_id, timestamp
            )
            
            # Process message if present
            if "message" in messaging:
                self._process_message(conversation, messaging["message"], timestamp)
            
            # Process message reactions if present
            elif "reaction" in messaging:
                self._process_reaction(conversation, messaging["reaction"], timestamp)
            
            # Update conversation timestamp
            conversation.last_message_at = datetime.fromtimestamp(timestamp / 1000)
            integration.last_message_at = datetime.fromtimestamp(timestamp / 1000)
            
            self.db.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error processing messaging event: {str(e)}")
            return False
    
    def _get_or_create_conversation(self, integration: InstagramIntegration, 
                                  instagram_user_id: str, timestamp: int) -> InstagramConversation:
        """Get existing conversation or create new one"""
        
        # Look for existing conversation
        conversation = self.db.query(InstagramConversation).filter(
            InstagramConversation.integration_id == integration.id,
            InstagramConversation.instagram_user_id == instagram_user_id,
            InstagramConversation.is_active == True
        ).first()
        
        if conversation:
            return conversation
        
        # Create new conversation
        conversation = InstagramConversation(
            integration_id=integration.id,
            tenant_id=integration.tenant_id,
            instagram_user_id=instagram_user_id,
            conversation_id=str(uuid.uuid4()),
            created_at=datetime.fromtimestamp(timestamp / 1000),
            is_active=True,
            conversation_status="open"
        )
        
        self.db.add(conversation)
        self.db.flush()  # Get ID
        
        # Try to get user profile info
        api_service = InstagramAPIService(integration, self.db)
        profile = api_service.get_user_profile(instagram_user_id)
        
        if profile:
            conversation.instagram_username = profile.get("username")
            conversation.user_profile_name = profile.get("name")
            conversation.user_profile_picture = profile.get("profile_picture")
        
        logger.info(f"📱 Created new Instagram conversation: {conversation.conversation_id}")
        return conversation
    
    def _process_message(self, conversation: InstagramConversation, 
                        message_data: Dict, timestamp: int) -> InstagramMessage:
        """Process incoming message"""
        
        message_id = message_data.get("mid")
        text_content = message_data.get("text")
        
        # Determine message type
        message_type = "text"
        media_url = None
        
        if "attachments" in message_data:
            attachment = message_data["attachments"][0]
            attachment_type = attachment.get("type", "unknown")
            
            if attachment_type in ["image", "video", "audio"]:
                message_type = attachment_type
                media_url = attachment.get("payload", {}).get("url")
        
        # Check for story reply
        reply_to_story = "reply_to" in message_data
        story_id = None
        if reply_to_story:
            story_id = message_data.get("reply_to", {}).get("story", {}).get("id")
        
        # Create message record
        instagram_message = InstagramMessage(
            conversation_id=conversation.id,
            tenant_id=conversation.tenant_id,
            instagram_message_id=message_id,
            message_uuid=str(uuid.uuid4()),
            message_type=message_type,
            content=text_content,
            media_url=media_url,
            is_from_user=True,
            message_status="received",
            reply_to_story=reply_to_story,
            story_id=story_id,
            instagram_timestamp=datetime.fromtimestamp(timestamp / 1000),
            raw_webhook_data=message_data
        )
        
        self.db.add(instagram_message)
        
        # Update conversation stats
        conversation.update_message_stats(is_from_user=True)
        
        logger.info(f"💬 Processed Instagram message: {instagram_message.message_uuid}")
        return instagram_message
    
    def _process_reaction(self, conversation: InstagramConversation, 
                         reaction_data: Dict, timestamp: int):
        """Process message reaction (like/unlike)"""
        
        reaction_type = reaction_data.get("action")  # "react" or "unreact"
        emoji = reaction_data.get("emoji")
        message_id = reaction_data.get("mid")
        
        logger.info(f"👍 Instagram reaction: {reaction_type} - {emoji} on message {message_id}")
        
        # For now, just log reactions. Could be extended to store reaction data
        # in a separate table if needed for analytics
    
    def verify_webhook_challenge(self, params: Dict) -> Optional[str]:
        """Verify webhook challenge during setup"""
        mode = params.get("hub.mode")
        token = params.get("hub.verify_token")
        challenge = params.get("hub.challenge")
        
        if mode == "subscribe" and token:
            # Check against database tokens for any integration
            integration = self.db.query(InstagramIntegration).filter(
                InstagramIntegration.webhook_verify_token == token
            ).first()
            
            if integration:
                logger.info(f"✅ Instagram webhook verified for tenant {integration.tenant_id}")
                return challenge
        
        logger.warning("❌ Instagram webhook verification failed")
        return None


class InstagramConversationManager:
    """🔥 ENHANCED: Manage Instagram conversations with unified intelligent engine"""
    
    def __init__(self, db: Session):
        self.db = db
        self.memory_managers = {}  # Cache per tenant
    
    def _get_memory_manager(self, tenant_id: int):
        """Get or create memory manager for tenant"""
        if tenant_id not in self.memory_managers:
            from app.instagram.memory import InstagramMemoryManager
            self.memory_managers[tenant_id] = InstagramMemoryManager(self.db, tenant_id)
        return self.memory_managers[tenant_id]
    
    def process_incoming_message(self, conversation: InstagramConversation, 
                               message: InstagramMessage) -> Optional[str]:
        """🔥 ENHANCED: Process incoming message with unified intelligent engine"""
        try:
            # Get memory manager for this tenant
            memory_manager = self._get_memory_manager(conversation.tenant_id)
            
            # Process with unified engine + Instagram formatting
            formatted_response = memory_manager.process_with_unified_engine(
                conversation, message
            )
            
            if not formatted_response:
                logger.error(f"❌ No response from unified engine")
                return None
            
            # Send response via Instagram API
            api_service = InstagramAPIService(conversation.integration, self.db)
            
            success, instagram_message_id = api_service.send_message(
                conversation.instagram_user_id,
                formatted_response["content"],
                formatted_response["message_type"],
                formatted_response.get("quick_replies")
            )
            
            if success:
                # Store bot message in Instagram system
                bot_message = InstagramMessage(
                    conversation_id=conversation.id,
                    tenant_id=conversation.tenant_id,
                    instagram_message_id=instagram_message_id,
                    message_uuid=str(uuid.uuid4()),
                    message_type=formatted_response["message_type"],
                    content=formatted_response["content"],
                    is_from_user=False,
                    message_status="sent",
                    instagram_timestamp=datetime.utcnow()
                )
                
                self.db.add(bot_message)
                conversation.update_message_stats(is_from_user=False)
                
                # Sync to core memory
                memory_manager.sync_instagram_message_to_core(bot_message)
                
                self.db.commit()
                
                logger.info(f"✅ Unified engine response sent to Instagram user: {conversation.instagram_user_id}")
                logger.info(f"🎯 Response source: {formatted_response.get('answered_by')} | Intent: {formatted_response.get('intent')} | Architecture: {formatted_response.get('architecture')}")
                
                return formatted_response["content"]
            else:
                logger.error(f"❌ Failed to send Instagram response")
                return None
                
        except Exception as e:
            logger.error(f"💥 Error processing Instagram message with unified engine: {str(e)}")
            return None
    
    async def process_incoming_message_chunked(self, conversation: InstagramConversation, 
                                             message: InstagramMessage) -> Optional[str]:
        """🔥 NEW: Process with chunked response support for long responses"""
        try:
            # Get memory manager and API service
            memory_manager = self._get_memory_manager(conversation.tenant_id)
            api_service = InstagramAPIService(conversation.integration, self.db)
            
            # Process with chunked response handling
            final_response = await memory_manager.process_with_chunked_response(
                conversation, message, api_service
            )
            
            if final_response:
                # Update conversation stats and sync to core memory
                conversation.update_message_stats(is_from_user=False)
                
                # Create a combined message record for chunked responses
                combined_message = InstagramMessage(
                    conversation_id=conversation.id,
                    tenant_id=conversation.tenant_id,
                    instagram_message_id=f"chunked_{uuid.uuid4()}",
                    message_uuid=str(uuid.uuid4()),
                    message_type="text",
                    content=final_response,
                    is_from_user=False,
                    message_status="sent",
                    instagram_timestamp=datetime.utcnow()
                )
                
                self.db.add(combined_message)
                memory_manager.sync_instagram_message_to_core(combined_message)
                self.db.commit()
                
                logger.info(f"✅ Chunked response sent to Instagram user: {conversation.instagram_user_id}")
                
                return final_response
            else:
                logger.error(f"❌ Failed to send chunked response")
                return None
                
        except Exception as e:
            logger.error(f"💥 Error processing chunked Instagram message: {str(e)}")
            return None
    
    def get_conversation_history(self, conversation: InstagramConversation, 
                               limit: int = 20) -> List[Dict]:
        """🔥 ENHANCED: Get conversation history with unified memory"""
        try:
            memory_manager = self._get_memory_manager(conversation.tenant_id)
            return memory_manager.get_conversation_history_unified(conversation, limit)
        except Exception as e:
            logger.error(f"Error getting conversation history: {str(e)}")
            return []
    
    def close_conversation(self, conversation_id: str, reason: str = "user_request") -> bool:
        """Close a conversation"""
        try:
            conversation = self.db.query(InstagramConversation).filter(
                InstagramConversation.conversation_id == conversation_id
            ).first()
            
            if conversation:
                conversation.is_active = False
                conversation.conversation_status = "closed"
                conversation.updated_at = datetime.utcnow()
                self.db.commit()
                
                logger.info(f"📝 Closed Instagram conversation: {conversation_id} - {reason}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error closing conversation: {str(e)}")
            return False