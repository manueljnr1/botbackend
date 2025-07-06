

import logging
import asyncio
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session


from app.chatbot.unified_intelligent_engine import get_unified_intelligent_engine
from app.telegram.service import TelegramService
from app.telegram.models import TelegramIntegration, TelegramChat
from app.telegram.utils import TelegramUtils
from app.tenants.models import Tenant


from app.pricing.integration_helpers import (
    check_conversation_limit_dependency_with_super_tenant,
    track_conversation_started_with_super_tenant
)

logger = logging.getLogger(__name__)

class TelegramMessageHandler:
    """
    Handles incoming Telegram messages and generates appropriate responses using UnifiedIntelligentEngine
    """
    
    def __init__(self, db: Session):
        self.db = db
        # Initialize unified intelligent engine instead of chatbot engine
        self.unified_engine = get_unified_intelligent_engine(db)
    
    async def process_update(self, update: Dict[str, Any], integration: TelegramIntegration) -> bool:
        """
        Process incoming Telegram update
        
        Args:
            update: Telegram update object
            integration: TelegramIntegration instance
            
        Returns:
            bool: Success status
        """
        try:
            # Initialize Telegram service
            telegram_service = TelegramService(integration.bot_token)
            
            # Handle different update types
            if "message" in update:
                success = await self._handle_message(update["message"], integration, telegram_service)
            elif "callback_query" in update:
                success = await self._handle_callback_query(update["callback_query"], integration, telegram_service)
            elif "edited_message" in update:
                success = await self._handle_edited_message(update["edited_message"], integration, telegram_service)
            else:
                logger.info(f"Unhandled update type for tenant {integration.tenant_id}: {list(update.keys())}")
                success = True  # Don't consider unknown updates as failures
            
            # Update integration stats
            if success:
                integration.total_messages_received += 1
                integration.last_webhook_received = datetime.utcnow()
                integration.error_count = 0  # Reset error count on success
            else:
                integration.error_count += 1
                integration.last_error_at = datetime.utcnow()
            
            self.db.commit()
            
            await telegram_service.close()
            return success
            
        except Exception as e:
            logger.error(f"Error processing Telegram update for tenant {integration.tenant_id}: {e}")
            integration.error_count += 1
            integration.last_error = str(e)
            integration.last_error_at = datetime.utcnow()
            self.db.commit()
            return False
    
    async def _handle_message(self, message: Dict[str, Any], 
                             integration: TelegramIntegration, 
                             telegram_service: TelegramService) -> bool:
        """Handle incoming text message"""
        try:
            # Extract message details
            chat_id = message["chat"]["id"]
            user_id = message["from"]["id"]
            text = message.get("text", "").strip()
            
            if not text:
                # Handle non-text messages (photos, documents, etc.)
                await self._handle_non_text_message(message, integration, telegram_service)
                return True
            
            # Get or create chat record
            chat_record = await self._get_or_create_chat(message, integration)
            
            # Handle commands
            if text.startswith("/"):
                return await self._handle_command(text, chat_id, chat_record, integration, telegram_service)
            
            # Check pricing limits
            try:
                check_conversation_limit_dependency_with_super_tenant(integration.tenant_id, self.db)
            except Exception as pricing_error:
                error_msg = "I'm sorry, but you've reached your conversation limit. Please contact support to upgrade your plan."
                await telegram_service.send_message(chat_id, error_msg)
                logger.warning(f"Conversation limit reached for tenant {integration.tenant_id}")
                return True
            
            # Show typing indicator
            if integration.enable_typing_indicator:
                await telegram_service.send_typing_action(chat_id)
            
            # Process message with unified intelligent engine
            response_data = await self._process_with_unified_engine(text, chat_record, integration)
            
            if response_data.get("success"):
                # Format response for Telegram
                formatted_response = TelegramUtils.format_response_for_telegram(
                    response_data["response"]
                )
                
                # Create inline keyboard if needed
                inline_keyboard = self._create_response_keyboard(response_data)
                
                # Send response
                send_result = await telegram_service.send_message(
                    chat_id=chat_id,
                    text=formatted_response,
                    reply_markup=inline_keyboard,
                    parse_mode="Markdown"
                )
                
                if send_result.get("success"):
                    # Track conversation
                    track_conversation_started_with_super_tenant(
                        tenant_id=integration.tenant_id,
                        user_identifier=chat_record.user_identifier,
                        platform="telegram",
                        db=self.db
                    )
                    
                    # Update stats
                    integration.total_messages_sent += 1
                    integration.last_message_sent = datetime.utcnow()
                    chat_record.total_messages += 1
                    chat_record.last_message_at = datetime.utcnow()
                    
                    # Log intelligent engine insights
                    logger.info(f"✅ Telegram response sent via {response_data.get('answered_by', 'unknown')} "
                              f"(Intent: {response_data.get('intent', 'unknown')}, "
                              f"Context: {response_data.get('context', 'unknown')})")
                    
                    return True
                else:
                    logger.error(f"Failed to send Telegram message: {send_result.get('error')}")
                    return False
            else:
                # Handle unified engine error
                error_response = "I'm sorry, I'm having trouble processing your message right now. Please try again later."
                await telegram_service.send_message(chat_id, error_response)
                return False
                
        except Exception as e:
            logger.error(f"Error handling Telegram message: {e}")
            return False
    
    async def _process_with_unified_engine(self, text: str, chat_record: TelegramChat, 
                                         integration: TelegramIntegration) -> Dict[str, Any]:
        """Process message with unified intelligent engine"""
        try:
            # Get tenant's API key
            tenant = self.db.query(Tenant).filter(Tenant.id == integration.tenant_id).first()
            if not tenant:
                return {"success": False, "error": "Tenant not found"}
            
            logger.info(f"🚀 Processing Telegram message with UnifiedIntelligentEngine for tenant {tenant.id}")
            
            # Process with unified intelligent engine
            result = self.unified_engine.process_message(
                api_key=tenant.api_key,
                user_message=text,
                user_identifier=chat_record.user_identifier,
                platform="telegram"
            )
            
            # Log the intelligent insights
            if result.get("success"):
                logger.info(f"🧠 Unified Engine Results: "
                          f"Intent={result.get('intent', 'unknown')}, "
                          f"Context={result.get('context', 'unknown')}, "
                          f"AnsweredBy={result.get('answered_by', 'unknown')}, "
                          f"TokenEfficiency={result.get('token_efficiency', 'unknown')}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing with unified engine: {e}")
            return {"success": False, "error": str(e)}
    
    # Keep all the existing methods unchanged
    async def _handle_command(self, command: str, chat_id: str, chat_record: TelegramChat,
                             integration: TelegramIntegration, telegram_service: TelegramService) -> bool:
        """Handle Telegram commands like /start, /help"""
        try:
            command_lower = command.lower().split()[0]  # Get just the command part
            
            if command_lower == "/start":
                welcome_msg = integration.welcome_message or self._get_default_welcome_message(integration)
                
                # Create welcome keyboard
                keyboard = telegram_service.create_inline_keyboard([
                    [
                        {"text": "💬 Start Chatting", "callback_data": "start_chat"},
                        {"text": "❓ Help", "callback_data": "help"}
                    ]
                ])
                
                await telegram_service.send_message(
                    chat_id=chat_id,
                    text=welcome_msg,
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
                
            elif command_lower == "/help":
                help_msg = integration.help_message or self._get_default_help_message(integration)
                await telegram_service.send_message(chat_id, help_msg, parse_mode="Markdown")
                
            elif command_lower == "/settings":
                settings_msg = await self._get_settings_message(chat_record, integration)
                keyboard = self._create_settings_keyboard()
                
                await telegram_service.send_message(
                    chat_id=chat_id,
                    text=settings_msg,
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
                
            else:
                # Unknown command - process with unified engine
                return await self._process_unknown_command(command, chat_id, chat_record, integration, telegram_service)
            
            return True
            
        except Exception as e:
            logger.error(f"Error handling command {command}: {e}")
            return False
    
    async def _process_unknown_command(self, command: str, chat_id: str, chat_record: TelegramChat,
                                      integration: TelegramIntegration, 
                                      telegram_service: TelegramService) -> bool:
        """Process unknown commands as regular messages using unified engine"""
        # Remove the / and treat as regular message
        text = command[1:] if command.startswith("/") else command
        response_data = await self._process_with_unified_engine(text, chat_record, integration)
        
        if response_data.get("success"):
            formatted_response = TelegramUtils.format_response_for_telegram(response_data["response"])
            await telegram_service.send_message(chat_id, formatted_response, parse_mode="Markdown")
            return True
        
        return False
    
    async def _handle_callback_query(self, callback_query: Dict[str, Any], 
                                    integration: TelegramIntegration,
                                    telegram_service: TelegramService) -> bool:
        """Handle inline keyboard button callbacks"""
        try:
            query_id = callback_query["id"]
            data = callback_query.get("data", "")
            chat_id = callback_query["message"]["chat"]["id"]
            message_id = callback_query["message"]["message_id"]
            
            # Answer callback query to stop loading animation
            await telegram_service._make_request("answerCallbackQuery", callback_query_id=query_id)
            
            if data == "start_chat":
                response = "Great! I'm here to help you. What can I assist you with today?"
                await telegram_service.send_message(chat_id, response)
                
            elif data == "help":
                help_msg = integration.help_message or self._get_default_help_message(integration)
                await telegram_service.send_message(chat_id, help_msg, parse_mode="Markdown")
                
            elif data.startswith("settings_"):
                # Handle settings callbacks
                setting = data.replace("settings_", "")
                await self._handle_settings_callback(setting, chat_id, message_id, integration, telegram_service)
                
            else:
                # Unknown callback
                await telegram_service.send_message(chat_id, "Sorry, I didn't understand that action.")
            
            return True
            
        except Exception as e:
            logger.error(f"Error handling callback query: {e}")
            return False
    
    async def _handle_edited_message(self, message: Dict[str, Any],
                                    integration: TelegramIntegration,
                                    telegram_service: TelegramService) -> bool:
        """Handle edited messages"""
        # For now, we'll just acknowledge edited messages
        # In the future, we could implement re-processing logic
        logger.info(f"Received edited message for tenant {integration.tenant_id}")
        return True
    
    async def _handle_non_text_message(self, message: Dict[str, Any],
                                      integration: TelegramIntegration,
                                      telegram_service: TelegramService) -> bool:
        """Handle photos, documents, etc."""
        chat_id = message["chat"]["id"]
        
        if "photo" in message:
            response = "I received your photo! However, I can only process text messages at the moment. Please describe what you'd like help with."
        elif "document" in message:
            response = "I received your document! I can only process text messages right now. Please tell me how I can help you."
        elif "voice" in message:
            response = "I received your voice message! I can only process text messages at the moment. Please type your question."
        else:
            response = "I received your message! I can only process text messages right now. Please type your question."
        
        await telegram_service.send_message(chat_id, response)
        return True
    
    async def _get_or_create_chat(self, message: Dict[str, Any], 
                                 integration: TelegramIntegration) -> TelegramChat:
        """Get or create chat record"""
        try:
            chat_id = str(message["chat"]["id"])
            user_id = str(message["from"]["id"])
            
            # Try to find existing chat
            chat_record = self.db.query(TelegramChat).filter(
                TelegramChat.tenant_id == integration.tenant_id,
                TelegramChat.chat_id == chat_id,
                TelegramChat.user_id == user_id
            ).first()
            
            if chat_record:
                # Update last activity
                chat_record.last_message_at = datetime.utcnow()
                return chat_record
            
            # Create new chat record
            chat_record = TelegramChat(
                tenant_id=integration.tenant_id,
                telegram_integration_id=integration.id,
                chat_id=chat_id,
                chat_type=message["chat"]["type"],
                user_id=user_id,
                username=message["from"].get("username"),
                first_name=message["from"].get("first_name"),
                last_name=message["from"].get("last_name"),
                language_code=message["from"].get("language_code", "en"),
                is_active=True
            )
            
            self.db.add(chat_record)
            self.db.commit()
            self.db.refresh(chat_record)
            
            logger.info(f"Created new Telegram chat record for tenant {integration.tenant_id}, user {user_id}")
            return chat_record
            
        except Exception as e:
            logger.error(f"Error getting/creating chat record: {e}")
            raise
    
    def _create_response_keyboard(self, response_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create inline keyboard based on response and intelligent insights"""
        response_text = response_data.get("response", "").lower()
        intent = response_data.get("intent", "")
        answered_by = response_data.get("answered_by", "")
        
        # Enhanced keyboard creation based on intelligent engine insights
        if intent == "functional" or "setup" in response_text:
            return TelegramService.create_inline_keyboard([
                [
                    {"text": "📝 Step by step guide", "callback_data": "guide_detailed"},
                    {"text": "❓ More help", "callback_data": "help"}
                ]
            ])
        elif intent == "support" or answered_by == "FAQ":
            return TelegramService.create_inline_keyboard([
                [
                    {"text": "🔧 More troubleshooting", "callback_data": "troubleshoot"},
                    {"text": "👤 Contact support", "callback_data": "contact_support"}
                ]
            ])
        elif any(word in response_text for word in ["contact", "support", "help"]):
            return TelegramService.create_inline_keyboard([
                [
                    {"text": "💬 Continue chat", "callback_data": "start_chat"},
                    {"text": "❓ FAQ", "callback_data": "help"}
                ]
            ])
        
        return None
    
    def _create_settings_keyboard(self) -> Dict[str, Any]:
        """Create settings inline keyboard"""
        return TelegramService.create_inline_keyboard([
            [
                {"text": "🔔 Notifications", "callback_data": "settings_notifications"},
                {"text": "🌍 Language", "callback_data": "settings_language"}
            ],
            [
                {"text": "❓ Help", "callback_data": "help"},
                {"text": "🔙 Back", "callback_data": "start_chat"}
            ]
        ])
    
    async def _handle_settings_callback(self, setting: str, chat_id: str, message_id: int,
                                       integration: TelegramIntegration, 
                                       telegram_service: TelegramService) -> bool:
        """Handle settings-related callbacks"""
        try:
            if setting == "notifications":
                text = "🔔 *Notification Settings*\n\nCurrently, all notifications are enabled. You can manage notification preferences in your account settings."
            elif setting == "language":
                text = "🌍 *Language Settings*\n\nI currently support English. More languages will be added soon!"
            else:
                text = "⚙️ *Settings*\n\nUse the buttons below to configure your preferences."
            
            await telegram_service.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode="Markdown",
                reply_markup=self._create_settings_keyboard()
            )
            return True
            
        except Exception as e:
            logger.error(f"Error handling settings callback: {e}")
            return False
    
    def _get_default_welcome_message(self, integration: TelegramIntegration) -> str:
        """Get default welcome message"""
        tenant = self.db.query(Tenant).filter(Tenant.id == integration.tenant_id).first()
        company_name = tenant.business_name if tenant else "our company"
        
        return f"""🤖 *Welcome to {company_name}!*

I'm your AI assistant, powered by advanced intelligent technology to help you with any questions you might have.

You can:
• Ask me anything about our products or services
• Get help with setup and configuration
• Find answers to common questions

Just type your question and I'll do my best to help! 

Use /help to see available commands."""
    
    def _get_default_help_message(self, integration: TelegramIntegration) -> str:
        """Get default help message"""
        tenant = self.db.query(Tenant).filter(Tenant.id == integration.tenant_id).first()
        company_name = tenant.business_name if tenant else "our company"
        
        return f"""❓ *Help & Commands*

*Available Commands:*
/start - Welcome message and quick actions
/help - Show this help message
/settings - Configure your preferences

*How to use:*
• Just type your question naturally
• I can help with product info, setup guides, and troubleshooting
• Use the inline buttons for quick actions

*Need more help?*
I'm an intelligent AI assistant for {company_name}. I can understand your intent and provide contextual responses efficiently.

Just ask me anything! 😊"""
    
    async def _get_settings_message(self, chat_record: TelegramChat, 
                                   integration: TelegramIntegration) -> str:
        """Get settings message with user info"""
        return f"""⚙️ *Settings & Preferences*

*Your Information:*
• Name: {chat_record.display_name}
• Language: {chat_record.language_code.upper()}
• Chat Type: {chat_record.chat_type.title()}

*Available Settings:*
Use the buttons below to configure your preferences."""