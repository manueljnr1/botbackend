# from fastapi import APIRouter, Depends, HTTPException, Header
# from sqlalchemy.orm import Session
# from typing import List, Optional
# from pydantic import BaseModel
# import sqlite3
# import hashlib
# import os

# # Import OpenAI with error handling
# try:
#     import openai
#     OPENAI_AVAILABLE = True
#     # Check OpenAI version to determine client initialization
#     OPENAI_VERSION = openai.__version__ if hasattr(openai, "__version__") else "unknown"
#     print(f"OpenAI version: {OPENAI_VERSION}")
# except ImportError:
#     OPENAI_AVAILABLE = False
#     OPENAI_VERSION = "not installed"
#     print("⚠️ Warning: OpenAI package not installed. Using simple matching instead.")

# from app.database import get_db

# router = APIRouter()

# # Initialize OpenAI client based on version
# client = None
# if OPENAI_AVAILABLE:
#     try:
#         api_key = os.getenv("OPENAI_API_KEY")
#         if not api_key:
#             print("⚠️ Warning: OPENAI_API_KEY environment variable is not set")
#             OPENAI_AVAILABLE = False
#         else:
#             # Different initialization based on version
#             if hasattr(openai, 'OpenAI'):  # New version (1.x.x)
#                 try:
#                     client = openai.OpenAI(api_key=api_key)
#                     print("✅ Initialized OpenAI client with new API (v1+)")
#                 except Exception as e:
#                     # Try without proxies if that's the issue
#                     try:
#                         # Just set the API key without creating a client
#                         openai.api_key = api_key
#                         client = True  # We'll use openai directly
#                         print("✅ Set OpenAI API key directly")
#                     except Exception as inner_e:
#                         print(f"⚠️ Error setting OpenAI API key: {inner_e}")
#                         OPENAI_AVAILABLE = False
#             else:  # Old version (0.x.x)
#                 try:
#                     openai.api_key = api_key
#                     client = True  # We'll use openai directly
#                     print("✅ Initialized OpenAI with legacy API (v0.x)")
#                 except Exception as e:
#                     print(f"⚠️ Error initializing legacy OpenAI: {e}")
#                     OPENAI_AVAILABLE = False
#     except Exception as e:
#         print(f"⚠️ Error initializing OpenAI client: {e}")
#         OPENAI_AVAILABLE = False

# # Pydantic models for request/response
# class ChatRequest(BaseModel):
#     message: str
#     user_identifier: str

# class ChatResponse(BaseModel):
#     session_id: str
#     response: str
#     success: bool
#     is_new_session: bool

# # Chat endpoint
# @router.post("/chat", response_model=ChatResponse)
# async def chat(request: ChatRequest, api_key: str = Header(..., alias="X-API-Key")):
#     """
#     Send a message to the chatbot and get a response
#     """
#     try:
#         # Connect to the database
#         conn = sqlite3.connect("chatbot.db")
#         cursor = conn.cursor()
        
#         # Verify API key
#         cursor.execute("SELECT id, name FROM tenants WHERE api_key = ? AND is_active = 1", (api_key,))
#         tenant = cursor.fetchone()
        
#         if not tenant:
#             raise HTTPException(status_code=400, detail="Invalid API key or inactive tenant")
        
#         tenant_id, tenant_name = tenant
        
#         # Get FAQs for the tenant
#         cursor.execute("SELECT question, answer FROM faqs WHERE tenant_id = ?", (tenant_id,))
#         faqs = cursor.fetchall()
        
#         if not faqs:
#             raise HTTPException(status_code=400, detail="No FAQs found for this tenant")
        
#         # Create a session ID for this conversation
#         session_id = hashlib.md5(f"{tenant_id}:{request.user_identifier}".encode()).hexdigest()
        
#         # Create messages table if it doesn't exist
#         cursor.execute("""
#         CREATE TABLE IF NOT EXISTS chat_messages (
#             id INTEGER PRIMARY KEY AUTOINCREMENT,
#             session_id TEXT NOT NULL,
#             content TEXT NOT NULL,
#             is_from_user BOOLEAN NOT NULL DEFAULT 1,
#             created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
#         )
#         """)
        
#         # Store user message
#         cursor.execute(
#             "INSERT INTO chat_messages (session_id, content, is_from_user) VALUES (?, ?, 1)",
#             (session_id, request.message)
#         )
        
#         # Generate response based on availability of OpenAI
#         if OPENAI_AVAILABLE and client:
#             # Get previous messages from this session (if any)
#             cursor.execute("""
#             SELECT content, is_from_user
#             FROM chat_messages
#             WHERE session_id = ?
#             ORDER BY created_at
#             LIMIT 10
#             """, (session_id,))
#             previous_messages = cursor.fetchall()
            
#             # Format FAQs for the prompt
#             faq_text = ""
#             for question, answer in faqs:
#                 faq_text += f"Q: {question}\nA: {answer}\n\n"
            
#             # Create messages for the OpenAI API
#             messages = [
#                 {"role": "system", "content": f"""
# You are a helpful customer support assistant for {tenant_name}.
# You are friendly, helpful, and professional at all times.

