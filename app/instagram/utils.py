# app/instagram/utils.py
"""
Instagram Integration Utilities
Helper functions for Instagram API interactions and data processing
"""

import re
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

def validate_instagram_username(username: str) -> bool:
    """
    Validate Instagram username format
    
    Args:
        username: Instagram username to validate
        
    Returns:
        bool: True if valid, False otherwise
    """
    if not username:
        return False
    
    # Remove @ if present
    clean_username = username.lstrip('@')
    
    # Instagram username rules:
    # - 1-30 characters
    # - Only letters, numbers, periods, and underscores
    # - Cannot start or end with period
    # - Cannot have consecutive periods
    pattern = r'^[a-zA-Z0-9._]{1,30}$'
    
    if not re.match(pattern, clean_username):
        return False
    
    # Check for invalid patterns
    if clean_username.startswith('.') or clean_username.endswith('.'):
        return False
    
    if '..' in clean_username:
        return False
    
    return True

def validate_facebook_page_id(page_id: str) -> bool:
    """
    Validate Facebook Page ID format
    
    Args:
        page_id: Facebook Page ID to validate
        
    Returns:
        bool: True if valid, False otherwise
    """
    if not page_id:
        return False
    
    # Facebook Page IDs are typically numeric strings
    return page_id.isdigit() and len(page_id) >= 10

def validate_meta_app_id(app_id: str) -> bool:
    """
    Validate Meta App ID format
    
    Args:
        app_id: Meta App ID to validate
        
    Returns:
        bool: True if valid, False otherwise
    """
    if not app_id:
        return False
    
    # Meta App IDs are typically numeric strings
    return app_id.isdigit() and len(app_id) >= 10

def validate_access_token(token: str) -> bool:
    """
    Basic validation for access token format
    
    Args:
        token: Access token to validate
        
    Returns:
        bool: True if valid format, False otherwise
    """
    if not token:
        return False
    
    # Basic checks for token format
    if len(token) < 50:
        return False
    
    # Should not contain spaces
    if ' ' in token:
        return False
    
    return True

def extract_instagram_user_id_from_url(url: str) -> Optional[str]:
    """
    Extract Instagram user ID from Instagram URL
    
    Args:
        url: Instagram profile URL
        
    Returns:
        Optional[str]: Instagram username if found, None otherwise
    """
    try:
        parsed = urlparse(url)
        
        if parsed.netloc not in ['instagram.com', 'www.instagram.com']:
            return None
        
        # Extract username from path
        path_parts = parsed.path.strip('/').split('/')
        
        if len(path_parts) >= 1 and path_parts[0]:
            username = path_parts[0]
            
            if validate_instagram_username(username):
                return username.lower()
        
        return None
        
    except Exception as e:
        logger.error(f"Error extracting username from URL: {e}")
        return None

def format_instagram_message_for_display(message_type: str, content: str, 
                                        media_url: str = None) -> str:
    """
    Format Instagram message for display in chat interfaces
    
    Args:
        message_type: Type of message (text, image, video, etc.)
        content: Message content
        media_url: URL of media if applicable
        
    Returns:
        str: Formatted message for display
    """
    if message_type == "text":
        return content or ""
    
    elif message_type == "image":
        display = "[📷 Image]"
        if content:
            display += f" {content}"
        return display
    
    elif message_type == "video":
        display = "[🎥 Video]"
        if content:
            display += f" {content}"
        return display
    
    elif message_type == "audio":
        display = "[🎵 Audio]"
        if content:
            display += f" {content}"
        return display
    
    elif message_type == "story_reply":
        return f"[📖 Story Reply] {content or ''}"
    
    else:
        return f"[{message_type.title()}] {content or ''}"

def generate_conversation_summary(messages: List[Dict[str, Any]], 
                                max_length: int = 200) -> str:
    """
    Generate a summary of conversation messages
    
    Args:
        messages: List of message dictionaries
        max_length: Maximum length of summary
        
    Returns:
        str: Conversation summary
    """
    if not messages:
        return "No messages"
    
    # Get recent messages
    recent_messages = messages[-5:] if len(messages) > 5 else messages
    
    # Extract text content
    text_parts = []
    for msg in recent_messages:
        content = msg.get('content', '')
        if content and msg.get('message_type') == 'text':
            text_parts.append(content[:50])  # Limit each message
    
    if not text_parts:
        return f"{len(messages)} messages exchanged"
    
    summary = " ... ".join(text_parts)
    
    # Truncate if too long
    if len(summary) > max_length:
        summary = summary[:max_length-3] + "..."
    
    return summary

