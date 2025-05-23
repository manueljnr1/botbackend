

from fastapi import APIRouter, Depends, HTTPException, Header, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
import logging
import os
import asyncio
import random
import time
import re


from fastapi.responses import StreamingResponse
import json



from app.database import get_db
from app.chatbot.engine import ChatbotEngine
from app.chatbot.models import ChatSession, ChatMessage
from app.utils.language_service import language_service, SUPPORTED_LANGUAGES

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
    
    total_delay = typing_time + thinking_pause + end_pause
    
    # Add human variation
    total_delay *= random.uniform(0.8, 1.3)
    
    # Set bounds (1-6 seconds per sentence)
    return max(1.0, min(total_delay, 6.0))


# Chat endpoint
@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, api_key: str = Header(..., alias="X-API-Key"), db: Session = Depends(get_db)):
    """
    Send a message to the chatbot and get a response
    """
    try:
        # Debug - Log the API key being used
        logger.info(f"Processing chat request with API key: {api_key[:5]}...")
        
        
        # Initialize chatbot engine
        engine = ChatbotEngine(db)
        
        # Process message
        result = engine.process_message(api_key, request.message, request.user_identifier)
        
        if not result.get("success"):
            error_message = result.get("error", "Unknown error")
            logger.error(f"Chatbot error: {error_message}")
            
            # Handle OpenAI API key errors differently
            if "Incorrect API key provided" in error_message or "invalid_api_key" in error_message:
                logger.error("OpenAI API key error detected - using hardcoded key instead")
                
                # Try again with hardcoded API key
                # os.environ["OPENAI_API_KEY"]  # Replace with your valid key
                
                # Process message again
                result = engine.process_message(api_key, request.message, request.user_identifier)
                
                if result.get("success"):
                    return result
            
            # If we still have an error, raise an exception
            raise HTTPException(status_code=400, detail=error_message)
        
        return result
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}")
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




# Add this new endpoint anywhere in your router.py file
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
            
            logger.info(f"Initial thinking delay: {initial_delay:.2f} seconds")
            
            # Send thinking indicator
            yield f"{json.dumps({'type': 'thinking', 'delay': initial_delay})}\\n"
            await asyncio.sleep(initial_delay)
            
            # Get response
            engine = ChatbotEngine(db)
            result = engine.process_message(
                api_key=api_key,
                user_message=request.message,
                user_identifier=request.user_identifier
            )
            
            if not result.get("success"):
                yield f"{json.dumps({'type': 'error', 'error': result.get('error')})}\\n"
                return
            
            # Break into sentences
            full_response = result["response"]
            sentences = break_into_sentences(full_response)
            logger.info(f"Split into {len(sentences)} sentences")
            
            # Send start signal
            yield f"{json.dumps({'type': 'start', 'session_id': result.get('session_id'), 'total_sentences': len(sentences)})}\\n"
            
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
                
                yield f"{json.dumps(sentence_data)}\\n"
                logger.info(f"Sent sentence {i+1}/{len(sentences)}: '{sentence[:50]}...' (delay: {typing_delay:.2f}s)")
            
            # Send completion
            completion_data = {
                'type': 'complete',
                'session_id': result.get('session_id'),
                'total_time': time.time() - start_time,
                'sentences_sent': len(sentences)
            }
            yield f"{json.dumps(completion_data)}\\n"
            
        except Exception as e:
            logger.error(f"Error in sentence streaming: {str(e)}")
            yield f"{json.dumps({'type': 'error', 'error': str(e)})}\\n"
    
    return StreamingResponse(
        stream_sentences(),
        media_type="application/x-ndjson",  # Changed from text/event-stream
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )