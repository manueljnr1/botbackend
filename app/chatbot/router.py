from fastapi import APIRouter, Depends, HTTPException, Header, BackgroundTasks, Request, Form
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
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
from app.config import settings


from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
import json
from app.database import get_db
from app.chatbot.engine import ChatbotEngine
from app.chatbot.models import ChatSession, ChatMessage
from app.knowledge_base.models import FAQ 
from app.utils.language_service import language_service, SUPPORTED_LANGUAGES
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




# def should_generate_admin_followups_llm(user_question: str, bot_response: str, company_name: str, action: str = None) -> tuple[bool, List[str]]:
#     """
#     Use LLM to intelligently decide if admin follow-ups are needed and generate them
#     """
#     from langchain_openai import ChatOpenAI
#     from langchain.prompts import PromptTemplate
    
#     prompt = PromptTemplate(
#         input_variables=["user_question", "bot_response", "company_name", "action"],
#         template="""You are an expert admin assistant analyst. Analyze this admin interaction and decide if follow-up questions would be helpful.

# USER QUESTION: "{user_question}"
# BOT RESPONSE: "{bot_response}"
# COMPANY: {company_name}
# ACTION PERFORMED: {action}

# INSTRUCTIONS:
# 1. Determine if follow-up questions would help the admin continue their work
# 2. If YES, suggest 1-3 relevant admin follow-up questions
# 3. If NO, respond with "NO_FOLLOWUPS"

# Admin Context - Generate follow-ups for:
# - FAQ management tasks that might need continuation
# - Analytics requests that could be expanded
# - Settings changes that might need additional configuration
# - Complex admin procedures with multiple steps

# DON'T generate follow-ups for:
# - Simple greetings or acknowledgments
# - Complete error responses
# - Very short admin confirmations

# Format response as:
# DECISION: YES/NO
# FOLLOWUPS:
# 1. First admin follow-up question (if any)
# 2. Second admin follow-up question (if any)  
# 3. Third admin follow-up question (if any)

# Response:"""
#     )
    
#     try:
#         llm = ChatOpenAI(
#             model_name="gpt-3.5-turbo", 
#             temperature=0.3,
#             openai_api_key=settings.OPENAI_API_KEY
#         )
        
#         result = llm.invoke(prompt.format(
#             user_question=user_question,
#             bot_response=bot_response,
#             company_name=company_name,
#             action=action or "unknown"
#         ))
        
#         response_text = result.content if hasattr(result, 'content') else str(result)
        
#         # Parse LLM response
#         if "DECISION: NO" in response_text or "NO_FOLLOWUPS" in response_text:
#             logger.info(f"🤖 LLM decided NO admin follow-ups needed")
#             return False, []
        
#         # Extract follow-up questions
#         followups = []
#         lines = response_text.split('\n')
#         for line in lines:
#             if re.match(r'^\d+\.', line.strip()):
#                 followup = re.sub(r'^\d+\.\s*', '', line.strip())
#                 if followup:
#                     followups.append(followup)
        
#         if followups:
#             logger.info(f"🤖 LLM generated {len(followups)} admin follow-ups")
#             return True, followups[:3]  # Max 3
#         else:
#             return False, []
            
#     except Exception as e:
#         logger.error(f"Error in LLM admin follow-up generation: {e}")
#         # Fallback to simple admin rules
#         return should_generate_admin_followups_simple(user_question, bot_response, action)

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
        result = engine.process_message(api_key, request.message, request.user_identifier)
        
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
            check_conversation_limit_dependency_with_super_tenant(tenant.id, db)  # UPDATED
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
        check_conversation_limit_dependency_with_super_tenant(tenant.id, db)
        
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
        check_conversation_limit_dependency_with_super_tenant(tenant.id, db)  # UPDATED
        
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
    





# Add a specific model for the enhanced smart request
class SmartChatStreamingRequest(BaseModel):
    message: str
    user_identifier: str
    max_context: int = 20
    enable_streaming: bool = True

