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
from app.pricing.integration_helpers import check_message_limit_dependency, track_message_sent
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
    max_context: int = 20  # How many previous messages to remember

class SimpleDiscordRequest(BaseModel):
    message: str
    discord_user_id: str
    channel_id: str
    guild_id: str
    max_context: int = 20


class SmartChatRequest(BaseModel):
    message: str
    user_identifier: str
    max_context: int = 20

class TenantFeedbackResponse(BaseModel):
    feedback_id: str
    response: str





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
    Send a message to the chatbot and get a response
    """
    try:
        # Debug - Log the API key being used
        logger.info(f"💬 Processing chat request with API key: {api_key[:10]}...")
        logger.info(f"📝 Message: {request.message[:50]}...")
        
        # 🔒 PRICING CHECK - Get tenant and check message limits
        logger.info("🔍 Getting tenant from API key...")
        tenant = get_tenant_from_api_key(api_key, db)
        logger.info(f"✅ Found tenant: {tenant.name} (ID: {tenant.id})")
        
        logger.info("🚦 Checking message limits...")
        check_message_limit_dependency(tenant.id, db)
        logger.info("✅ Message limit check passed")
        
        # Initialize chatbot engine
        logger.info("🤖 Initializing chatbot engine...")
        engine = ChatbotEngine(db)
        
        # Process message
        logger.info("⚡ Processing message with chatbot engine...")
        result = engine.process_message(api_key, request.message, request.user_identifier)
        
        if not result.get("success"):
            error_message = result.get("error", "Unknown error")
            logger.error(f"❌ Chatbot error: {error_message}")
            
            # Handle OpenAI API key errors differently
            if "Incorrect API key provided" in error_message or "invalid_api_key" in error_message:
                logger.error("🔑 OpenAI API key error detected - using hardcoded key instead")
                
                # Try again with hardcoded API key
                # os.environ["OPENAI_API_KEY"]  # Replace with your valid key
                
                # Process message again
                result = engine.process_message(api_key, request.message, request.user_identifier)
                
                if result.get("success"):
                    # 📊 PRICING TRACK - Log successful message usage
                    logger.info("📊 Tracking message usage (after retry)...")
                    track_success = track_message_sent(tenant.id, db)
                    logger.info(f"📈 Message tracking result: {track_success}")
                    return result
            
            # If we still have an error, raise an exception
            raise HTTPException(status_code=400, detail=error_message)
        
        # 📊 PRICING TRACK - Log successful message usage
        logger.info("📊 Tracking message usage...")
        track_success = track_message_sent(tenant.id, db)
        logger.info(f"📈 Message tracking result: {track_success}")
        
        # Log the response for debugging
        logger.info(f"✅ Chat successful, response length: {len(result.get('response', ''))}")
        
        return result
    except HTTPException:
        # Re-raise HTTP exceptions (including pricing limit errors)
        logger.error("🚫 HTTP Exception occurred (pricing limit or other)")
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
    Simplified streaming - sends JSON lines instead of SSE format
    """
    
    async def stream_sentences():
        try:
            logger.info(f"🎬 Starting streaming chat for API key: {api_key[:10]}...")
            
            # 🔒 PRICING CHECK - Get tenant and check message limits FIRST
            logger.info("🔍 Getting tenant and checking limits for streaming...")
            tenant = get_tenant_from_api_key(api_key, db)
            check_message_limit_dependency(tenant.id, db)
            logger.info(f"✅ Streaming limits OK for tenant: {tenant.name}")
            
            start_time = time.time()
            
            # Calculate initial thinking delay
            message_lower = request.message.lower()
            complexity_score = sum(1 for word in ['explain', 'detail', 'how', 'why'] if word in message_lower)
            
            # FAQ patterns get quicker responses
            faq_patterns = ['what is your', 'what are your', 'business hours', 'contact', 'website', 'phone', 'email', 'price', 'cost']
            is_faq_like = any(pattern in message_lower for pattern in faq_patterns)
            
            if is_faq_like:
                initial_delay = random.uniform(0.8, 2.5)
            elif complexity_score > 2:
                initial_delay = random.uniform(4.0, 8.0)
            elif complexity_score > 0:
                initial_delay = random.uniform(2.5, 6.0)
            else:
                initial_delay = random.uniform(1.2, 4.0)
            
            logger.info(f"⏱️ Initial thinking delay: {initial_delay:.2f} seconds")
            
            # Send thinking indicator
            yield f"{json.dumps({'type': 'thinking', 'delay': initial_delay})}\n"
            await asyncio.sleep(initial_delay)
            
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
            
            # 📊 PRICING TRACK - Log successful message usage (streaming counts as 1 message)
            logger.info("📊 Tracking streaming message usage...")
            track_success = track_message_sent(tenant.id, db)
            logger.info(f"📈 Streaming message tracking result: {track_success}")
            
            # Break into sentences
            full_response = result["response"]
            sentences = break_into_sentences(full_response)
            logger.info(f"📝 Split response into {len(sentences)} sentences")
            
            # Send start signal
            yield f"{json.dumps({'type': 'start', 'session_id': result.get('session_id'), 'total_sentences': len(sentences)})}\n"
            
            # Stream each sentence
            for i, sentence in enumerate(sentences):
                typing_delay = calculate_sentence_delay(sentence, is_last=(i == len(sentences) - 1))
                await asyncio.sleep(typing_delay)
                
                sentence_data = {
                    'type': 'sentence',
                    'text': sentence.strip(),
                    'index': i,
                    'total_sentences': len(sentences),
                    'is_last': i == len(sentences) - 1,
                    'delay': typing_delay
                }
                
                yield f"{json.dumps(sentence_data)}\n"
                logger.info(f"📤 Sent sentence {i+1}/{len(sentences)}: '{sentence[:30]}...' (delay: {typing_delay:.2f}s)")
            
            # Send completion
            completion_data = {
                'type': 'complete',
                'session_id': result.get('session_id'),
                'total_time': time.time() - start_time,
                'sentences_sent': len(sentences)
            }
            yield f"{json.dumps(completion_data)}\n"
            
            logger.info(f"🎉 Streaming completed successfully in {time.time() - start_time:.2f}s")
            
        except HTTPException as e:
            # Handle pricing limit errors and other HTTP exceptions
            logger.error(f"🚫 HTTP error in streaming: {e.detail}")
            yield f"{json.dumps({'type': 'error', 'error': e.detail, 'status_code': e.status_code})}\n"
        except Exception as e:
            logger.error(f"💥 Error in streaming: {str(e)}")
            yield f"{json.dumps({'type': 'error', 'error': str(e)})}\n"
    
    return StreamingResponse(
        stream_sentences(),
        media_type="application/x-ndjson",  # Changed from text/event-stream
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
        
        # Pricing check
        tenant = get_tenant_from_api_key(api_key, db)
        check_message_limit_dependency(tenant.id, db)
        
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
        
        # Track message usage
        track_message_sent(tenant.id, db)
        
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
        
        # Pricing check
        tenant = get_tenant_from_api_key(api_key, db)
        check_message_limit_dependency(tenant.id, db)
        
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
        
        # Track message usage
        track_message_sent(tenant.id, db)
        
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
    """
    try:
        logger.info(f"🧠📧 Smart feedback chat for: {request.user_identifier}")
        
        # Pricing check
        tenant = get_tenant_from_api_key(api_key, db)
        check_message_limit_dependency(tenant.id, db)
        
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
        
        # Track message usage
        track_message_sent(tenant.id, db)
        
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



