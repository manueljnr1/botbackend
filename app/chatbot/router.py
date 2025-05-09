from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import sqlite3
import openai
import os
import random
import hashlib
from app.database import get_db
from app.config import settings

# Configure OpenAI
openai.api_key = settings.OPENAI_API_KEY

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

# Helper function to rephrase response using GPT-3.5
async def rephrase_with_gpt(faq_answer: str, question: str, personality: str = "friendly") -> str:
    """
    Use GPT-3.5 Turbo to rephrase an FAQ answer to make it sound more natural and conversational
    """
    # Define different personalities for variety
    personalities = {
        "friendly": "You're a friendly and helpful customer support agent. Rephrase this answer to sound more natural and conversational.",
        "professional": "You're a professional customer support representative. Rephrase this answer to sound authoritative but helpful.",
        "casual": "You're a casual, laid-back support agent. Rephrase this answer to sound relaxed but still helpful.",
        "enthusiastic": "You're an enthusiastic customer support agent. Rephrase this answer with energy and positivity."
    }
    
    # Randomly select a personality if not specified
    if personality not in personalities:
        personality = random.choice(list(personalities.keys()))
    
    persona = personalities[personality]
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": f"{persona} Keep the same information but make it sound more natural and conversational."},
                {"role": "user", "content": f"Customer asked: {question}\n\nOriginal answer: {faq_answer}\n\nPlease rephrase this to sound more natural and conversational. Keep all the important information but make it sound like a real person is responding, not just reading from a script. Keep it concise."}
            ],
            max_tokens=300,
            temperature=0.7,
        )
        
        # Extract and return the rephrased response
        rephrased_answer = response.choices[0].message.content.strip()
        return rephrased_answer
    
    except Exception as e:
        # If there's an error with GPT-3.5, return the original answer
        print(f"Error rephrasing with GPT-3.5: {e}")
        return faq_answer

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
        
        # Default response if no match is found
        default_response = "I'm sorry, I don't have information about that. Here are some topics I can help with:\n\n"
        
        # Add topics
        topics = [faq[0] for faq in faqs]
        default_response += "- " + "\n- ".join(topics[:5])
        
        # Try to find a matching FAQ
        matched_answer = None
        matched_question = None
        
        for question, answer in faqs:
            if any(keyword.lower() in request.message.lower() for keyword in question.lower().split()):
                matched_answer = answer
                matched_question = question
                break
        
        # If we found a match, use GPT-3.5 to rephrase it
        if matched_answer:
            # Randomly select a personality
            personalities = ["friendly", "professional", "casual", "enthusiastic"]
            persona = random.choice(personalities)
            
            # Rephrase the answer with GPT-3.5
            response = await rephrase_with_gpt(matched_answer, matched_question, persona)
        else:
            response = default_response
        
        # Create session ID based on user identifier
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