"""
Environment variable utilities
"""
import os
import logging

logger = logging.getLogger(__name__)

def get_twilio_credentials():
    """Get Twilio credentials from environment variables"""
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    
    if not account_sid or not auth_token:
        logger.error("Twilio credentials not found in environment variables")
        return None, None
    
    return account_sid, auth_token

def get_whatsapp_api_key(phone_number):
    """Get API key for a WhatsApp phone number"""
    # Remove '+' and any non-digit characters
    clean_number = ''.join(filter(str.isdigit, str(phone_number)))
    
    # Try specific key for this number
    key = os.getenv(f"WHATSAPP_NUMBER_{clean_number}_API_KEY")
    
    # Fall back to default key
    if not key:
        logger.warning(f"No API key found for WhatsApp number {clean_number}")
        key = os.getenv("DEFAULT_API_KEY")
        if key:
            logger.info(f"Using DEFAULT_API_KEY as fallback")
    
    return key
