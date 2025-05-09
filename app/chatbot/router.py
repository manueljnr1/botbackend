from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import sqlite3
import os
import random
import hashlib
import json
import traceback
import time
import re
from datetime import datetime
from app.database import get_db
from app.config import settings

# Set up OpenAI
try:
    import openai
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", settings.OPENAI_API_KEY if hasattr(settings, "OPENAI_API_KEY") else None)
    print(f"OpenAI API Key available: {bool(OPENAI_API_KEY)}")
    
    if OPENAI_API_KEY:
        openai.api_key = OPENAI_API_KEY
    else:
        print("WARNING: OpenAI API key not found. Direct LLM responses will not work.")
    
    OPENAI_AVAILABLE = bool(OPENAI_API_KEY)
except ImportError:
    print("WARNING: OpenAI package not installed. Direct LLM responses will not work.")
    OPENAI_AVAILABLE = False

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

# Common greeting patterns
GREETING_PATTERNS = [
    r'^hi\b',
    r'^hello\b',
    r'^hey\b',
    r'^good morning\b',
    r'^good afternoon\b',
    r'^good evening\b',
    r'^howdy\b',
    r'^greetings\b',
    r'^what\'s up\b',
    r'^hiya\b',
]

# Common gratitude patterns
GRATITUDE_PATTERNS = [
    r'^thank',
    r'^thanks',
    r'^appreciate',
    r'^grateful',
]

# Common farewell patterns
FAREWELL_PATTERNS = [
    r'^bye\b',
    r'^goodbye\b',
    r'^see you\b',
    r'^talk to you later\b',
    r'^have a good',
    r'^farewell\b',
]

# Get time of day for greetings
def get_time_of_day():
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return "morning"
    elif 12 <= hour < 17:
        return "afternoon"
    else:
        return "evening"

# Helper function for direct LLM response
async def get_direct_llm_response(message: str, context: str = None, user_history: List = None) -> str:
    """
    Get a direct response from the LLM for common conversational messages
    """
    if not OPENAI_AVAILABLE:
        # Fallback responses without OpenAI
        if any(re.search(pattern, message.lower()) for pattern in GREETING_PATTERNS):
            time_of_day = get_time_of_day()
            greetings = [
                f"Good {time_of_day}! How can I assist you today?",
                f"Hello there! How can I help you this {time_of_day}?",
                f"Hi! Welcome to our customer support. What can I do for you today?",
                f"Hey! Thanks for reaching out. How may I help you this {time_of_day}?"
            ]
            return random.choice(greetings)
        
        elif any(re.search(pattern, message.lower()) for pattern in GRATITUDE_PATTERNS):
            gratitude_responses = [
                "You're welcome! Is there anything else I can help with?",
                "Happy to help! Let me know if you need anything else.",
                "Anytime! Is there something else you'd like to know?",
                "My pleasure! Don't hesitate to ask if you have more questions."
            ]
            return random.choice(gratitude_responses)
        
        elif any(re.search(pattern, message.lower()) for pattern in FAREWELL_PATTERNS):
            farewell_responses = [
                "Goodbye! Have a great day!",
                "See you later! Feel free to come back if you have more questions.",
                "Take care! Don't hesitate to reach out if you need anything else.",
                "Bye for now! It was a pleasure assisting you."
            ]
            return random.choice(farewell_responses)
        
        return None
    
    print(f"Getting direct LLM response for: {message}")
    
    # Prepare system message
    system_message = "You are a helpful, friendly customer support assistant."
    if context:
        system_message += f" You have the following information about the company: {context}"
    
    # Prepare chat history for context
    messages = [{"role": "system", "content": system_message}]
    
    # Add user history if available
    if user_history:
        # Take last 5 messages maximum
        for msg in user_history[-5:]:
            role = "assistant" if not msg["is_from_user"] else "user"
            messages.append({"role": role, "content": msg["content"]})
    
    # Add current message
    messages.append({"role": "user", "content": message})
    
    try:
        # Try with older OpenAI API first
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=messages,
                max_tokens=150,
                temperature=0.7,
            )
            
            # Extract response
            llm_response = response.choices[0].message.content.strip()
            print(f"LLM Response (old API): {llm_response}")
            return llm_response
            
        # Try with newer OpenAI API if the older one fails
        except AttributeError:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=OPENAI_API_KEY)
                
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=messages,
                    max_tokens=150,
                    temperature=0.7,
                )
                
                # Extract response
                llm_response = response.choices[0].message.content.strip()
                print(f"LLM Response (new API): {llm_response}")
                return llm_response
            except Exception as e2:
                print(f"Error with new OpenAI API format: {e2}")
                return None
    
    except Exception as e:
        print(f"Error getting direct LLM response: {str(e)}")
        print(traceback.format_exc())
        return None

