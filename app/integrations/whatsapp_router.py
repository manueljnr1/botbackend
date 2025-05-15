# from fastapi import FastAPI, Request, HTTPException, APIRouter, Depends # Added APIRouter
# from twilio.rest import Client
# from twilio.request_validator import RequestValidator
# from sqlalchemy.orm import Session # For type hinting if using Depends(get_db)

# from app.chatbot.engine import ChatbotEngine
# from app.database import SessionLocal, get_db # Assuming get_db for consistency if preferred
# import logging
# import os

# # --- Configuration & Initialization ---

# # Consider making TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN part of a settings module
# TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
# TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
# DEFAULT_TENANT_API_KEY_FOR_WHATSAPP = os.getenv("DEFAULT_TENANT_API_KEY_FOR_WHATSAPP") # For the test tenant

# if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
#     logging.warning("Twilio credentials (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN) are not fully set in environment variables.")
#     # Depending on your app's needs, you might want to raise an error or disable this module
#     # For now, we'll let it proceed, but Twilio client will fail if used.

# try:
#     client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
#     validator = RequestValidator(TWILIO_AUTH_TOKEN)
# except Exception as e:
#     client = None
#     validator = None
#     logging.error(f"Failed to initialize Twilio client or validator: {e}. WhatsApp integration will not work.")


# # --- Logging Setup ---
# # Simpler log path, assuming this file is in app/integrations/ and logs go in project_root/logs
# # Adjust if your structure is different or use a configurable path.
# log_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'logs', 'whatsapp_debug.log')
# os.makedirs(os.path.dirname(log_file_path), exist_ok=True)

# logging.basicConfig(
#     filename=log_file_path,
#     level=logging.DEBUG,
#     format='%(asctime)s - %(levelname)s - %(message)s - %(funcName)s'
# )

# # --- Router Definition ---
# # Using APIRouter if this is meant to be included in a main FastAPI app
# # If you pass the main 'app' instance directly to register_whatsapp_routes, that's also fine.
# # This example uses APIRouter for modularity.
# router = APIRouter(
#     prefix="/integrations/whatsapp", # Define prefix here
#     tags=["WhatsApp Integration"]
# )

# # --- Helper Functions ---

# def get_api_key_for_whatsapp_number(phone_number_receiving_message: str) -> str | None:
#     """
#     Get the Chatbot API key associated with a specific WhatsApp business number.
#     This function needs to map your Twilio WhatsApp number(s) to your tenant API keys.
    
#     Args:
#         phone_number_receiving_message: The WhatsApp number (owned by you via Twilio) 
#                                         that received the message from the user.
#                                         Twilio sends this as the 'To' field.
    
#     Returns:
#         The API key for the tenant associated with this WhatsApp number, or None.
#     """
#     logging.debug(f"Attempting to get API key for WhatsApp number: {phone_number_receiving_message}")

#     # Example: Using environment variables (as in your original code)
#     # Format: WHATSAPP_NUMBER_whatsapp:+14155238886_API_KEY=your_tenant_api_key
#     # Twilio numbers often come with "whatsapp:" prefix.
#     # Ensure env var names are shell-compatible (e.g., no colons, plus signs).
#     # You might need to strip "whatsapp:" and sanitize the number for the env var name.
#     sanitized_number = phone_number_receiving_message.replace('whatsapp:', '').replace('+', '')
#     env_var_name = f"WHATSAPP_NUMBER_{sanitized_number}_API_KEY"
#     api_key = os.getenv(env_var_name)

#     if api_key:
#         logging.info(f"Found API key via env var {env_var_name} for number {phone_number_receiving_message}")
#         return api_key

#     # Fallback to a default API key if you have one for testing or a single primary tenant
#     if DEFAULT_TENANT_API_KEY_FOR_WHATSAPP:
#         logging.info(f"Using DEFAULT_TENANT_API_KEY_FOR_WHATSAPP for number {phone_number_receiving_message}")
#         return DEFAULT_TENANT_API_KEY_FOR_WHATSAPP
        
#     logging.warning(f"No API key configured for WhatsApp number: {phone_number_receiving_message} (checked env var {env_var_name} and default)")
#     return None


# # --- Webhook Endpoint ---

