from fastapi import APIRouter, Depends, HTTPException, Header, BackgroundTasks, Request, Form
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from pydantic import BaseModel
from pydantic import EmailStr
from fastapi import Form
from pydantic import Field
import logging
import os
import uuid
import asyncio
from datetime import datetime
from svix import Webhook, WebhookVerificationError  # Add this import for Webhook and WebhookVerificationError
import random
import time
import re


from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
import json



from app.database import get_db
from app.chatbot.engine import ChatbotEngine

from app.chatbot.models import ChatSession, ChatMessage
from app.utils.language_service import language_service, SUPPORTED_LANGUAGES
from app.chatbot.memory import EnhancedChatbotMemory


from app.chatbot.smart_feedback import AdvancedSmartFeedbackManager, PendingFeedback, FeedbackWebhookHandler


# 🔥 PRICING INTEGRATION - ADD THESE IMPORTS
from app.pricing.integration_helpers import (
    check_conversation_limit_dependency,  # Changed from check_message_limit_dependency
    track_conversation_started,           # New function for conversation tracking
    track_message_sent                    # Updated function
)
from app.tenants.router import get_tenant_from_api_key

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="templates")

router = APIRouter()

# Pydantic models
class ChatRequest(BaseModel):
    message: str
    user_identifier: str

class ChatResponse(BaseModel):
    session_id: str
    response: str
    success: bool
    is_new_session: bool
    user_id: str  # 🆕 NEW
    auto_generated_user_id: bool = False  # 🆕 NEW

class ChatHistory(BaseModel):
    session_id: str
    messages: List[dict]


class SupportedLanguage(BaseModel):
    code: str
    name: str




class StreamingChatRequest(BaseModel):
    message: str
    user_identifier: str
    enable_streaming: bool = True

class ChatChunk(BaseModel):
    chunk: str
    is_complete: bool
    chunk_index: int
    total_delay: float

class PlatformChatRequest(BaseModel):
    message: str
    user_identifier: str
    platform: str = "web"
    platform_data: Optional[Dict] = None

class DiscordChatRequest(BaseModel):
    message: str
    discord_user_id: str
    channel_id: str
    guild_id: str


class SlackChatRequest(BaseModel):
    message: str
    slack_user_id: str
    channel_id: str
    team_id: str
    thread_ts: Optional[str] = None
    max_context: int = 50


class WhatsAppChatRequest(BaseModel):
    message: str
    phone_number: str

class WebChatRequest(BaseModel):
    message: str
    user_identifier: str
    session_token: Optional[str] = None



class SimpleChatRequest(BaseModel):
    message: str
    user_identifier: str
    max_context: int = 200  # How many previous messages to remember

class SimpleDiscordRequest(BaseModel):
    message: str
    discord_user_id: str
    channel_id: str
    guild_id: str
    max_context: int = 50


class SmartChatRequest(BaseModel):
    message: str
    user_identifier: str
    max_context: int = 200

class TenantFeedbackResponse(BaseModel):
    feedback_id: str
    response: str


class WebChatbotRequest(BaseModel):
    message: str
    user_identifier: str
    max_context: int = 20
    enable_streaming: bool = True


class ChatRequest(BaseModel):
    message: str
    user_identifier: str

class ChatResponse(BaseModel):
    session_id: str
    response: str
    success: bool
    is_new_session: bool

class ChatHistory(BaseModel):
    session_id: str
    messages: List[dict]

class SmartChatRequest(BaseModel):
    message: str
    user_identifier: str
    max_context: int = 200




def break_into_sentences(response: str) -> list:
    """Break response into natural sentences for streaming"""
    
    response = response.strip()
    
    # Split by sentence endings, keeping the punctuation
    sentence_pattern = r'(?<=[.!?])\s+(?=[A-Z])'
    sentences = re.split(sentence_pattern, response)
    
    clean_sentences = []
    for sentence in sentences:
        sentence = sentence.strip()
        if sentence and len(sentence) > 10:  # Only meaningful sentences
            # Ensure sentence ends with punctuation
            if not sentence.endswith(('.', '!', '?')):
                sentence += '.'
            clean_sentences.append(sentence)
    
    return clean_sentences if clean_sentences else [response]