# You could also create a dedicated streaming endpoint that's more explicit
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

class IncidentReviewRequest(BaseModel):
    reviewer_notes: Optional[str] = None

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

class SecuritySettingsRequest(BaseModel):
    security_level: str = "standard"  # standard, strict, custom
    allow_custom_prompts: bool = True
    security_notifications_enabled: bool = True

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




# @router.post("/chat/smart")
# async def smart_chat_with_followup_streaming(
#     request: SmartChatRequest,
#     api_key: str = Header(..., alias="X-API-Key"),
#     db: Session = Depends(get_db)
# ):
#     """
#     Smart chat with instant main response + streamed follow-up suggestions
#     NOW WITH: Intelligent topic change detection using LLM
#     """
    
#     async def stream_with_followups():
#         try:
#             logger.info(f"🚀 Smart chat with follow-up streaming + context analysis for: {request.user_identifier}")
            
#             # Get tenant and check limits
#             tenant = get_tenant_from_api_key(api_key, db)
#             check_conversation_limit_dependency_with_super_tenant(tenant.id, db)
            
#             # Initialize chatbot engine FIRST
#             engine = ChatbotEngine(db)
            
#             # Auto-generate user ID if needed
#             user_id = request.user_identifier
#             auto_generated = False
            
#             if not user_id or user_id.startswith('temp_') or user_id.startswith('session_'):
#                 user_id = f"auto_{str(uuid.uuid4())}"
#                 auto_generated = True
            
#             # Send initial metadata
#             yield f"{json.dumps({'type': 'metadata', 'user_id': user_id, 'auto_generated': auto_generated})}\n"
            
#             # Get conversation history for context analysis
#             from app.chatbot.simple_memory import SimpleChatbotMemory
#             memory = SimpleChatbotMemory(db, tenant.id)
#             conversation_history = memory.get_conversation_history(user_id, request.max_context)
            
#             # NEW: Analyze conversation context with LLM - USE ENGINE METHOD
#             context_analysis = None
#             topic_change_response = None

#             if conversation_history and len(conversation_history) > 1:
#                 # Call the method from the engine instance
#                 context_analysis = engine.analyze_conversation_context_llm(
#                     request.message, 
#                     conversation_history, 
#                     tenant.name
#                 )
                
#                 logger.info(f"🧠 Context analysis: {context_analysis.get('type')} - {context_analysis.get('reasoning', 'N/A')}")
                
#                 # Handle greeting types AND conversation questions
#                 special_handling_types = ['RECENT_GREETING', 'FRESH_GREETING', 'SIMPLE_GREETING', 'CONVERSATION_SUMMARY', 'CONVERSATION_SUMMARY_FALLBACK']
                
#                 if context_analysis and context_analysis.get('type') in special_handling_types:
#                     logger.info(f"🔄 Detected special handling type: {context_analysis.get('type')}")
                    
#                     # Generate appropriate response
#                     topic_change_response = engine.handle_topic_change_response(
#                         request.message,
#                         context_analysis.get('previous_topic', ''),
#                         context_analysis.get('suggested_approach', ''),
#                         tenant.name,
#                         context_analysis  # Pass the full analysis
#                     )
                    
#                     if topic_change_response and len(topic_change_response.strip()) > 0:
#                         logger.info(f"🔄 Generated response: {topic_change_response[:50]}...")
#                     else:
#                         logger.info(f"🔄 No response generated, proceeding normally")
#                         topic_change_response = None
#                 else:
#                     logger.info(f"🔄 Normal processing for type: {context_analysis.get('type', 'UNKNOWN')}")
            
#             # If greeting detected, send that response instead
#             if topic_change_response:
#                 logger.info(f"🔄 Sending greeting response")
                
#                 # Store the conversation in memory
#                 session_id, _ = memory.get_or_create_session(user_id, "web")
#                 memory.store_message(session_id, request.message, True)
#                 memory.store_message(session_id, topic_change_response, False)
                
#                 # Send greeting response as main response
#                 main_response = {
#                     'type': 'main_response',
#                     'content': topic_change_response,
#                     'session_id': session_id,
#                     'answered_by': 'GREETING_DETECTION',
#                     'context_analysis': context_analysis
#                 }
#                 yield f"{json.dumps(main_response)}\n"
                
#                 # Wait a moment, then ask clarifying follow-up
#                 await asyncio.sleep(1.5)
                
#                 clarifying_followup = {
#                     'type': 'followup',
#                     'content': "What would you like help with?",
#                     'index': 0,
#                     'is_last': True
#                 }
#                 yield f"{json.dumps(clarifying_followup)}\n"
                
#                 # Send completion
#                 yield f"{json.dumps({'type': 'complete', 'total_followups': 1, 'greeting_handled': True})}\n"
                
#                 # Track conversation
#                 track_conversation_started_with_super_tenant(
#                     tenant_id=tenant.id,
#                     user_identifier=user_id,
#                     platform="web",
#                     db=db
#                 )
                
#                 return
            
#             # Continue with normal processing if no greeting
#             result = engine.process_web_message_with_advanced_feedback_llm(
#                 api_key=api_key,
#                 user_message=request.message,
#                 user_identifier=user_id,
#                 max_context=request.max_context,
#                 use_smart_llm=True
#             )
            
#             if not result.get("success"):
#                 logger.error(f"❌ Smart chat failed: {result.get('error')}")
#                 yield f"{json.dumps({'type': 'error', 'error': result.get('error')})}\n"
#                 return
            
#             logger.info("✅ Chatbot response received successfully")
            
#             # Track conversation
#             track_conversation_started_with_super_tenant(
#                 tenant_id=tenant.id,
#                 user_identifier=user_id,
#                 platform="web",
#                 db=db
#             )
            
#             # Send main response INSTANTLY
#             main_response = {
#                 'type': 'main_response',
#                 'content': result["response"],
#                 'session_id': result.get('session_id'),
#                 'answered_by': result.get('answered_by'),
#                 'email_captured': result.get('email_captured', False),
#                 'feedback_triggered': result.get('feedback_triggered', False),
#                 'context_analysis': context_analysis  # Include analysis in response
#             }
#             yield f"{json.dumps(main_response)}\n"
            
#             # Wait before follow-ups
#             await asyncio.sleep(1.5)
            
#             # Generate and stream follow-up suggestions using LLM
#             should_generate, followups = should_generate_followups_llm(
#                 request.message, 
#                 result["response"], 
#                 tenant.name
#             )
            
#             if should_generate and followups:
#                 for i, followup in enumerate(followups):
#                     if i > 0:
#                         delay = calculate_followup_delay(followup)
#                         await asyncio.sleep(delay)
                    
#                     followup_data = {
#                         'type': 'followup',
#                         'content': followup,
#                         'index': i,
#                         'is_last': i == len(followups) - 1
#                     }
#                     yield f"{json.dumps(followup_data)}\n"
            
#             # Send completion signal
#             yield f"{json.dumps({'type': 'complete', 'total_followups': len(followups) if followups else 0})}\n"
            
#             logger.info(f"✅ Smart chat with follow-ups + context analysis completed")
            
#         except HTTPException as e:
#             logger.error(f"🚫 HTTP error in smart chat: {e.detail}")
#             yield f"{json.dumps({'type': 'error', 'error': e.detail, 'status_code': e.status_code})}\n"
#         except Exception as e:
#             logger.error(f"💥 Error in smart follow-up streaming: {str(e)}")
#             import traceback
#             logger.error(traceback.format_exc())
#             yield f"{json.dumps({'type': 'error', 'error': str(e)})}\n"
    
#     return StreamingResponse(
#         stream_with_followups(),
#         media_type="application/x-ndjson",
#         headers={
#             "Cache-Control": "no-cache",
#             "Connection": "keep-alive",
#             "X-Accel-Buffering": "no"
#         }
#     )


