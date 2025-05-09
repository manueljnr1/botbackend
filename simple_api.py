#!/usr/bin/env python3
"""
Simple API for the chatbot that doesn't require the full app structure
"""
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
import uvicorn
import sqlite3
import os
from typing import Optional, List, Dict

# Create the FastAPI app
app = FastAPI(
    title="Simple Chatbot API",
    description="Simplified API for the chatbot",
    version="1.0.0"
)

# Pydantic models
class ChatRequest(BaseModel):
    message: str
    user_identifier: str

class ChatResponse(BaseModel):
    session_id: str
    response: str
    success: bool
    is_new_session: bool

# Chatbot endpoint
@app.post("/chatbot/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, api_key: str = Header(..., alias="X-API-Key")):
    """
    Send a message to the chatbot and get a response
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
        if conn:
            conn.close()

# Root endpoint
@app.get("/")
def root():
    return {"message": "Simple Chatbot API"}

# Health check endpoint
@app.get("/health")
def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run("simple_api:app", host="0.0.0.0", port=8001, reload=True)