def calculate_response_time_stats(messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate response time statistics from message history
    
    Args:
        messages: List of message dictionaries with timestamps
        
    Returns:
        Dict: Statistics including average response time
    """
    try:
        response_times = []
        
        for i in range(1, len(messages)):
            current_msg = messages[i]
            previous_msg = messages[i-1]
            
            # Check if this is a bot response to user message
            if (not current_msg.get('is_from_user') and 
                previous_msg.get('is_from_user')):
                
                current_time = datetime.fromisoformat(current_msg['created_at'].replace('Z', '+00:00'))
                previous_time = datetime.fromisoformat(previous_msg['created_at'].replace('Z', '+00:00'))
                
                response_time = (current_time - previous_time).total_seconds()
                
                # Only count reasonable response times (less than 1 hour)
                if 0 < response_time < 3600:
                    response_times.append(response_time)
        
        if not response_times:
            return {
                "average_response_time": None,
                "fastest_response": None,
                "slowest_response": None,
                "total_responses": 0
            }
        
        return {
            "average_response_time": sum(response_times) / len(response_times),
            "fastest_response": min(response_times),
            "slowest_response": max(response_times),
            "total_responses": len(response_times)
        }
        
    except Exception as e:
        logger.error(f"Error calculating response time stats: {e}")
        return {
            "average_response_time": None,
            "fastest_response": None,
            "slowest_response": None,
            "total_responses": 0,
            "error": str(e)
        }

def sanitize_webhook_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize webhook payload for safe storage and logging
    
    Args:
        payload: Raw webhook payload
        
    Returns:
        Dict: Sanitized payload
    """
    try:
        # Create a copy to avoid modifying original
        sanitized = payload.copy()
        
        # Remove or mask sensitive data
        sensitive_fields = ['access_token', 'token', 'secret', 'password']
        
        def sanitize_recursive(obj):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if any(sensitive in key.lower() for sensitive in sensitive_fields):
                        obj[key] = "[MASKED]"
                    elif isinstance(value, (dict, list)):
                        sanitize_recursive(value)
            elif isinstance(obj, list):
                for item in obj:
                    if isinstance(item, (dict, list)):
                        sanitize_recursive(item)
        
        sanitize_recursive(sanitized)
        return sanitized
        
    except Exception as e:
        logger.error(f"Error sanitizing webhook payload: {e}")
        return {"error": "Failed to sanitize payload"}

def format_instagram_quick_replies(options: List[str], max_options: int = 11) -> List[Dict[str, str]]:
    """
    Format quick reply options for Instagram API
    
    Args:
        options: List of quick reply text options
        max_options: Maximum number of options (Instagram limit is 13)
        
    Returns:
        List[Dict]: Formatted quick replies for Instagram API
    """
    if not options:
        return []
    
    # Limit to max options
    limited_options = options[:max_options]
    
    quick_replies = []
    for i, option in enumerate(limited_options):
        # Truncate option text if too long (Instagram limit is 20 characters)
        display_text = option[:20] if len(option) > 20 else option
        
        quick_replies.append({
            "content_type": "text",
            "title": display_text,
            "payload": f"QUICK_REPLY_{i}_{option[:10]}"  # Unique payload
        })
    
    return quick_replies

def parse_instagram_timestamp(timestamp: int) -> datetime:
    """
    Parse Instagram timestamp to datetime object
    
    Args:
        timestamp: Instagram timestamp (milliseconds since epoch)
        
    Returns:
        datetime: Parsed datetime object
    """
    try:
        # Instagram timestamps are in milliseconds
        return datetime.fromtimestamp(timestamp / 1000)
    except (ValueError, TypeError) as e:
        logger.error(f"Error parsing Instagram timestamp {timestamp}: {e}")
        return datetime.utcnow()

def generate_webhook_verify_token() -> str:
    """
    Generate a secure webhook verify token
    
    Returns:
        str: Random verify token
    """
    import secrets
    import string
    
    # Generate a random string with letters and numbers
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(32))

def validate_instagram_media_url(url: str) -> bool:
    """
    Validate Instagram media URL format
    
    Args:
        url: Media URL to validate
        
    Returns:
        bool: True if valid, False otherwise
    """
    if not url:
        return False
    
    try:
        parsed = urlparse(url)
        
        # Check if it's a valid URL
        if not parsed.scheme or not parsed.netloc:
            return False
        
        # Check if it's HTTPS
        if parsed.scheme != 'https':
            return False
        
        # Check if it's from Instagram domains
        valid_domains = [
            'scontent.cdninstagram.com',
            'instagram.com',
            'fbcdn.net',
            'scontent.xx.fbcdn.net'
        ]
        
        return any(domain in parsed.netloc for domain in valid_domains)
        
    except Exception as e:
        logger.error(f"Error validating media URL: {e}")
        return False

def get_instagram_error_message(error_code: int, error_message: str) -> str:
    """
    Get user-friendly error message for Instagram API errors
    
    Args:
        error_code: Error code from Instagram API
        error_message: Original error message
        
    Returns:
        str: User-friendly error message
    """
    error_map = {
        100: "Invalid parameter provided",
        190: "Access token has expired or is invalid",
        200: "Permission denied - missing required permissions",
        368: "User is temporarily blocked from messaging",
        551: "User cannot receive messages at this time",
        10: "Permission denied - application not authorized",
        2500: "User has not responded within 24 hours",
    }
    
    if error_code in error_map:
        return f"{error_map[error_code]}: {error_message}"
    
    return f"Instagram API Error ({error_code}): {error_message}"