@router.post("/chat/smart")
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






# @router.post("/chat/super-tenant-admin")
# async def super_tenant_admin_chat(
#     request: SmartChatRequest,
#     tenant_api_key: str = Header(..., alias="X-Tenant-API-Key"),
#     chatbot_api_key: str = Header(..., alias="X-Chatbot-API-Key"),
#     super_tenant_context: str = Header(None, alias="X-Super-Tenant-Context"),
#     db: Session = Depends(get_db)
# ):
#     """
#     Super Tenant Admin Chat with Full LLM Intelligence
#     Routes ALL interactions through LLM - no hardcoded responses
#     """
    
#     async def stream_admin_response():
#         try:
#             logger.info(f"🤖 LLM-powered admin chat: {request.message[:50]}...")
            
#             # Security validation
#             if super_tenant_context != "super_tenant_official_widget":
#                 logger.warning(f"🚨 Unauthorized admin access attempt")
#                 yield f"{json.dumps({'type': 'error', 'error': 'Admin features not available in this context', 'status_code': 403})}\n"
#                 return
            
#             # Validate chatbot owner is super tenant
#             try:
#                 chatbot_owner = get_tenant_from_api_key(chatbot_api_key, db)
#                 SUPER_TENANT_IDS = [324112833]
                
#                 if not getattr(chatbot_owner, 'is_super_tenant', False) and chatbot_owner.id not in SUPER_TENANT_IDS:
#                     logger.warning(f"🚨 Unauthorized super tenant access: {chatbot_owner.id}")
#                     yield f"{json.dumps({'type': 'error', 'error': 'Unauthorized chatbot host', 'status_code': 403})}\n"
#                     return
                    
#             except Exception as e:
#                 logger.error(f"❌ Invalid chatbot API key: {str(e)}")
#                 yield f"{json.dumps({'type': 'error', 'error': 'Invalid chatbot credentials', 'status_code': 403})}\n"
#                 return
            
#             # Authenticate admin tenant
#             try:
#                 tenant = get_tenant_from_api_key(tenant_api_key, db)
#                 check_conversation_limit_dependency_with_super_tenant(tenant.id, db)
                
#                 if not tenant.is_active:
#                     yield f"{json.dumps({'type': 'error', 'error': 'Account inactive', 'status_code': 403})}\n"
#                     return
                    
#             except Exception as e:
#                 logger.error(f"❌ Tenant authentication failed: {str(e)}")
#                 yield f"{json.dumps({'type': 'error', 'error': 'Authentication failed', 'status_code': 403})}\n"
#                 return
            
#             # Auto-generate user ID
#             user_id = request.user_identifier
#             auto_generated = False
            
#             if not user_id or user_id.startswith('temp_') or user_id.startswith('session_'):
#                 user_id = f"admin_auto_{str(uuid.uuid4())}"
#                 auto_generated = True
            
#             # Send metadata
#             yield f"{json.dumps({'type': 'metadata', 'user_id': user_id, 'auto_generated': auto_generated, 'admin_mode': True, 'tenant_id': tenant.id, 'super_tenant_name': chatbot_owner.name})}\n"
            
#             # Initialize memory for conversation context
#             from app.chatbot.simple_memory import SimpleChatbotMemory
#             memory = SimpleChatbotMemory(db, tenant.id)
#             conversation_history = memory.get_conversation_history(user_id, request.max_context)
            
#             # **SMART CHAT INTEGRATION: Use conversation context analysis like smart chat**
#             context_analysis = None
#             topic_change_response = None
            
#             # Initialize chatbot engine for FAQ/KB checking
#             engine = ChatbotEngine(db)

#             if conversation_history and len(conversation_history) > 1:
#                 # Call the method from the engine instance (same as smart chat)
#                 context_analysis = engine.analyze_conversation_context_llm(
#                     request.message, 
#                     conversation_history, 
#                     tenant.name
#                 )
                
#                 logger.info(f"🧠 Admin context analysis: {context_analysis.get('type')} - {context_analysis.get('reasoning', 'N/A')}")
                
