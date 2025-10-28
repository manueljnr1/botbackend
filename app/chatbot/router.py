from fastapi import APIRouter, Depends, HTTPException, Header, BackgroundTasks, Request, Form
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from pydantic import EmailStr
from fastapi import Form, Request, Query
from pydantic import Field
import logging
import os
import uuid
from sqlalchemy.orm import aliased
from functools import lru_cache
import asyncio
from datetime import datetime
from svix import Webhook, WebhookVerificationError 
import random
import time
import re
from sqlalchemy import func, over
from sqlalchemy.orm import aliased
from app.config import settings
from datetime import datetime, timedelta

from fastapi.responses import Response, FileResponse



from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
import json
from app.database import get_db
from app.chatbot.engine import ChatbotEngine
from app.chatbot.models import ChatSession, ChatMessage
from app.knowledge_base.models import FAQ 
from app.chatbot.memory import EnhancedChatbotMemory
from app.tenants.models import Tenant
from app.chatbot.smart_feedback import AdvancedSmartFeedbackManager, PendingFeedback, FeedbackWebhookHandler
from app.chatbot.security import SecurityPromptManager
from app.chatbot.security import SecurityPromptManager, SecurityIncident
from app.chatbot.security import validate_and_sanitize_tenant_prompt
from app.live_chat.models import LiveChatConversation
from app.live_chat.queue_service import LiveChatQueueService
from app.chatbot.admin_router import router as admin_router
from app.chatbot.super_tenant_admin_engine import get_super_tenant_admin_engine
from app.tenants.models import Tenant
from sqlalchemy import func
from app.chatbot.unified_intelligent_engine import get_unified_intelligent_engine
from app.chatbot.email_scraper_engine import EmailScraperEngine, ScrapedEmail
from app.chatbot.escalation_engine import EscalationEngine


