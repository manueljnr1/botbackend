 # app/telegram/utils.py
"""
Telegram Integration Utilities
Helper functions for Telegram bot operations
"""

import re
import logging
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse
import hashlib
import hmac

logger = logging.getLogger(__name__)

class TelegramUtils:
    """
    Utility functions for Telegram integration
    """
    
    @staticmethod
    def format_response_for_telegram(text: str) -> str:
        """
        Format chatbot response for Telegram display
        Converts various formatting to Telegram Markdown
        """
        if not text:
            return "I'm sorry, I couldn't generate a response."
        
        # Convert HTML-style bold to Telegram markdown
        text = re.sub(r'<b>(.*?)</b>', r'*\1*', text)
        text = re.sub(r'<strong>(.*?)</strong>', r'*\1*', text)
        
        # Convert HTML-style italic to Telegram markdown
        text = re.sub(r'<i>(.*?)</i>', r'_\1_', text)
        text = re.sub(r'<em>(.*?)</em>', r'_\1_', text)
        
        # Convert **bold** to *bold* (Telegram style)
        text = re.sub(r'\*\*(.*?)\*\*', r'*\1*', text)
        
        # Handle bullet points - ensure proper spacing
        text = re.sub(r'^[•\-\*]\s*', '• ', text, flags=re.MULTILINE)
        
        # Handle numbered lists
        text = re.sub(r'^\d+\.\s*', lambda m: f'{m.group(0)}', text, flags=re.MULTILINE)
        
        # Convert code blocks
        text = re.sub(r'```(.*?)```', r'`\1`', text, flags=re.DOTALL)
        
        # Clean up excessive newlines
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # Telegram message length limit
        if len(text) > 4096:
            text = text[:4090] + "..."
            logger.warning("Message truncated due to Telegram length limit")
        
        return text.strip()
    
    @staticmethod
    def escape_markdown_v2(text: str) -> str:
        """
        Escape special characters for Telegram MarkdownV2
        """
        # Characters that need escaping in MarkdownV2
        escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        
        for char in escape_chars:
            text = text.replace(char, f'\\{char}')
        
        return text
    
    @staticmethod
    def create_deep_link(bot_username: str, payload: str) -> str:
        """
        Create a deep link for the Telegram bot
        
        Args:
            bot_username: Bot username (without @)
            payload: Payload parameter
        
        Returns:
            Deep link URL
        """
        return f"https://t.me/{bot_username}?start={payload}"
    
    @staticmethod
    def extract_command_args(text: str) -> tuple[str, List[str]]:
        """
        Extract command and arguments from message text
        
        Args:
            text: Message text starting with /
            
        Returns:
            Tuple of (command, args_list)
        """
        parts = text.split()
        if not parts or not parts[0].startswith('/'):
            return "", []
        
        command = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []
        
        return command, args
    
    @staticmethod
    def validate_bot_token(token: str) -> bool:
        """
        Validate Telegram bot token format
        
        Args:
            token: Bot token to validate
            
        Returns:
            True if valid format
        """
        if not token:
            return False
        
        # Telegram bot token format: {bot_id}:{bot_token}
        # bot_id is numeric, bot_token is alphanumeric with specific length
        pattern = r'^\d+:[A-Za-z0-9_-]{35}$'
        return bool(re.match(pattern, token))
    
    @staticmethod
    def extract_bot_id(token: str) -> Optional[str]:
        """
        Extract bot ID from token
        
        Args:
            token: Bot token
            
        Returns:
            Bot ID if valid token, None otherwise
        """
        if not TelegramUtils.validate_bot_token(token):
            return None
        
        return token.split(':')[0]
    
    @staticmethod
    def format_user_mention(user_id: int, first_name: str, username: Optional[str] = None) -> str:
        """
        Format user mention for logging/display
        
        Args:
            user_id: Telegram user ID
            first_name: User's first name
            username: User's username (optional)
            
        Returns:
            Formatted user mention
        """
        if username:
            return f"@{username} ({first_name}, ID: {user_id})"
        else:
            return f"{first_name} (ID: {user_id})"
    
    @staticmethod
    def validate_webhook_url(url: str) -> bool:
        """
        Validate webhook URL format
        
        Args:
            url: Webhook URL to validate
            
        Returns:
            True if valid
        """
        try:
            parsed = urlparse(url)
            
            # Must be HTTPS
            if parsed.scheme != 'https':
                return False
            
            # Must have valid hostname
            if not parsed.hostname:
                return False
            
            # Path should exist
            if not parsed.path:
                return False
            
            return True
            
        except Exception:
            return False
    
    @staticmethod
    def generate_webhook_secret() -> str:
        """
        Generate secure webhook secret token
        
        Returns:
            Random secret token
        """
        import secrets
        return secrets.token_urlsafe(32)
    
    @staticmethod
    def verify_webhook_signature(data: bytes, signature: str, secret: str) -> bool:
        """
        Verify webhook signature (if using secret token)
        
        Args:
            data: Raw webhook data
            signature: Provided signature
            secret: Webhook secret
            
        Returns:
            True if signature is valid
        """
        try:
            expected_signature = hmac.new(
                secret.encode('utf-8'),
                data,
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(signature, expected_signature)
            
        except Exception as e:
            logger.error(f"Error verifying webhook signature: {e}")
            return False
    
    @staticmethod
    def format_error_message(error_code: int, description: str) -> str:
        """
        Format API error message for user display
        
        Args:
            error_code: Telegram API error code
            description: Error description
            
        Returns:
            User-friendly error message
        """
        user_messages = {
            400: "There was an issue with your request. Please try again.",
            401: "Bot authentication failed. Please contact support.",
            403: "I don't have permission to send messages. Please check bot settings.",
            404: "Chat not found. Please restart the conversation.",
            429: "Too many requests. Please wait a moment and try again.",
            500: "Telegram service is temporarily unavailable. Please try again later."
        }
        
        return user_messages.get(error_code, "An unexpected error occurred. Please try again.")
    
    @staticmethod
    def chunk_long_message(text: str, max_length: int = 4096) -> List[str]:
        """
        Split long message into chunks that fit Telegram limits
        
        Args:
            text: Message text to split
            max_length: Maximum length per chunk
            
        Returns:
            List of message chunks
        """
        if len(text) <= max_length:
            return [text]
        
        chunks = []
        current_chunk = ""
        
        # Split by paragraphs first
        paragraphs = text.split('\n\n')
        
        for paragraph in paragraphs:
            # If adding this paragraph would exceed limit
            if len(current_chunk) + len(paragraph) + 2 > max_length:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                
                # If single paragraph is too long, split by sentences
                if len(paragraph) > max_length:
                    sentences = paragraph.split('. ')
                    for sentence in sentences:
                        if len(current_chunk) + len(sentence) + 2 > max_length:
                            if current_chunk:
                                chunks.append(current_chunk.strip())
                                current_chunk = ""
                        
                        current_chunk += sentence + ". "
                else:
                    current_chunk = paragraph + "\n\n"
            else:
                current_chunk += paragraph + "\n\n"
        
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        return chunks
    
    @staticmethod
    def sanitize_callback_data(data: str, max_length: int = 64) -> str:
        """
        Sanitize callback data for inline keyboards
        
        Args:
            data: Callback data string
            max_length: Maximum allowed length
            
        Returns:
            Sanitized callback data
        """
        # Remove invalid characters
        data = re.sub(r'[^\w\-_.]', '_', data)
        
        # Truncate if too long
        if len(data) > max_length:
            data = data[:max_length]
        
        return data
    
    @staticmethod
    def format_file_size(size_bytes: int) -> str:
        """
        Format file size in human readable format
        
        Args:
            size_bytes: Size in bytes
            
        Returns:
            Formatted size string
        """
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        
        return f"{size_bytes:.1f} {size_names[i]}"
    
    @staticmethod
    def create_progress_bar(current: int, total: int, length: int = 20) -> str:
        """
        Create a text progress bar
        
        Args:
            current: Current progress value
            total: Total/max value
            length: Length of progress bar in characters
            
        Returns:
            Progress bar string
        """
        if total == 0:
            return "█" * length
        
        filled_length = int(length * current // total)
        bar = "█" * filled_length + "░" * (length - filled_length)
        percentage = round(100 * current / total, 1)
        
        return f"{bar} {percentage}%"
    
    @staticmethod
    def extract_entities(message: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Extract entities from Telegram message
        
        Args:
            message: Telegram message object
            
        Returns:
            Dictionary of entity types and their data
        """
        entities = message.get("entities", [])
        text = message.get("text", "")
        
        extracted = {
            "mentions": [],
            "hashtags": [],
            "urls": [],
            "emails": [],
            "phone_numbers": [],
            "bot_commands": []
        }
        
        for entity in entities:
            start = entity["offset"]
            length = entity["length"]
            entity_text = text[start:start + length]
            entity_type = entity["type"]
            
            if entity_type == "mention":
                extracted["mentions"].append(entity_text)
            elif entity_type == "hashtag":
                extracted["hashtags"].append(entity_text)
            elif entity_type == "url":
                extracted["urls"].append(entity_text)
            elif entity_type == "email":
                extracted["emails"].append(entity_text)
            elif entity_type == "phone_number":
                extracted["phone_numbers"].append(entity_text)
            elif entity_type == "bot_command":
                extracted["bot_commands"].append(entity_text)
        
        return extracted