#                 # Handle greeting types AND conversation questions (same as smart chat)
#                 special_handling_types = ['RECENT_GREETING', 'FRESH_GREETING', 'SIMPLE_GREETING', 'CONVERSATION_SUMMARY', 'CONVERSATION_SUMMARY_FALLBACK']
                
#                 if context_analysis and context_analysis.get('type') in special_handling_types:
#                     logger.info(f"🔄 Detected special handling type: {context_analysis.get('type')}")
                    
#                     # Generate appropriate response (same as smart chat)
#                     topic_change_response = engine.handle_topic_change_response(
#                         request.message,
#                         context_analysis.get('previous_topic', ''),
#                         context_analysis.get('suggested_approach', ''),
#                         tenant.name,
#                         context_analysis
#                     )
                    
#                     if topic_change_response and len(topic_change_response.strip()) > 0:
#                         logger.info(f"🔄 Generated admin greeting response: {topic_change_response[:50]}...")
#                     else:
#                         topic_change_response = None

#             # If greeting detected, send that response instead (same as smart chat)
#             if topic_change_response:
#                 logger.info(f"🔄 Sending admin greeting response")
                
#                 # Store the conversation in memory
#                 session_id, _ = memory.get_or_create_session(user_id, "admin_web")
#                 memory.store_message(session_id, request.message, True)
#                 memory.store_message(session_id, topic_change_response, False)
                
#                 # Send greeting response as main response
#                 main_response = {
#                     'type': 'main_response',
#                     'content': topic_change_response,
#                     'session_id': session_id,
#                     'answered_by': 'ADMIN_GREETING_DETECTION',
#                     'context_analysis': context_analysis,
#                     'admin_mode': True,
#                     'tenant_id': tenant.id
#                 }
#                 yield f"{json.dumps(main_response)}\n"
                
#                 # Wait a moment, then ask clarifying follow-up
#                 await asyncio.sleep(1.5)
                
#                 clarifying_followup = {
#                     'type': 'followup',
#                     'content': "What would you like help with?",
#                     'index': 0,
#                     'is_last': True
#                 }
#                 yield f"{json.dumps(clarifying_followup)}\n"
                
#                 # Send completion
#                 yield f"{json.dumps({'type': 'complete', 'total_followups': 1, 'admin_greeting_handled': True})}\n"
                
#                 # Track conversation
#                 track_conversation_started_with_super_tenant(
#                     tenant_id=tenant.id,
#                     user_identifier=user_id,
#                     platform="admin_web",
#                     db=db
#                 )
                
#                 return

#             # **CRITICAL: Analyze message to determine admin vs normal chatbot response**
#             admin_context_analysis = await analyze_admin_message_with_llm(
#                 request.message, 
#                 conversation_history, 
#                 tenant,
#                 chatbot_owner
#             )
            
#             # **KEY DECISION: Route based on LLM analysis**
#             if admin_context_analysis.get('requires_admin_engine', True):
#                 # Use admin engine for specific admin tasks
#                 admin_engine = get_super_tenant_admin_engine(db)
                
#                 result = admin_engine.process_admin_message(
#                     user_message=request.message,
#                     authenticated_tenant_id=tenant.id,
#                     user_identifier=user_id,
#                     session_context={
#                         "admin_mode": True, 
#                         "super_tenant_hosted": True, 
#                         "chatbot_owner_id": chatbot_owner.id,
#                         "llm_context": admin_context_analysis
#                     }
#                 )
                
#                 if not result.get("success"):
#                     logger.error(f"❌ Admin engine failed: {result.get('error')}")
#                     yield f"{json.dumps({'type': 'error', 'error': result.get('error')})}\n"
#                     return
                
#                 # Store conversation
#                 session_id, _ = memory.get_or_create_session(user_id, "admin_web")
#                 memory.store_message(session_id, request.message, True)
#                 memory.store_message(session_id, result["response"], False)
                
