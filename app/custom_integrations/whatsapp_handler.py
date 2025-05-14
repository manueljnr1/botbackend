"""
Custom WhatsApp integration that doesn't use Twilio client
"""
from fastapi import FastAPI, Request, HTTPException
from app.chatbot.engine import ChatbotEngine
from app.database import SessionLocal
from app.tenants.models import Tenant
import logging
import json

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app.custom_integrations.whatsapp_handler")

def register_whatsapp_routes(app: FastAPI):
    """Register WhatsApp integration routes"""
    
    @app.post("/custom/whatsapp")
    async def handle_whatsapp_webhook(request: Request):
        """Handle WhatsApp webhook without using Twilio client"""
        # Log the request
        logger.info(f"Received WhatsApp webhook request")
        
        try:
            # Get form data from the request
            form_data = await request.form()
            form_dict = dict(form_data)
            logger.info(f"Request form data: {form_dict}")
            
            # Extract message details
            from_number = form_dict.get("From", "unknown")
            to_number = form_dict.get("To", "unknown")
            message_body = form_dict.get("Body", "")
            
            logger.info(f"Message from {from_number} to {to_number}: {message_body}")
            
            # Create database session
            db = SessionLocal()
            
            try:
                # Find first active tenant
                tenant = db.query(Tenant).filter(Tenant.is_active == True).first()
                
                if not tenant:
                    logger.error("No active tenant found")
                    return {"error": "No active tenant found", "success": False}
                
                # Process the message using the tenant's API key
                logger.info(f"Using tenant: {tenant.name} (ID: {tenant.id})")
                
                # Create chatbot engine and process message
                engine = ChatbotEngine(db)
                result = engine.process_message(
                    api_key=tenant.api_key,
                    user_message=message_body,
                    user_identifier=from_number
                )
                
                # Check result
                if result.get("success"):
                    bot_response = result.get("response", "I'm sorry, I couldn't process your request.")
                    logger.info(f"Bot response: {bot_response[:50]}...")
                    
                    # For Twilio, create a TwiML response
                    twiml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{bot_response}</Message>
</Response>"""
                    
                    # Return the response
                    return {"message": bot_response, "twiml": twiml_response, "success": True}
                else:
                    error = result.get("error", "Unknown error")
                    logger.error(f"Error processing message: {error}")
                    return {"error": error, "success": False}
                
            except Exception as e:
                logger.exception(f"Error in WhatsApp webhook handler: {e}")
                return {"error": str(e), "success": False}
            finally:
                db.close()
                
        except Exception as e:
            logger.exception(f"Error parsing WhatsApp webhook request: {e}")
            return {"error": str(e), "success": False}
