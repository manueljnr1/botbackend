import os
from pathlib import Path
from dotenv import load_dotenv

# env_path = Path(__file__).resolve().parent.parent / '.env'
# if env_path.exists():
#     load_dotenv(dotenv_path=env_path)
#     print(f"Loaded environment variables from {env_path}")
# else:
#     print(f"Warning: .env file not found at {env_path}")


from fastapi import FastAPI, Request, Depends, HTTPException

from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import uvicorn
import logging



from app.database import engine, Base, get_db
from app.auth.router import router as auth_router
from app.tenants.router import router as tenants_router
from app.knowledge_base.router import router as kb_router
from app.chatbot.router import router as chatbot_router
from app.integrations.whatsapp_router import include_whatsapp_router

# Create database tables
Base.metadata.create_all(bind=engine)



app = FastAPI(
    title="Multi-Tenant Customer Support Chatbot",
    description="AI-powered customer support chatbot for multiple businesses",
    version="1.0.0"
)

# After app definition and CORS middleware:

# @app.post("/custom/whatsapp")
# async def custom_whatsapp_webhook(request: Request):
#     """Handle WhatsApp webhook directly without Twilio client"""
#     # Log the request
#     print(f"Received WhatsApp webhook request")
    
#     try:
#         # Get form data from the request
#         form_data = await request.form()
#         form_dict = dict(form_data)
#         print(f"Request form data: {form_dict}")
        
#         # Extract message details
#         from_number = form_dict.get("From", "unknown")
#         to_number = form_dict.get("To", "unknown")
#         message_body = form_dict.get("Body", "")
        
#         print(f"Message from {from_number} to {to_number}: {message_body}")
        
#         # Create database session
#         db = SessionLocal()
        
#         try:
#             # Find first active tenant
#             from app.tenants.models import Tenant
#             tenant = db.query(Tenant).filter(Tenant.is_active == True).first()
            
#             if not tenant:
#                 print("No active tenant found")
#                 return {"error": "No active tenant found", "success": False}
            
#             # Process the message using the tenant's API key
#             print(f"Using tenant: {tenant.name} (ID: {tenant.id})")
            
#             # Create chatbot engine and process message
#             from app.chatbot.engine import ChatbotEngine
#             engine = ChatbotEngine(db)
#             result = engine.process_message(
#                 api_key=tenant.api_key,
#                 user_message=message_body,
#                 user_identifier=from_number
#             )
            
#             # Check result
#             if result.get("success"):
#                 bot_response = result.get("response", "I'm sorry, I couldn't process your request.")
#                 print(f"Bot response: {bot_response[:50]}...")
                
#                 # Return the response
#                 return {"message": bot_response, "success": True}
#             else:
#                 error = result.get("error", "Unknown error")
#                 print(f"Error processing message: {error}")
#                 return {"error": error, "success": False}
            
#         except Exception as e:
#             print(f"Error in WhatsApp webhook handler: {e}")
#             return {"error": str(e), "success": False}
#         finally:
#             db.close()
            
#     except Exception as e:
#         print(f"Error parsing WhatsApp webhook request: {e}")
#         return {"error": str(e), "success": False}

# Configure CORS


import os
from openai import OpenAI
from app.utils.email_service import email_service

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Specify allowed origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Include routers
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(tenants_router, prefix="/tenants", tags=["Tenants"])
app.include_router(kb_router, prefix="/knowledge-base", tags=["Knowledge Base"])
app.include_router(chatbot_router, prefix="/chatbot", tags=["Chatbot"])
include_whatsapp_router(app)


try:
    from app.integrations.whatsapp_router import include_whatsapp_router
    include_whatsapp_router(app)
    logger.info("WhatsApp router initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize WhatsApp router: {e}")

try:
    from app.auth.router import router as auth_router
    app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
    logger.info("Auth router initialized")
except Exception as e:
    logger.error(f"Failed to import auth router: {e}")

try:
    from app.tenants.router import router as tenants_router
    app.include_router(tenants_router, prefix="/tenants", tags=["Tenants"])
    logger.info("Tenants router initialized")
except Exception as e:
    logger.error(f"Failed to import tenants router: {e}")

try:
    from app.knowledge_base.router import router as kb_router
    app.include_router(kb_router, prefix="/knowledge-base", tags=["Knowledge Base"])
    logger.info("Knowledge base router initialized")
except Exception as e:
    logger.error(f"Failed to import knowledge base router: {e}")

try:
    from app.chatbot.router import router as chatbot_router
    app.include_router(chatbot_router, prefix="/chatbot", tags=["Chatbot"])
    logger.info("Chatbot router initialized")
except Exception as e:
    logger.error(f"Failed to import chatbot router: {e}")

@app.get("/")
def root():
    return {"message": "Welcome to Multi-Tenant Customer Support Chatbot API"}

# Health check endpoint
@app.get("/health")
def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.post("/whatsapp-test")
async def whatsapp_test(request: Request):
    """Test endpoint for WhatsApp webhook"""
    try:
        form_data = await request.form()
        logger.info(f"Received WhatsApp test webhook: {dict(form_data)}")
        
        # Simple echo response
        body = form_data.get("Body", "No message")
        return {
            "response": f"Echo: {body}"
        }
    except Exception as e:
        logger.error(f"Error in WhatsApp test webhook: {e}")
        return {"error": str(e)}    
@app.get("/health")
def health_check():
    # Check environment variables
    env_vars = {
        "TWILIO_ACCOUNT_SID": os.getenv("TWILIO_ACCOUNT_SID", "Not set"),
        "TWILIO_AUTH_TOKEN": os.getenv("TWILIO_AUTH_TOKEN", "Not set") != "Not set",
        "Database URL": os.getenv("DATABASE_URL", "Default SQLite"),
        "OpenAI API Key": os.getenv("OPENAI_API_KEY", "Not set") != "Not set"
    }
    
    # WhatsApp numbers with API keys
    whatsapp_keys = {}
    for key in os.environ:
        if key.startswith("WHATSAPP_NUMBER_") and key.endswith("_API_KEY"):
            number = key.replace("WHATSAPP_NUMBER_", "").replace("_API_KEY", "")
            whatsapp_keys[number] = "Configured"
    
    return {
        "status": "healthy",
        "environment": env_vars,
        "whatsapp_numbers": whatsapp_keys
    }

import os

@app.get("/debug/env")
async def debug_env():
    """Debug endpoint to check environment variables"""
    # Only show part of the key for security
    whatsapp_key = os.getenv("WHATSAPP_NUMBER_14155238886_API_KEY", "")
    masked_key = whatsapp_key[:5] + "..." if whatsapp_key else "Not set"
    return {
        "WHATSAPP_NUMBER_14155238886_API_KEY": masked_key,
        "DEFAULT_API_KEY": os.getenv("DEFAULT_API_KEY", "Not set")[:5] + "..." if os.getenv("DEFAULT_API_KEY") else "Not set"
    }