# Based on the provided FAQs below, you will answer customer questions about {tenant_name}'s products, services, policies, and procedures.
# If a question is outside the scope of the FAQs, acknowledge that you don't have enough information and offer to connect the customer with a human agent.

# Here are the FAQs you should use to answer questions:

# {faq_text}

# Remember to:
# - Be concise and clear in your responses
# - Use a friendly tone
# - Stay within the scope of the provided FAQs
# - If you're not sure about an answer, say so instead of making something up
# """
#                 }
#             ]
            
#             # Add conversation history
#             for content, is_from_user in previous_messages:
#                 role = "user" if is_from_user else "assistant"
#                 messages.append({"role": role, "content": content})
            
#             # Add the current user message
#             messages.append({"role": "user", "content": request.message})
            
#             try:
#                 # Call the OpenAI API (handle different versions)
#                 if hasattr(openai, 'OpenAI') and hasattr(client, 'chat'):  # New client with chat completions
#                     response = client.chat.completions.create(
#                         model="gpt-4",
#                         messages=messages,
#                         max_tokens=500,
#                         temperature=0.7
#                     )
#                     bot_response = response.choices[0].message.content
#                 else:  # Legacy client
#                     response = openai.ChatCompletion.create(
#                         model="gpt-4",
#                         messages=messages,
#                         max_tokens=500,
#                         temperature=0.7
#                     )
#                     bot_response = response['choices'][0]['message']['content']
#             except Exception as e:
#                 print(f"⚠️ Error calling OpenAI API: {e}")
#                 # Fall back to simple matching if OpenAI API call fails
#                 bot_response = simple_matching(request.message, faqs)
#         else:
#             # Use simple matching if OpenAI not available
#             bot_response = simple_matching(request.message, faqs)
        
#         # Store bot response
#         cursor.execute(
#             "INSERT INTO chat_messages (session_id, content, is_from_user) VALUES (?, ?, 0)",
#             (session_id, bot_response)
#         )
        
#         conn.commit()
        
#         # Check if this is a new session
#         cursor.execute(
#             "SELECT COUNT(*) FROM chat_messages WHERE session_id = ?",
#             (session_id,)
#         )
#         message_count = cursor.fetchone()[0]
#         is_new_session = message_count <= 2  # Just the message we added and its response
        
#         return {
#             "session_id": session_id,
#             "response": bot_response,
#             "success": True,
#             "is_new_session": is_new_session
#         }
        
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
#     finally:
#         if 'conn' in locals() and conn:
#             conn.close()

# def simple_matching(message, faqs):
#     """Simple keyword matching fallback when OpenAI is not available"""
#     # Default response with topics
#     response = "I'm sorry, I don't have information about that. Here are some topics I can help with:\n\n"
    
#     # Add topics
#     topics = [faq[0] for faq in faqs]
#     response += "- " + "\n- ".join(topics[:5])
    
#     # Try to find a matching FAQ
#     for question, answer in faqs:
#         if any(keyword.lower() in message.lower() for keyword in question.lower().split()):
#             response = answer
#             break
    
#     return response

# # Get chat history
# @router.get("/history/{session_id}")
# async def get_chat_history(session_id: str, api_key: str = Header(..., alias="X-API-Key")):
#     """
#     Get the chat history for a session
#     """
#     try:
#         # Connect to the database
#         conn = sqlite3.connect("chatbot.db")
#         conn.row_factory = sqlite3.Row  # This enables column access by name
#         cursor = conn.cursor()
        
#         # Verify API key
#         cursor.execute("SELECT id FROM tenants WHERE api_key = ? AND is_active = 1", (api_key,))
#         tenant = cursor.fetchone()
        
#         if not tenant:
#             raise HTTPException(status_code=400, detail="Invalid API key or inactive tenant")
        
#         # Get messages
#         cursor.execute("""
#         SELECT content, is_from_user, created_at 
#         FROM chat_messages 
#         WHERE session_id = ? 
#         ORDER BY created_at
#         """, (session_id,))
        
#         messages = cursor.fetchall()
        
#         return {
#             "session_id": session_id,
#             "messages": [dict(msg) for msg in messages]
#         }
        
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
#     finally:
#         if 'conn' in locals() and conn:
#             conn.close()



from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
import logging

from app.database import get_db
from app.chatbot.engine import ChatbotEngine
from app.chatbot.models import ChatSession, ChatMessage

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

# Chat endpoint
@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, api_key: str = Header(..., alias="X-API-Key"), db: Session = Depends(get_db)):
    """
    Send a message to the chatbot and get a response
    """
    try:
        # Initialize chatbot engine
        engine = ChatbotEngine(db)
        
        # Process message
        result = engine.process_message(api_key, request.message, request.user_identifier)
        
        if not result.get("success"):
            error_message = result.get("error", "Unknown error")
            logger.error(f"Chatbot error: {error_message}")
            raise HTTPException(status_code=400, detail=error_message)
        
        return result
    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")

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