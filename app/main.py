import os
from pathlib import Path
from dotenv import load_dotenv

project_root = Path(__file__).parent.parent  # Go up from app/ to project root
env_file = project_root / ".env"
load_dotenv(env_file)


from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse
from app.database import engine, Base, get_db
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import uvicorn
import logging
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from datetime import datetime
from fastapi.staticfiles import StaticFiles

from app.chatbot.models import ChatSession, ChatMessage
from app.pricing.models import PricingPlan, TenantSubscription 
from app.tenants.models import Tenant
from app.auth.models import User, TenantCredentials
from app.database import engine, Base, get_db
from app.auth.router import router as auth_router
from app.tenants.router import router as tenants_router
from app.knowledge_base.router import router as kb_router
from app.chatbot.router import router as chatbot_router

from app.analytics.router import router as analytics_router
from app.admin.router import router as admin_router
from app.discord.router import router as discord_router, get_bot_manager as get_discord_bot_manager
from app.pricing.router import router as pricing_router
from app.pricing.middleware import PricingMiddleware
from app.slack.router import router as slack_router, get_bot_manager as get_slack_bot_manager
from app.slack.thread_memory import SlackThreadMemory, SlackChannelContext
from app.payments.router import router as payments_router
from app.instagram.router import router as instagram_router
from app.instagram.bot_manager import get_instagram_bot_manager
from app.telegram.router import router as telegram_router
from app.telegram.bot_manager import get_telegram_bot_manager
from app.live_chat.auth_router import router as live_chat_auth_router
from app.live_chat.router import router as live_chat_main_router
from app.live_chat.customer_detection_config import CustomerDetectionMiddleware, detection_config
from app.live_chat.transcript_router import router as transcript_router

from app.chatbot.admin_router import router as enhanced_admin_router
from app.admin import intent_training_router



from app.config import settings
# from app.live_chat import auth_router, router as live_chat_router
import asyncio


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ✅ Validate production configuration at startup
try:
    settings.validate_production_config()
    env_emoji = "🔒" if settings.is_production() else "🧪" if settings.is_staging() else "🔧"
    logger.info(f"{env_emoji} Configuration validated for environment: {settings.ENVIRONMENT}")
except ValueError as e:
    logger.error(f"❌ Configuration error: {e}")
    if settings.requires_security_validation():  # Both production AND staging
        raise  # Fail fast in production and staging
    else:
        logger.warning("⚠️ Configuration issues detected but continuing in development mode")

# Create database tables
# Base.metadata.create_all(bind=engine)

from app.database import create_tables_safely

try:
    create_tables_safely()
    logger.info("✅ Database tables created successfully")
except Exception as e:
    logger.error(f"❌ Failed to create database tables: {e}")
    if settings.is_production():
        raise  # Fail fast in production
    else:
        logger.warning("⚠️ Continuing without table creation in development mode")




app = FastAPI(
    title="LYRA",
    description="AI-powered customer support chatbot for multiple businesses",
    version="1.0.0",
    debug=settings.is_development(),
    openapi_url="/backend/openapi.json",
    # docs_url="/admin-docs" if settings.is_development() else None,
    # redoc_url="/admin-redoc" if settings.is_development() else None
)

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not JWT_SECRET_KEY or len(JWT_SECRET_KEY) < 32:
    raise ValueError("JWT_SECRET_KEY must be at least 32 characters")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # Must be False when using "*"
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

logger.info(f"🌐 CORS configured for {settings.ENVIRONMENT}: Open (API key protected)")



# HTTPS redirect for production
railway_environment = os.getenv("RAILWAY_PROJECT_ID") or os.getenv("RAILWAY_ENVIRONMENT")

if settings.requires_security_validation() and not railway_environment:
    app.add_middleware(HTTPSRedirectMiddleware)
    logger.info("🔒 HTTPS redirect middleware enabled")
