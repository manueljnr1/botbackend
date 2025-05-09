#!/usr/bin/env python3
"""
Simple API for the chatbot with CORS support and proper GPT-4 integration
"""
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import sqlite3
import os
import hashlib
from typing import Optional, List, Dict
import openai
from openai import OpenAI

# Initialize OpenAI client
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("⚠️ Warning: OPENAI_API_KEY environment variable not set")
    print("Please set your OpenAI API key in the .env file or export it:")
    print("export OPENAI_API_KEY=your-key-here")
    api_key = input("Enter your OpenAI API key: ")

client = OpenAI(api_key=api_key)

# Create the FastAPI app
app = FastAPI(
    title="Simple Chatbot API with LLM",
    description="Simplified API for the chatbot using GPT-4",
    version="1.0.0"
)

# Add CORS middleware to allow requests from any origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
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

class Tenant(BaseModel):
    id: int
    name: str
    api_key: str
    is_active: bool

class FAQ(BaseModel):
    id: int
    question: str
    answer: str

class FAQCreate(BaseModel):
    question: str
    answer: str

# Chatbot endpoint
@app.post("/chatbot/chat", response_model=ChatResponse)
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
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            content TEXT NOT NULL,
            is_from_user BOOLEAN NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
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
@app.get("/chatbot/history/{session_id}")
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

# Get tenants API for the FAQ editor
@app.get("/tenants", response_model=List[Tenant])
async def get_tenants():
    """Get all active tenants"""
    try:
        conn = sqlite3.connect("chatbot.db")
        conn.row_factory = sqlite3.Row  # This enables column access by name
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, name, api_key, is_active FROM tenants WHERE is_active = 1")
        tenants = cursor.fetchall()
        
        return [dict(tenant) for tenant in tenants]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        if conn:
            conn.close()

# Get FAQs API for the FAQ editor
@app.get("/faqs/{tenant_id}", response_model=List[FAQ])
async def get_faqs(tenant_id: int):
    """Get all FAQs for a tenant"""
    try:
        conn = sqlite3.connect("chatbot.db")
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Verify tenant exists
        cursor.execute("SELECT id FROM tenants WHERE id = ? AND is_active = 1", (tenant_id,))
        tenant = cursor.fetchone()
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found or inactive")
        
        # Get FAQs
        cursor.execute("SELECT id, question, answer FROM faqs WHERE tenant_id = ?", (tenant_id,))
        faqs = cursor.fetchall()
        
        return [dict(faq) for faq in faqs]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        if conn:
            conn.close()

# Create FAQ API for the FAQ editor
@app.post("/faqs/{tenant_id}", response_model=FAQ)
async def create_faq(tenant_id: int, faq: FAQCreate):
    """Create a new FAQ for a tenant"""
    try:
        conn = sqlite3.connect("chatbot.db")
        cursor = conn.cursor()
        
        # Verify tenant exists
        cursor.execute("SELECT id FROM tenants WHERE id = ? AND is_active = 1", (tenant_id,))
        tenant = cursor.fetchone()
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found or inactive")
        
        # Create FAQ
        cursor.execute(
            "INSERT INTO faqs (tenant_id, question, answer) VALUES (?, ?, ?)",
            (tenant_id, faq.question, faq.answer)
        )
        conn.commit()
        
        # Get the new FAQ
        faq_id = cursor.lastrowid
        cursor.execute("SELECT id, question, answer FROM faqs WHERE id = ?", (faq_id,))
        new_faq = cursor.fetchone()
        
        return {
            "id": new_faq[0],
            "question": new_faq[1],
            "answer": new_faq[2]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        if conn:
            conn.close()

# Delete FAQ API for the FAQ editor
@app.delete("/faqs/{tenant_id}/{faq_id}")
async def delete_faq(tenant_id: int, faq_id: int):
    """Delete a FAQ"""
    try:
        conn = sqlite3.connect("chatbot.db")
        cursor = conn.cursor()
        
        # Verify tenant exists
        cursor.execute("SELECT id FROM tenants WHERE id = ? AND is_active = 1", (tenant_id,))
        tenant = cursor.fetchone()
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found or inactive")
        
        # Verify FAQ exists and belongs to tenant
        cursor.execute("SELECT id FROM faqs WHERE id = ? AND tenant_id = ?", (faq_id, tenant_id))
        faq = cursor.fetchone()
        if not faq:
            raise HTTPException(status_code=404, detail="FAQ not found or does not belong to this tenant")
        
        # Delete FAQ
        cursor.execute("DELETE FROM faqs WHERE id = ?", (faq_id,))
        conn.commit()
        
        return {"message": "FAQ deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        if conn:
            conn.close()

# Root endpoint
@app.get("/")
def root():
    return {"message": "Simple Chatbot API with LLM"}

# Health check endpoint
@app.get("/health")
def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    print("Starting chatbot API with LLM integration...")
    print("API will be available at: http://localhost:8001")
    print("You can open your HTML chat interface in your browser")
    uvicorn.run("simple_api_with_cors_llm:app", host="0.0.0.0", port=8001, reload=True)