#                 # Send main response
#                 main_response = {
#                     'type': 'main_response',
#                     'content': result.get("response", ""),
#                     'session_id': session_id,
#                     'answered_by': result.get('action', 'ADMIN_ENGINE'),
#                     'action': result.get('action'),
#                     'requires_confirmation': result.get('requires_confirmation', False),
#                     'requires_input': result.get('requires_input', False),
#                     'admin_mode': True,
#                     'tenant_id': tenant.id,
#                     'context_analysis': context_analysis
#                 }
                
#             else:
#                 # **SMART CHAT CORE: Use the EXACT same FAQ/KB processing as smart chat**
#                 logger.info(f"🔍 Using smart chat FAQ/KB processing for admin context")
                
#                 result = engine.process_web_message_with_advanced_feedback_llm(
#                     api_key=tenant_api_key,  # Use tenant's API key
#                     user_message=request.message,
#                     user_identifier=user_id,
#                     max_context=request.max_context,
#                     use_smart_llm=True  # Same as smart chat
#                 )
                
#                 if not result.get("success"):
#                     logger.error(f"❌ Smart chat processing failed: {result.get('error')}")
#                     yield f"{json.dumps({'type': 'error', 'error': result.get('error')})}\n"
#                     return
                
#                 # Enhanced response with admin context
#                 main_response = {
#                     'type': 'main_response',
#                     'content': result["response"],
#                     'session_id': result.get('session_id'),
#                     'answered_by': f"ADMIN_{result.get('answered_by', 'CHATBOT')}",
#                     'email_captured': result.get('email_captured', False),
#                     'feedback_triggered': result.get('feedback_triggered', False),
#                     'faq_matched': result.get('faq_matched', False),
#                     'admin_mode': True,
#                     'tenant_id': tenant.id,
#                     'context_analysis': context_analysis,
#                     'admin_context_analysis': admin_context_analysis
#                 }
            
#             yield f"{json.dumps(main_response)}\n"
            
#             # Track conversation
#             track_conversation_started_with_super_tenant(
#                 tenant_id=tenant.id,
#                 user_identifier=user_id,
#                 platform="admin_web",
#                 db=db
#             )
            
#             # Generate intelligent follow-ups using LLM (same logic as smart chat)
#             await asyncio.sleep(1.5)
            
#             # Use the SAME follow-up generation as smart chat
#             should_generate, followups = should_generate_followups_llm(
#                 request.message, 
#                 main_response['content'], 
#                 tenant.name
#             )
            
#             # If no regular follow-ups, generate admin-specific ones
#             if not (should_generate and followups):
#                 admin_followups = await generate_admin_followups_llm(
#                     request.message,
#                     main_response['content'],
#                     tenant,
#                     admin_context_analysis
#                 )
#                 followups = admin_followups
#                 should_generate = bool(followups)
            
#             # Stream follow-ups (same as smart chat)
#             if should_generate and followups:
#                 for i, followup in enumerate(followups):
#                     if i > 0:
#                         await asyncio.sleep(calculate_followup_delay(followup))
                    
#                     followup_data = {
#                         'type': 'followup',
#                         'content': followup,
#                         'index': i,
#                         'is_last': i == len(followups) - 1,
#                         'admin_followup': True
#                     }
#                     yield f"{json.dumps(followup_data)}\n"
            
#             # Send completion (same as smart chat)
#             yield f"{json.dumps({'type': 'complete', 'total_followups': len(followups) if followups else 0, 'admin_enhanced': True})}\n"
            
#         except HTTPException as e:
#             logger.error(f"🚫 HTTP error: {e.detail}")
#             yield f"{json.dumps({'type': 'error', 'error': e.detail, 'status_code': e.status_code})}\n"
#         except Exception as e:
#             logger.error(f"💥 Error: {str(e)}")
#             yield f"{json.dumps({'type': 'error', 'error': str(e)})}\n"
    
