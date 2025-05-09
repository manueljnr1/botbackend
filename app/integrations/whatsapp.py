from fastapi import FastAPI, Request, HTTPException
from twilio.rest import Client
from twilio.request_validator import RequestValidator
from app.chatbot.engine import ChatbotEngine
from app.database import SessionLocal
import os

# Initialize Twilio client
client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
validator = RequestValidator(os.getenv("TWILIO_AUTH_TOKEN"))

def register_whatsapp_routes(app: FastAPI):
    """Register WhatsApp integration routes"""
    
    @app.post("/integrations/whatsapp/webhook")
    async def handle_whatsapp_webhook(request: Request):
        # Verify the request is from Twilio
        form_data = await request.form()
        if not validator.validate(str(request.url), form_data, request.headers.get("X-Twilio-Signature", "")):
            raise HTTPException(status_code=403, detail="Invalid request signature")
        
        # Get message details
        from_number = form_data.get("From")
        to_number = form_data.get("To")
        message_body = form_data.get("Body")
        
        # Get API key based on the phone number
        api_key = get_api_key_for_whatsapp_number(to_number)
        if not api_key:
            return {"error": "No API key configured for this number"}
        
        # Process the message
        db = SessionLocal()
        try:
            engine = ChatbotEngine(db)
            user_identifier = from_number
            
            result = engine.process_message(api_key, message_body, user_identifier)
            
            if result.get("success"):
                # Send response via WhatsApp
                message = client.messages.create(
                    from_=to_number,
                    body=result.get("response"),
                    to=from_number
                )
                return {"message_sid": message.sid}
        finally:
            db.close()
        
        return {"status": "ok"}


def get_api_key_for_whatsapp_number(phone_number: str) -> str:
    """Get API key for a WhatsApp number - implement based on your configuration"""
    # This should be configured per WhatsApp business number
    # You might want to store this in the database or configuration
    # For now, returning a default value
    return os.getenv(f"WHATSAPP_NUMBER_{phone_number.replace('+', '')}_API_KEY", os.getenv("DEFAULT_API_KEY"))