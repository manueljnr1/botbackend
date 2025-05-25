from fastapi import APIRouter, Depends, HTTPException, Header, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from pydantic import BaseModel
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


@router.post("/chat/discord", response_model=ChatResponse)
async def chat_discord(
    request: DiscordChatRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Discord-specific chat endpoint with memory
    """
    try:
        # Pricing check
        tenant = get_tenant_from_api_key(api_key, db)
        check_message_limit_dependency(tenant.id, db)
        
        # Initialize chatbot engine
        engine = ChatbotEngine(db)
        
        # Process Discord message
        result = engine.process_discord_message(
            api_key=api_key,
            user_message=request.message,
            discord_user_id=request.discord_user_id,
            channel_id=request.channel_id,
            guild_id=request.guild_id
        )
        
        if not result.get("success"):
            error_message = result.get("error", "Unknown error")
            logger.error(f"❌ Discord chat error: {error_message}")
            raise HTTPException(status_code=400, detail=error_message)
        
        # Track message usage
        track_message_sent(tenant.id, db)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"💥 Error in Discord chat: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

# Fix the broken enhanced memory endpoint:
@router.post("/chat/enhanced", response_model=ChatResponse)
async def chat_with_enhanced_memory(
    request: PlatformChatRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Chat endpoint with enhanced cross-platform memory
    """
    try:
        logger.info(f"🧠 Enhanced memory chat for {request.platform}: {request.user_identifier}")
        
        # Pricing check
        tenant = get_tenant_from_api_key(api_key, db)
        check_message_limit_dependency(tenant.id, db)
        
        # Initialize chatbot engine
        engine = ChatbotEngine(db)
        
        # Process with enhanced memory
        result = engine.process_message_with_enhanced_memory(
            api_key=api_key,
            user_message=request.message,
            user_identifier=request.user_identifier,
            platform_data=request.platform_data
        )
        
        if not result.get("success"):
            error_message = result.get("error", "Unknown error")
            logger.error(f"❌ Enhanced memory chat error: {error_message}")
            raise HTTPException(status_code=400, detail=error_message)
        
        # Track message usage
        track_message_sent(tenant.id, db)
        
        logger.info(f"✅ Enhanced memory chat successful")
        logger.info(f"📊 Memory stats: {result.get('memory_stats', {})}")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"💥 Error in enhanced memory chat: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

# Fix the broken cache endpoint at the end:
@router.get("/memory/cache/web/{user_identifier}")
async def get_cached_web_session(
    user_identifier: str,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Retrieve cached web session data
    """
    engine = ChatbotEngine(db)
    tenant = engine._get_tenant_by_api_key(api_key)
    if not tenant:
        raise HTTPException(status_code=403, detail="Invalid API key")
    
    # In a real implementation, you'd retrieve from cache
    # For now, we'll get the memory from database
    memory = EnhancedChatbotMemory(db, tenant.id)
    web_identifier = f"web:{user_identifier}" if not user_identifier.startswith("web:") else user_identifier
    
    cross_platform_memory = memory.get_cross_platform_memory(web_identifier)
    
    return {
        "user_identifier": user_identifier,
        "session_data": cross_platform_memory,
        "retrieved_at": datetime.now().isoformat()
    }

# Additional useful endpoints:

@router.get("/memory/user/{user_identifier}/sessions")
async def get_user_sessions(
    user_identifier: str,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get all sessions for a specific user across platforms"""
    engine = ChatbotEngine(db)
    tenant = engine._get_tenant_by_api_key(api_key)
    if not tenant:
        raise HTTPException(status_code=403, detail="Invalid API key")
    
    # Get sessions for this user identifier and similar ones
    memory = EnhancedChatbotMemory(db, tenant.id)
    normalized_id, platform = memory.normalize_user_identifier(user_identifier)
    
    # Find all possible identifiers for this user
    possible_identifiers = [
        user_identifier,
        normalized_id,
        f"discord:{normalized_id}",
        f"whatsapp:{normalized_id}",
        f"web:{normalized_id}",
    ]
    
    sessions = db.query(ChatSession).filter(
        ChatSession.tenant_id == tenant.id,
        ChatSession.user_identifier.in_(possible_identifiers)
    ).order_by(ChatSession.created_at.desc()).all()
    
    session_list = []
    for session in sessions:
        message_count = db.query(ChatMessage).filter(
            ChatMessage.session_id == session.id
        ).count()
        
        session_list.append({
            "session_id": session.session_id,
            "user_identifier": session.user_identifier,
            "platform": session.platform or "web",
            "created_at": session.created_at.isoformat(),
            "is_active": session.is_active,
            "message_count": message_count
        })
    
    return {
        "user_identifier": user_identifier,
        "total_sessions": len(session_list),
        "sessions": session_list
    }

@router.post("/memory/cleanup")
async def cleanup_old_conversations(
    days_old: int = 30,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Clean up old conversation sessions"""
    engine = ChatbotEngine(db)
    tenant = engine._get_tenant_by_api_key(api_key)
    if not tenant:
        raise HTTPException(status_code=403, detail="Invalid API key")
    
    memory = EnhancedChatbotMemory(db, tenant.id)
    cleaned_sessions = memory.cleanup_old_sessions(days_old)
    
    return {"message": f"Cleaned up {cleaned_sessions} old sessions"}

@router.get("/memory/stats")
async def get_memory_stats(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get overall memory system statistics for the tenant"""
    engine = ChatbotEngine(db)
    tenant = engine._get_tenant_by_api_key(api_key)
    if not tenant:
        raise HTTPException(status_code=403, detail="Invalid API key")
    
    # Get overall stats
    total_sessions = db.query(ChatSession).filter(
        ChatSession.tenant_id == tenant.id
    ).count()
    
    active_sessions = db.query(ChatSession).filter(
        ChatSession.tenant_id == tenant.id,
        ChatSession.is_active == True
    ).count()
    
    total_messages = db.query(ChatMessage).join(ChatSession).filter(
        ChatSession.tenant_id == tenant.id
    ).count()
    
    # Platform breakdown
    platform_stats = db.query(
        ChatSession.platform,
        db.func.count(ChatSession.id).label('count')
    ).filter(
        ChatSession.tenant_id == tenant.id
    ).group_by(ChatSession.platform).all()
    
    platform_breakdown = {stat.platform or "web": stat.count for stat in platform_stats}
    
    return {
        "tenant_id": tenant.id,
        "total_sessions": total_sessions,
        "active_sessions": active_sessions,
        "total_messages": total_messages,
        "platform_breakdown": platform_breakdown,
        "generated_at": datetime.now().isoformat()
    }


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