# @router.post("/webhook") # Path relative to router prefix, so full path will be /integrations/whatsapp/webhook
# async def handle_whatsapp_webhook(request: Request, db: Session = Depends(get_db)): # Using Depends(get_db)
#     """
#     Handles incoming WhatsApp messages from Twilio.
#     Validates the request, processes the message using ChatbotEngine, and sends a reply.
#     """
#     if not client or not validator:
#         logging.error("Twilio client/validator not initialized. Cannot process WhatsApp webhook.")
#         # Return 503 to indicate service is unavailable, but Twilio might just see a failure.
#         # It's better to ensure client/validator are initialized on app startup.
#         raise HTTPException(status_code=503, detail="WhatsApp integration is not configured properly.")

#     # Log the raw request body for debugging (Twilio sends form data)
#     raw_body = await request.body()
#     logging.debug(f"Received WhatsApp webhook. Raw Body: {raw_body.decode()}")

#     # Parse form data (Twilio sends application/x-www-form-urlencoded)
#     form_data = await request.form()
#     form_data_dict = dict(form_data) # Convert to dict for easier logging/access
#     logging.debug(f"Parsed Form Data: {form_data_dict}")

#     # Verify the request is from Twilio
#     twilio_signature = request.headers.get("X-Twilio-Signature", "")
#     # Construct the full URL as Twilio expects it for validation
#     # request.url is a Starlette URL object.
#     url_for_validation = str(request.url)
    
#     # If behind a proxy that terminates TLS, request.url might be http.
#     # Twilio often expects the public https URL. You might need to adjust this
#     # based on your deployment setup (e.g., using headers like X-Forwarded-Proto).
#     # For now, we assume request.url is what Twilio signed.
#     # If validation fails, log the components used for validation.
#     if not validator.validate(url_for_validation, form_data_dict, twilio_signature):
#         logging.warning(f"Invalid Twilio request signature. URL: {url_for_validation}, Signature: {twilio_signature}, Form Data: {form_data_dict}")
#         raise HTTPException(status_code=403, detail="Invalid Twilio request signature. Access denied.")
    
#     logging.info("Twilio request signature validated successfully.")

#     # Get message details from Twilio's payload
#     from_number = form_data_dict.get("From")       # User's WhatsApp number (e.g., "whatsapp:+1234567890")
#     to_number = form_data_dict.get("To")         # Your Twilio WhatsApp number (e.g., "whatsapp:+0987654321")
#     message_body = form_data_dict.get("Body")    # The text message from the user
#     profile_name = form_data_dict.get("ProfileName") # User's WhatsApp profile name

#     if not from_number or not to_number or message_body is None: # message_body can be an empty string
#         logging.error(f"Missing critical information from Twilio payload: From={from_number}, To={to_number}, Body exists={message_body is not None}")
#         # Respond to Twilio to acknowledge receipt but indicate an issue.
#         # An empty 200 OK is often best to prevent retries for malformed (but validated) requests.
#         return # Return an empty 200 OK

#     logging.info(f"Processing message from {from_number} (Profile: {profile_name}) to {to_number}: '{message_body}'")

#     # Get the Tenant API key based on *your* Twilio WhatsApp number that received the message
#     api_key = "sk-420a63812b9d4458937df4e223f4edaa"  # Hardcoded for testing
#     if not api_key:
#         logging.error(f"No tenant API key configured for Twilio WhatsApp number: {to_number}. Cannot process message.")
#         # Acknowledge receipt to Twilio. You might send a generic error to the user if you have a default "from" number.
#         return # Return an empty 200 OK

#     # Process the message using your ChatbotEngine
#     # The `db` session is now provided by FastAPI's dependency injection
#     try:
#         engine = ChatbotEngine(db=db) # ChatbotEngine expects db session in __init__
        
#         # Use the user's WhatsApp number (from_number) as the unique user_identifier for the session
#         user_identifier = from_number 
        
#         logging.debug(f"Calling ChatbotEngine for tenant_api_key: {api_key}, user: {user_identifier}, message: '{message_body}'")
#         engine_response = engine.process_message(
#             api_key=api_key,
#             user_message=message_body,
#             user_identifier=user_identifier
#         )
        
#         logging.debug(f"ChatbotEngine response: {engine_response}")