def calculate_sentence_delay(sentence: str, is_last: bool = False) -> float:
    """Calculate realistic delay for typing a sentence"""
    
    # Base typing speed (characters per second)
    typing_speed = random.uniform(18, 30)
    typing_time = len(sentence) / typing_speed
    
    # Add thinking pause based on sentence complexity
    thinking_pause = 0
    
    # Longer pause for complex sentences
    if any(word in sentence.lower() for word in ['however', 'therefore', 'additionally', 'furthermore']):
        thinking_pause += random.uniform(0.5, 1.0)
    
    # Pause based on sentence ending
    if sentence.endswith('.'):
        end_pause = random.uniform(1.0, 2.0)
    elif sentence.endswith('!'):
        end_pause = random.uniform(0.8, 1.5)
    elif sentence.endswith('?'):
        end_pause = random.uniform(1.2, 2.2)
    else:
        end_pause = random.uniform(0.6, 1.0)
    
    # Longer pause for the last sentence
    if is_last:
        end_pause *= random.uniform(1.3, 1.8)
    
    total_delay = thinking_pause + end_pause
    
    # Add human variation
    total_delay *= random.uniform(0.8, 1.3)
    
    # Set bounds (1-6 seconds per sentence)
    return max(1.0, min(total_delay, 6.0))