# Helper function to rephrase response using GPT-3.5
async def rephrase_with_gpt(faq_answer: str, question: str, personality: str = "friendly") -> str:
    """
    Use GPT-3.5 Turbo to rephrase an FAQ answer to make it sound more natural and conversational
    """
    if not OPENAI_AVAILABLE:
        print("WARNING: OpenAI not available. Returning original answer.")
        return faq_answer
    
    print(f"Rephrasing answer for question: {question}")
    print(f"Original answer: {faq_answer}")
    print(f"Personality: {personality}")
    
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
        # Try with older OpenAI API first
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": f"{persona} Keep the same information but make it sound more natural and conversational."},
                    {"role": "user", "content": f"Customer asked: {question}\n\nOriginal answer: {faq_answer}\n\nPlease rephrase this to sound more natural and conversational. Add a brief greeting. Keep all the important information but make it sound like a real person is responding, not just reading from a script. Keep it concise."}
                ],
                max_tokens=300,
                temperature=0.7,
            )
            
            # Extract response
            rephrased_answer = response.choices[0].message.content.strip()
            print(f"Rephrased answer: {rephrased_answer}")
            return rephrased_answer
            
        # Try with newer OpenAI API if the older one fails
        except AttributeError:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=OPENAI_API_KEY)
                
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": f"{persona} Keep the same information but make it sound more natural and conversational."},
                        {"role": "user", "content": f"Customer asked: {question}\n\nOriginal answer: {faq_answer}\n\nPlease rephrase this to sound more natural and conversational. Add a brief greeting. Keep all the important information but make it sound like a real person is responding, not just reading from a script. Keep it concise."}
                    ],
                    max_tokens=300,
                    temperature=0.7,
                )
                
                # Extract response
                rephrased_answer = response.choices[0].message.content.strip()
                print(f"Rephrased answer (new API): {rephrased_answer}")
                return rephrased_answer
            except Exception as e2:
                print(f"Error with new OpenAI API format: {e2}")
                return faq_answer
    
    except Exception as e:
        print(f"ERROR rephrasing with GPT-3.5: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return faq_answer

# Chat endpoint
@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, api_key: str = Header(..., alias="X-API-Key")):
    """
    Send a message to the chatbot and get a response
    """
    print(f"Received chat request: {request.message}")
    print(f"API Key: {api_key[:5]}...")
    
    try:
        # Connect to the database
        conn = sqlite3.connect("chatbot.db")
        cursor = conn.cursor()
        
        # Verify API key
        cursor.execute("SELECT id, name FROM tenants WHERE api_key = ? AND is_active = 1", (api_key,))
        tenant = cursor.fetchone()
        
        if not tenant:
            print(f"Invalid API key: {api_key[:5]}...")
            raise HTTPException(status_code=400, detail="Invalid API key or inactive tenant")
        
        tenant_id, tenant_name = tenant
        print(f"Found tenant: {tenant_name} (ID: {tenant_id})")
        
        # Create session ID based on user identifier
        session_id = hashlib.md5(f"{tenant_id}:{request.user_identifier}".encode()).hexdigest()
        
        # Get user chat history if available
        user_history = []
        try:
            conn.row_factory = sqlite3.Row
            history_cursor = conn.cursor()
            
            # Create messages table if it doesn't exist
            history_cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                content TEXT NOT NULL,
                is_from_user BOOLEAN NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            
            # Get previous messages
            history_cursor.execute("""
            SELECT content, is_from_user, created_at 
            FROM chat_messages 
            WHERE session_id = ? 
            ORDER BY created_at DESC
            LIMIT 10
            """, (session_id,))
            
            user_history = [dict(row) for row in history_cursor.fetchall()]
            user_history.reverse()  # Put in chronological order
            
            print(f"Found {len(user_history)} previous messages for this session")
        except Exception as e:
            print(f"Warning: Could not fetch message history: {e}")
        
        # Reset row factory
        conn.row_factory = None
        cursor = conn.cursor()
        
        # Check if this is a conversational message (greeting, farewell, thanks)
        is_greeting = any(re.search(pattern, request.message.lower()) for pattern in GREETING_PATTERNS)
        is_gratitude = any(re.search(pattern, request.message.lower()) for pattern in GRATITUDE_PATTERNS)
        is_farewell = any(re.search(pattern, request.message.lower()) for pattern in FAREWELL_PATTERNS)
        
        if is_greeting or is_gratitude or is_farewell:
            print("Detected conversational message, using direct LLM response")
            
            # Get company description for context
            company_context = f"{tenant_name} is a company that provides customer support."
            
            # Get direct LLM response
            direct_response = await get_direct_llm_response(
                request.message, 
                context=company_context,
                user_history=user_history
            )
            
            if direct_response:
                # Store messages and return response
                try:
                    # Store user message
                    cursor.execute(
                        "INSERT INTO chat_messages (session_id, content, is_from_user) VALUES (?, ?, 1)",
                        (session_id, request.message)
                    )
                    
                    # Store bot response
                    cursor.execute(
                        "INSERT INTO chat_messages (session_id, content, is_from_user) VALUES (?, ?, 0)",
                        (session_id, direct_response)
                    )
                    
                    conn.commit()
                except Exception as e:
                    print(f"Warning: Could not store messages: {e}")
                
                return {
                    "session_id": session_id,
                    "response": direct_response,
                    "success": True,
                    "is_new_session": len(user_history) == 0
                }
        
        # If not a conversational message or direct LLM failed, 
        # continue with FAQ matching
        print("Proceeding with FAQ matching")
        
        # Get FAQs for the tenant
        cursor.execute("SELECT question, answer FROM faqs WHERE tenant_id = ?", (tenant_id,))
        faqs = cursor.fetchall()
        
        if not faqs:
            print(f"No FAQs found for tenant ID: {tenant_id}")
            
            # If no FAQs but we have OpenAI, try direct response
            if OPENAI_AVAILABLE:
                company_context = f"{tenant_name} is a company that provides customer support."
                direct_response = await get_direct_llm_response(
                    request.message, 
                    context=company_context,
                    user_history=user_history
                )
                
                if direct_response:
                    # Store messages and return response
                    try:
                        # Store user message
                        cursor.execute(
                            "INSERT INTO chat_messages (session_id, content, is_from_user) VALUES (?, ?, 1)",
                            (session_id, request.message)
                        )
                        
                        # Store bot response
                        cursor.execute(
                            "INSERT INTO chat_messages (session_id, content, is_from_user) VALUES (?, ?, 0)",
                            (session_id, direct_response)
                        )
                        
                        conn.commit()
                    except Exception as e:
                        print(f"Warning: Could not store messages: {e}")
                    
                    return {
                        "session_id": session_id,
                        "response": direct_response,
                        "success": True,
                        "is_new_session": len(user_history) == 0
                    }
            
            raise HTTPException(status_code=400, detail="No FAQs found for this tenant")
        
        print(f"Found {len(faqs)} FAQs for tenant")
        
        # Default response if no match is found
        default_response = "I'm sorry, I don't have specific information about that. Here are some topics I can help with:\n\n"
        
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
                print(f"Matched FAQ: {question}")
                break
        
        # If we found a match, use GPT-3.5 to rephrase it
        if matched_answer:
            print("Found matching FAQ, attempting to rephrase...")
            # Randomly select a personality
            personalities = ["friendly", "professional", "casual", "enthusiastic"]
            persona = random.choice(personalities)
            
            try:
                # Rephrase the answer with GPT-3.5
                response = await rephrase_with_gpt(matched_answer, matched_question, persona)
                print(f"Successfully rephrased response")
            except Exception as e:
                print(f"Error rephrasing: {str(e)}")
                print(traceback.format_exc())
                response = matched_answer
        else:
            print("No matching FAQ found, trying direct LLM response before using default")
            
            # Try direct LLM response before falling back to default
            if OPENAI_AVAILABLE:
                company_context = f"{tenant_name} is a company that provides customer support services."
                faq_context = "The company can help with: " + ", ".join(topics[:5])
                context = f"{company_context} {faq_context}"
                
                direct_response = await get_direct_llm_response(
                    request.message, 
                    context=context,
                    user_history=user_history
                )
                
                if direct_response:
                    response = direct_response
                else:
                    response = default_response
            else:
                response = default_response
        
        # Store messages
        try:
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
            "is_new_session": len(user_history) == 0
        }
        
    except Exception as e:
        print(f"ERROR in chat endpoint: {str(e)}")
        print(traceback.format_exc())
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
        print(f"Error in get_chat_history: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()