#         if engine_response and engine_response.get("success"):
#             bot_reply_text = engine_response.get("response")
#             if bot_reply_text:
#                 try:
#                     logging.info(f"Sending reply to {from_number}: '{bot_reply_text}'")
#                     client.messages.create(
#                         from_=to_number, # Reply from your Twilio WhatsApp number
#                         body=bot_reply_text,
#                         to=from_number    # Send to the user's WhatsApp number
#                     )
#                     logging.info(f"Successfully sent WhatsApp reply to {from_number}")
#                 except Exception as e:
#                     logging.error(f"Failed to send WhatsApp reply to {from_number}: {e}")
#                     # Don't raise HTTPException here as we've processed the incoming,
#                     # but failed on the outgoing. Twilio should still get a 200 OK.
#             else:
#                 logging.warning("ChatbotEngine reported success but provided no response text.")
#         else:
#             error_detail = engine_response.get("error", "Chatbot engine failed to process the message.")
#             logging.error(f"ChatbotEngine processing failed for user {from_number}: {error_detail}")
#             # Optionally, send a generic error message back to the user via WhatsApp if appropriate
#             # client.messages.create(from_=to_number, body="Sorry, I encountered an issue. Please try again later.", to=from_number)

#     except Exception as e:
#         logging.exception(f"Unexpected error during WhatsApp message processing for user {from_number}: {e}")
#         # For unexpected errors, it's okay to let FastAPI return a 500,
#         # or you can catch it and return an empty 200 OK to Twilio to prevent retries,
#         # while logging the error thoroughly.
#         # For now, let FastAPI handle it as a 500 if it's truly unexpected.
#         # However, if the ChatbotEngine itself raises an HTTPException, it should be handled.
#         if isinstance(e, HTTPException):
#             raise # Re-raise known HTTPExceptions
#         else:
#             # For other unhandled exceptions from the engine or this webhook logic
#             raise HTTPException(status_code=500, detail="An internal error occurred while processing your WhatsApp message.")

#     # Always return an empty 200 OK to Twilio to acknowledge receipt of the webhook,
#     # unless a critical error like signature validation failed (which raises HTTPException).
#     # The actual reply to the user is sent via the Twilio API call above.
#     return # FastAPI will return an empty 200 OK by default

# # --- Function to register this router with the main FastAPI app ---
# def include_whatsapp_router(app: FastAPI):
#     """
#     Includes the WhatsApp router in the main FastAPI application.
#     Call this from your main.py.
#     """
#     if not client or not validator:
#         logging.error("Cannot include WhatsApp router: Twilio client/validator not initialized.")
#         return
#     app.include_router(router)
#     logging.info("WhatsApp router included successfully.")


# @app.post("/integrations/whatsapp/webhook")
# async def handle_whatsapp_webhook(request: Request):
#     # Comment out the signature validation code for testing
#     """
#     # Verify the request is from Twilio
#     form_data = await request.form()
#     if not validator.validate(str(request.url), form_data, request.headers.get("X-Twilio-Signature", "")):
#         raise HTTPException(status_code=403, detail="Invalid request signature")
#     """
    
#     # Get message details
#     form_data = await request.form()
#     logging.info(f"Received WhatsApp message: {dict(form_data)}")
    
#     from_number = form_data.get("From")
#     to_number = form_data.get("To")
#     message_body = form_data.get("Body")
    
#     # Get API key based on the phone number
#     api_key = "sk-420a63812b9d4458937df4e223f4edaa"  # Hardcoded for testing
#     if not api_key:
#         logging.error(f"No API key found for number: {to_number}")
#         return {"error": "No API key configured for this number"}
    
#     # Process the message
#     db = SessionLocal()
#     try:
#         engine = ChatbotEngine(db)
#         user_identifier = from_number
        
#         result = engine.process_message(api_key, message_body, user_identifier)
        
#         if result.get("success"):
#             # Send response via WhatsApp
#             message = client.messages.create(
#                 from_=to_number,
#                 body=result.get("response"),
#                 to=from_number
#             )
#             return {"message_sid": message.sid}
#         else:
#             logging.error(f"Error processing message: {result.get('error')}")
#             return {"error": result.get("error")}
#     except Exception as e:
#         logging.error(f"Exception in webhook: {str(e)}")
#         return {"error": str(e)}
#     finally:
#         db.close()
    
#     return {"status": "ok"}


# from app.utils.env import get_twilio_credentials, get_whatsapp_api_key
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from twilio.rest import Client
from twilio.request_validator import RequestValidator
import logging
import os


from app.chatbot.engine import ChatbotEngine
from app.database import SessionLocal, get_db

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
        
        # Process the message
        try:
            engine = ChatbotEngine(db)
            user_identifier = from_number
            
            logger.info(f"Processing message with API key: {api_key[:5]}...")
            result = engine.process_message(api_key, message_body, user_identifier)
            
            if result.get("success"):
                bot_response = result.get("response")
                logger.info(f"Bot response: {bot_response}")
                
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