# Chat endpoint - 🔥 MODIFIED WITH PRICING AND DEBUG LOGGING
@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, api_key: str = Header(..., alias="X-API-Key"), db: Session = Depends(get_db)):
    """
    Send a message to the chatbot and get a response - UPDATED for conversation-based pricing
    """
    try:
        # Debug - Log the API key being used
        logger.info(f"💬 Processing chat request with API key: {api_key[:10]}...")
        logger.info(f"📝 Message: {request.message[:50]}...")
        
        # 🔒 PRICING CHECK - Get tenant and check conversation limits (UPDATED)
        logger.info("🔍 Getting tenant from API key...")
        tenant = get_tenant_from_api_key(api_key, db)
        logger.info(f"✅ Found tenant: {tenant.name} (ID: {tenant.id})")
        
        logger.info("🚦 Checking conversation limits...")
        check_conversation_limit_dependency(tenant.id, db)  # UPDATED
        logger.info("✅ Conversation limit check passed")
        
        # Initialize chatbot engine
        logger.info("🤖 Initializing chatbot engine...")
        engine = ChatbotEngine(db)
        
        # Process message
        logger.info("⚡ Processing message with chatbot engine...")
        result = engine.process_message(api_key, request.message, request.user_identifier)
        
        if not result.get("success"):
            error_message = result.get("error", "Unknown error")
            logger.error(f"❌ Chatbot error: {error_message}")
            raise HTTPException(status_code=400, detail=error_message)
        
        # 📊 PRICING TRACK - Track conversation usage (UPDATED)
        logger.info("📊 Tracking conversation usage...")
        track_success = track_conversation_started(
            tenant_id=tenant.id,
            user_identifier=request.user_identifier,
            platform="web",
            db=db
        )
        logger.info(f"📈 Conversation tracking result: {track_success}")
        
        # Log the response for debugging
        logger.info(f"✅ Chat successful, response length: {len(result.get('response', ''))}")
        
        return result
    except HTTPException:
        # Re-raise HTTP exceptions (including pricing limit errors)
        logger.error("🚫 HTTP Exception occurred (conversation limit or other)")
        raise
    except Exception as e:
        logger.error(f"💥 Error in chat endpoint: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        # Return a more user-friendly error
        raise HTTPException(
            status_code=500, 
            detail="An internal server error occurred. Please try again later."
        )

# Get chat history
@router.get("/history/{session_id}", response_model=ChatHistory)
async def get_chat_history(session_id: str, api_key: str = Header(..., alias="X-API-Key"), db: Session = Depends(get_db)):
    """
    Get the chat history for a specific session
    """
    # Verify the API key and get tenant
    engine = ChatbotEngine(db)
    tenant = engine._get_tenant_by_api_key(api_key)
    if not tenant:
        raise HTTPException(status_code=403, detail="Invalid API key")
    
    # Get session
    session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if not session or session.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Get messages
    messages = db.query(ChatMessage).filter(ChatMessage.session_id == session.id).order_by(ChatMessage.created_at).all()
    
    return {
        "session_id": session_id,
        "messages": [
            {
                "content": msg.content,
                "is_from_user": msg.is_from_user,
                "created_at": msg.created_at.isoformat()
            }
            for msg in messages
        ]
    }

# End chat session
@router.post("/end-session")
async def end_chat_session(session_id: str, api_key: str = Header(..., alias="X-API-Key"), db: Session = Depends(get_db)):
    """
    End a chat session
    """
    # Verify the API key and get tenant
    engine = ChatbotEngine(db)
    tenant = engine._get_tenant_by_api_key(api_key)
    if not tenant:
        raise HTTPException(status_code=403, detail="Invalid API key")
    
    # Verify session belongs to tenant
    session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if not session or session.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # End session
    success = engine.end_session(session_id)
    
    if not success:
        raise HTTPException(status_code=400, detail="Failed to end session")
    
    return {"message": "Session ended successfully"}







# Add a simple test endpoint
@router.get("/ping")
async def ping():
    """
    Simple endpoint to test if the router is working
    """
    return {"message": "Chatbot router is working!"}




# 🔥 MODIFIED STREAMING ENDPOINT WITH PRICING AND DEBUG LOGGING
@router.post("/chat/delayed")
async def chat_with_simple_sentence_streaming(
    request: ChatRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Simplified streaming - Send JSON messages with realistic typing delays
    - Breaks response into sentences
    - Streams each sentence with a delay
    """
    
    async def stream_sentences():
        try:
            logger.info(f"🎬 Starting streaming chat for API key: {api_key[:10]}...")
            
            # 🔒 PRICING CHECK - Get tenant and check limits FIRST (UPDATED)
            logger.info("🔍 Getting tenant and checking limits for streaming...")
            tenant = get_tenant_from_api_key(api_key, db)
            check_conversation_limit_dependency(tenant.id, db)  # UPDATED
            logger.info(f"✅ Streaming limits OK for tenant: {tenant.name}")
            
            start_time = time.time()
            
            # ... existing delay calculation code ...
            
            # Get response
            logger.info("🤖 Getting response from chatbot engine...")
            engine = ChatbotEngine(db)
            result = engine.process_message(
                api_key=api_key,
                user_message=request.message,
                user_identifier=request.user_identifier
            )
            
            if not result.get("success"):
                logger.error(f"❌ Streaming chat failed: {result.get('error')}")
                yield f"{json.dumps({'type': 'error', 'error': result.get('error')})}\n"
                return
            
            logger.info("✅ Chatbot response received successfully")
            
            # 📊 PRICING TRACK - Track conversation usage (UPDATED)
            logger.info("📊 Tracking streaming conversation usage...")
            track_success = track_conversation_started(
                tenant_id=tenant.id,
                user_identifier=request.user_identifier,
                platform="web",
                db=db
            )
            logger.info(f"📈 Streaming conversation tracking result: {track_success}")
            
            # ... rest of streaming logic remains the same ...
            
        except HTTPException as e:
            # Handle conversation limit errors and other HTTP exceptions (UPDATED)
            logger.error(f"🚫 HTTP error in streaming: {e.detail}")
            yield f"{json.dumps({'type': 'error', 'error': e.detail, 'status_code': e.status_code})}\n"
        except Exception as e:
            logger.error(f"💥 Error in streaming: {str(e)}")
            yield f"{json.dumps({'type': 'error', 'error': str(e)})}\n"
    
    return StreamingResponse(
        stream_sentences(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )



# Fix the broken enhanced memory endpoint:

@router.post("/chat/with-handoff", response_model=ChatResponse)
async def chat_with_handoff_detection(
    request: ChatRequest, 
    api_key: str = Header(..., alias="X-API-Key"), 
    db: Session = Depends(get_db)
):
    """
    Enhanced chat endpoint that automatically detects handoff requests
    """
    try:
        # Check pricing limits first
        tenant = get_tenant_from_api_key(api_key, db)
        check_conversation_limit_dependency(tenant.id, db)
        
        # Initialize chatbot engine
        engine = ChatbotEngine(db)
        
        # Process with handoff detection
        result = engine.process_message_with_handoff_detection(
            api_key, request.message, request.user_identifier
        )
        
        if not result.get("success"):
            error_message = result.get("error", "Unknown error")
            raise HTTPException(status_code=400, detail=error_message)
        
        # Track message usage
        track_message_sent(tenant.id, db)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in handoff-enabled chat: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
    


@router.post("/chat/simple", response_model=ChatResponse)
async def chat_with_simple_memory(
    request: SimpleChatRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Simple chat endpoint with basic conversation memory
    - Remembers conversation within the same platform/session
    - No cross-platform complexity
    - Configurable context length
    """
    try:
        logger.info(f"🧠 Simple memory chat for: {request.user_identifier}")
        
        # Pricing check (UPDATED)
        tenant = get_tenant_from_api_key(api_key, db)
        check_conversation_limit_dependency(tenant.id, db)  # UPDATED
        
        # Initialize chatbot engine
        engine = ChatbotEngine(db)
        
        # Process with simple memory
        result = engine.process_message_simple_memory(
            api_key=api_key,
            user_message=request.message,
            user_identifier=request.user_identifier,
            platform="web",
            max_context=request.max_context
        )
        
        if not result.get("success"):
            error_message = result.get("error", "Unknown error")
            logger.error(f"❌ Simple memory chat error: {error_message}")
            raise HTTPException(status_code=400, detail=error_message)
        
        # Track conversation usage (UPDATED)
        track_conversation_started(
            tenant_id=tenant.id,
            user_identifier=request.user_identifier,
            platform="web",
            db=db
        )
        
        logger.info(f"✅ Simple memory chat successful - used {result.get('context_messages', 0)} context messages")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"💥 Error in simple memory chat: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
    



@router.post("/chat/discord/simple", response_model=ChatResponse)
async def discord_chat_simple(
    request: SimpleDiscordRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Simplified Discord chat endpoint with basic memory
    - Remembers Discord conversations for the same user
    - No cross-platform memory
    - Clean and simple
    """
    try:
        logger.info(f"🎮 Simple Discord chat for user: {request.discord_user_id}")
        
        # Pricing check (UPDATED)
        tenant = get_tenant_from_api_key(api_key, db)
        check_conversation_limit_dependency(tenant.id, db)  # UPDATED
        
        # Initialize chatbot engine
        engine = ChatbotEngine(db)
        
        # Process Discord message with simple memory
        result = engine.process_discord_message_simple(
            api_key=api_key,
            user_message=request.message,
            discord_user_id=request.discord_user_id,
            channel_id=request.channel_id,
            guild_id=request.guild_id,
            max_context=request.max_context
        )
        
        if not result.get("success"):
            error_message = result.get("error", "Unknown error")
            logger.error(f"❌ Simple Discord chat error: {error_message}")
            raise HTTPException(status_code=400, detail=error_message)
        
        # Track conversation usage (UPDATED)
        track_conversation_started(
            tenant_id=tenant.id,
            user_identifier=f"discord:{request.discord_user_id}",
            platform="discord",
            db=db
        )
        
        logger.info(f"✅ Simple Discord chat successful - remembered {result.get('context_messages', 0)} previous messages")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"💥 Error in simple Discord chat: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
    


@router.get("/memory/simple/stats/{user_identifier}")
async def get_simple_memory_stats(
    user_identifier: str,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Get simple memory statistics for a user - useful for debugging
    """
    try:
        engine = ChatbotEngine(db)
        result = engine.get_user_memory_stats(api_key, user_identifier)
        
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Unknown error"))
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting memory stats: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
    


@router.post("/memory/simple/cleanup")
async def cleanup_simple_memory(
    days_old: int = 90,  # More generous than the complex system
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Clean up old conversation sessions - simplified version
    """
    from app.chatbot.simple_memory import SimpleChatbotMemory
    
    engine = ChatbotEngine(db)
    tenant = engine._get_tenant_by_api_key(api_key)
    if not tenant:
        raise HTTPException(status_code=403, detail="Invalid API key")
    
    memory = SimpleChatbotMemory(db, tenant.id)
    cleaned_sessions = memory.cleanup_old_sessions(days_old)
    
    return {
        "message": f"Cleaned up {cleaned_sessions} old sessions",
        "days_old_threshold": days_old
    }



        



    e



@router.get("/analytics/conversations")
async def get_conversation_analytics(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db),
    days: int = 30
):
    """
    Get conversation analytics for tenant (Advanced Analytics feature)
    """
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        # Check if tenant has access to advanced analytics
        from app.pricing.integration_helpers import check_feature_access_dependency
        check_feature_access_dependency(tenant.id, "advanced_analytics", db)
        
        # Get conversation analytics
        from app.pricing.integration_helpers import get_conversation_analytics
        analytics = get_conversation_analytics(tenant.id, db, days)
        
        return {
            "success": True,
            "tenant_id": tenant.id,
            "analytics": analytics
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting conversation analytics: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")




@router.post("/conversation/end")
async def end_conversation(
    user_identifier: str,
    platform: str = "web",
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Manually end a conversation session
    """
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        from app.pricing.integration_helpers import end_conversation_session
        success = end_conversation_session(tenant.id, user_identifier, platform, db)
        
        return {
            "success": success,
            "message": "Conversation ended successfully" if success else "No active conversation found"
        }
        
    except Exception as e:
        logger.error(f"Error ending conversation: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")



@router.post("/chat/slack/simple", response_model=ChatResponse)
async def slack_chat_simple(
    request: SlackChatRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Slack chat endpoint similar to Discord simple
    - Remembers conversations per Slack channel
    - Supports thread awareness
    - Clean and simple like Discord endpoint
    """
    try:
        logger.info(f"💬 Slack chat for user: {request.slack_user_id} in channel: {request.channel_id}")
        
        # Pricing check
        tenant = get_tenant_from_api_key(api_key, db)
        check_conversation_limit_dependency(tenant.id, db)
        
        # Initialize chatbot engine
        engine = ChatbotEngine(db)
        
        # Process Slack message with simple memory
        result = engine.process_slack_message_simple_with_delay(
            api_key=api_key,
            user_message=request.message,
            slack_user_id=request.slack_user_id,
            channel_id=request.channel_id,
            team_id=request.team_id,
            max_context=request.max_context
        )
        
        if not result.get("success"):
            error_message = result.get("error", "Unknown error")
            logger.error(f"❌ Slack chat error: {error_message}")
            raise HTTPException(status_code=400, detail=error_message)
        
        # Track conversation usage
        track_conversation_started(
            tenant_id=tenant.id,
            user_identifier=f"slack:{request.slack_user_id}",
            platform="slack",
            db=db
        )
        
        logger.info(f"✅ Slack chat successful - channel: {request.channel_id}")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"💥 Error in Slack chat: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
    

@router.post("/chat/smart", response_model=ChatResponse)
async def chat_with_advanced_smart_feedback(
    request: SmartChatRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Advanced web chat endpoint with enhanced smart feedback system."""
    try:
        logger.info(f"🧠📧 Advanced smart feedback chat for: {request.user_identifier}")
        
        # 🆕 NEW: Auto-generate UUID if user_identifier is missing or looks temporary
        user_id = request.user_identifier
        auto_generated = False
        
        if not user_id or len(user_id) < 10 or user_id.startswith('temp_') or user_id.startswith('session_'):
            user_id = f"auto_{str(uuid.uuid4())}"
            auto_generated = True
            logger.info(f"🔄 Auto-generated UUID for user: {user_id}")
        else:
            logger.info(f"👤 Using provided user_identifier: {user_id}")
        
        tenant = get_tenant_from_api_key(api_key, db)
        check_conversation_limit_dependency(tenant.id, db)
        
        engine = ChatbotEngine(db)
        result = engine.process_web_message_with_advanced_feedback(
            api_key=api_key,
            user_message=request.message,
            user_identifier=user_id,  # 🆕 Use the processed user_id
            max_context=request.max_context
        )
        
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Unknown error"))
        
        track_conversation_started(
            tenant_id=tenant.id,
            user_identifier=user_id,  # 🆕 Use the processed user_id
            platform="web",
            db=db
        )
        
        logger.info("✅ Advanced smart feedback chat successful")
        
        # 🆕 NEW: Add the user_id to response so frontend can store it
        result["user_id"] = user_id
        result["auto_generated_user_id"] = auto_generated
        
        return result
        
    except HTTPException as e:
        logger.error(f"HTTP exception in smart chat: {e.detail}")
        raise
    except Exception as e:
        logger.error(f"💥 Error in advanced smart feedback chat: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
    

# Add webhook endpoint for processing email replies
@router.post("/webhook/email-reply")
async def handle_email_reply_webhook(request: Request, db: Session = Depends(get_db)):
    """Handle incoming events from Resend with Svix signature verification."""
    headers = request.headers
    try:
        payload = await request.body()
    except Exception as e:
        logger.error(f"Could not read request body: {e}")
        raise HTTPException(status_code=400, detail="Invalid request body")

    expected_secret = os.getenv("WEBHOOK_SECRET")
    if not expected_secret:
        logger.error("CRITICAL: WEBHOOK_SECRET environment variable not set.")
        raise HTTPException(status_code=500, detail="Webhook secret not configured on the server.")

    try:
        wh = Webhook(expected_secret)
        webhook_data = wh.verify(payload, headers)
        logger.info("✅ Webhook signature verified successfully.")
    except WebhookVerificationError as e:
        logger.warning(f"Webhook signature verification failed: {e}")
        raise HTTPException(status_code=403, detail="Invalid signature.")

    # Process only the inbound email event, ignore others like 'sent' or 'delivered'
    if webhook_data.get("type") == "inbound.email.created":
        try:
            logger.info(f"📨 Received verified inbound email: {webhook_data.get('data', {}).get('subject')}")
            # Logic to process the inbound email reply would go here if needed in the future.
            # For the form-based system, we can just acknowledge receipt.
            return {"success": True, "message": "Inbound email processed."}
        except Exception as e:
            logger.error(f"💥 Error processing inbound email: {e}")
            raise HTTPException(status_code=500, detail="Webhook processing failed")
    else:
        # Acknowledge other event types without processing them
        logger.info(f"Received and acknowledged non-critical webhook event: {webhook_data.get('type')}")
        return {"success": True, "message": f"Event '{webhook_data.get('type')}' acknowledged."}

# Enhanced feedback analytics endpoint
@router.get("/feedback/analytics")
async def get_advanced_feedback_analytics(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db),
    days: int = 30
):
    """
    Get comprehensive feedback analytics with real-time data
    """
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        # Initialize advanced feedback manager
        feedback_manager = AdvancedSmartFeedbackManager(db, tenant.id)
        
        # Get comprehensive analytics
        analytics = feedback_manager.get_feedback_analytics(days)
        
        return {
            "success": True,
            "tenant_id": tenant.id,
            "tenant_name": tenant.name,
            "analytics": analytics
        }
        
    except Exception as e:
        logger.error(f"Error getting advanced feedback analytics: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

# Enhanced pending feedback endpoint
@router.get("/feedback/pending/advanced")
async def get_advanced_pending_feedback(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db),
    limit: int = 20
):
    """
    Get enhanced list of pending feedback requests with tracking info
    """
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        feedback_manager = AdvancedSmartFeedbackManager(db, tenant.id)
        pending_requests = feedback_manager.get_pending_feedback_list(limit)
        
        return {
            "success": True,
            "pending_requests": pending_requests,
            "total_count": len(pending_requests),
            "tenant_id": tenant.id
        }
        
    except Exception as e:
        logger.error(f"Error getting advanced pending feedback: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

# Retry failed notification endpoint
@router.post("/feedback/retry/{feedback_id}")
async def retry_feedback_notification(
    feedback_id: str,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Retry sending tenant notification for failed feedback
    """
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        feedback_manager = AdvancedSmartFeedbackManager(db, tenant.id)
        success = feedback_manager.retry_failed_notification(feedback_id)
        
        if success:
            return {"success": True, "message": f"Notification retry successful for {feedback_id}"}
        else:
            return {"success": False, "message": f"Notification retry failed for {feedback_id}"}
        
    except Exception as e:
        logger.error(f"Error retrying feedback notification: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

# Test email endpoint for debugging
@router.post("/feedback/test-email")
async def test_feedback_email(
    test_email: str,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Test endpoint to send a sample feedback email (for debugging)
    """
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        feedback_manager = AdvancedSmartFeedbackManager(db, tenant.id)
        
        # Create test feedback request
        test_feedback_id = str(uuid.uuid4())
        test_context = [
            {"role": "user", "content": "Hello, I need help with my account"},
            {"role": "assistant", "content": "I'm sorry, I don't have information about account issues"}
        ]
        
        # Mock tenant object for testing
        class MockTenant:
            def __init__(self, email, name):
                self.email = email
                self.name = name
        
        mock_tenant = MockTenant(test_email, tenant.name)
        
        # Send test notification
        success, email_id = feedback_manager._send_tenant_notification_advanced(
            feedback_id=test_feedback_id,
            tenant=mock_tenant,
            user_question="Test question: How do I reset my password?",
            bot_response="I'm sorry, I don't have information about password reset procedures.",
            conversation_context=test_context,
            user_email="testuser@example.com"
        )
        
        if success:
            return {
                "success": True,
                "message": f"Test email sent successfully to {test_email}",
                "email_id": email_id,
                "feedback_id": test_feedback_id
            }
        else:
            return {
                "success": False,
                "message": f"Failed to send test email to {test_email}"
            }
        
    except Exception as e:
        logger.error(f"Error sending test email: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
    

    

@router.get("/feedback/form/{feedback_id}", response_class=HTMLResponse)
async def get_feedback_form(request: Request, feedback_id: str, db: Session = Depends(get_db)):
    """Serves the enhanced HTML form to the tenant with business info"""
    logger.info(f"Serving enhanced feedback form for ID: {feedback_id}")
    
    # Get feedback record to check status and get business info
    feedback_record = db.query(PendingFeedback).filter(
        PendingFeedback.feedback_id == feedback_id
    ).first()
    
    if not feedback_record:
        return HTMLResponse(content="""
            <div style='font-family: sans-serif; text-align: center; padding: 50px;'>
                <h1>Form Not Found</h1>
                <p>This feedback form does not exist or has been removed.</p>
            </div>
        """, status_code=404)
    
    # Check if form is already expired/submitted
    if feedback_record.form_expired or feedback_record.user_notified:
        return HTMLResponse(content="""
            <div style='font-family: sans-serif; text-align: center; padding: 50px;'>
                <h1>⏰ Form Expired</h1>
                <p>This feedback form has already been used or has expired for security reasons.</p>
                <p>If you need to provide additional feedback, please contact support.</p>
            </div>
        """, status_code=410)
    
    # Mark form as accessed
    if not feedback_record.form_accessed:
        feedback_record.form_accessed = True
        feedback_record.form_accessed_at = datetime.utcnow()
        db.commit()
    
    # Get business name
    tenant = db.query(Tenant).filter(Tenant.id == feedback_record.tenant_id).first()
    business_name = getattr(tenant, 'business_name', 'Your Business') if tenant else 'Your Business'
    
    # Read the enhanced template file
    try:
        with open("templates/enhanced_feedback_form.html", "r") as f:
            template_content = f.read()
        
        # Replace template variables
        template_content = template_content.replace("{{ feedback_id }}", feedback_id)
        template_content = template_content.replace("{{ business_name | default('Your Business') }}", business_name)
        template_content = template_content.replace("{{ user_question | default('') }}", feedback_record.user_question or "")
        
        return HTMLResponse(content=template_content)
        
    except FileNotFoundError:
        # Fallback to inline template if file not found
        logger.warning("Enhanced feedback form template file not found, using inline template")
        return templates.TemplateResponse(
            "feedback_form.html",  # Your existing template
            {
                "request": request, 
                "feedback_id": feedback_id,
                "business_name": business_name,
                "user_question": feedback_record.user_question
            }
        )

@router.post("/feedback/submit")
async def handle_enhanced_feedback_submission(
    feedback_id: str = Form(...),
    tenant_response: str = Form(...),
    add_to_faq: bool = Form(False),
    db: Session = Depends(get_db)
):
    """Enhanced feedback submission with simplified FAQ integration"""
    logger.info(f"Received enhanced feedback submission for ID: {feedback_id}")
    
    feedback_record = db.query(PendingFeedback).filter(
        PendingFeedback.feedback_id == feedback_id
    ).first()
    
    if not feedback_record:
        raise HTTPException(status_code=404, detail="Feedback ID not found.")
    
    # Check if already processed
    if feedback_record.form_expired or feedback_record.user_notified:
        return HTMLResponse(content="""
            <div style='font-family: sans-serif; text-align: center; padding: 50px;'>
                <h1>⏰ Form Already Processed</h1>
                <p>This feedback form has already been submitted.</p>
            </div>
        """, status_code=410)
    
    try:
        # Store the enhanced response data
        feedback_record.tenant_response = tenant_response.strip()
        feedback_record.add_to_faq = add_to_faq
        
        # If user wants to add to FAQ, use the original question and tenant response
        if add_to_faq:
            feedback_record.faq_question = feedback_record.user_question
            feedback_record.faq_answer = tenant_response.strip()
            
            # Create FAQ entry automatically
            try:
                new_faq = FAQ(
                    tenant_id=feedback_record.tenant_id,
                    question=feedback_record.user_question,
                    answer=tenant_response.strip()
                )
                db.add(new_faq)
                feedback_record.faq_created = True
                logger.info(f"✅ Created FAQ entry for feedback {feedback_id}")
            except Exception as faq_error:
                logger.error(f"❌ Failed to create FAQ: {faq_error}")
        
        # Mark form as expired to prevent reuse
        feedback_record.form_expired = True
        feedback_record.status = "responded"
        
        # Process the tenant response (send to customer)
        feedback_manager = AdvancedSmartFeedbackManager(db, feedback_record.tenant_id)
        success = feedback_manager.process_tenant_response(feedback_id, tenant_response)
        
        if success:
            db.commit()
            
            success_message = "Thank you! Your response has been sent to the customer."
            if feedback_record.faq_created:
                success_message += " The question and answer have also been added to your FAQ section."
            
            return HTMLResponse(content=f"""
                <div style='font-family: Inter, sans-serif; text-align: center; padding: 60px 40px; max-width: 600px; margin: 0 auto;'>
                    <div style='background: linear-gradient(135deg, #6B46C1, #9333EA); color: white; padding: 30px; border-radius: 20px; box-shadow: 0 20px 60px rgba(0,0,0,0.1);'>
                        <div style='font-size: 48px; margin-bottom: 20px;'>✅</div>
                        <h1 style='margin: 0 0 15px 0; font-size: 24px;'>Response Sent Successfully!</h1>
                        <p style='margin: 0; font-size: 16px; opacity: 0.9;'>{success_message}</p>
                        <div style='margin-top: 30px; padding-top: 20px; border-top: 1px solid rgba(255,255,255,0.2); font-size: 14px; opacity: 0.8;'>
                            This form has been securely closed and cannot be used again.
                        </div>
                    </div>
                </div>
            """, status_code=200)
        else:
            raise HTTPException(status_code=500, detail="Failed to process feedback.")
            
    except Exception as e:
        logger.error(f"Error processing enhanced feedback: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to process feedback.")
