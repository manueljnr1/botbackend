

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
import logging
import os

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



@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest, 
    api_key: str = Header(..., alias="X-API-Key"), 
    db: Session = Depends(get_db)
):
    """
    Send a message to the chatbot and get a response
    Optionally specify a language code to receive responses in that language
    """
    logger.info(f"Processing chat request with API key: {api_key[:3]}...")
    
    engine = ChatbotEngine(db)
    result = engine.process_message_with_language(
        api_key=api_key,
        user_message=request.message,
        user_identifier=request.user_identifier,
        target_language=request.language
    )
    if not result.get("success"):
        logger.error(f"Error processing message: {result.get('error', 'Unknown error')}")
        raise HTTPException(status_code=400, detail=result.get("error", "Unknown error"))
    
    return result



# Add a simple test endpoint
@router.get("/ping")
async def ping():
    """
    Simple endpoint to test if the router is working
    """
    return {"message": "Chatbot router is working!"}




#-------------LANGUAGE SUPPORT  ENDPOINTS----------------

# @router.get("/languages", response_model=List[SupportedLanguage])
# async def get_supported_languages():
#     """
#     Get a list of supported languages
#     """
#     return [
#         {"code": code, "name": name}
#         for code, name in SUPPORTED_LANGUAGES.items()
#     ]


# @router.post("/language/{session_id}")
# async def set_session_language(
#     session_id: str,
#     language: str,
#     api_key: str = Header(..., alias="X-API-Key"),
#     db: Session = Depends(get_db)
# ):
#     """
#     Set the language for a chat session
#     """
    # # Verify the language code
    # if language not in SUPPORTED_LANGUAGES:
    #     raise HTTPException(status_code=400, detail=f"Unsupported language code: {language}")
    
    # # Verify the API key and get tenant
    # engine = ChatbotEngine(db)
    # tenant = engine._get_tenant_by_api_key(api_key)
    # if not tenant:
    #     raise HTTPException(status_code=403, detail="Invalid API key")
    
    # # Get session
    # session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    # if not session or session.tenant_id != tenant.id:
    #     raise HTTPException(status_code=404, detail="Session not found")
    
    # # Update session language
    # session.language_code = language
    # db.commit()
    
    # return {
    #     "message": f"Session language set to {SUPPORTED_LANGUAGES[language]} ({language})"
    # }