#     return StreamingResponse(
#         stream_admin_response(),
#         media_type="application/x-ndjson",
#         headers={
#             "Cache-Control": "no-cache",
#             "Connection": "keep-alive",
#             "X-Accel-Buffering": "no"
#         }
#     )




@router.post("/chat/super-tenant-admin")
async def super_tenant_admin_chat(
    request: SmartChatRequest,
    tenant_api_key: str = Header(..., alias="X-Tenant-API-Key"),
    chatbot_api_key: str = Header(..., alias="X-Chatbot-API-Key"),
    super_tenant_context: str = Header(None, alias="X-Super-Tenant-Context"),
    db: Session = Depends(get_db)
):
    """
    Super Tenant Admin Chat with intelligent delay simulation
    """
    
    async def stream_admin_response():
        try:
            logger.info(f"🤖 Admin chat with delay simulation: {request.message[:50]}...")
            
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
            yield f"{json.dumps({'type': 'metadata', 'user_id': user_id, 'auto_generated': auto_generated, 'admin_mode': True, 'tenant_id': tenant.id, 'super_tenant_name': chatbot_owner.name})}\n"
            
            # Initialize memory and context analysis
            from app.chatbot.simple_memory import SimpleChatbotMemory
            memory = SimpleChatbotMemory(db, tenant.id)
            conversation_history = memory.get_conversation_history(user_id, request.max_context)
            
            # ⭐ NEW: Initialize delay simulator for admin
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
                    'response_delay': response_delay if delay_simulator else 0
                }
                yield f"{json.dumps(main_response)}\n"
                
                # Natural follow-up delay for admin
                followup_delay = 2.2 + random.uniform(0.3, 0.8)  # 2.2-3.0s for admin
                await asyncio.sleep(followup_delay)
                
                clarifying_followup = {
                    'type': 'followup',
                    'content': "What would you like help with?",
                    'index': 0,
                    'is_last': True
                }
                yield f"{json.dumps(clarifying_followup)}\n"
                
                yield f"{json.dumps({'type': 'complete', 'total_followups': 1, 'admin_greeting_handled': True})}\n"
                
                track_conversation_started_with_super_tenant(
                    tenant_id=tenant.id,
                    user_identifier=user_id,
                    platform="admin_web",
                    db=db
                )
                
                return

            # ⭐ ENHANCED: Analyze admin message context
            admin_context_analysis = await analyze_admin_message_with_llm(
                request.message, 
                conversation_history, 
                tenant,
                chatbot_owner
            )
            
            # ⭐ Process admin message with timing
            start_time = time.time()
            
            if admin_context_analysis.get('requires_admin_engine', True):
                # Use admin engine
                admin_engine = get_super_tenant_admin_engine(db)
                
                result = admin_engine.process_admin_message(
                    user_message=request.message,
                    authenticated_tenant_id=tenant.id,
                    user_identifier=user_id,
                    session_context={
                        "admin_mode": True, 
                        "super_tenant_hosted": True, 
                        "chatbot_owner_id": chatbot_owner.id,
                        "llm_context": admin_context_analysis
                    }
                )
                
                if not result.get("success"):
                    logger.error(f"❌ Admin engine failed: {result.get('error')}")
                    yield f"{json.dumps({'type': 'error', 'error': result.get('error')})}\n"
                    return
                
                session_id, _ = memory.get_or_create_session(user_id, "admin_web")
                memory.store_message(session_id, request.message, True)
                memory.store_message(session_id, result["response"], False)
                
                # ⭐ Calculate admin-specific delay
                response_delay = 0
                if delay_simulator:
                    # Admin responses tend to be more complex, slight bias toward longer delays
                    base_delay = delay_simulator.calculate_response_delay(request.message, result["response"])
                    admin_complexity_bonus = 0.3  # 300ms bonus for admin operations
                    response_delay = min(5.0, base_delay + admin_complexity_bonus)
                    
                    processing_time = time.time() - start_time
                    actual_delay = max(0.3, response_delay - processing_time)  # Min 300ms for admin
                    
                    logger.info(f"⏱️ Admin delay: {response_delay:.2f}s, Processing: {processing_time:.2f}s, Actual: {actual_delay:.2f}s")
                    await asyncio.sleep(actual_delay)
                
                main_response = {
                    'type': 'main_response',
                    'content': result.get("response", ""),
                    'session_id': session_id,
                    'answered_by': result.get('action', 'ADMIN_ENGINE'),
                    'action': result.get('action'),
                    'requires_confirmation': result.get('requires_confirmation', False),
                    'requires_input': result.get('requires_input', False),
                    'admin_mode': True,
                    'tenant_id': tenant.id,
                    'context_analysis': context_analysis,
                    'response_delay': response_delay
                }
                
            else:
                # Use smart chat processing with admin context
                logger.info(f"🔍 Using smart chat processing for admin context")
                
                result = engine.process_web_message_with_advanced_feedback_llm(
                    api_key=tenant_api_key,
                    user_message=request.message,
                    user_identifier=user_id,
                    max_context=request.max_context,
                    use_smart_llm=True
                )
                
                if not result.get("success"):
                    logger.error(f"❌ Smart chat processing failed: {result.get('error')}")
                    yield f"{json.dumps({'type': 'error', 'error': result.get('error')})}\n"
                    return
                
                # ⭐ Calculate delay for smart admin response
                response_delay = 0
                if delay_simulator:
                    response_delay = delay_simulator.calculate_response_delay(request.message, result["response"])
                    processing_time = time.time() - start_time
                    actual_delay = max(0.2, response_delay - processing_time)
                    
                    logger.info(f"⏱️ Smart admin delay: {response_delay:.2f}s, Actual: {actual_delay:.2f}s")
                    await asyncio.sleep(actual_delay)
                
                main_response = {
                    'type': 'main_response',
                    'content': result["response"],
                    'session_id': result.get('session_id'),
                    'answered_by': f"ADMIN_{result.get('answered_by', 'CHATBOT')}",
                    'email_captured': result.get('email_captured', False),
                    'feedback_triggered': result.get('feedback_triggered', False),
                    'faq_matched': result.get('faq_matched', False),
                    'admin_mode': True,
                    'tenant_id': tenant.id,
                    'context_analysis': context_analysis,
                    'admin_context_analysis': admin_context_analysis,
                    'response_delay': response_delay
                }
            
            yield f"{json.dumps(main_response)}\n"
            
            # Track conversation
            track_conversation_started_with_super_tenant(
                tenant_id=tenant.id,
                user_identifier=user_id,
                platform="admin_web",
                db=db
            )
            
            # ⭐ ENHANCED: Admin follow-up timing
            base_admin_delay = 2.0 + random.uniform(0.4, 1.0)  # 2.0-3.0s for admin follow-ups
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
                    admin_context_analysis
                )
                followups = admin_followups
                should_generate = bool(followups)
            
            # Stream follow-ups with admin timing
            if should_generate and followups:
                for i, followup in enumerate(followups):
                    if i > 0:
                        # ⭐ Admin-appropriate inter-followup delays
                        inter_delay = 1.0 + random.uniform(0.2, 0.6)  # 1.0-1.6s between admin follow-ups
                        await asyncio.sleep(inter_delay)
                    
                    followup_data = {
                        'type': 'followup',
                        'content': followup,
                        'index': i,
                        'is_last': i == len(followups) - 1,
                        'admin_followup': True
                    }
                    yield f"{json.dumps(followup_data)}\n"
            
            # Send completion
            yield f"{json.dumps({'type': 'complete', 'total_followups': len(followups) if followups else 0, 'admin_enhanced': True, 'delay_simulation': True})}\n"
            
        except HTTPException as e:
            logger.error(f"🚫 HTTP error: {e.detail}")
            yield f"{json.dumps({'type': 'error', 'error': e.detail, 'status_code': e.status_code})}\n"
        except Exception as e:
            logger.error(f"💥 Error: {str(e)}")
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