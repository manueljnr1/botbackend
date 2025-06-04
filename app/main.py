import os
from pathlib import Path
from dotenv import load_dotenv

project_root = Path(__file__).parent.parent  # Go up from app/ to project root
env_file = project_root / ".env"
load_dotenv(env_file)


from fastapi import FastAPI, Request, Depends, HTTPException
from app.database import engine, Base, get_db
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import uvicorn
import logging
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

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
    title="LYRA",
    description="AI-powered customer support chatbot for multiple businesses",
    version="1.0.0",
    debug=True
)

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not JWT_SECRET_KEY or len(JWT_SECRET_KEY) < 32:
    raise ValueError("JWT_SECRET_KEY must be at least 32 characters")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)

# HTTPS redirect for production
if os.getenv("ENVIRONMENT") == "production":
    app.add_middleware(HTTPSRedirectMiddleware)

# Add trusted host middleware
app.add_middleware(
    TrustedHostMiddleware, 
    allowed_hosts=[
        "agentlyra.com",
        "www.agentlyra.com", 
        "frontier-j08o.onrender.com",
        "localhost",
        "127.0.0.1"
    ]
)

# Add security headers
@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response

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





@app.on_event("startup")
async def startup_event():
    """Combined startup event"""
    try:
        logger.info("🚀 Starting application initialization...")
        
        # 1. Start Discord and Slack bots
        try:
            discord_manager = get_discord_bot_manager()
            await discord_manager.start_all_bots()
            logger.info("✅ All Discord bots started successfully")
        except Exception as e:
            logger.error(f"❌ Error starting Discord bots: {e}")
        
        try:
            slack_manager = get_slack_bot_manager()
            db = next(get_db())
            await slack_manager.initialize_bots(db)
            logger.info("✅ All Slack bots initialized successfully")
        except Exception as e:
            logger.error(f"❌ Error starting Slack bots: {e}")
        
        # 2. Ensure all tenants have subscriptions
        try:
            from app.database import SessionLocal
            from app.tenants.models import Tenant
            from app.pricing.models import TenantSubscription
            from app.pricing.service import PricingService
            
            db = SessionLocal()
            
            try:
                logger.info("🔍 Checking for tenants without subscriptions...")
                
                tenants_without_subscriptions = db.query(Tenant).outerjoin(
                    TenantSubscription,
                    (Tenant.id == TenantSubscription.tenant_id) & (TenantSubscription.is_active == True)
                ).filter(
                    TenantSubscription.id.is_(None),
                    Tenant.is_active == True
                ).all()
                
                if tenants_without_subscriptions:
                    logger.info(f"📊 Found {len(tenants_without_subscriptions)} tenants without subscriptions")
                    
                    pricing_service = PricingService(db)
                    pricing_service.create_default_plans()
                    
                    fixed_count = 0
                    for tenant in tenants_without_subscriptions:
                        try:
                            logger.info(f"🔧 Fixing subscription for tenant: {tenant.name} (ID: {tenant.id})")
                            subscription = pricing_service.create_free_subscription_for_tenant(tenant.id)
                            
                            if subscription:
                                fixed_count += 1
                                logger.info(f"✅ Fixed subscription for {tenant.name}")
                            else:
                                logger.error(f"❌ Failed to create subscription for {tenant.name}")
                                
                        except Exception as e:
                            logger.error(f"💥 Error fixing tenant {tenant.name}: {e}")
                    
                    logger.info(f"🎉 Fixed subscriptions for {fixed_count}/{len(tenants_without_subscriptions)} tenants")
                else:
                    logger.info("✅ All tenants have subscriptions")
                    
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"💥 Error in startup subscription check: {e}")
        
        logger.info("🎉 Application startup completed")
        
    except Exception as e:
        logger.error(f"💥 Error in startup event: {e}")




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
    # Add environment check for security
    host = "0.0.0.0" if os.getenv("ENVIRONMENT") == "development" else "127.0.0.1"
    uvicorn.run("app.main:app", host=host, port=8000, reload=True)

