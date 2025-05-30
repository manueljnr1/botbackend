import os
from pathlib import Path
from dotenv import load_dotenv

from fastapi import FastAPI, Request, Depends, HTTPException
from app.database import engine, Base, get_db
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import uvicorn
import logging

from app.chatbot.models import ChatSession, ChatMessage
from app.tenants.models import Tenant
from app.auth.models import User, TenantCredentials
from app.database import engine, Base, get_db
from app.auth.router import router as auth_router
from app.tenants.router import router as tenants_router
from app.knowledge_base.router import router as kb_router
from app.chatbot.router import router as chatbot_router
from app.integrations.whatsapp_router import include_whatsapp_router
from app.analytics.router import router as analytics_router
from app.admin.router import router as admin_router
from app.discord.router import router as discord_router, get_bot_manager as get_discord_bot_manager
from app.pricing.router import router as pricing_router
from app.pricing.middleware import PricingMiddleware
from app.live_chat.router import router as live_chat_router
from app.slack.router import router as slack_router, get_bot_manager as get_slack_bot_manager
from app.slack.thread_memory import SlackThreadMemory, SlackChannelContext

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Multi-Tenant Customer Support Chatbot",
    description="AI-powered customer support chatbot for multiple businesses",
    version="1.0.0",
    debug=True
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Specify allowed origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add pricing middleware
app.add_middleware(PricingMiddleware)

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Include all routers (CLEANED UP - NO DUPLICATES)
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(tenants_router, prefix="/tenants", tags=["Tenants"])
app.include_router(kb_router, prefix="/knowledge-base", tags=["Knowledge Base"])
app.include_router(chatbot_router, prefix="/chatbot", tags=["Chatbot"])
app.include_router(analytics_router, prefix="/analytics", tags=["Analytics"])
app.include_router(admin_router, prefix="/admin", tags=["Admin"])
app.include_router(pricing_router, prefix="/pricing", tags=["Pricing"])
app.include_router(live_chat_router, prefix="/live-chat", tags=["Live Chat"])
app.include_router(discord_router, prefix="/api/discord", tags=["Discord"])
app.include_router(slack_router, prefix="/api/slack", tags=["Slack"])  # SINGLE INCLUSION

# Initialize WhatsApp router
try:
    include_whatsapp_router(app)
    logger.info("WhatsApp router initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize WhatsApp router: {e}")

@app.get("/")
def root():
    return {"message": "Welcome to Multi-Tenant Customer Support Chatbot API"}

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

# SINGLE STARTUP EVENT - NO DUPLICATES
@app.on_event("startup")
async def startup_event():
    """Start Discord and Slack bots on application startup"""
    try:
        logger.info("🚀 Starting bot integrations...")
        
        # Start Discord bots
        try:
            discord_manager = get_discord_bot_manager()
            await discord_manager.start_all_bots()
            logger.info("✅ All Discord bots started successfully")
        except Exception as e:
            logger.error(f"❌ Error starting Discord bots: {e}")
        
        # Start Slack bots
        try:
            slack_manager = get_slack_bot_manager()
            db = next(get_db())
            await slack_manager.initialize_bots(db)
            logger.info("✅ All Slack bots initialized successfully")
        except Exception as e:
            logger.error(f"❌ Error starting Slack bots: {e}")
        
        logger.info("🎉 Bot integration startup completed")
        
    except Exception as e:
        logger.error(f"💥 Error in startup event: {e}")

# SINGLE SHUTDOWN EVENT - NO DUPLICATES
@app.on_event("shutdown")
async def shutdown_event():
    """Stop Discord and Slack bots on application shutdown"""
    try:
        logger.info("🛑 Shutting down bot integrations...")
        
        # Stop Discord bots
        try:
            discord_manager = get_discord_bot_manager()
            await discord_manager.stop_all_bots()
            logger.info("✅ All Discord bots stopped successfully")
        except Exception as e:
            logger.error(f"❌ Error stopping Discord bots: {e}")
        
        # Slack bots are event-driven and don't need explicit stopping
        logger.info("✅ Slack bots shutdown completed")
        
        logger.info("🏁 Bot integration shutdown completed")
        
    except Exception as e:
        logger.error(f"💥 Error in shutdown event: {e}")

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)