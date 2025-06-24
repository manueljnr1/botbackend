# app/telegram/service.py
"""
Telegram Bot API Service
Handles all Telegram API communications
"""

import asyncio
import aiohttp
import logging
from typing import Dict, Any, Optional, List, Union
from datetime import datetime
import json
import os
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

class TelegramService:
    """
    Service for interacting with Telegram Bot API
    """
    
    BASE_URL = "https://api.telegram.org/bot"
    FILE_URL = "https://api.telegram.org/file/bot"
    
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.api_url = f"{self.BASE_URL}{bot_token}/"
        self.file_api_url = f"{self.FILE_URL}{bot_token}/"
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def _ensure_session(self):
        """Ensure aiohttp session exists"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout)
    
    async def close(self):
        """Close aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def _make_request(self, method: str, **kwargs) -> Dict[str, Any]:
        """
        Make API request to Telegram Bot API
        """
        await self._ensure_session()
        
        url = urljoin(self.api_url, method)
        
        try:
            async with self.session.post(url, json=kwargs) as response:
                data = await response.json()
                
                if data.get("ok"):
                    return {"success": True, "result": data.get("result")}
                else:
                    error_msg = data.get("description", "Unknown error")
                    logger.error(f"Telegram API error for {method}: {error_msg}")
                    return {"success": False, "error": error_msg, "error_code": data.get("error_code")}
                    
        except asyncio.TimeoutError:
            logger.error(f"Timeout error for Telegram API method: {method}")
            return {"success": False, "error": "Request timeout"}
        except Exception as e:
            logger.error(f"Exception in Telegram API request {method}: {str(e)}")
            return {"success": False, "error": str(e)}
    
    # ============ BOT MANAGEMENT ============
    
    async def get_me(self) -> Dict[str, Any]:
        """Get bot information"""
        return await self._make_request("getMe")
    
    async def set_webhook(self, webhook_url: str, secret_token: Optional[str] = None,
                         max_connections: int = 40, drop_pending_updates: bool = False) -> Dict[str, Any]:
        """Set webhook for receiving updates"""
        params = {
            "url": webhook_url,
            "max_connections": max_connections,
            "drop_pending_updates": drop_pending_updates
        }
        
        if secret_token:
            params["secret_token"] = secret_token
        
        return await self._make_request("setWebhook", **params)
    
    async def delete_webhook(self, drop_pending_updates: bool = False) -> Dict[str, Any]:
        """Delete webhook"""
        return await self._make_request("deleteWebhook", drop_pending_updates=drop_pending_updates)
    
    async def get_webhook_info(self) -> Dict[str, Any]:
        """Get current webhook status"""
        return await self._make_request("getWebhookInfo")
    
    # ============ MESSAGING ============
    
    async def send_message(self, chat_id: Union[int, str], text: str,
                          parse_mode: Optional[str] = "Markdown",
                          reply_markup: Optional[Dict] = None,
                          disable_web_page_preview: bool = True,
                          disable_notification: bool = False,
                          reply_to_message_id: Optional[int] = None) -> Dict[str, Any]:
        """Send text message"""
        
        # Telegram has a 4096 character limit
        if len(text) > 4096:
            text = text[:4090] + "..."
            logger.warning(f"Message truncated for chat {chat_id} due to length limit")
        
        params = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": disable_web_page_preview,
            "disable_notification": disable_notification
        }
        
        if parse_mode:
            params["parse_mode"] = parse_mode
        if reply_markup:
            params["reply_markup"] = reply_markup
        if reply_to_message_id:
            params["reply_to_message_id"] = reply_to_message_id
        
        return await self._make_request("sendMessage", **params)
    
    async def send_typing_action(self, chat_id: Union[int, str]) -> Dict[str, Any]:
        """Send typing indicator"""
        return await self._make_request("sendChatAction", chat_id=chat_id, action="typing")
    
    async def edit_message_text(self, chat_id: Union[int, str], message_id: int,
                               text: str, parse_mode: Optional[str] = "Markdown",
                               reply_markup: Optional[Dict] = None) -> Dict[str, Any]:
        """Edit existing message"""
        params = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text
        }
        
        if parse_mode:
            params["parse_mode"] = parse_mode
        if reply_markup:
            params["reply_markup"] = reply_markup
        
        return await self._make_request("editMessageText", **params)
    
    async def delete_message(self, chat_id: Union[int, str], message_id: int) -> Dict[str, Any]:
        """Delete message"""
        return await self._make_request("deleteMessage", chat_id=chat_id, message_id=message_id)
    
    # ============ FILE HANDLING ============
    
    async def send_photo(self, chat_id: Union[int, str], photo: str,
                        caption: Optional[str] = None,
                        parse_mode: Optional[str] = "Markdown") -> Dict[str, Any]:
        """Send photo message"""
        params = {
            "chat_id": chat_id,
            "photo": photo
        }
        
        if caption:
            params["caption"] = caption
        if parse_mode:
            params["parse_mode"] = parse_mode
        
        return await self._make_request("sendPhoto", **params)
    
    async def send_document(self, chat_id: Union[int, str], document: str,
                           caption: Optional[str] = None) -> Dict[str, Any]:
        """Send document"""
        params = {
            "chat_id": chat_id,
            "document": document
        }
        
        if caption:
            params["caption"] = caption
        
        return await self._make_request("sendDocument", **params)
    
    async def get_file(self, file_id: str) -> Dict[str, Any]:
        """Get file information"""
        return await self._make_request("getFile", file_id=file_id)
    
    # ============ CHAT MANAGEMENT ============
    
    async def get_chat(self, chat_id: Union[int, str]) -> Dict[str, Any]:
        """Get chat information"""
        return await self._make_request("getChat", chat_id=chat_id)
    
    async def get_chat_member(self, chat_id: Union[int, str], user_id: int) -> Dict[str, Any]:
        """Get chat member information"""
        return await self._make_request("getChatMember", chat_id=chat_id, user_id=user_id)
    
    async def leave_chat(self, chat_id: Union[int, str]) -> Dict[str, Any]:
        """Leave chat"""
        return await self._make_request("leaveChat", chat_id=chat_id)
    
    # ============ INLINE KEYBOARDS ============
    
    @staticmethod
    def create_inline_keyboard(buttons: List[List[Dict[str, str]]]) -> Dict[str, Any]:
        """
        Create inline keyboard markup
        
        Args:
            buttons: List of button rows, each row is a list of buttons
                    Each button: {"text": "Button Text", "callback_data": "data"}
                    or {"text": "URL Button", "url": "https://example.com"}
        """
        return {
            "inline_keyboard": buttons
        }
    
    @staticmethod
    def create_reply_keyboard(buttons: List[List[str]], 
                             resize_keyboard: bool = True,
                             one_time_keyboard: bool = False) -> Dict[str, Any]:
        """Create reply keyboard markup"""
        keyboard = [[{"text": btn} for btn in row] for row in buttons]
        
        return {
            "keyboard": keyboard,
            "resize_keyboard": resize_keyboard,
            "one_time_keyboard": one_time_keyboard
        }
    
    @staticmethod
    def remove_keyboard() -> Dict[str, Any]:
        """Remove reply keyboard"""
        return {"remove_keyboard": True}
    
    # ============ MESSAGE FORMATTING ============
    
    @staticmethod
    def escape_markdown(text: str) -> str:
        """Escape Markdown special characters"""
        special_chars = ['*', '_', '`', '[']
        for char in special_chars:
            text = text.replace(char, f'\\{char}')
        return text
    
    @staticmethod
    def format_message_for_telegram(text: str, use_markdown: bool = True) -> str:
        """
        Format message text for Telegram
        Converts basic formatting to Telegram Markdown
        """
        if not use_markdown:
            return text
        
        # Convert **bold** to *bold*
        import re
        text = re.sub(r'\*\*(.*?)\*\*', r'*\1*', text)
        
        # Convert bullet points to proper format
        text = re.sub(r'^[•\-\*]\s+', '• ', text, flags=re.MULTILINE)
        
        # Convert numbered lists
        text = re.sub(r'^\d+\.\s+', lambda m: f'{m.group(0)}', text, flags=re.MULTILINE)
        
        return text
    
    # ============ WEBHOOK VALIDATION ============
    
    @staticmethod
    def validate_webhook_request(update: Dict[str, Any], secret_token: Optional[str] = None) -> bool:
        """
        Validate webhook request
        """
        # Basic validation - check if update has required fields
        if not isinstance(update, dict):
            return False
        
        # Check for update_id (required field)
        if "update_id" not in update:
            return False
        
        # Additional secret token validation would go here
        # This is a placeholder for security validation
        
        return True
    
    # ============ ERROR HANDLING ============
    
    @staticmethod
    def handle_api_error(error_code: int, description: str) -> str:
        """
        Handle common Telegram API errors
        """
        error_messages = {
            400: "Bad Request - Check your parameters",
            401: "Unauthorized - Invalid bot token",
            403: "Forbidden - Bot was blocked by user or lacks permissions",
            404: "Not Found - Chat or user not found",
            429: "Too Many Requests - Rate limit exceeded",
            500: "Internal Server Error - Telegram server issue"
        }
        
        if error_code in error_messages:
            return f"{error_messages[error_code]}: {description}"
        else:
            return f"API Error {error_code}: {description}"