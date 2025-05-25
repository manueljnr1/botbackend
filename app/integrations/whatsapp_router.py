# from app.utils.env import get_twilio_credentials, get_whatsapp_api_key
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from twilio.rest import Client
from twilio.request_validator import RequestValidator
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))


from app.chatbot.engine import ChatbotEngine
from app.database import SessionLocal, get_db

# 🔥 PRICING INTEGRATION - ADD THESE IMPORTS
from app.pricing.integration_helpers import check_message_limit_dependency, track_message_sent
from app.tenants.router import get_tenant_from_api_key


# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create router
router = APIRouter()

# Initialize Twilio client
client = None
validator = None

try:
    # Get Twilio credentials from environment variables
    account_sid, auth_token = get_twilio_credentials()
    if account_sid and auth_token:
        client = Client(account_sid, auth_token)
    else:
        logger.error("Cannot initialize Twilio client - missing credentials")
        client = None
except Exception as e:
    print(f"Error: {e}")

def get_api_key_for_whatsapp_number(phone_number: str) -> str:
    """Get API key for a WhatsApp number"""
    return get_whatsapp_api_key(phone_number)
    # Extract the number part from "whatsapp:+14155238886" format
    if phone_number and phone_number.startswith("whatsapp:"):
        phone_number = phone_number.replace("whatsapp:", "")
    
    # Remove the '+' character
    if phone_number and "+" in phone_number:
        phone_number = phone_number.replace("+", "")
    
    # Log all environment variables for debugging
    logger.debug("Looking for environment variable: WHATSAPP_NUMBER_%s_API_KEY", phone_number)
    
    # Try to get the API key from environment variable
    api_key = None
    if phone_number:
        env_var_name = f"WHATSAPP_NUMBER_{phone_number}_API_KEY"
        api_key = os.getenv(env_var_name)
        
        if api_key:
            logger.info(f"Found API key for WhatsApp number {phone_number}")
        else:
            logger.warning(f"No API key found for WhatsApp number {phone_number}")
            # Try the default API key as fallback
            api_key = os.getenv("DEFAULT_API_KEY")
            if api_key:
                logger.info("Using DEFAULT_API_KEY as fallback")
            else:
                logger.error("No DEFAULT_API_KEY found")
    
    return api_key

# 🔥 MODIFIED WITH PRICING CHECKS
@router.post("/webhook")
async def handle_whatsapp_webhook(request: Request, db: Session = Depends(get_db)):
    """Handle incoming WhatsApp messages"""
    logger.info("Received WhatsApp webhook request")
    
    try:
        # Get the form data
        form_data = await request.form()
        logger.info(f"Received WhatsApp data: {dict(form_data)}")
        
        # Skip signature validation for testing
        """
        # Verify the request is from Twilio
        if validator:
            url = str(request.url)
            signature = request.headers.get("X-Twilio-Signature", "")
            
            if not validator.validate(url, form_data, signature):
                logger.warning(f"Invalid Twilio request signature. URL: {url}, Signature: {signature}, Form Data: {dict(form_data)}")
                raise HTTPException(status_code=403, detail="Invalid request signature")
        """
        
        # Get message details
        from_number = form_data.get("From")
        to_number = form_data.get("To")
        message_body = form_data.get("Body")
        
        logger.info(f"Message from {from_number} to {to_number}: {message_body}")
        
        api_key = get_api_key_for_phone(to_number)
        if not api_key:
            logger.error(f"No API key configured for number: {to_number}")
            return {"error": "No API key configured for this number"}
        
        # 🔒 PRICING CHECK - Get tenant and check message limits
        tenant = get_tenant_from_api_key(api_key, db)
        check_message_limit_dependency(tenant.id, db)
        
        # Process the message
        try:
            engine = ChatbotEngine(db)
            user_identifier = from_number
            
            logger.info(f"Processing message with API key: {api_key[:5]}...")
            result = engine.process_message(api_key, message_body, user_identifier)
            
            if result.get("success"):
                bot_response = result.get("response")
                logger.info(f"Bot response: {bot_response}")
                
                # 📊 PRICING TRACK - Log successful message usage
                track_message_sent(tenant.id, db)
                
                # Send response via WhatsApp
                if client:
                    message = client.messages.create(
                        from_=to_number,
                        body=bot_response,
                        to=from_number
                    )
                    logger.info(f"Response sent with SID: {message.sid}")
                    return {"message_sid": message.sid}
                else:
                    logger.error("Twilio client not initialized")
                    return {"error": "Twilio client not initialized"}
            else:
                error = result.get("error", "Unknown error")
                logger.error(f"Error processing message: {error}")
                return {"error": error}
        except HTTPException as e:
            # Handle pricing limit errors
            logger.error(f"Pricing limit exceeded for tenant {tenant.id}: {e.detail}")
            
            # Optionally send a limit exceeded message to WhatsApp user
            if client:
                limit_message = "You've reached your message limit for this month. Please upgrade your plan to continue chatting."
                try:
                    client.messages.create(
                        from_=to_number,
                        body=limit_message,
                        to=from_number
                    )
                    logger.info("Sent limit exceeded message to WhatsApp user")
                except Exception as send_error:
                    logger.error(f"Failed to send limit message: {send_error}")
            
            return {"error": "Message limit exceeded"}
        except Exception as e:
            logger.exception(f"Error in chatbot engine: {e}")
            return {"error": str(e)}
    except Exception as e:
        logger.exception(f"Error processing webhook: {e}")
        return {"error": str(e)}

# Simple test endpoint that doesn't require authentication
@router.post("/test")
async def test_whatsapp_webhook(request: Request):
    """Simple test endpoint for WhatsApp webhook"""
    try:
        # Get form data
        form_data = await request.form()
        logger.info(f"Received test webhook data: {dict(form_data)}")
        
        # Extract message
        body = form_data.get("Body", "No message provided")
        from_number = form_data.get("From", "Unknown")
        
        # Create a simple response
        response = f"Echo: {body}"
        logger.info(f"Sending test response: {response}")
        
        # Send response if Twilio client is initialized
        if client and from_number:
            to_number = form_data.get("To")
            if to_number:
                try:
                    message = client.messages.create(
                        from_=to_number,
                        body=response,
                        to=from_number
                    )
                    logger.info(f"Test response sent with SID: {message.sid}")
                    return {"message_sid": message.sid, "response": response}
                except Exception as e:
                    logger.error(f"Error sending Twilio message: {e}")
            
        return {"response": response}
    except Exception as e:
        logger.exception(f"Error in test webhook: {e}")
        return {"error": str(e)}

def include_whatsapp_router(app):
    """Include WhatsApp router in the app"""
    app.include_router(router, prefix="/integrations/whatsapp", tags=["WhatsApp"])