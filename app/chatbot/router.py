# from fastapi import APIRouter, Depends, HTTPException, Header
# from sqlalchemy.orm import Session
# from typing import List, Optional
# from pydantic import BaseModel

# from app.database import get_db
# from app.chatbot.engine import ChatbotEngine
# from app.chatbot.models import ChatSession, ChatMessage

# router = APIRouter()

# # Pydantic models for request/response
# class ChatRequest(BaseModel):
#     message: str
#     user_identifier: str

# class ChatResponse(BaseModel):
#     session_id: str
#     response: str
#     success: bool
#     is_new_session: bool

# class ChatHistory(BaseModel):
#     session_id: str
#     messages: List[dict]

# # Chat endpoint
# @router.post("/chat", response_model=ChatResponse)
# async def chat(request: ChatRequest, api_key: str = Header(..., alias="X-API-Key"), db: Session = Depends(get_db)):
#     """
#     Send a message to the chatbot and get a response
#     """
#     engine = ChatbotEngine(db)
#     result = engine.process_message(api_key, request.message, request.user_identifier)
    
#     if not result.get("success"):
#         raise HTTPException(status_code=400, detail=result.get("error", "Unknown error"))
    
#     return result

# # Get chat history
# @router.get("/history/{session_id}", response_model=ChatHistory)
# async def get_chat_history(session_id: str, api_key: str = Header(..., alias="X-API-Key"), db: Session = Depends(get_db)):
#     """
#     Get the chat history for a specific session
#     """
#     # Verify the API key and get tenant
#     engine = ChatbotEngine(db)
#     tenant = engine._get_tenant_by_api_key(api_key)
#     if not tenant:
#         raise HTTPException(status_code=403, detail="Invalid API key")
    
#     # Get session
#     session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
#     if not session or session.tenant_id != tenant.id:
#         raise HTTPException(status_code=404, detail="Session not found")
    
#     # Get messages
#     messages = db.query(ChatMessage).filter(ChatMessage.session_id == session.id).order_by(ChatMessage.created_at).all()
    
#     return {
#         "session_id": session_id,
#         "messages": [
#             {
#                 "content": msg.content,
#                 "is_from_user": msg.is_from_user,
#                 "created_at": msg.created_at.isoformat()
#             }
#             for msg in messages
#         ]
#     }

# # End chat session
# @router.post("/end-session")
# async def end_chat_session(session_id: str, api_key: str = Header(..., alias="X-API-Key"), db: Session = Depends(get_db)):
#     """
#     End a chat session
#     """
#     # Verify the API key and get tenant
#     engine = ChatbotEngine(db)
#     tenant = engine._get_tenant_by_api_key(api_key)
#     if not tenant:
#         raise HTTPException(status_code=403, detail="Invalid API key")
    
#     # Verify session belongs to tenant
#     session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
#     if not session or session.tenant_id != tenant.id:
#         raise HTTPException(status_code=404, detail="Session not found")
    
#     # End session
#     success = engine.end_session(session_id)
    
#     if not success:
#         raise HTTPException(status_code=400, detail="Failed to end session")
    
#     return {"message": "Session ended successfully"}


from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
import sqlite3

from app.database import get_db

router = APIRouter()

# Pydantic models for request/response
class ChatRequest(BaseModel):
    message: str
    user_identifier: str

class ChatResponse(BaseModel):
    session_id: str
    response: str
    success: bool
    is_new_session: bool

# Chat endpoint
@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, api_key: str = Header(..., alias="X-API-Key")):
    """
    Send a message to the chatbot and get a response
    """
    # We'll use direct SQLite access for now instead of the engine
    try:
        # Connect to the database
        conn = sqlite3.connect("chatbot.db")
        cursor = conn.cursor()
        
        # Verify API key
        cursor.execute("SELECT id, name FROM tenants WHERE api_key = ? AND is_active = 1", (api_key,))
        tenant = cursor.fetchone()
        
        if not tenant:
            raise HTTPException(status_code=400, detail="Invalid API key or inactive tenant")
        
        tenant_id, tenant_name = tenant
        
        # Get FAQs for the tenant
        cursor.execute("SELECT question, answer FROM faqs WHERE tenant_id = ?", (tenant_id,))
        faqs = cursor.fetchall()
        
        if not faqs:
            raise HTTPException(status_code=400, detail="No FAQs found for this tenant")
        
        # Simple FAQ matching
        response = "I'm sorry, I don't have information about that. Here are some topics I can help with:\n\n"
        
        # Add topics
        topics = [faq[0] for faq in faqs]
        response += "- " + "\n- ".join(topics[:5])
        
        # Try to find a matching FAQ
        for question, answer in faqs:
            if any(keyword.lower() in request.message.lower() for keyword in question.lower().split()):
                response = answer
                break
        
        # Create session ID based on user identifier
        import hashlib
        session_id = hashlib.md5(f"{tenant_id}:{request.user_identifier}".encode()).hexdigest()
        
        # Simple history tracking
        try:
            # Create messages table if it doesn't exist
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                content TEXT NOT NULL,
                is_from_user BOOLEAN NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            
            # Store user message
            cursor.execute(
                "INSERT INTO chat_messages (session_id, content, is_from_user) VALUES (?, ?, 1)",
                (session_id, request.message)
            )
            
            # Store bot response
            cursor.execute(
                "INSERT INTO chat_messages (session_id, content, is_from_user) VALUES (?, ?, 0)",
                (session_id, response)
            )
            
            conn.commit()
        except Exception as e:
            print(f"Warning: Could not store messages: {e}")
        
        return {
            "session_id": session_id,
            "response": response,
            "success": True,
            "is_new_session": False  # For simplicity
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()

# Get chat history
@router.get("/history/{session_id}")
async def get_chat_history(session_id: str, api_key: str = Header(..., alias="X-API-Key")):
    """
    Get the chat history for a session
    """
    try:
        # Connect to the database
        conn = sqlite3.connect("chatbot.db")
        conn.row_factory = sqlite3.Row  # This enables column access by name
        cursor = conn.cursor()
        
        # Verify API key
        cursor.execute("SELECT id FROM tenants WHERE api_key = ? AND is_active = 1", (api_key,))
        tenant = cursor.fetchone()
        
        if not tenant:
            raise HTTPException(status_code=400, detail="Invalid API key or inactive tenant")
        
        # Get messages
        cursor.execute("""
        SELECT content, is_from_user, created_at 
        FROM chat_messages 
        WHERE session_id = ? 
        ORDER BY created_at
        """, (session_id,))
        
        messages = cursor.fetchall()
        
        return {
            "session_id": session_id,
            "messages": [dict(msg) for msg in messages]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()