else:
    logger.info("🚂 Railway detected or dev mode - HTTPS redirect disabled")

# Add trusted host middleware
if settings.requires_security_validation():
    trusted_hosts = settings.get_allowed_domains_list()
    if trusted_hosts:
        # app.add_middleware(TrustedHostMiddleware, allowed_hosts=trusted_hosts)
        logger.info(f"🔒 Trusted hosts configured: {trusted_hosts}")
    elif settings.is_production():  # Only warn for production
        logger.warning("⚠️ No trusted hosts configured for production")



# Add security headers
# @app.middleware("http")
# async def add_security_headers(request, call_next):
#     response = await call_next(request)
#     response.headers["X-Content-Type-Options"] = "nosniff"
#     response.headers["X-Frame-Options"] = "DENY"
#     response.headers["X-XSS-Protection"] = "1; mode=block"
    
    
#     if settings.requires_security_validation():
#         response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
#         response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    
#     return response






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
app.include_router(discord_router, prefix="/api/discord", tags=["Discord"])
app.include_router(slack_router, prefix="/api/slack", tags=["Slack"])  # SINGLE INCLUSION
app.include_router(payments_router, prefix="/api/payments", tags=["payments"])
app.include_router(instagram_router, prefix="/api/instagram", tags=["Instagram"])
app.include_router(telegram_router, prefix="/api/telegram", tags=["Telegram"])

app.include_router(live_chat_auth_router, prefix="/live-chat/auth", tags=["Live Chat Auth"])
app.include_router(live_chat_main_router, prefix="/live-chat", tags=["Live Chat"])
app.add_middleware(CustomerDetectionMiddleware, enabled=True)
app.include_router(transcript_router, prefix="/live-chat/transcript", tags=["transcripts"])
app.include_router(admin_router, prefix="/chatbot/enhanced-admin", tags=["Enhanced Admin"])
app.include_router(intent_training_router.router, prefix="/admin/intent-training", tags=["admin-intent"])
app.mount("/static", StaticFiles(directory="static"), name="static")



@app.get("/")
def root():
    return {"message": "LYRA is saying Hello!"}







# @app.get("/health")
# def health_check():
#     # Check environment variables
#     env_vars = {
#         "TWILIO_ACCOUNT_SID": os.getenv("TWILIO_ACCOUNT_SID", "Not set"),
#         "TWILIO_AUTH_TOKEN": os.getenv("TWILIO_AUTH_TOKEN", "Not set") != "Not set",
#         "Database URL": os.getenv("DATABASE_URL", "Default SQLite"),
#         "OpenAI API Key": os.getenv("OPENAI_API_KEY", "Not set") != "Not set",
#         "Frontend URL": settings.FRONTEND_URL or "Using default localhost:3000",  # ✅ Show config
#         "Environment": settings.ENVIRONMENT
#     }

    

@app.get("/health")
def health_check():
    """Enhanced health check with database monitoring"""
    from app.database import database_health_check
    
    try:
        # Check database health
        db_health = database_health_check()
        
        # Check environment variables
        env_vars = {
            "Environment": settings.ENVIRONMENT,
            "Database": "✅ Connected" if db_health["status"] == "healthy" else "❌ Issues",
            "OpenAI API": "✅ Configured" if os.getenv("OPENAI_API_KEY") else "❌ Missing",
            "Frontend URL": settings.FRONTEND_URL or "Using default",
        }
        
        return {
            "status": "healthy" if db_health["status"] == "healthy" else "degraded",
            "timestamp": datetime.utcnow().isoformat(),
            "environment": env_vars,
            "database": db_health
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }











@app.get("/health/live-chat")
async def live_chat_health_check():
    """Health check endpoint for live chat system"""
    try:
        from app.live_chat.websocket_manager import websocket_manager
        
        # Check database connectivity
        db = next(get_db())
        
        # Check WebSocket manager
        connection_stats = websocket_manager.get_connection_stats()
        
        return {
            "status": "healthy",
            "service": "live_chat",
            "websocket_connections": connection_stats["total_connections"],
            "active_connections": connection_stats["active_connections"],
            "timestamp": datetime.utcnow().isoformat(),
            "database_connected": True
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "service": "live_chat",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }







@app.on_event("startup")
async def startup_event():
    """Combined startup event - UPDATED with Telegram"""
    try:
        env_emoji = "🔒" if settings.is_production() else "🧪" if settings.is_staging() else "🔧"
        logger.info(f"🚀 Starting LYRA application {env_emoji} (Environment: {settings.ENVIRONMENT})...")


        from app.database import retry_database_initialization
        
        db_success = await retry_database_initialization()
        if not db_success:
            logger.error("❌ Database initialization failed - some features may not work")
            if settings.is_production():
                # In production, you might want to exit
                logger.error("🚨 Exiting due to database failure in production")
                import sys
                sys.exit(1)

        
        # 1. Start Discord, Slack, Instagram, and Telegram bots
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
        
        try:
            instagram_manager = get_instagram_bot_manager()
            db = next(get_db())
            await instagram_manager.initialize_bots(db)
            logger.info("✅ All Instagram bots initialized successfully")
        except Exception as e:
            logger.error(f"❌ Error starting Instagram bots: {e}")
        
        # NEW: Telegram bot initialization
        try:
            telegram_manager = get_telegram_bot_manager()
            db = next(get_db())
            await telegram_manager.initialize_bots(db)
            logger.info("✅ All Telegram bots initialized successfully")
        except Exception as e:
            logger.error(f"❌ Error starting Telegram bots: {e}")
        
        # 2. Ensure all tenants have subscriptions (existing code remains the same)
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

# 4. UPDATE YOUR EXISTING shutdown_event FUNCTION:
# Replace your current shutdown_event with this updated version:

@app.on_event("shutdown")
async def shutdown_event():
    """Stop Discord, Slack, Instagram, and Telegram bots on application shutdown"""
    try:
        logger.info("🛑 Shutting down bot integrations...")
        
        # Stop Discord bots
        try:
            discord_manager = get_discord_bot_manager()
            await discord_manager.stop_all_bots()
            logger.info("✅ All Discord bots stopped successfully")
        except Exception as e:
            logger.error(f"❌ Error stopping Discord bots: {e}")
        
        # Stop Instagram bots
        try:
            instagram_manager = get_instagram_bot_manager()
            await instagram_manager.stop_all_bots()
            logger.info("✅ All Instagram bots stopped successfully")
        except Exception as e:
            logger.error(f"❌ Error stopping Instagram bots: {e}")
        
        # NEW: Stop Telegram bots
        try:
            telegram_manager = get_telegram_bot_manager()
            await telegram_manager.stop_all_bots()
            logger.info("✅ All Telegram bots stopped successfully")
        except Exception as e:
            logger.error(f"❌ Error stopping Telegram bots: {e}")
        
        # Slack bots are event-driven and don't need explicit stopping
        logger.info("✅ Slack bots shutdown completed")
        
        logger.info("🏁 Bot integration shutdown completed")
        
    except Exception as e:
        logger.error(f"💥 Error in shutdown event: {e}")





    
if __name__ == "__main__":
    # Enhanced environment check for security
    if settings.is_production():
        host = "127.0.0.1"  # More secure for production
        reload = False
        logger.info("🔒 Starting in production mode")
    elif settings.is_staging():
        host = "0.0.0.0"  # Allow external connections for staging
        reload = False  # No reload in staging
        logger.info("🧪 Starting in staging mode")
    else:
        host = "0.0.0.0"  # Allow external connections in development
        reload = True
        logger.info("🔧 Starting in development mode")
    
    uvicorn.run(
        "app.main:app", 
        host=host, 
        port=8000, 
        reload=reload,
        log_level="info"
    )