from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
import sqlite3
import hashlib
import openai
import os
from openai import OpenAI

from app.database import get_db

router = APIRouter()

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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
    Send a message to the chatbot and get a response using GPT-4
    """
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
        
        # Format FAQs for the prompt
        faq_text = ""
        for question, answer in faqs:
            faq_text += f"Q: {question}\nA: {answer}\n\n"
        
        # Create a session ID for this conversation
        session_id = hashlib.md5(f"{tenant_id}:{request.user_identifier}".encode()).hexdigest()
        
        # Get previous messages from this session (if any)
        cursor.execute("""
        SELECT content, is_from_user
        FROM chat_messages
        WHERE session_id = ?
        ORDER BY created_at
        LIMIT 10
        """, (session_id,))
        previous_messages = cursor.fetchall()
        
        # Create messages for the OpenAI API
        messages = [
            {"role": "system", "content": f"""
You are a helpful customer support assistant for {tenant_name}.
You are friendly, helpful, and professional at all times.

Based on the provided FAQs below, you will answer customer questions about {tenant_name}'s products, services, policies, and procedures.
If a question is outside the scope of the FAQs, acknowledge that you don't have enough information and offer to connect the customer with a human agent.

Here are the FAQs you should use to answer questions:

{faq_text}

Remember to:
- Be concise and clear in your responses
- Use a friendly tone
- Stay within the scope of the provided FAQs
- If you're not sure about an answer, say so instead of making something up
"""
            }
        ]
        
        # Add conversation history
        for content, is_from_user in previous_messages:
            role = "user" if is_from_user else "assistant"
            messages.append({"role": role, "content": content})
        
        # Add the current user message
        messages.append({"role": "user", "content": request.message})
        
        # Call the OpenAI API
        response = client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            max_tokens=500,
            temperature=0.7
        )
        
        # Get the assistant's response
        bot_response = response.choices[0].message.content
        
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
            (session_id, bot_response)
        )
        
        conn.commit()
        
        # Check if this is a new session
        cursor.execute(
            "SELECT COUNT(*) FROM chat_messages WHERE session_id = ?",
            (session_id,)
        )
        message_count = cursor.fetchone()[0]
        is_new_session = message_count <= 2  # Just the message we added and its response
        
        return {
            "session_id": session_id,
            "response": bot_response,
            "success": True,
            "is_new_session": is_new_session
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