# 🔥 PRICING INTEGRATION - ADD THESE IMPORTS
from app.pricing.integration_helpers import (
    check_conversation_limit_dependency_with_super_tenant,
    check_integration_limit_dependency_with_super_tenant,
    track_conversation_started_with_super_tenant,  # ← ADD THIS LINE
    track_conversation_started,
    track_message_sent
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

class TenantPromptUpdate(BaseModel):
    system_prompt: str



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
    user_email: Optional[str] = None 
    user_name: Optional[str] = None

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



class ChatHistory(BaseModel):
    session_id: str
    messages: List[dict]

class SmartChatRequest(BaseModel):
    message: str
    user_identifier: str
    max_context: int = 200
    user_email: Optional[str] = None 
    user_name: Optional[str] = None


class DiscordSmartChatRequest(BaseModel):
    message: str
    discord_user_id: str
    channel_id: str
    guild_id: str
    max_context: int = 20

class SmartChatStreamingRequest(BaseModel):
    message: str
    user_identifier: str
    max_context: int = 20
    enable_streaming: bool = True

class IncidentReviewRequest(BaseModel):
    reviewer_notes: Optional[str] = None


class SecuritySettingsRequest(BaseModel):
    security_level: str = "standard"  # standard, strict, custom
    allow_custom_prompts: bool = True
    security_notifications_enabled: bool = True


def detect_handoff_triggers(user_message: str) -> bool:
    '''Detect if user message should trigger handoff to live chat'''
    handoff_triggers = [
        "speak to human", "talk to human", "human agent", "live agent",
        "customer service", "customer support", "speak to agent",
        "talk to agent", "live chat", "human help", "real person",
        "not helpful", "doesn't work", "frustrated", "urgent",
        "complaint", "billing issue", "refund", "cancel"
    ]
    
    message_lower = user_message.lower()
    return any(trigger in message_lower for trigger in handoff_triggers)


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





def should_generate_admin_followups_simple(user_question: str, bot_response: str, action: str = None) -> tuple[bool, List[str]]:
    """Fallback simple rules for admin follow-ups if LLM fails"""
    
    user_lower = user_question.lower()
    response_lower = bot_response.lower()
    
    # Skip for simple acknowledgments
    skip_patterns = ['hello', 'hi', 'hey', 'thanks', 'ok', 'okay']
    if any(pattern in user_lower for pattern in skip_patterns) and len(user_question) < 20:
        return False, []
    
    # Skip for very short responses
    if len(bot_response) < 100:
        return False, []
    
    # Generate based on action type
    if action and 'faq' in action.lower():
        return True, [
            "Would you like to add another FAQ?",
            "Want to see all your FAQs?"
        ]
    elif action and 'analytics' in action.lower():
        return True, [
            "Need analytics for a different time period?",
            "Want to see detailed conversation patterns?"
        ]
    elif action and 'settings' in action.lower():
        return True, [
            "Want to update other chatbot settings?",
            "Need help with branding customization?"
        ]
    elif len(bot_response) > 300:
        return True, [
            "Need clarification on any part?",
            "What else would you like to manage?"
        ]
    
    return False, []

def calculate_followup_delay(followup: str) -> float:
    """Calculate natural delay for follow-up questions"""
    import random
    base_delay = 1.2
    length_factor = min(len(followup) / 150, 1.0)
    variation = random.uniform(0.8, 1.2)
    return (base_delay + length_factor) * variation



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
        check_conversation_limit_dependency_with_super_tenant(tenant.id, db)  # UPDATED
        logger.info("✅ Conversation limit check passed")
        
        # Initialize chatbot engine
        logger.info("🤖 Initializing chatbot engine...")
        engine = ChatbotEngine(db)
        
        # Process message
        logger.info("⚡ Processing message with chatbot engine...")
        result = await engine.process_message(api_key, request.message, request.user_identifier)
        
        if not result.get("success"):
            error_message = result.get("error", "Unknown error")
            logger.error(f"❌ Chatbot error: {error_message}")
            raise HTTPException(status_code=400, detail=error_message)
        
        # 📊 PRICING TRACK - Track conversation usage (UPDATED)
        logger.info("📊 Tracking conversation usage...")
        track_success = track_conversation_started_with_super_tenant(
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





@router.get("/ping")
async def ping():
    """
    Simple endpoint to test if the router is working
    """
    return {"message": "Chatbot router is working!"}



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
            check_conversation_limit_dependency_with_super_tenant(tenant.id, db)  # UPDATED
            logger.info(f"✅ Streaming limits OK for tenant: {tenant.name}")
            
            start_time = time.time()
            
            # ... existing delay calculation code ...
            
            # Get response
            logger.info("🤖 Getting response from chatbot engine...")
            engine = ChatbotEngine(db)
            result = await engine.process_message(
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
            track_success = track_conversation_started_with_super_tenant(
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
        check_conversation_limit_dependency_with_super_tenant(tenant.id, db)
        
        # Initialize chatbot engine
        engine = ChatbotEngine(db)
        
        # Process with handoff detection
        result = await engine.process_message_with_handoff_detection(
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
        check_conversation_limit_dependency_with_super_tenant(tenant.id, db)  # UPDATED
        
        # Initialize chatbot engine
        engine = ChatbotEngine(db)
        
        # Process with simple memory
        result =await engine.process_message_simple_memory(
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
        track_conversation_started_with_super_tenant(
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
        check_conversation_limit_dependency_with_super_tenant(tenant.id, db)  # UPDATED
        
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
        track_conversation_started_with_super_tenant(
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
        check_conversation_limit_dependency_with_super_tenant(tenant.id, db)
        
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
        track_conversation_started_with_super_tenant(
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
    




@router.post("/chat/smart-streaming")
async def smart_chat_streaming_dedicated(
    request: SmartChatStreamingRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Dedicated streaming endpoint for smart feedback chat
    """
    # Call the regular smart chat endpoint instead
    return await smart_chat_with_followup_streaming(
        SmartChatRequest(
            message=request.message,
            user_identifier=request.user_identifier,
            max_context=request.max_context
        ),
        False,  # enable_streaming=False
        api_key,
        db
    )




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



@router.get("/tenant-info")
async def get_tenant_info_for_frontend(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Enhanced tenant info with full branding support"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        return {
            "success": True,
            "business_name": tenant.business_name,
            "tenant_id": tenant.id,
            # "chatbot_widget_icon": settings.CHATBOT_WIDGET_ICON_URL,
            "chatbot_widget_icon": "",
            "branding": {
                # Colors
                "primary_color": tenant.primary_color or "#007bff",
                "secondary_color": tenant.secondary_color or "#f0f4ff", 
                "text_color": tenant.text_color or "#222222",
                "background_color": tenant.background_color or "#ffffff",
                "user_bubble_color": tenant.user_bubble_color or "#007bff",
                "bot_bubble_color": tenant.bot_bubble_color or "#f0f4ff",
                "border_color": tenant.border_color or "#e0e0e0",
                
                # Logo
                "logo_image": tenant.logo_image_url,
                "logo_text": tenant.logo_text or (tenant.business_name or tenant.name)[:2].upper(),
                
                # Layout
                "border_radius": tenant.border_radius or "12px",
                "widget_position": tenant.widget_position or "bottom-right",
                "font_family": tenant.font_family or "Inter, sans-serif",
                
                # Custom CSS
                "custom_css": tenant.custom_css
            }
        }
    except Exception as e:
        # Fallback branding
        return {
            "success": False,
            "tenant_id": tenant.id,
            "business_name": "Chatbot",
            # "chatbot_widget_icon": settings.CHATBOT_WIDGET_ICON_URL,
            "chatbot_widget_icon": "",
            "branding": {
                "primary_color": "#007bff",
                "secondary_color": "#f0f4ff",
                "text_color": "#222222",
                "background_color": "#ffffff",
                "user_bubble_color": "#007bff", 
                "bot_bubble_color": "#f0f4ff",
                "border_color": "#e0e0e0",
                "logo_text": "AI",
                "border_radius": "12px",
                "widget_position": "bottom-right",
                "font_family": "Inter, sans-serif"
            }
        }




@router.get("/security/analytics")
async def get_security_analytics(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db),
    days: int = 30
):
    """Get comprehensive security analytics for the tenant"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        security_manager = SecurityPromptManager(db, tenant.id)
        analytics = security_manager.get_security_analytics(days)
        
        return analytics
        
    except Exception as e:
        logger.error(f"Error getting security analytics: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/security/incidents")
async def get_security_incidents(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db),
    limit: int = 50,
    reviewed: Optional[bool] = None
):
    """Get list of security incidents for the tenant"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        query = db.query(SecurityIncident).filter(
            SecurityIncident.tenant_id == tenant.id
        )
        
        if reviewed is not None:
            query = query.filter(SecurityIncident.reviewed == reviewed)
        
        incidents = query.order_by(
            SecurityIncident.detected_at.desc()
        ).limit(limit).all()
        
        incidents_data = []
        for incident in incidents:
            incidents_data.append({
                "id": incident.id,
                "user_identifier": incident.user_identifier,
                "platform": incident.platform,
                "risk_type": incident.risk_type,
                "severity_score": incident.severity_score,
                "detected_at": incident.detected_at.isoformat(),
                "reviewed": incident.reviewed,
                "user_message_preview": incident.user_message[:100] + "..." if len(incident.user_message) > 100 else incident.user_message
            })
        
        return {
            "success": True,
            "incidents": incidents_data,
            "total_count": len(incidents_data)
        }
        
    except Exception as e:
        logger.error(f"Error getting security incidents: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
    


@router.get("/security/incidents/{incident_id}")
async def get_security_incident_details(
    incident_id: int,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get detailed information about a specific security incident"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        security_manager = SecurityPromptManager(db, tenant.id)
        incident_details = security_manager.get_incident_details(incident_id)
        
        if not incident_details:
            raise HTTPException(status_code=404, detail="Security incident not found")
        
        return {
            "success": True,
            "incident": incident_details
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting incident details: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")



@router.post("/security/incidents/{incident_id}/review")
async def mark_incident_reviewed(
    incident_id: int,
    request: IncidentReviewRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Mark a security incident as reviewed"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        security_manager = SecurityPromptManager(db, tenant.id)
        success = security_manager.mark_incident_reviewed(
            incident_id, 
            request.reviewer_notes
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Security incident not found")
        
        return {
            "success": True,
            "message": f"Incident {incident_id} marked as reviewed"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking incident as reviewed: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/security/cleanup")
async def cleanup_old_security_incidents(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db),
    days_old: int = 90
):
    """Clean up old reviewed security incidents"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        security_manager = SecurityPromptManager(db, tenant.id)
        cleaned_count = security_manager.cleanup_old_incidents(days_old)
        
        return {
            "success": True,
            "message": f"Cleaned up {cleaned_count} old security incidents",
            "days_threshold": days_old
        }
        
    except Exception as e:
        logger.error(f"Error cleaning up security incidents: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")



@router.post("/security/settings")
async def update_security_settings(
    request: SecuritySettingsRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Update tenant security settings"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        # Validate security level
        valid_levels = ["standard", "strict", "custom"]
        if request.security_level not in valid_levels:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid security level. Must be one of: {valid_levels}"
            )
        
        # Update tenant security settings
        tenant.security_level = request.security_level
        tenant.allow_custom_prompts = request.allow_custom_prompts
        tenant.security_notifications_enabled = request.security_notifications_enabled
        
        db.commit()
        
        logger.info(f"Updated security settings for tenant {tenant.id}")
        
        return {
            "success": True,
            "message": "Security settings updated successfully",
            "settings": {
                "security_level": tenant.security_level,
                "allow_custom_prompts": tenant.allow_custom_prompts,
                "security_notifications_enabled": tenant.security_notifications_enabled
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating security settings: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/security/settings")
async def get_security_settings(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get current tenant security settings"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        return {
            "success": True,
            "settings": {
                "security_level": getattr(tenant, 'security_level', 'standard'),
                "allow_custom_prompts": getattr(tenant, 'allow_custom_prompts', True),
                "security_notifications_enabled": getattr(tenant, 'security_notifications_enabled', True),
                "system_prompt_configured": bool(getattr(tenant, 'system_prompt', None)),
                "system_prompt_validated": getattr(tenant, 'system_prompt_validated', False)
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting security settings: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
    



@router.post("/chat/with-handoff", response_model=ChatResponse)
async def chat_with_handoff_detection(
    request: ChatRequest, 
    api_key: str = Header(..., alias="X-API-Key"), 
    db: Session = Depends(get_db)
):
    '''Enhanced chat endpoint that detects handoff requests'''
    try:
        # Check pricing limits first
        tenant = get_tenant_from_api_key(api_key, db)
        check_conversation_limit_dependency_with_super_tenant(tenant.id, db)
        
        # Check for handoff triggers
        if detect_handoff_triggers(request.message):
            # Create live chat conversation
            live_conversation = LiveChatConversation(
                tenant_id=tenant.id,
                customer_identifier=request.user_identifier,
                handoff_reason="triggered",
                handoff_trigger=request.message,
                original_question=request.message,
                status="queued"
            )
            
            db.add(live_conversation)
            db.commit()
            db.refresh(live_conversation)
            
            # Add to queue
            queue_service = LiveChatQueueService(db)
            queue_result = queue_service.add_to_queue(
                conversation_id=live_conversation.id,
                priority=2,  # Higher priority for triggered handoffs
                assignment_criteria={"source": "chatbot_trigger", "trigger": request.message}
            )
            
            # Return handoff response
            return {
                "session_id": f"handoff_{live_conversation.id}",
                "response": "I understand you'd like to speak with a human agent. I'm connecting you to our support team now. Please wait a moment...",
                "success": True,
                "is_new_session": True,
                "handoff_triggered": True,
                "live_chat_conversation_id": live_conversation.id,
                "queue_position": queue_result.get("position"),
                "estimated_wait_time": queue_result.get("estimated_wait_time")
            }
        
        # Normal chatbot processing if no handoff triggered
        engine = ChatbotEngine(db)
        result = engine.process_message(api_key, request.message, request.user_identifier)
        
        if not result.get("success"):
            error_message = result.get("error", "Unknown error")
            raise HTTPException(status_code=400, detail=error_message)
        
        # Track message usage
        track_conversation_started_with_super_tenant(
            tenant_id=tenant.id,
            user_identifier=request.user_identifier,
            platform="web",
            db=db
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in handoff-enabled chat: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")





def break_formatted_response_smartly(response: str) -> List[str]:
    """
    Break response into chunks while PRESERVING formatting structure
    This is the key to maintaining formatting during streaming
    """
    import re
    
    # First, detect if response has formatting
    has_numbered_list = re.search(r'^\d+\.', response, re.MULTILINE)
    has_bullet_points = re.search(r'^[•\-\*]\s', response, re.MULTILINE) 
    has_headers = re.search(r'^#{1,3}\s', response, re.MULTILINE)
    has_steps = re.search(r'step\s+\d+', response, re.IGNORECASE)
    
    if has_numbered_list or has_bullet_points or has_headers or has_steps:
        return break_by_logical_sections(response)
    else:
        return break_by_sentences_with_context(response)

def break_by_logical_sections(response: str) -> List[str]:
    """
    Break formatted content by logical sections, not sentences
    This preserves the structure of lists, steps, etc.
    """
    chunks = []
    current_chunk = ""
    
    lines = response.split('\n')
    
    for i, line in enumerate(lines):
        line = line.strip()
        
        # Check if this line starts a new logical section
        is_new_section = (
            re.match(r'^Step \d+:', line, re.IGNORECASE) or           # Step headers
            re.match(r'^\d+\.', line) or                              # Numbered items  
            re.match(r'^#{1,3}\s', line) or                          # Headers
            re.match(r'^[•\-\*]\s', line) or                         # Bullet points
            re.match(r'^\*\*.*\*\*:?$', line) or                     # Bold headers
            (line.endswith(':') and len(line) < 50 and i < len(lines) - 1)  # Short lines ending with :
        )
        
        # If starting new section and we have content, yield current chunk
        if is_new_section and current_chunk.strip():
            chunks.append(current_chunk.strip())
            current_chunk = ""
        
        # Add line to current chunk
        if line:
            current_chunk += line + '\n'
        else:
            current_chunk += '\n'
        
        # For very long sections, break them up
        if len(current_chunk) > 300 and not is_new_section:
            # Look for good break points within the section
            sentences = re.split(r'(?<=[.!?])\s+', current_chunk)
            if len(sentences) > 1:
                # Keep first part, start new chunk with remainder
                break_point = len(sentences) // 2
                chunks.append(' '.join(sentences[:break_point]).strip())
                current_chunk = ' '.join(sentences[break_point:]) + '\n'
    
    # Add final chunk
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    return [chunk for chunk in chunks if chunk.strip()]

def break_by_sentences_with_context(response: str) -> List[str]:
    """
    For unformatted text, break by sentences but keep context
    """
    import re
    
    # Split into sentences but preserve some context
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', response)
    chunks = []
    
    i = 0
    while i < len(sentences):
        chunk = sentences[i]
        
        # If sentence is very short, combine with next
        if len(chunk) < 50 and i < len(sentences) - 1:
            chunk += ' ' + sentences[i + 1]
            i += 1
        
        chunks.append(chunk.strip())
        i += 1
    
    return chunks

def calculate_formatting_aware_delay(chunk: str) -> float:
    """
    Calculate delay based on chunk content and complexity
    Longer delays for headers, shorter for list items
    """
    import re
    
    base_delay = 0.8
    
    # Headers need more thinking time
    if re.match(r'^#{1,3}\s|^Step \d+:|^\*\*.*\*\*:?$', chunk):
        return base_delay + 1.5
    
    # List items are quicker
    if re.match(r'^\d+\.|^[•\-\*]\s', chunk):
        return base_delay + 0.5
    
    # Regular content - based on length
    length_factor = min(len(chunk) / 100, 2.0)
    return base_delay + length_factor





@router.post("/chat/smart/Legacy")
async def smart_chat_with_followup_streaming(
    request: SmartChatRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Smart chat with intelligent delay simulation + follow-up suggestions
    """
    
    async def stream_with_followups():
        try:
            logger.info(f"🚀 Smart chat with delay simulation for: {request.user_identifier}")
            
            # Get tenant and check limits
            tenant = get_tenant_from_api_key(api_key, db)
            check_conversation_limit_dependency_with_super_tenant(tenant.id, db)
            
            # Initialize chatbot engine
            engine = ChatbotEngine(db)
            
            # Auto-generate user ID if needed
            user_id = request.user_identifier
            auto_generated = False
            
            if not user_id or user_id.startswith('temp_') or user_id.startswith('session_'):
                user_id = f"auto_{str(uuid.uuid4())}"
                auto_generated = True
            
            # Send initial metadata
            yield f"{json.dumps({'type': 'metadata', 'user_id': user_id, 'auto_generated': auto_generated})}\n"
            
            # Get conversation history for context analysis
            from app.chatbot.simple_memory import SimpleChatbotMemory
            memory = SimpleChatbotMemory(db, tenant.id)
            conversation_history = memory.get_conversation_history(user_id, request.max_context)
            
            # Context analysis for greetings/special cases
            context_analysis = None
            topic_change_response = None

            if conversation_history and len(conversation_history) > 1:
                context_analysis = engine.analyze_conversation_context_llm(
                    request.message, 
                    conversation_history, 
                    tenant.name
                )
                
                logger.info(f"🧠 Context analysis: {context_analysis.get('type')} - {context_analysis.get('reasoning', 'N/A')}")
                
                special_handling_types = ['RECENT_GREETING', 'FRESH_GREETING', 'SIMPLE_GREETING', 'CONVERSATION_SUMMARY', 'CONVERSATION_SUMMARY_FALLBACK']
                
                if context_analysis and context_analysis.get('type') in special_handling_types:
                    topic_change_response = engine.handle_topic_change_response(
                        request.message,
                        context_analysis.get('previous_topic', ''),
                        context_analysis.get('suggested_approach', ''),
                        tenant.name,
                        context_analysis
                    )
            
            # ⭐ NEW: Initialize delay simulator
            delay_simulator = engine.delay_simulator
            
            # Handle greeting responses with delay
            if topic_change_response:
                logger.info(f"🔄 Sending greeting response with delay simulation")
                
                session_id, _ = memory.get_or_create_session(user_id, "web")
                memory.store_message(session_id, request.message, True)
                memory.store_message(session_id, topic_change_response, False)
                
                # ⭐ Calculate and apply delay for greeting
                if delay_simulator:
                    response_delay = delay_simulator.calculate_response_delay(request.message, topic_change_response)
                    logger.info(f"⏱️ Applying {response_delay:.2f}s delay for greeting")
                    await asyncio.sleep(response_delay)
                
                main_response = {
                    'type': 'main_response',
                    'content': topic_change_response,
                    'session_id': session_id,
                    'answered_by': 'GREETING_DETECTION',
                    'context_analysis': context_analysis,
                    'response_delay': response_delay if delay_simulator else 0
                }
                yield f"{json.dumps(main_response)}\n"
                
                # Follow-up with natural delay
                followup_delay = 2.0 + random.uniform(0.5, 1.5)  # 2-3.5s variation
                await asyncio.sleep(followup_delay)
                
                clarifying_followup = {
                    'type': 'followup',
                    'content': "What would you like help with?",
                    'index': 0,
                    'is_last': True
                }
                yield f"{json.dumps(clarifying_followup)}\n"
                
                yield f"{json.dumps({'type': 'complete', 'total_followups': 1, 'greeting_handled': True})}\n"
                
                track_conversation_started_with_super_tenant(
                    tenant_id=tenant.id,
                    user_identifier=user_id,
                    platform="web",
                    db=db
                )
                
                return
            
            # ⭐ ENHANCED: Process normal message with timing
            start_time = time.time()
            
            result = engine.process_web_message_with_advanced_feedback_llm(
                api_key=api_key,
                user_message=request.message,
                user_identifier=user_id,
                max_context=request.max_context,
                use_smart_llm=True
            )
            
            if not result.get("success"):
                logger.error(f"❌ Smart chat failed: {result.get('error')}")
                yield f"{json.dumps({'type': 'error', 'error': result.get('error')})}\n"
                return
            
            logger.info("✅ Chatbot response received successfully")
            
            # ⭐ Calculate intelligent delay based on question complexity and response
            response_delay = 0
            if delay_simulator:
                response_delay = delay_simulator.calculate_response_delay(request.message, result["response"])
                processing_time = time.time() - start_time
                
                # Subtract processing time from delay (don't double-delay)
                actual_delay = max(0.2, response_delay - processing_time)
                
                logger.info(f"⏱️ Calculated delay: {response_delay:.2f}s, Processing: {processing_time:.2f}s, Actual delay: {actual_delay:.2f}s")
                await asyncio.sleep(actual_delay)
            
            # Track conversation
            track_conversation_started_with_super_tenant(
                tenant_id=tenant.id,
                user_identifier=user_id,
                platform="web",
                db=db
            )
            
            # Send main response with delay info
            main_response = {
                'type': 'main_response',
                'content': result["response"],
                'session_id': result.get('session_id'),
                'answered_by': result.get('answered_by'),
                'email_captured': result.get('email_captured', False),
                'feedback_triggered': result.get('feedback_triggered', False),
                'context_analysis': context_analysis,
                'response_delay': response_delay if delay_simulator else 0,
                'total_processing_time': time.time() - start_time
            }
            yield f"{json.dumps(main_response)}\n"
            
            # ⭐ ENHANCED: Smart follow-up timing
            base_followup_delay = 1.8 + random.uniform(0.3, 0.9)  # 1.8-2.7s variation
            await asyncio.sleep(base_followup_delay)
            
            # Generate and stream follow-up suggestions
            should_generate, followups = should_generate_followups_llm(
                request.message, 
                result["response"], 
                tenant.name
            )
            
            if should_generate and followups:
                for i, followup in enumerate(followups):
                    if i > 0:
                        # ⭐ Natural delays between follow-ups
                        inter_followup_delay = 0.8 + random.uniform(0.2, 0.6)  # 0.8-1.4s
                        await asyncio.sleep(inter_followup_delay)
                    
                    followup_data = {
                        'type': 'followup',
                        'content': followup,
                        'index': i,
                        'is_last': i == len(followups) - 1
                    }
                    yield f"{json.dumps(followup_data)}\n"
            
            # Send completion signal
            yield f"{json.dumps({'type': 'complete', 'total_followups': len(followups) if followups else 0, 'delay_simulation': True})}\n"
            
            logger.info(f"✅ Smart chat with delays completed")
            
        except HTTPException as e:
            logger.error(f"🚫 HTTP error in smart chat: {e.detail}")
            yield f"{json.dumps({'type': 'error', 'error': e.detail, 'status_code': e.status_code})}\n"
        except Exception as e:
            logger.error(f"💥 Error in smart chat with delays: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            yield f"{json.dumps({'type': 'error', 'error': str(e)})}\n"
    
    return StreamingResponse(
        stream_with_followups(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )









def should_generate_followups_llm(user_question: str, bot_response: str, company_name: str) -> tuple[bool, List[str]]:
    """
    Use LLM to intelligently decide if follow-ups are needed and generate them
    Returns: (should_generate, followup_list)
    """
    from langchain_openai import ChatOpenAI
    from langchain.prompts import PromptTemplate
    
    prompt = PromptTemplate(
        input_variables=["user_question", "bot_response", "company_name"],
        template="""You are an expert conversation analyst. Analyze this customer service interaction and decide if follow-up questions would be helpful.

USER QUESTION: "{user_question}"

BOT RESPONSE: "{bot_response}"

COMPANY: {company_name}

INSTRUCTIONS:
1. Determine if follow-up questions would genuinely help the user
2. If YES, suggest 1-3 relevant follow-up questions
3. If NO, respond with "NO_FOLLOWUPS"

DON'T generate follow-ups for:
- Simple greetings or thank you messages
- Basic contact information requests  
- Very short/complete answers
- Questions already fully answered

DO generate follow-ups for:
- Setup/configuration instructions
- Complex procedures with multiple steps
- Feature explanations that might need clarification
- When user might need deeper help

Format response as:
DECISION: YES/NO
FOLLOWUPS:
1. First follow-up question (if any)
2. Second follow-up question (if any)  
3. Third follow-up question (if any)

Response:"""
    )
    
    try:
        llm = ChatOpenAI(
            model_name="gpt-3.5-turbo", 
            temperature=0.3,
            openai_api_key=settings.OPENAI_API_KEY
        )
        
        result = llm.invoke(prompt.format(
            user_question=user_question,
            bot_response=bot_response,
            company_name=company_name
        ))
        
        response_text = result.content if hasattr(result, 'content') else str(result)
        
        # Parse LLM response
        if "DECISION: NO" in response_text or "NO_FOLLOWUPS" in response_text:
            logger.info(f"🤖 LLM decided NO follow-ups needed for: {user_question[:50]}...")
            return False, []
        
        # Extract follow-up questions
        followups = []
        lines = response_text.split('\n')
        for line in lines:
            if re.match(r'^\d+\.', line.strip()):
                followup = re.sub(r'^\d+\.\s*', '', line.strip())
                if followup:
                    followups.append(followup)
        
        if followups:
            logger.info(f"🤖 LLM generated {len(followups)} follow-ups for: {user_question[:50]}...")
            return True, followups[:3]  # Max 3
        else:
            logger.info(f"🤖 LLM decided NO follow-ups needed")
            return False, []
            
    except Exception as e:
        logger.error(f"Error in LLM follow-up generation: {e}")
        # Fallback to simple rules
        return should_generate_followups_simple(user_question, bot_response)

def should_generate_followups_simple(user_question: str, bot_response: str) -> tuple[bool, List[str]]:
    """Fallback simple rules if LLM fails"""
    
    # Skip follow-ups for simple cases
    user_lower = user_question.lower()
    response_lower = bot_response.lower()
    
    # Don't generate for simple requests
    skip_patterns = [
        'hello', 'hi', 'hey', 'thanks', 'thank you',
        'what is your email', 'contact', 'phone number',
        'business hours', 'when are you open'
    ]
    
    if any(pattern in user_lower for pattern in skip_patterns):
        return False, []
    
    # Don't generate for very short responses
    if len(bot_response) < 100:
        return False, []
    
    # Generate for complex responses
    if len(bot_response) > 300 or 'step' in response_lower:
        return True, [
            "Would you like me to explain any part in more detail?",
            f"Any other questions about this process?"
        ]
    
    return False, []

def calculate_followup_delay(followup: str) -> float:
    """
    Calculate natural delay for follow-up questions
    Shorter delays for follow-ups to feel conversational
    """
    base_delay = 1.2  # Slightly faster than main content
    
    # Longer questions need slightly more time
    length_factor = min(len(followup) / 150, 1.0)
    
    # Add some natural variation
    import random
    variation = random.uniform(0.8, 1.2)
    
    return (base_delay + length_factor) * variation





@router.get("/admin-help")
async def get_admin_help(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Get comprehensive admin help and available commands
    """
    try:
        # 🔒 Validate authentication
        tenant = get_tenant_from_api_key(api_key, db)
        
        from app.chatbot.admin_intent_parser import AdminIntentParser
        parser = AdminIntentParser()
        
        return {
            "success": True,
            "tenant_id": tenant.id,
            "tenant_name": tenant.name,
            "help_text": parser.get_help_text(),
            "admin_features": {
                "natural_language": True,
                "faq_management": True,
                "analytics": True,
                "settings": True,
                "confirmations": True
            },
            "example_conversations": [
                {
                    "user": "Add FAQ: What are your business hours?",
                    "bot": "Great! I have the question: 'What are your business hours?' What should the answer be?"
                },
                {
                    "user": "Show my analytics",
                    "bot": "📊 Analytics for YourBusiness\n• FAQs: 15\n• Chat Sessions (30 days): 234\n• Messages: 1,456"
                },
                {
                    "user": "Delete FAQ #5",
                    "bot": "⚠️ Are you sure you want to delete FAQ #5? Type 'yes' to confirm or 'no' to cancel."
                }
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting admin help: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get admin help")

# Include the admin router in your main router
# Add this to the bottom of your router.py file:
router.include_router(admin_router, prefix="/admin-enhanced", tags=["Enhanced Admin Chat"])

# Add this endpoint to check if user is in admin mode
@router.get("/is-admin-context")
async def check_admin_context(
    api_key: str = Header(..., alias="X-API-Key"),
    is_super_tenant_chat: bool = False,  # This would come from frontend context
    db: Session = Depends(get_db)
):
    """
    Check if current context supports admin operations
    Frontend should call this when user is on super tenant's chat widget
    """
    try:
        # 🔒 Validate authentication
        tenant = get_tenant_from_api_key(api_key, db)
        
        # In a real implementation, you'd check:
        # 1. Is user authenticated?
        # 2. Are they on the super tenant's website/chat?
        # 3. Is this the official super tenant chatbot?
        
        admin_available = (
            tenant.is_active and 
            is_super_tenant_chat  # This indicates they're using super tenant's chat
        )
        
        return {
            "success": True,
            "tenant_id": tenant.id,
            "tenant_name": tenant.name,
            "admin_mode_available": admin_available,
            "is_authenticated": True,
            "is_super_tenant_context": is_super_tenant_chat,
            "admin_capabilities": {
                "faq_management": admin_available,
                "settings_update": admin_available,
                "analytics_view": admin_available,
                "branding_update": admin_available
            } if admin_available else {}
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking admin context: {str(e)}")
        return {
            "success": False,
            "admin_mode_available": False,
            "error": "Failed to check admin context"
        }





@router.post("/chat/super-tenant-admin")
async def super_tenant_admin_chat(
    request: SmartChatRequest,
    http_request: Request,
    tenant_api_key: str = Header(..., alias="X-Tenant-API-Key"),
    chatbot_api_key: str = Header(..., alias="X-Chatbot-API-Key"),
    super_tenant_context: str = Header(None, alias="X-Super-Tenant-Context"),
    db: Session = Depends(get_db)
):
    """
    Super Tenant Admin Chat with Unified Engine Integration + Intelligent Delay Simulation
    Now with 80% token efficiency for conversational queries
    """
    
    async def stream_admin_response():
        try:
            logger.info(f"🤖 Enhanced admin chat with unified engine: {request.message[:50]}...")
            
            # Security validation
            if super_tenant_context != "super_tenant_official_widget":
                logger.warning(f"🚨 Unauthorized admin access attempt")
                yield f"{json.dumps({'type': 'error', 'error': 'Admin features not available in this context', 'status_code': 403})}\n"
                return
            
            # Validate chatbot owner is super tenant
            try:
                chatbot_owner = get_tenant_from_api_key(chatbot_api_key, db)
                SUPER_TENANT_IDS = [324112833]
                
                if not getattr(chatbot_owner, 'is_super_tenant', False) and chatbot_owner.id not in SUPER_TENANT_IDS:
                    logger.warning(f"🚨 Unauthorized super tenant access: {chatbot_owner.id}")
                    yield f"{json.dumps({'type': 'error', 'error': 'Unauthorized chatbot host', 'status_code': 403})}\n"
                    return
                    
            except Exception as e:
                logger.error(f"❌ Invalid chatbot API key: {str(e)}")
                yield f"{json.dumps({'type': 'error', 'error': 'Invalid chatbot credentials', 'status_code': 403})}\n"
                return
            
            # Authenticate admin tenant
            try:
                tenant = get_tenant_from_api_key(tenant_api_key, db)
                check_conversation_limit_dependency_with_super_tenant(tenant.id, db)
                
                if not tenant.is_active:
                    yield f"{json.dumps({'type': 'error', 'error': 'Account inactive', 'status_code': 403})}\n"
                    return
                    
            except Exception as e:
                logger.error(f"❌ Tenant authentication failed: {str(e)}")
                yield f"{json.dumps({'type': 'error', 'error': 'Authentication failed', 'status_code': 403})}\n"
                return
            
            # Auto-generate user ID
            user_id = request.user_identifier
            auto_generated = False
            
            if not user_id or user_id.startswith('temp_') or user_id.startswith('session_'):
                user_id = f"admin_auto_{str(uuid.uuid4())}"
                auto_generated = True
            
            # Send metadata
            yield f"{json.dumps({'type': 'metadata', 'user_id': user_id, 'auto_generated': auto_generated, 'admin_mode': True, 'tenant_id': tenant.id, 'super_tenant_name': chatbot_owner.name, 'unified_engine_enabled': True})}\n"
            
            # Initialize memory and context analysis
            from app.chatbot.simple_memory import SimpleChatbotMemory
            memory = SimpleChatbotMemory(db, tenant.id)
            conversation_history = memory.get_conversation_history(user_id, request.max_context)
            
            # ⭐ KEEP: Initialize delay simulator for admin
            engine = ChatbotEngine(db)
            delay_simulator = engine.delay_simulator
            
            # Context analysis for admin conversations
            context_analysis = None
            topic_change_response = None
            
            if conversation_history and len(conversation_history) > 1:
                context_analysis = engine.analyze_conversation_context_llm(
                    request.message, 
                    conversation_history, 
                    tenant.name
                )
                
                logger.info(f"🧠 Admin context analysis: {context_analysis.get('type')} - {context_analysis.get('reasoning', 'N/A')}")
                
                special_handling_types = ['RECENT_GREETING', 'FRESH_GREETING', 'SIMPLE_GREETING', 'CONVERSATION_SUMMARY', 'CONVERSATION_SUMMARY_FALLBACK']
                
                if context_analysis and context_analysis.get('type') in special_handling_types:
                    topic_change_response = engine.handle_topic_change_response(
                        request.message,
                        context_analysis.get('previous_topic', ''),
                        context_analysis.get('suggested_approach', ''),
                        tenant.name,
                        context_analysis
                    )
            
            # Handle admin greeting with delay
            if topic_change_response:
                logger.info(f"🔄 Sending admin greeting response with delay")
                
                session_id, _ = memory.get_or_create_session(user_id, "admin_web")
                memory.store_message(session_id, request.message, True)
                memory.store_message(session_id, topic_change_response, False)
                
                # ⭐ Calculate delay for admin greeting
                if delay_simulator:
                    response_delay = delay_simulator.calculate_response_delay(request.message, topic_change_response)
                    logger.info(f"⏱️ Admin greeting delay: {response_delay:.2f}s")
                    await asyncio.sleep(response_delay)
                
                main_response = {
                    'type': 'main_response',
                    'content': topic_change_response,
                    'session_id': session_id,
                    'answered_by': 'ADMIN_GREETING_DETECTION',
                    'context_analysis': context_analysis,
                    'admin_mode': True,
                    'tenant_id': tenant.id,
                    'response_delay': response_delay if delay_simulator else 0,
                    'unified_engine_enhanced': True
                }
                yield f"{json.dumps(main_response)}\n"
                
                # Natural follow-up delay for admin
                followup_delay = 2.2 + random.uniform(0.3, 0.8)
                await asyncio.sleep(followup_delay)
                
                clarifying_followup = {
                    'type': 'followup',
                    'content': "What would you like help with?",
                    'index': 0,
                    'is_last': True
                }
                yield f"{json.dumps(clarifying_followup)}\n"
                
                yield f"{json.dumps({'type': 'complete', 'total_followups': 1, 'admin_greeting_handled': True, 'unified_engine': True})}\n"
                
                track_conversation_started_with_super_tenant(
                    tenant_id=tenant.id,
                    user_identifier=user_id,
                    platform="admin_web",
                    db=db
                )
                
                return
            
            # ⭐ ENHANCED: Process admin message with unified engine integration
            start_time = time.time()
            
            # 🆕 Use enhanced admin engine with unified integration
            admin_engine = get_super_tenant_admin_engine(db)
            
            result = await admin_engine.process_admin_message(
                user_message=request.message,
                authenticated_tenant_id=tenant.id,
                user_identifier=user_id,
                session_context={
                    "admin_mode": True,
                    "super_tenant_hosted": True,
                    "chatbot_owner_id": chatbot_owner.id,
                    "unified_engine_available": True
                }
            )
            
            if not result.get("success"):
                logger.error(f"❌ Enhanced admin engine failed: {result.get('error')}")
                yield f"{json.dumps({'type': 'error', 'error': result.get('error')})}\n"
                return
            
            session_id, _ = memory.get_or_create_session(user_id, "admin_web")
            
            # ⭐ Calculate admin-specific delay with unified engine considerations
            response_delay = 0
            if delay_simulator:
                base_delay = delay_simulator.calculate_response_delay(request.message, result["response"])
                
                # Adjust delay based on processing method
                processing_method = result.get("processing_method", "admin_engine")
                if processing_method == "unified_engine":
                    # Unified engine responses are more natural, slightly reduce delay
                    admin_complexity_bonus = 0.1
                else:
                    # Traditional admin responses, normal delay bonus
                    admin_complexity_bonus = 0.3
                
                response_delay = min(5.0, base_delay + admin_complexity_bonus)
                processing_time = time.time() - start_time
                actual_delay = max(0.3, response_delay - processing_time)
                
                logger.info(f"⏱️ Admin delay: {response_delay:.2f}s, Processing: {processing_time:.2f}s, Method: {processing_method}, Actual: {actual_delay:.2f}s")
                await asyncio.sleep(actual_delay)
            
            main_response = {
                'type': 'main_response',
                'content': result.get("response", ""),
                'session_id': session_id,
                'answered_by': result.get("action", "ENHANCED_ADMIN_ENGINE"),
                'processing_method': result.get("processing_method", "admin_engine"),
                'token_efficiency': result.get("token_efficiency"),
                'action': result.get('action'),
                'requires_confirmation': result.get('requires_confirmation', False),
                'requires_input': result.get('requires_input', False),
                'admin_mode': True,
                'tenant_id': tenant.id,
                'context_analysis': context_analysis,
                'response_delay': response_delay,
                'unified_engine_enhanced': True
            }
            
            yield f"{json.dumps(main_response)}\n"
            
            # Track conversation
            track_conversation_started_with_super_tenant(
                tenant_id=tenant.id,
                user_identifier=user_id,
                platform="admin_web",
                db=db
            )
            
            # ⭐ ENHANCED: Admin follow-up timing with unified engine awareness
            base_admin_delay = 2.0 + random.uniform(0.4, 1.0)
            await asyncio.sleep(base_admin_delay)
            
            # Generate intelligent follow-ups
            should_generate, followups = should_generate_followups_llm(
                request.message, 
                main_response['content'], 
                tenant.name
            )
            
            # If no regular follow-ups, generate admin-specific ones
            if not (should_generate and followups):
                admin_followups = await generate_admin_followups_llm(
                    request.message,
                    main_response['content'],
                    tenant,
                    {"processing_method": result.get("processing_method")}
                )
                followups = admin_followups
                should_generate = bool(followups)
            
            # Stream follow-ups with admin timing
            if should_generate and followups:
                for i, followup in enumerate(followups):
                    if i > 0:
                        inter_delay = 1.0 + random.uniform(0.2, 0.6)
                        await asyncio.sleep(inter_delay)
                    
                    followup_data = {
                        'type': 'followup',
                        'content': followup,
                        'index': i,
                        'is_last': i == len(followups) - 1,
                        'admin_followup': True,
                        'unified_engine_enhanced': True
                    }
                    yield f"{json.dumps(followup_data)}\n"
            
            # Send completion
            yield f"{json.dumps({
                'type': 'complete', 
                'total_followups': len(followups) if followups else 0, 
                'admin_enhanced': True, 
                'delay_simulation': True,
                'unified_engine_integration': True,
                'token_efficiency': result.get("token_efficiency", "Standard admin processing"),
                'processing_method': result.get("processing_method", "admin_engine")
            })}\n"
            
        except HTTPException as e:
            logger.error(f"🚫 HTTP error: {e.detail}")
            yield f"{json.dumps({'type': 'error', 'error': e.detail, 'status_code': e.status_code})}\n"
        except Exception as e:
            logger.error(f"💥 Error: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            yield f"{json.dumps({'type': 'error', 'error': str(e)})}\n"
    
    return StreamingResponse(
        stream_admin_response(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )




# **NEW LLM FUNCTIONS FOR ADMIN INTELLIGENCE**

# Import LLM availability check
try:
    from langchain_openai import ChatOpenAI
    from langchain.prompts import PromptTemplate
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False

async def analyze_admin_message_with_llm(
    user_message: str, 
    conversation_history: List[Dict], 
    tenant: Tenant,
    chatbot_owner: Tenant
) -> Dict[str, Any]:
    """
    LLM analysis to determine admin context and routing
    """
    try:
        if not LLM_AVAILABLE:
            return {"requires_admin_engine": True, "type": "fallback"}
        
        # Build context
        history_text = ""
        if conversation_history:
            recent_messages = conversation_history[-5:]
            for msg in recent_messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")[:100]
                history_text += f"{role}: {content}\n"
        
        llm = ChatOpenAI(
            model_name="gpt-3.5-turbo",
            temperature=0.3,
            openai_api_key=settings.OPENAI_API_KEY
        )
        
        prompt = PromptTemplate(
            input_variables=["user_message", "conversation_history", "tenant_name", "super_tenant_name"],
            template="""You are analyzing an admin message to determine the best routing and response approach.

CONTEXT:
- User: Business owner managing their chatbot
- Tenant: {tenant_name}
- Super Tenant: {super_tenant_name}
- Platform: Admin dashboard

USER MESSAGE: "{user_message}"

CONVERSATION HISTORY:
{conversation_history}

ADMIN CAPABILITIES:
- FAQ management (create, update, delete, list)
- Analytics viewing
- Settings updates
- Integration management
- General business guidance

TASK: Analyze and determine:
1. Is this a SPECIFIC EXECUTABLE COMMAND with complete data OR just a help request/question?
2. Does the user provide actual data to execute an action?
3. What type of response approach would be most helpful?

CRITICAL DISTINCTIONS:
- "can you help me add faq?" = HELP REQUEST (requires_admin_engine: false)
- "add FAQ: What are your hours? Answer: 9-5 weekdays" = EXECUTABLE COMMAND (requires_admin_engine: true)
- "show my analytics" = EXECUTABLE COMMAND (requires_admin_engine: true)
- "how do I create an FAQ?" = HELP REQUEST (requires_admin_engine: false)
- "what can you do?" = HELP REQUEST (requires_admin_engine: false)

RESPONSE FORMAT (JSON):
{{
    "requires_admin_engine": true/false,
    "interaction_type": "executable_command|help_request|greeting|question",
    "admin_domain": "faq|analytics|settings|integrations|general",
    "has_complete_data": true/false,
    "user_intent_confidence": 0.95,
    "reasoning": "explanation of analysis"
}}

Use admin_engine ONLY for executable commands with complete data.
Use conversational_llm for help requests, questions, and guidance.

JSON Response:"""
        )
        
        response = llm.invoke(prompt.format(
            user_message=user_message,
            conversation_history=history_text,
            tenant_name=tenant.name,
            super_tenant_name=chatbot_owner.name
        ))
        
        response_text = response.content if hasattr(response, 'content') else str(response)
        
        import json
        import re
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            analysis = json.loads(json_match.group())
            logger.info(f"🧠 Admin LLM analysis: {analysis.get('interaction_type')} - {analysis.get('reasoning', '')[:50]}...")
            return analysis
        
    except Exception as e:
        logger.error(f"Error in admin LLM analysis: {e}")
    
    # Fallback
    return {"requires_admin_engine": True, "type": "fallback"}

async def generate_admin_followups_llm(
    user_message: str,
    assistant_response: str,
    tenant: Tenant,
    context_analysis: Dict[str, Any]
) -> List[str]:
    """
    Generate intelligent admin follow-ups using LLM
    """
    try:
        if not LLM_AVAILABLE:
            return []
        
        llm = ChatOpenAI(
            model_name="gpt-3.5-turbo",
            temperature=0.4,
            openai_api_key=settings.OPENAI_API_KEY
        )
        
        prompt = PromptTemplate(
            input_variables=["user_message", "assistant_response", "tenant_name", "interaction_type"],
            template="""Generate helpful follow-up suggestions for an admin conversation.

USER MESSAGE: "{user_message}"
ASSISTANT RESPONSE: "{assistant_response}"
BUSINESS: {tenant_name}
INTERACTION TYPE: {interaction_type}

TASK: Generate 2-3 natural follow-up suggestions that would genuinely help the business owner continue their admin work.

GUIDELINES:
- Make suggestions specific and actionable
- Consider what they might logically want to do next
- Keep suggestions conversational, not robotic
- Focus on business value
- Avoid obvious or redundant suggestions

EXAMPLES:
- "Want to see how your recent changes are performing?"
- "Need help setting up Discord for your community?"
- "Should we optimize your top-performing FAQs?"

Generate 2-3 relevant follow-ups as a JSON array:
["suggestion1", "suggestion2", "suggestion3"]

JSON Response:"""
        )
        
        response = llm.invoke(prompt.format(
            user_message=user_message,
            assistant_response=assistant_response,
            tenant_name=tenant.business_name or tenant.name,
            interaction_type=context_analysis.get('interaction_type', 'general')
        ))
        
        response_text = response.content if hasattr(response, 'content') else str(response)
        
        import json
        import re
        json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if json_match:
            followups = json.loads(json_match.group())
            logger.info(f"🔄 Generated {len(followups)} admin follow-ups")
            return followups[:3]  # Max 3
        
    except Exception as e:
        logger.error(f"Error generating admin follow-ups: {e}")
    
    return []





@router.post("/chat/Base-base")
async def smart_chat_with_followup_streaming(
    request: SmartChatRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Smart chat with unified intelligent engine + streaming
    """
    
    async def stream_with_followups():
        try:
            logger.info(f"🚀 Unified smart chat for: {request.user_identifier}")
            
            # Get tenant and check limits
            tenant = get_tenant_from_api_key(api_key, db)
            check_conversation_limit_dependency_with_super_tenant(tenant.id, db)
            
            # ⭐ NEW: Initialize unified intelligent engine
            engine = get_unified_intelligent_engine(db)
            
            # Auto-generate user ID if needed
            user_id = request.user_identifier
            auto_generated = False
            
            if not user_id or user_id.startswith('temp_') or user_id.startswith('session_'):
                user_id = f"auto_{str(uuid.uuid4())}"
                auto_generated = True
            
            # Send initial metadata
            yield f"{json.dumps({'type': 'metadata', 'user_id': user_id, 'auto_generated': auto_generated, 'engine': 'unified_intelligent'})}\n"
            
            # ⭐ SIMPLIFIED: Process with unified engine (single call)
            start_time = time.time()
            
            result = await engine.process_message(
                api_key=api_key,
                user_message=request.message,
                user_identifier=user_id,
                platform="web"
            )
            
            if not result.get("success"):
                logger.error(f"❌ Unified smart chat failed: {result.get('error')}")
                yield f"{json.dumps({'type': 'error', 'error': result.get('error')})}\n"
                return
            
            logger.info("✅ Unified engine response received successfully")
            
            # ⭐ INTELLIGENT DELAY: Based on response complexity
            response_delay = 0
            processing_time = time.time() - start_time
            
            # Simple delay calculation based on response length and intent
            response_length = len(result.get("response", ""))
            intent = result.get("intent", "general")
            
            # Base delay calculation
            if intent == "casual":
                base_delay = 0.5 + (response_length / 200)  # Quick for casual
            elif intent in ["functional", "support"]:
                base_delay = 1.0 + (response_length / 150)  # Thoughtful for complex
            else:
                base_delay = 0.8 + (response_length / 180)  # Standard
            
            # Add some natural variation
            import random
            actual_delay = max(0.3, (base_delay * random.uniform(0.8, 1.2)) - processing_time)
            
            logger.info(f"⏱️ Calculated delay: {actual_delay:.2f}s for {intent} intent")
            await asyncio.sleep(actual_delay)
            
            # Track conversation
            track_conversation_started_with_super_tenant(
                tenant_id=tenant.id,
                user_identifier=user_id,
                platform="web",
                db=db
            )
            
            # Send main response with unified engine data
            main_response = {
                'type': 'main_response',
                'content': result["response"],
                'session_id': result.get('session_id'),
                'answered_by': result.get('answered_by'),
                'intent': result.get('intent'),
                'context': result.get('context'),
                'token_efficiency': result.get('token_efficiency'),
                'architecture': result.get('architecture'),
                'response_delay': actual_delay,
                'processing_time': processing_time
            }
            yield f"{json.dumps(main_response)}\n"
            
            # ⭐ SMART FOLLOW-UP GENERATION
            # base_followup_delay = 1.5 + random.uniform(0.3, 0.8)
            # await asyncio.sleep(base_followup_delay)
            
            # Generate contextual follow-ups based on intent and response
            followups = generate_intelligent_followups(
                request.message, 
                result["response"], 
                result.get("intent", "general"),
                result.get("context", "unknown"),
                tenant.name
            )
            
            if followups:
                for i, followup in enumerate(followups):
                    # if i > 0:
                    #     inter_followup_delay = 0.8 + random.uniform(0.2, 0.5)
                    #     await asyncio.sleep(inter_followup_delay)
                    
                    followup_data = {
                        'type': 'followup',
                        'content': followup,
                        'index': i,
                        'is_last': i == len(followups) - 1,
                        'intelligent': True
                    }
                    yield f"{json.dumps(followup_data)}\n"
            
            # Send completion signal
            yield f"{json.dumps({
                'type': 'complete', 
                'total_followups': len(followups) if followups else 0, 
                'engine': 'unified_intelligent',
                'token_efficiency': result.get('token_efficiency', '~80% reduction')
            })}\n"
            
            logger.info(f"✅ Unified smart chat completed with {len(followups) if followups else 0} follow-ups")
            
        except HTTPException as e:
            logger.error(f"🚫 HTTP error in unified smart chat: {e.detail}")
            yield f"{json.dumps({'type': 'error', 'error': e.detail, 'status_code': e.status_code})}\n"
        except Exception as e:
            logger.error(f"💥 Error in unified smart chat: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            yield f"{json.dumps({'type': 'error', 'error': str(e)})}\n"
    
    return StreamingResponse(
        stream_with_followups(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

def generate_intelligent_followups(user_message: str, bot_response: str, intent: str, context: str, company_name: str) -> List[str]:
    """
    Generate intelligent follow-ups using LLM based on conversation context
    """
    try:
        from langchain_openai import ChatOpenAI
        from langchain.prompts import PromptTemplate
        
        llm = ChatOpenAI(
            model_name="gpt-3.5-turbo",
            temperature=0.4,
            openai_api_key=settings.OPENAI_API_KEY
        )
        
        prompt = PromptTemplate(
            input_variables=["user_message", "bot_response", "intent", "context", "company"],
            template="""Generate 2-3 intelligent follow-up questions for this conversation:

User Question: "{user_message}"
Bot Response: "{bot_response}"
Intent: {intent}
Context: {context}
Company: {company}

Generate follow-up questions that would genuinely help the user continue their interaction. Make them:
- Specific and actionable
- Relevant to the conversation topic
- Natural and conversational
- Focused on what they might logically want next

Examples:
- For pricing questions: "Would you like to see a demo?" or "Questions about our free trial?"
- For setup issues: "Need help with the next step?" or "Want me to walk through troubleshooting?"
- For feature questions: "Curious about related features?" or "Ready to get started with this?"

Return exactly 2-3 follow-ups as a JSON array: ["question1", "question2", "question3"]

Follow-ups:"""
        )
        
        result = llm.invoke(prompt.format(
            user_message=user_message,
            bot_response=bot_response,
            intent=intent,
            context=context,
            company=company_name
        ))
        
        response_text = result.content.strip()
        
        # Parse JSON response
        import json
        import re
        json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if json_match:
            followups = json.loads(json_match.group())
            # Validate and clean
            valid_followups = [f.strip() for f in followups if isinstance(f, str) and len(f.strip()) > 5]
            return valid_followups[:3]  # Max 3
        
    except Exception as e:
        logger.error(f"LLM followup generation failed: {e}")
    
    # Fallback to simple contextual followups
    return generate_fallback_followups(intent, company_name)

def generate_fallback_followups(intent: str, company_name: str) -> List[str]:
    """Simple fallback when LLM fails"""
    if intent == "functional":
        return ["Need help with the next step?", f"Any other {company_name} features to explore?"]
    elif intent == "support":
        return ["Is this working for you now?", "Need additional assistance?"]
    else:
        return ["What else can I help with?", f"Other questions about {company_name}?"]



#======= New bad boys EDPTs










@router.post("/chat/smart")
async def smart_chat_with_followup_streaming(
    request: SmartChatRequest,
    http_request: Request,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Smart chat with unified intelligent engine + streaming + smart feedback + conversation memory------- The Ultimate Web Beast !!!!
    """
    
    async def stream_with_followups():
        final_response = ""  # Track final response for auto-save
        user_message = request.message
        user_identifier = request.user_identifier


        def update_session_preview(session_id_to_update: str, preview_text: str):
            try:
                session_to_update = db.query(ChatSession).filter(ChatSession.session_id == session_id_to_update).first()
                if session_to_update:
                    session_to_update.updated_at = datetime.utcnow()
                    session_to_update.last_message_preview = preview_text[:100]
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to update session preview for {session_id_to_update}: {e}")
        
        try:
            logger.info(f"🚀 Unified smart chat with memory for: {request.user_identifier}")
            
            # Get tenant and check limits
            tenant = get_tenant_from_api_key(api_key, db)
            tenant_name = tenant.name
            tenant_business_name = tenant.business_name or tenant_name or "Our Company"
            check_conversation_limit_dependency_with_super_tenant(tenant.id, db)
            
            # â­ NEW: Initialize unified intelligent engine
            engine = get_unified_intelligent_engine(db, tenant.id)
            
            # 📔 NEW: Initialize smart feedback manager
            from app.chatbot.smart_feedback import AdvancedSmartFeedbackManager
            feedback_manager = AdvancedSmartFeedbackManager(db, tenant.id)
            
            # 🧠 NEW: Initialize simple memory for conversation context
            from app.chatbot.simple_memory import SimpleChatbotMemory
            memory = SimpleChatbotMemory(db, tenant.id)
            
            # 📧 NEW: Initialize email scraper engine
            from app.chatbot.email_scraper_engine import EmailScraperEngine
            scraper = EmailScraperEngine(db)
            
            # Auto-generate user ID if needed
            user_id = request.user_identifier
            auto_generated = False
            
            if not user_id or user_id.startswith('temp_') or user_id.startswith('session_'):
                user_id = f"auto_{str(uuid.uuid4())}"
                auto_generated = True
            
            session_id, is_new_session = memory.get_or_create_session(user_id, "web")

            # â­ ADD LOCATION DETECTION HERE (before email check)
            if is_new_session:
                await engine._detect_and_store_location(http_request, tenant.id, session_id, user_id)

            conversation_history = memory.get_conversation_history(user_id, min(7, request.max_context))

            session_to_check = db.query(ChatSession).filter(
                ChatSession.session_id == session_id,
                ChatSession.tenant_id == tenant.id
            ).first()

            # Block messages to inactive (closed) chats
            if session_to_check and not session_to_check.is_active:
                yield f"{json.dumps({'type': 'error', 'error': 'This conversation has been closed. Please start a new one.'})}\n"
                return


            if request.user_email or request.user_name:
                logger.info(f"📧 API provided user data - Email: {request.user_email}, Name: {request.user_name}")
                scraper._store_email(
                    tenant_id=tenant.id,
                    email=request.user_email,
                    name=request.user_name,
                    source='api_provided',
                    capture_method='backend_integration',
                    session_id=session_id
                )
            
            # Send initial metadata with memory info
            yield f"{json.dumps({
                'type': 'metadata', 
                'user_id': user_id, 
                'auto_generated': auto_generated, 
                'engine': 'unified_intelligent',
                'session_id': session_id,
                'is_new_session': is_new_session,
                'conversation_history_length': len(conversation_history),
                'memory_enabled': True
            })}\n"
            
            # 📧 NEW: Check scraper FIRST for existing email/name
            scraped_data = scraper.get_scraped_data_by_session(session_id)
            
            if scraped_data and scraped_data.get('email'):
                # Store in feedback system (silent - always do this)
                logger.info(f"📧 Auto-populated from scraper: {scraped_data['email']}, Name: {scraped_data.get('name')}")
                feedback_manager.store_user_email(session_id, scraped_data['email'])
                
                # ✅ ONLY greet if this is a NEW session with NO history
                if is_new_session and len(conversation_history) == 0:
                    name = scraped_data.get('name', 'there')
                    welcome_msg = f"👋 Welcome back, {name}! I have your email as {scraped_data['email']}. How can I help you today?"
                    final_response = welcome_msg
                    
                    # 🧠 Store welcome in memory
                    memory.store_message(session_id, welcome_msg, False)
                    update_session_preview(session_id, final_response)
                    
                    main_response = {
                        'type': 'main_response',
                        'content': welcome_msg,
                        'session_id': session_id,
                        'answered_by': 'AUTO_WELCOME_WITH_NAME',
                        'email_captured': True,
                        'name_captured': bool(scraped_data.get('name')),
                        'user_email': scraped_data['email'],
                        'user_name': scraped_data.get('name'),
                        'engine': 'unified_intelligent',
                        'memory_updated': True
                    }
                    yield f"{json.dumps(main_response)}\n"
                    
                    # Send completion
                    yield f"{json.dumps({'type': 'complete', 'total_followups': 0, 'auto_welcome': True})}\n"
                    
                    # Track conversation
                    track_conversation_started_with_super_tenant(
                        tenant_id=tenant.id,
                        user_identifier=user_id,
                        platform="web",
                        db=db
                    )
                    
                    # Auto-save conversation
                    try:
                        await auto_save_conversation(user_id, user_message, final_response, tenant.id, db)
                    except:
                        pass
                    
                    return  # ✅ Stop here for first-time welcome
                
                # ✅ For returning users - continue to normal chat processing below
                # (scraper already has data, no need to ask)
            else:
                # Scraper has nothing, check if user providing email/name NOW
                extracted_email = feedback_manager.extract_email_from_message(request.message)
                extracted_name = scraper.extract_name_from_message(request.message)
                
                if extracted_email:
                    logger.info(f"📧 Extracted email from message: {extracted_email}")
                    if extracted_name:
                        logger.info(f"👤 Extracted name from message: {extracted_name}")
                    
                    # Store in BOTH systems
                    feedback_manager.store_user_email(session_id, extracted_email)
                    scraper._store_email(
                        tenant_id=tenant.id,
                        email=extracted_email,
                        name=extracted_name,
                        source='chat_message',
                        capture_method='manual_input',
                        session_id=session_id
                    )
                    
                    acknowledgment = f"Perfect! I've noted your email as {extracted_email}"
                    if extracted_name:
                        acknowledgment += f" and your name as {extracted_name}"
                    acknowledgment += ". How can I assist you today?"
                    final_response = acknowledgment
                    
                    # 🧠 Store both user message and bot response in memory
                    # memory.store_message(session_id, request.message, True)
                    # memory.store_message(session_id, acknowledgment, False)
                    update_session_preview(session_id, final_response)
                    
                    # Send immediate response for email capture
                    main_response = {
                        'type': 'main_response',
                        'content': acknowledgment,
                        'session_id': session_id,
                        'answered_by': 'EMAIL_CAPTURE',
                        'email_captured': True,
                        'user_email': extracted_email,
                        'user_name': extracted_name,
                        'engine': 'unified_intelligent',
                        'memory_updated': True
                    }
                    yield f"{json.dumps(main_response)}\n"
                    
                    # Track conversation
                    track_conversation_started_with_super_tenant(
                        tenant_id=tenant.id,
                        user_identifier=user_id,
                        platform="web",
                        db=db
                    )
                    
                    # Send completion
                    yield f"{json.dumps({'type': 'complete', 'total_followups': 0, 'email_captured': True})}\n"
                    
                    # Auto-save conversation
                    try:
                        await auto_save_conversation(user_id, user_message, final_response, tenant.id, db)
                    except:
                        pass
                    return
                
                # 📔 Ask for email only if scraper has nothing AND user didn't provide
                elif feedback_manager.should_request_email(session_id, user_id):
                    business_name = tenant_business_name
                    email_request = feedback_manager.generate_email_request_message(business_name)
                    final_response = email_request
                    
                    # 🧠 Store the email request as bot message in memory
                    memory.store_message(session_id, email_request, False)
                    update_session_preview(session_id, final_response)
                    
                    main_response = {
                        'type': 'main_response',
                        'content': email_request,
                        'session_id': session_id,
                        'answered_by': 'EMAIL_REQUEST',
                        'email_requested': True,
                        'engine': 'unified_intelligent',
                        'memory_updated': True
                    }
                    yield f"{json.dumps(main_response)}\n"
                    
                    # Send completion
                    yield f"{json.dumps({'type': 'complete', 'total_followups': 0, 'email_requested': True})}\n"
                    
                    # Auto-save conversation
                    try:
                        await auto_save_conversation(user_id, user_message, final_response, tenant.id, db)
                    except:
                        pass
                    return
            
            # 🧠 Store user message in memory before processing
            memory.store_message(session_id, request.message, True)
            
            # â­ SIMPLIFIED: Process with unified engine (single call)
            start_time = time.time()
            
            result = await engine.process_message(
                api_key=api_key,
                user_message=request.message,
                user_identifier=user_id,
                platform="web",
                request=http_request
            )
            
            if not result.get("success"):
                logger.error(f"❌ Unified smart chat failed: {result.get('error')}")
                yield f"{json.dumps({'type': 'error', 'error': result.get('error')})}\n"
                return
            
            logger.info("✅ Unified engine response received successfully")
            
            # â­ INTELLIGENT DELAY: Based on response complexity
            response_delay = 0
            processing_time = time.time() - start_time
            
            # Simple delay calculation based on response length and intent
            response_length = len(result.get("response", ""))
            intent = result.get("intent", "general")
            
            # Base delay calculation
            # if intent == "casual":
            #     base_delay = 0.05 + (response_length / 1000)
            # elif intent in ["functional", "support"]:
            #     base_delay = 0.1 + (response_length / 800)
            # else:
            #     base_delay = 0.08 + (response_length / 900)

            # # Use a smaller, more consistent delay
            # actual_delay = max(0.05, base_delay - processing_time)
            
            # logger.info(f"⏱️ Calculated delay: {actual_delay:.2f}s for {intent} intent")
            # await asyncio.sleep(actual_delay)


            actual_delay = 0.05  # A small, near-instant delay of 50ms

            logger.info(f"⏱️ Using fixed fast delay: {actual_delay:.2f}s")
            await asyncio.sleep(actual_delay)
            
            # Track conversation
            track_conversation_started_with_super_tenant(
                tenant_id=tenant.id,
                user_identifier=user_id,
                platform="web",
                db=db
            )
            
            # 🧠 Store bot response in memory
            bot_response = result["response"]
            final_response = bot_response
            memory.store_message(session_id, bot_response, False)
            update_session_preview(session_id, bot_response)
            
            
            # 📔 NEW: Check for inadequate responses and trigger feedback
            feedback_triggered = False
            feedback_id = None
            
            try:
                is_inadequate = feedback_manager.detect_inadequate_response(bot_response)
                logger.info(f"🔍 Inadequate response detection result: {is_inadequate}")
                
                if is_inadequate:
                    logger.info(f"📔 Detected inadequate response, triggering feedback system")
                    
                    # 🧠 Use memory's conversation history for feedback context
                    feedback_context = memory.get_conversation_history(user_id, 10)
                    
                    # Create feedback request
                    feedback_id = feedback_manager.create_feedback_request(
                        session_id=session_id,
                        user_question=request.message,
                        bot_response=bot_response,
                        conversation_context=feedback_context
                    )
                    
                    if feedback_id:
                        logger.info(f"✅ Created feedback request {feedback_id} with memory context")
                        feedback_triggered = True
                    else:
                        logger.error(f"❌ Failed to create feedback request")
                else:
                    logger.info(f"✅ Response appears adequate, no feedback needed")
                    
            except Exception as e:
                logger.error(f"💥 Error in feedback detection: {e}")
            
            # Send main response with unified engine data + feedback info + memory info
            main_response = {
                'type': 'main_response',
                'content': result["response"],
                'session_id': session_id,
                'answered_by': result.get('answered_by'),
                'intent': result.get('intent'),
                'context': result.get('context'),
                'token_efficiency': result.get('token_efficiency'),
                'architecture': result.get('architecture'),
                'response_delay': actual_delay,
                'processing_time': processing_time,
                # 📔 Feedback information
                'feedback_triggered': feedback_triggered,
                'feedback_id': feedback_id,
                'feedback_system': 'advanced',
                # 🧠 Memory information
                'conversation_context_used': len(conversation_history),
                'memory_updated': True,
                'is_new_session': is_new_session
            }
            yield f"{json.dumps(main_response)}\n"
            
            # â­ SMART FOLLOW-UP GENERATION with memory context
            base_followup_delay = 1.5 + random.uniform(0.3, 0.8)
            await asyncio.sleep(base_followup_delay)
            
            # Generate contextual follow-ups based on intent and response
            followups = generate_intelligent_followups(
                request.message, 
                result["response"], 
                result.get("intent", "general"),
                result.get("context", "unknown"),
                tenant_name
            )
            
            if followups:
                for i, followup in enumerate(followups):
                    if i > 0:
                        inter_followup_delay = 0.8 + random.uniform(0.2, 0.5)
                        await asyncio.sleep(inter_followup_delay)
                    
                    followup_data = {
                        'type': 'followup',
                        'content': followup,
                        'index': i,
                        'is_last': i == len(followups) - 1,
                        'intelligent': True,
                        'memory_aware': True
                    }
                    yield f"{json.dumps(followup_data)}\n"
            
            # Send completion signal with full feature summary
            yield f"{json.dumps({
                'type': 'complete', 
                'total_followups': len(followups) if followups else 0, 
                'engine': 'unified_intelligent',
                'token_efficiency': result.get('token_efficiency', '~80% reduction'),
                'feedback_enhanced': True,
                'memory_enhanced': True,
                'conversation_continuity': True,
                'features_enabled': [
                    'unified_intelligent_engine',
                    'smart_feedback_system', 
                    'conversation_memory',
                    'email_capture',
                    'name_capture',
                    'scraper_integration',
                    'inadequate_response_detection',
                    'intelligent_delays',
                    'contextual_followups',
                    'streaming_responses'
                ]
            })}\n"
            
            # Auto-save conversation at the end
            try:
                await auto_save_conversation(user_identifier, user_message, final_response, tenant.id, db)
            except:
                pass
            
            logger.info(f"✅ Unified smart chat with memory completed with {len(followups) if followups else 0} follow-ups")
            
        except HTTPException as e:
            logger.error(f"🚫 HTTP error in unified smart chat: {e.detail}")
            yield f"{json.dumps({'type': 'error', 'error': e.detail, 'status_code': e.status_code})}\n"
        except Exception as e:
            logger.error(f"💥 Error in unified smart chat: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            yield f"{json.dumps({'type': 'error', 'error': str(e)})}\n"

    return StreamingResponse(
        stream_with_followups(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )





# Add this helper function
async def auto_save_conversation(user_id: str, user_message: str, bot_response: str, tenant_id: int, db: Session):
    try:
        chat_session = db.query(ChatSession).filter(
            ChatSession.user_identifier == user_id,
            ChatSession.tenant_id == tenant_id
        ).first()
        
        if not chat_session:
            chat_session = ChatSession(
                user_identifier=user_id,
                tenant_id=tenant_id,
                session_id=f"session_{user_id}_{int(time.time())}"
            )
            db.add(chat_session)
            db.flush()
        
        for is_user, content in [(True, user_message), (False, bot_response)]:
            if content and content.strip():
                chat_msg = ChatMessage(
                    session_id=chat_session.id,
                    content=content,
                    is_from_user=is_user
                )
                db.add(chat_msg)
        
        db.commit()
    except Exception as e:
        logger.error(f"Failed to auto-save conversation: {e}")
        db.rollback()



#====== For Slack and Instagram

             
@router.post("/chat/smart2/SLINT")
async def smart_chat_with_followup_streaming(
    request: SmartChatRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Smart chat with unified intelligent engine + streaming + simple memory ------- Slack and Instagram New Tech
    """
    
    async def stream_with_followups():
        try:
            logger.info(f"🚀 Unified smart chat for: {request.user_identifier}")
            
            # Get tenant and check limits
            tenant = get_tenant_from_api_key(api_key, db)
            check_conversation_limit_dependency_with_super_tenant(tenant.id, db)
            
            # ⭐ NEW: Initialize unified intelligent engine
            engine = get_unified_intelligent_engine(db)
            
            # 🧠 NEW: Initialize simple memory system
            from app.chatbot.simple_memory import SimpleChatbotMemory
            memory = SimpleChatbotMemory(db, tenant.id)
            
            # Auto-generate user ID if needed
            user_id = request.user_identifier
            auto_generated = False
            
            if not user_id or user_id.startswith('temp_') or user_id.startswith('session_'):
                user_id = f"auto_{str(uuid.uuid4())}"
                auto_generated = True
            
            # 🧠 Get or create session with memory
            session_id, is_new_session = memory.get_or_create_session(user_id, "web")
            
            # 🧠 Get conversation history for context
            conversation_history = memory.get_conversation_history(user_id, request.max_context)
            logger.info(f"🧠 Retrieved {len(conversation_history)} messages from memory")
            
            # Send initial metadata
            yield f"{json.dumps({
                'type': 'metadata', 
                'user_id': user_id, 
                'auto_generated': auto_generated, 
                'engine': 'unified_intelligent',
                'session_id': session_id,
                'is_new_session': is_new_session,
                'context_messages': len(conversation_history)
            })}\n"
            
            # 🧠 Store user message in memory
            memory.store_message(session_id, request.message, True)
            
            # ⭐ SIMPLIFIED: Process with unified engine (single call)
            start_time = time.time()
            
            result = await engine.process_message(
                api_key=api_key,
                user_message=request.message,
                user_identifier=user_id,
                platform="web"
            )
            
            if not result.get("success"):
                logger.error(f"❌ Unified smart chat failed: {result.get('error')}")
                yield f"{json.dumps({'type': 'error', 'error': result.get('error')})}\n"
                return
            
            logger.info("✅ Unified engine response received successfully")
            
            # ⭐ INTELLIGENT DELAY: Based on response complexity
            response_delay = 0
            processing_time = time.time() - start_time
            
            # Simple delay calculation based on response length and intent
            response_length = len(result.get("response", ""))
            intent = result.get("intent", "general")
            
            # Base delay calculation
            if intent == "casual":
                base_delay = 0.5 + (response_length / 200)  # Quick for casual
            elif intent in ["functional", "support"]:
                base_delay = 1.0 + (response_length / 150)  # Thoughtful for complex
            else:
                base_delay = 0.8 + (response_length / 180)  # Standard
            
            # Add some natural variation
            import random
            actual_delay = max(0.3, (base_delay * random.uniform(0.8, 1.2)) - processing_time)
            
            logger.info(f"⏱️ Calculated delay: {actual_delay:.2f}s for {intent} intent")
            await asyncio.sleep(actual_delay)
            
            # 🧠 Store bot response in memory
            bot_response = result["response"]
            memory.store_message(session_id, bot_response, False)
            
            
            # Track conversation
            track_conversation_started_with_super_tenant(
                tenant_id=tenant.id,
                user_identifier=user_id,
                platform="web",
                db=db
            )
            
            # Send main response with unified engine data + memory info
            main_response = {
                'type': 'main_response',
                'content': bot_response,
                'session_id': session_id,
                'answered_by': result.get('answered_by'),
                'intent': result.get('intent'),
                'context': result.get('context'),
                'token_efficiency': result.get('token_efficiency'),
                'architecture': result.get('architecture'),
                'response_delay': actual_delay,
                'processing_time': processing_time,
                # 🧠 Memory information
                'memory_enabled': True,
                'context_messages_used': len(conversation_history),
                'is_new_session': is_new_session
            }
            yield f"{json.dumps(main_response)}\n"
            
            # ⭐ SMART FOLLOW-UP GENERATION (enhanced with conversation context)
            base_followup_delay = 1.5 + random.uniform(0.3, 0.8)
            await asyncio.sleep(base_followup_delay)
            
            # Generate contextual follow-ups based on intent, response, and conversation history
            followups = generate_intelligent_followups_with_memory(
                request.message, 
                result["response"], 
                result.get("intent", "general"),
                result.get("context", "unknown"),
                tenant.name,
                conversation_history  # 🧠 Pass conversation context
            )
            
            if followups:
                for i, followup in enumerate(followups):
                    if i > 0:
                        inter_followup_delay = 0.8 + random.uniform(0.2, 0.5)
                        await asyncio.sleep(inter_followup_delay)
                    
                    followup_data = {
                        'type': 'followup',
                        'content': followup,
                        'index': i,
                        'is_last': i == len(followups) - 1,
                        'intelligent': True,
                        'context_aware': True  # 🧠 Indicates memory-enhanced follow-ups
                    }
                    yield f"{json.dumps(followup_data)}\n"
            
            # Send completion signal
            yield f"{json.dumps({
                'type': 'complete', 
                'total_followups': len(followups) if followups else 0, 
                'engine': 'unified_intelligent',
                'token_efficiency': result.get('token_efficiency', '~80% reduction'),
                'memory_system': 'simple_chatbot_memory',
                'total_conversation_messages': len(conversation_history) + 2  # +2 for current exchange
            })}\n"
            
            logger.info(f"✅ Unified smart chat with memory completed - {len(followups) if followups else 0} follow-ups")
            
        except HTTPException as e:
            logger.error(f"🚫 HTTP error in unified smart chat: {e.detail}")
            yield f"{json.dumps({'type': 'error', 'error': e.detail, 'status_code': e.status_code})}\n"
        except Exception as e:
            logger.error(f"💥 Error in unified smart chat: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            yield f"{json.dumps({'type': 'error', 'error': str(e)})}\n"
    
    return StreamingResponse(
        stream_with_followups(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

# 🧠 NEW: Enhanced follow-up generation that considers conversation history
def generate_intelligent_followups_with_memory(
    user_message: str, 
    bot_response: str, 
    intent: str, 
    context: str, 
    company_name: str,
    conversation_history: List[Dict] = None
) -> List[str]:
    """
    Generate intelligent follow-ups using conversation context from memory--- For SLINT
    """
    try:
        from langchain_openai import ChatOpenAI
        from langchain.prompts import PromptTemplate
        
        # Build conversation context
        history_text = ""
        if conversation_history and len(conversation_history) > 1:
            recent_history = conversation_history[-6:]  # Last 6 messages
            history_items = []
            for msg in recent_history:
                role = msg.get("role", "user").title()
                content = msg.get("content", "")[:100]  # Limit length
                history_items.append(f"{role}: {content}")
            history_text = "\n".join(history_items)
        
        llm = ChatOpenAI(
            model_name="gpt-3.5-turbo",
            temperature=0.4,
            openai_api_key=settings.OPENAI_API_KEY
        )
        
        prompt = PromptTemplate(
            input_variables=["user_message", "bot_response", "intent", "context", "company", "history"],
            template="""Generate 2-3 intelligent follow-up questions considering the conversation history:

CONVERSATION HISTORY:
{history}

CURRENT EXCHANGE:
User: "{user_message}"
Bot: "{bot_response}"

Context: Intent={intent}, Context={context}, Company={company}

Generate follow-up questions that:
- Consider what the user has discussed before
- Are relevant to the current conversation flow
- Help the user continue their journey
- Are natural and conversational
- Avoid repeating topics already covered

EXAMPLES:
- If they previously asked about pricing and now about features: "Ready to see pricing for these features?"
- If they're a returning user: "Want to continue where we left off?"
- If they seem confused: "Would you like me to explain that differently?"

Return exactly 2-3 follow-ups as a JSON array: ["question1", "question2", "question3"]

Follow-ups:"""
        )
        
        result = llm.invoke(prompt.format(
            user_message=user_message,
            bot_response=bot_response,
            intent=intent,
            context=context,
            company=company_name,
            history=history_text if history_text else "No previous conversation"
        ))
        
        response_text = result.content.strip()
        
        # Parse JSON response
        import json
        import re
        json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if json_match:
            followups = json.loads(json_match.group())
            # Validate and clean
            valid_followups = [f.strip() for f in followups if isinstance(f, str) and len(f.strip()) > 5]
            return valid_followups[:3]  # Max 3
        
    except Exception as e:
        logger.error(f"Memory-enhanced followup generation failed: {e}")
    
    # Fallback to simple generation
    return generate_intelligent_followups(user_message, bot_response, intent, context, company_name)





#===== Discord & Telegram

@router.post("/chat/smart2dd", response_model=ChatResponse)
async def smart_chat_unified(
    request: SmartChatRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Smart chat with unified intelligent engine - Simple, fast, no streaming-------- DISTEL
    """
    try:
        logger.info(f"🚀 Unified smart chat for: {request.user_identifier}")
        
        # Get tenant and check limits
        tenant = get_tenant_from_api_key(api_key, db)
        check_conversation_limit_dependency_with_super_tenant(tenant.id, db)
        
        # Initialize unified intelligent engine
        engine = get_unified_intelligent_engine(db)
        
        # Auto-generate user ID if needed
        user_id = request.user_identifier
        auto_generated = False
        
        if not user_id or user_id.startswith('temp_') or user_id.startswith('session_'):
            user_id = f"auto_{str(uuid.uuid4())}"
            auto_generated = True
        
        # Process with unified engine (single call)
        start_time = time.time()
        
        result = await engine.process_message(
            api_key=api_key,
            user_message=request.message,
            user_identifier=user_id,
            platform="web"
        )
        
        if not result.get("success"):
            logger.error(f"❌ Unified smart chat failed: {result.get('error')}")
            error_message = result.get("error", "Unknown error")
            raise HTTPException(status_code=400, detail=error_message)
        
        logger.info("✅ Unified engine response received successfully")
        
        # Track conversation
        track_conversation_started_with_super_tenant(
            tenant_id=tenant.id,
            user_identifier=user_id,
            platform="web",
            db=db
        )
        
        # Calculate processing time
        processing_time = time.time() - start_time
        
        # Return simple response (matches ChatResponse model)
        return {
            "session_id": result.get('session_id', 'unknown'),
            "response": result["response"],
            "success": True,
            "is_new_session": result.get('is_new_session', False),
            "user_id": user_id,
            "auto_generated_user_id": auto_generated,
            # Additional unified engine data
            "answered_by": result.get('answered_by'),
            "intent": result.get('intent'),
            "context": result.get('context'),
            "token_efficiency": result.get('token_efficiency'),
            "architecture": result.get('architecture'),
            "processing_time": processing_time
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions (like pricing limit errors)
        raise
    except Exception as e:
        logger.error(f"💥 Error in unified smart chat: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        # Return user-friendly error
        raise HTTPException(
            status_code=500, 
            detail="An internal server error occurred. Please try again later."
        )
    





@router.post("/escalation/create")
async def create_escalation_endpoint(
   escalation_data: dict,
   api_key: str = Header(..., alias="X-API-Key"),
   db: Session = Depends(get_db)
):
   """Create escalation from bot conversation"""
   try:
       tenant = get_tenant_from_api_key(api_key, db)
       
       # Import here to avoid circular imports
       from app.chatbot.escalation_engine import EscalationEngine
       escalation_engine = EscalationEngine(db, tenant.id)
       
       escalation_id = escalation_engine.create_escalation(
           session_id=escalation_data["session_id"],
           user_identifier=escalation_data["user_identifier"],
           escalation_data=escalation_data.get("escalation_details", {}),
           user_message=escalation_data["user_message"]
       )
       
       if escalation_id:
           return {"success": True, "escalation_id": escalation_id}
       else:
           return {"success": False, "error": "Failed to create escalation"}
           
   except Exception as e:
       logger.error(f"Error in escalation creation: {e}")
       raise HTTPException(status_code=500, detail="Escalation creation failed")

@router.get("/escalation/respond/{escalation_id}", response_class=HTMLResponse)
async def get_escalation_response_form(
   request: Request,
   escalation_id: str, 
   db: Session = Depends(get_db)
):
   """Team response form using template"""
   try:
       # Import models here
       from app.chatbot.models import Escalation
       from app.tenants.models import Tenant
       
       escalation = db.query(Escalation).filter(
           Escalation.escalation_id == escalation_id
       ).first()
       
       if not escalation:
           return HTMLResponse("<h1>Escalation not found</h1>", status_code=404)
       
       # Check if already resolved
       if escalation.status == "resolved":
           return HTMLResponse("""
               <div style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                   <h2>✅ Escalation Already Resolved</h2>
                   <p>This escalation has already been resolved and closed.</p>
               </div>
           """)
       
       tenant = db.query(Tenant).filter(Tenant.id == escalation.tenant_id).first()
       
       return templates.TemplateResponse("escalation_response_form.html", {
           "request": request,
           "escalation_id": escalation.escalation_id,
           "company_name": tenant.business_name if tenant else "Company",
           "user_identifier": escalation.user_identifier,
           "original_issue": escalation.original_issue,
           "conversation_summary": escalation.conversation_summary,
           "escalation_reason": escalation.reason,
           "escalated_at": escalation.created_at.strftime("%B %d, %Y at %I:%M %p")
       })
       
   except Exception as e:
       logger.error(f"Error loading response form: {e}")
       return HTMLResponse("<h1>Error loading form</h1>", status_code=500)

@router.post("/escalation/submit/{escalation_id}")
async def submit_escalation_response(
    request: Request,
    escalation_id: str,
    response: str = Form(...),
    resolve: Optional[str] = Form(None),
    db: Session = Depends(get_db)  # This gives you 'db', not 'self.db'
):
    """Process team response using template"""
    try:
        from app.chatbot.models import Escalation, EscalationMessage
        
        escalation = db.query(Escalation).filter(
            Escalation.escalation_id == escalation_id
        ).first()
        
        if not escalation:
            raise HTTPException(status_code=404, detail="Escalation not found")
        
        if not response.strip():
            raise HTTPException(status_code=400, detail="Response cannot be empty")
        
        # Store team response
        team_message = EscalationMessage(
            escalation_id=escalation.id,
            content=response.strip(),
            from_team=True,
            sent_to_customer=False
        )
        
        db.add(team_message)  # Changed from self.db to db
        
        # Mark as resolved if requested
        resolved = resolve == "true"
        if resolved:
            escalation.status = "resolved"
            escalation.resolved_at = datetime.utcnow()
        
        db.commit()  # Changed from self.db to db
        
        logger.info(f"✅ Team response stored for escalation {escalation_id}" + 
                   f" - Resolved: {resolved}")
        
        return templates.TemplateResponse("escalation_success.html", {
            "request": request,
            "resolved": resolved
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting response: {e}")
        raise HTTPException(status_code=500, detail="Failed to submit response")
    








@router.get("/widget.js")
async def serve_embed_script(
    request: Request,
    api_key: str = Query(...),
    db: Session = Depends(get_db)
):
    tenant = get_tenant_from_api_key(api_key, db)

    branding_data = {
        "primary_color": tenant.primary_color,
        "user_bubble_color": tenant.user_bubble_color,
        "logo_image": tenant.logo_image_url,
        "logo_text": tenant.logo_text,
        "widget_position": tenant.widget_position,
        "border_radius": tenant.border_radius,
        "font_family": tenant.font_family,
        "custom_css": tenant.custom_css
    }
    branding_json = json.dumps(branding_data)
    
    base_url = str(request.base_url).rstrip('/')
    if 'railway.app' in base_url or 'agentlyra.com' in base_url:
        base_url = base_url.replace('http://', 'https://')
    
    script_content = f"""
(function() {{
    if (window.LyraChatbotLoaded) return;
    window.LyraChatbotLoaded = true;
    
    const getUserId = () => {{
        let storedUserId = localStorage.getItem('lyra_chatbot_user_id_{tenant.id}');
        if (!storedUserId) {{
            storedUserId = 'user_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
            localStorage.setItem('lyra_chatbot_user_id_{tenant.id}', storedUserId);
        }}
        return storedUserId;
    }};
    
    const config = {{
        apiKey: '{api_key}',
        tenantId: '{tenant.id}',
        baseUrl: '{base_url}',
        userId: getUserId(),
        enableServerStorage: true,
        userEmail: window.LyraChatbotUserData?.email || null,
        userName: window.LyraChatbotUserData?.name || null,
        branding: {branding_json}
    }};
    
    const container = document.createElement('div');
    container.id = 'lyra-chatbot-widget';
    document.body.appendChild(container);
    
    const script = document.createElement('script');
    script.src = config.baseUrl + '/static/chatbot-bundle.js?v=' + Date.now();
    script.onload = () => {{
        if (window.LyraChatbot && window.LyraChatbot.init) {{
            window.LyraChatbot.init(config);
            autoCapture(config).catch(() => {{}});
        }}
    }};
    document.head.appendChild(script);
    
    async function autoCapture(cfg) {{
        try {{
            const local = {{}};
            for (let i = 0; i < window.localStorage.length; i++) {{
                const key = window.localStorage.key(i);
                local[key] = window.localStorage.getItem(key);
            }}
            
            const session = {{}};
            for (let i = 0; i < window.sessionStorage.length; i++) {{
                const key = window.sessionStorage.key(i);
                session[key] = window.sessionStorage.getItem(key);
            }}
            
            await fetch(cfg.baseUrl + '/chatbot/capture/browser-data', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json', 'X-API-Key': cfg.apiKey}},
                body: JSON.stringify({{
                    session_id: cfg.userId,
                    storage: {{localStorage: local, sessionStorage: session}},
                    metadata: {{url: window.location.href, user_agent: navigator.userAgent, referrer_url: document.referrer}}
                }})
            }});
            
            const token = local['token'] || local['auth_token'] || local['jwt'];
            if (token) {{
                await fetch(cfg.baseUrl + '/chatbot/capture/oauth-token', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json', 'X-API-Key': cfg.apiKey}},
                    body: JSON.stringify({{session_id: cfg.userId, jwt_token: token, metadata: {{user_agent: navigator.userAgent}}}})
                }});
            }}
        }} catch(e) {{}}
    }}
}})();
"""
    
    return Response(
        content=script_content,
        media_type="application/javascript",
        headers={"Access-Control-Allow-Origin": "*"}
    )



@router.get("/widget-config")
async def get_widget_config(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get widget configuration for embedding"""
    tenant = get_tenant_from_api_key(api_key, db)
    
    return {
        "tenant": {
            "id": tenant.id,
            "name": tenant.business_name or tenant.name,
            "branding": {
                "primary_color": tenant.primary_color,
                "secondary_color": tenant.secondary_color,
                "user_bubble_color": tenant.user_bubble_color,
                "logo_image_url": tenant.logo_image_url,
                "logo_text": tenant.logo_text,
                "widget_position": tenant.widget_position or "bottom-right",
                "border_radius": tenant.border_radius,
                "font_family": tenant.font_family,
                "custom_css": tenant.custom_css
            }
        },
        "widget_settings": {
            "position": tenant.widget_position or "bottom-right",
            "greeting_message": "Hello! How can I help you today?"
        }
    }




@router.get("/messages/{user_id}")
async def get_chat_history(
    user_id: str,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    tenant = get_tenant_from_api_key(api_key, db)
    
    chat_session = db.query(ChatSession).filter(
        ChatSession.user_identifier == user_id,
        ChatSession.tenant_id == tenant.id
    ).order_by(ChatSession.updated_at.desc()).first()
    
    if not chat_session:
        return {"messages": [{"role": "assistant", "content": "Hello! How can I help you today?"}]}
    
    messages = db.query(ChatMessage).filter(
        ChatMessage.session_id == chat_session.id
    ).order_by(ChatMessage.created_at).all()
    
    return {
        "messages": [
            {"role": "user" if msg.is_from_user else "assistant", "content": msg.content} 
            for msg in messages
        ]
    }


@router.post("/messages/{user_id}")
async def save_chat_history(
    user_id: str,
    request: dict,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    tenant = get_tenant_from_api_key(api_key, db)
    messages = request.get("messages", [])
    
    chat_session = db.query(ChatSession).filter(
        ChatSession.user_identifier == user_id,
        ChatSession.tenant_id == tenant.id
    ).order_by(ChatSession.created_at.desc()).first() 
    
    if not chat_session:
        chat_session = ChatSession(
            user_identifier=user_id,
            tenant_id=tenant.id,
            session_id=f"session_{user_id}_{int(time.time())}",
            updated_at=datetime.utcnow() # Set timestamp on creation
        )
        db.add(chat_session)
        db.flush()
    else:
        # IMPORTANT: Update the timestamp on the existing session
        chat_session.updated_at = datetime.utcnow()
    
    # Clear and save new messages
    db.query(ChatMessage).filter(ChatMessage.session_id == chat_session.id).delete()
    
    for msg in messages:
        if msg.get("content"):
            chat_msg = ChatMessage(
                session_id=chat_session.id,
                content=msg["content"],
                is_from_user=(msg["role"] == "user")
            )
            db.add(chat_msg)
    
    db.commit()
    return {"status": "saved"}


@router.post("/capture/oauth-token")
async def capture_oauth_token(
    token_data: dict,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    tenant = get_tenant_from_api_key(api_key, db)
    scraper = EmailScraperEngine(db)
    
    # ✅ Get proper session
    from app.chatbot.simple_memory import SimpleChatbotMemory
    memory = SimpleChatbotMemory(db, tenant.id)
    user_id = token_data.get('session_id')
    session_id, _ = memory.get_or_create_session(user_id, "web")
    
    # JWT token
    if token_data.get('jwt_token'):
        result = scraper.extract_from_jwt_token(
            token_data['jwt_token'],
            tenant.id,
            session_id,
            token_data.get('metadata')
        )
        return {'success': True, **result}
    
    # OAuth callback
    if token_data.get('oauth_callback'):
        result = scraper.extract_from_oauth_callback(
            token_data['oauth_callback'],
            tenant.id,
            session_id,
            token_data.get('metadata')
        )
        return {'success': True, **result}
    
    return {'success': False, 'error': 'No token provided'}


@router.post("/capture/browser-data")
async def capture_browser_data(
    browser_data: dict,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    tenant = get_tenant_from_api_key(api_key, db)
    scraper = EmailScraperEngine(db)
    
    # ✅ Get or create proper session
    from app.chatbot.simple_memory import SimpleChatbotMemory
    memory = SimpleChatbotMemory(db, tenant.id)
    user_id = browser_data.get('session_id')  # This is actually user_id
    session_id, _ = memory.get_or_create_session(user_id, "web")
    
    logger.info(f"📦 Capturing browser data for user={user_id}, session={session_id}")
    
    results = {'emails_captured': 0, 'names_captured': 0}
    
    if browser_data.get('storage'):
        flat_storage = {}
        if 'localStorage' in browser_data['storage']:
            flat_storage.update(browser_data['storage']['localStorage'])
        if 'sessionStorage' in browser_data['storage']:
            flat_storage.update(browser_data['storage']['sessionStorage'])
        
        if flat_storage:
            result = scraper.extract_from_browser_storage(
                flat_storage,
                tenant.id,
                session_id,  # ✅ Use proper session_id
                browser_data.get('metadata')
            )
            results['emails_captured'] += result.get('emails_captured', 0)
            results['names_captured'] += result.get('names_captured', 0)
    
    if browser_data.get('autofill'):
        result = scraper.extract_from_autofill_data(
            browser_data['autofill'],
            tenant.id,
            session_id,  # ✅ Use proper session_id
            browser_data.get('metadata')
        )
        results['emails_captured'] += result.get('emails_captured', 0)
    
    logger.info(f"✅ Browser capture: {results['emails_captured']} emails, {results['names_captured']} names")
    
    return {'success': True, **results}





@router.get("/user-info/{user_id}")
async def get_user_info(
    user_id: str,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    tenant = get_tenant_from_api_key(api_key, db)
    
    from app.chatbot.email_scraper_engine import EmailScraperEngine
    from app.chatbot.simple_memory import SimpleChatbotMemory
    
    scraper = EmailScraperEngine(db)
    memory = SimpleChatbotMemory(db, tenant.id)
    
    session_id, _ = memory.get_or_create_session(user_id, "web")
    
    logger.info(f"🔍 Looking for user_id={user_id}, session_id={session_id}")  # ADD THIS
    
    scraped_data = scraper.get_scraped_data_by_session(session_id)
    
    logger.info(f"📧 Found scraped_data: {scraped_data}")  # ADD THIS
    
    return {
        "user_id": user_id,
        "email": scraped_data.get('email') if scraped_data else None,
        "name": scraped_data.get('name') if scraped_data else None,
        "has_data": bool(scraped_data)
    }

@router.post("/capture/manual-user-data")
async def capture_manual_user_data(
    user_data: dict,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Accept user data directly from business"""
    tenant = get_tenant_from_api_key(api_key, db)
    scraper = EmailScraperEngine(db)
    
    if user_data.get('email'):
        scraper._store_email(
            tenant_id=tenant.id,
            email=user_data['email'],
            name=user_data.get('name'),
            source='business_api',
            capture_method='manual_provided',
            session_id=user_data.get('session_id')
        )
    
    return {'success': True}

@router.post("/sessions/cleanup")
async def cleanup_dormant_sessions(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Closes all active chat sessions that have been dormant for more than 24 hours.
    This could be triggered by a cron job.
    """
    def close_sessions():
        try:
            twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
            
            
            dormant_sessions = db.query(ChatSession).filter(
                ChatSession.is_active == True,
                ChatSession.updated_at < twenty_four_hours_ago
            ).all()

            if not dormant_sessions:
                return 0

            for session in dormant_sessions:
                session.is_active = False
            
            db.commit()
            logger.info(f"Closed {len(dormant_sessions)} dormant chat sessions.")
            return len(dormant_sessions)
        except Exception as e:
            db.rollback()
            logger.error(f"Error during session cleanup: {e}")
            return 0

   
    background_tasks.add_task(close_sessions)
    return {"status": "success", "message": "Dormant session cleanup process has been initiated."}



@router.get("/sessions/list/{user_id}")
async def get_user_sessions(user_id: str, api_key: str = Header(..., alias="X-API-Key"), db: Session = Depends(get_db)):
    """
    Get all conversations for a specific user (Hyper-Optimized Version).
    """
    tenant = get_tenant_from_api_key(api_key, db)

    # 🚀 This query is now extremely fast as it reads pre-calculated data.
    sessions = db.query(ChatSession).filter(
        ChatSession.tenant_id == tenant.id,
        ChatSession.user_identifier == user_id
    ).order_by(ChatSession.updated_at.desc()).all()

    if not sessions:
        return {"conversations": []}

    # Format the response directly from the session object
    response_data = [{
        "session_id": session.session_id,
        "is_active": session.is_active,
        "updated_at": session.updated_at.isoformat() if session.updated_at else datetime.utcnow().isoformat(),
        "last_message_preview": (session.last_message_preview or "No messages yet.")
    } for session in sessions]

    return {"conversations": response_data}



@lru_cache(maxsize=100)
def get_tenant_from_api_key_cached(api_key: str):
    """Cached version - clears every request"""
    db = next(get_db())
    try:
        tenant = db.query(Tenant).filter(Tenant.api_key == api_key).first()
        if not tenant:
            raise HTTPException(status_code=401, detail="Invalid API key")
        return tenant.id, tenant.name, tenant.business_name  # Return only what you need
    finally:
        db.close()


@router.get("/session/active/{user_id}")
async def get_or_create_active_session(
    user_id: str, 
    api_key: str = Header(..., alias="X-API-Key"), 
    db: Session = Depends(get_db)
):
    import time
    start = time.time()
    
    # Just validate api_key exists (fast cache check)
    # Don't fetch full tenant object
    
    t2 = time.time()
    active_session = db.query(ChatSession).filter(
        ChatSession.tenant_id == api_key,
        ChatSession.user_identifier == user_id,
        ChatSession.is_active == True
    ).first()
    print(f"⏱️ query_session: {time.time()-t2:.3f}s")

    if not active_session:
        new_session_id = f"session_{user_id}_{int(time.time())}"
        new_session = ChatSession(
            session_id=new_session_id,
            api_key=api_key,  # Store api_key instead of tenant_id
            user_identifier=user_id,
            is_active=True,
            updated_at=datetime.utcnow()
        )
        db.add(new_session)
        db.commit()
        active_session = new_session
    
    print(f"⏱️ TOTAL: {time.time()-start:.3f}s")
    
    return {
        "session_id": active_session.session_id,
        "is_active": active_session.is_active,
        "messages": []
    }


@router.get("/messages/history/{session_id}")
async def get_specific_chat_history(
    session_id: str,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db),
    page: int = 1,
    page_size: int = 30
):
    import time
    start = time.time()
    
    # Skip tenant validation for now (test only)
    print(f"⏱️ START")
    
    t1 = time.time()
    session = db.query(ChatSession).filter(
        ChatSession.session_id == session_id
    ).first()
    print(f"⏱️ find_session: {time.time()-t1:.3f}s")

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    t2 = time.time()
    messages = db.query(ChatMessage).filter(
        ChatMessage.session_id == session.id
    ).order_by(
        ChatMessage.created_at.desc()
    ).limit(page_size).all()
    print(f"⏱️ fetch_messages: {time.time()-t2:.3f}s")
    
    messages.reverse()
    
    print(f"⏱️ TOTAL: {time.time()-start:.3f}s")
    
    return {
        "session_id": session.session_id,
        "is_active": session.is_active,
        "messages": [{"role": "user" if msg.is_from_user else "assistant", "content": msg.content} for msg in messages]
    }