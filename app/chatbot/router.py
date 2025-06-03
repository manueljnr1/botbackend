from fastapi import APIRouter, Depends, HTTPException, Header, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from pydantic import BaseModel
from pydantic import EmailStr
import logging
import os
import asyncio
from datetime import datetime
import random
import time
import re


from fastapi.responses import StreamingResponse
import json



from app.database import get_db
from app.chatbot.engine import ChatbotEngine

from app.chatbot.models import ChatSession, ChatMessage
from app.utils.language_service import language_service, SUPPORTED_LANGUAGES
from app.chatbot.memory import EnhancedChatbotMemory


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
        check_message_limit_dependency(tenant.id, db)
        
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


@router.post("/chat/smart", response_model=ChatResponse)
async def chat_with_smart_feedback(
    request: SmartChatRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Web chat endpoint with smart feedback system that:
- Asks for email on new conversations
- Detects when bot doesn't have good answers  
- Automatically sends feedback requests to tenant
- Delivers tenant responses as follow-ups
- Remembers conversation context (last 200 messages by default)
    """
    try:
        logger.info(f"🧠📧 Smart feedback chat for: {request.user_identifier}")
        
        # Pricing check (UPDATED)
        tenant = get_tenant_from_api_key(api_key, db)
        check_conversation_limit_dependency(tenant.id, db)  # UPDATED
        
        # Initialize chatbot engine
        engine = ChatbotEngine(db)
        
        # Process with smart feedback system
        result = engine.process_web_message_with_feedback(
            api_key=api_key,
            user_message=request.message,
            user_identifier=request.user_identifier,
            max_context=request.max_context
        )
        
        if not result.get("success"):
            error_message = result.get("error", "Unknown error")
            logger.error(f"❌ Smart feedback chat error: {error_message}")
            raise HTTPException(status_code=400, detail=error_message)
        
        # Track conversation usage (UPDATED)
        track_conversation_started(
            tenant_id=tenant.id,
            user_identifier=request.user_identifier,
            platform="web",
            db=db
        )
        
        # Log special feedback events
        if result.get("email_requested"):
            logger.info("📧 Requested user email for feedback system")
        elif result.get("email_captured"):
            logger.info(f"📧 Captured user email: {result.get('user_email')}")
        elif result.get("feedback_triggered"):
            logger.info(f"🔔 Triggered feedback request: {result.get('feedback_id')}")
        
        logger.info(f"✅ Smart feedback chat successful")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"💥 Error in smart feedback chat: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
    


@router.post("/feedback/respond")
async def handle_tenant_feedback(
    request: TenantFeedbackResponse,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Handle tenant's response to feedback request
    This processes the tenant's email reply and sends follow-up to user
    """
    try:
        engine = ChatbotEngine(db)
        
        result = engine.handle_tenant_feedback_response(
            api_key=api_key,
            feedback_id=request.feedback_id,
            tenant_response=request.response
        )
        
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Failed to process feedback"))
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error handling tenant feedback: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/feedback/stats")
async def get_feedback_statistics(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Get feedback system statistics for tenant
    """
    try:
        engine = ChatbotEngine(db)
        result = engine.get_feedback_stats(api_key)
        
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Failed to get stats"))
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting feedback stats: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/feedback/pending")
async def get_pending_feedback_requests(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Get list of pending feedback requests for tenant
    """
    try:
        from app.chatbot.smart_feedback import PendingFeedback
        
        tenant = get_tenant_from_api_key(api_key, db)
        
        pending_requests = db.query(PendingFeedback).filter(
            PendingFeedback.tenant_id == tenant.id,
            PendingFeedback.user_notified == False
        ).order_by(PendingFeedback.created_at.desc()).all()
        
        requests_data = []
        for request in pending_requests:
            requests_data.append({
                "feedback_id": request.feedback_id,
                "user_question": request.user_question,
                "bot_response": request.bot_response,
                "user_email": request.user_email,
                "created_at": request.created_at.isoformat(),
                "tenant_email_sent": request.tenant_email_sent
            })
        
        return {
            "success": True,
            "pending_requests": requests_data,
            "total_count": len(requests_data)
        }
        
    except Exception as e:
        logger.error(f"Error getting pending feedback: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


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
    

@router.post("/chat/webchatbot")
async def webchatbot_chat_enhanced(
    request: WebChatbotRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Enhanced webchatbot endpoint that combines:
    - Smart feedback system (email collection, inadequate response detection)
    - Delayed streaming (human-like typing with sentence breaks)
    - Advanced conversation memory
    """
    
    if request.enable_streaming:
        # Use streaming response with smart feedback
        return await _webchatbot_with_streaming(request, api_key, db)
    else:
        # Use regular response with smart feedback
        return await _webchatbot_without_streaming(request, api_key, db)

async def _webchatbot_with_streaming(request: WebChatbotRequest, api_key: str, db: Session):
    """Streaming version with smart feedback"""
    
    async def stream_smart_sentences():
        try:
            logger.info(f"🎬🧠 Starting enhanced webchatbot (streaming) for: {request.user_identifier}")
            
            # 🔒 PRICING CHECK
            tenant = get_tenant_from_api_key(api_key, db)
            check_conversation_limit_dependency(tenant.id, db)
            logger.info(f"✅ Streaming limits OK for tenant: {tenant.name}")
            
            start_time = time.time()
            
            # Initialize chatbot engine
            engine = ChatbotEngine(db)
            
            # Process with smart feedback system (this handles email requests, etc.)
            result = engine.process_web_message_with_feedback(
                api_key=api_key,
                user_message=request.message,
                user_identifier=request.user_identifier,
                max_context=request.max_context
            )
            
            if not result.get("success"):
                logger.error(f"❌ Smart feedback processing failed: {result.get('error')}")
                yield f"{json.dumps({'type': 'error', 'error': result.get('error')})}\n"
                return
            
            # 📊 PRICING TRACK
            track_conversation_started(
                tenant_id=tenant.id,
                user_identifier=request.user_identifier,
                platform="web",
                db=db
            )
            
            # Check if this was an email request/capture (don't stream these)
            if result.get("email_requested") or result.get("email_captured"):
                logger.info("📧 Email interaction - sending immediate response")
                yield f"{json.dumps({'type': 'complete', 'content': result['response'], 'is_complete': True, 'special_action': result.get('email_requested', False) or result.get('email_captured', False)})}\n"
                return
            
            bot_response = result["response"]
            
            # Log special feedback events
            if result.get("feedback_triggered"):
                logger.info(f"🔔 Feedback triggered during streaming: {result.get('feedback_id')}")
            
            # Break response into sentences for streaming
            sentences = break_into_sentences(bot_response)
            logger.info(f"📝 Split response into {len(sentences)} sentences for streaming")
            
            # Send initial metadata
            yield f"{json.dumps({'type': 'start', 'total_sentences': len(sentences), 'session_id': result.get('session_id')})}\n"
            
            # Stream each sentence with delays
            for i, sentence in enumerate(sentences):
                is_last = (i == len(sentences) - 1)
                
                # Calculate delay for this sentence
                delay = calculate_sentence_delay(sentence, is_last)
                
                # Wait for the calculated delay
                logger.info(f"⏱️ Sentence {i+1}/{len(sentences)}: waiting {delay:.2f}s")
                await asyncio.sleep(delay)
                
                # Send the sentence
                chunk_data = {
                    'type': 'chunk',
                    'content': sentence,
                    'chunk_index': i,
                    'total_chunks': len(sentences),
                    'delay_used': delay,
                    'is_complete': is_last
                }
                
                # Add feedback info to final chunk if applicable
                if is_last and result.get("feedback_triggered"):
                    chunk_data['feedback_triggered'] = True
                    chunk_data['feedback_id'] = result.get('feedback_id')
                
                yield f"{json.dumps(chunk_data)}\n"
            
            # Send completion signal
            total_time = time.time() - start_time
            completion_data = {
                'type': 'complete',
                'total_processing_time': total_time,
                'context_messages': result.get('context_messages', 0),
                'is_new_session': result.get('is_new_session', False)
            }
            
            yield f"{json.dumps(completion_data)}\n"
            
            logger.info(f"✅ Enhanced webchatbot streaming completed in {total_time:.2f}s")
            
        except HTTPException as e:
            logger.error(f"🚫 HTTP error in enhanced streaming: {e.detail}")
            yield f"{json.dumps({'type': 'error', 'error': e.detail, 'status_code': e.status_code})}\n"
        except Exception as e:
            logger.error(f"💥 Error in enhanced streaming: {str(e)}")
            yield f"{json.dumps({'type': 'error', 'error': str(e)})}\n"
    
    return StreamingResponse(
        stream_smart_sentences(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

async def _webchatbot_without_streaming(request: WebChatbotRequest, api_key: str, db: Session):
    """Non-streaming version with smart feedback (fallback)"""
    
    try:
        logger.info(f"🧠 Enhanced webchatbot (non-streaming) for: {request.user_identifier}")
        
        # Pricing check
        tenant = get_tenant_from_api_key(api_key, db)
        check_conversation_limit_dependency(tenant.id, db)
        
        # Initialize chatbot engine
        engine = ChatbotEngine(db)
        
        # Process with smart feedback system
        result = engine.process_web_message_with_feedback(
            api_key=api_key,
            user_message=request.message,
            user_identifier=request.user_identifier,
            max_context=request.max_context
        )
        
        if not result.get("success"):
            error_message = result.get("error", "Unknown error")
            logger.error(f"❌ Enhanced webchatbot error: {error_message}")
            raise HTTPException(status_code=400, detail=error_message)
        
        # Track conversation usage
        track_conversation_started(
            tenant_id=tenant.id,
            user_identifier=request.user_identifier,
            platform="web",
            db=db
        )
        
        # Log special feedback events
        if result.get("email_requested"):
            logger.info("📧 Requested user email")
        elif result.get("email_captured"):
            logger.info(f"📧 Captured user email: {result.get('user_email')}")
        elif result.get("feedback_triggered"):
            logger.info(f"🔔 Triggered feedback request: {result.get('feedback_id')}")
        
        logger.info(f"✅ Enhanced webchatbot (non-streaming) successful")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"💥 Error in enhanced webchatbot: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

# Additional endpoint for checking streaming capability
@router.get("/chat/webchatbot/capabilities")
async def get_webchatbot_capabilities(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get webchatbot capabilities and configuration"""
    
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        return {
            "success": True,
            "capabilities": {
                "streaming": True,
                "smart_feedback": True,
                "email_collection": True,
                "conversation_memory": True,
                "delay_simulation": True,
                "feedback_detection": True
            },
            "tenant_config": {
                "name": tenant.name,
                "feedback_enabled": getattr(tenant, 'enable_feedback_system', True),
                "feedback_email": getattr(tenant, 'feedback_email', None) is not None
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting webchatbot capabilities: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")