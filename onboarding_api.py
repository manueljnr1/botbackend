#!/usr/bin/env python3
"""
API for user onboarding and knowledge base management
"""
from fastapi import FastAPI, File, UploadFile, Form, Header, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import sqlite3
import uuid
import os
import shutil
import pandas as pd
import uvicorn
import hashlib
from passlib.context import CryptContext

# Initialize FastAPI
app = FastAPI(
    title="Chatbot Onboarding API",
    description="API for tenant onboarding and knowledge base management",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Database setup
DB_PATH = "chatbot.db"

# Directories for file storage
UPLOAD_DIR = "uploads"
TEMP_DIR = "temp"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# Pydantic models
class TenantCreate(BaseModel):
    business_name: str
    email: str
    password: str
    industry: str

class FAQ(BaseModel):
    question: str
    answer: str

class TenantResponse(BaseModel):
    tenant_id: int
    business_name: str
    api_key: str

class MessageRequest(BaseModel):
    message: str
    user_identifier: str

class MessageResponse(BaseModel):
    response: str
    session_id: str

def get_db_connection():
    """Create a database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the database with necessary tables"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create tenants table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tenants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        hashed_password TEXT NOT NULL,
        industry TEXT,
        api_key TEXT UNIQUE NOT NULL,
        is_active BOOLEAN NOT NULL DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create knowledge_bases table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS knowledge_bases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        file_path TEXT NOT NULL,
        file_type TEXT NOT NULL,
        vector_store_id TEXT UNIQUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (tenant_id) REFERENCES tenants (id)
    )
    ''')
    
    # Create faqs table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS faqs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id INTEGER NOT NULL,
        question TEXT NOT NULL,
        answer TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (tenant_id) REFERENCES tenants (id)
    )
    ''')
    
    # Create chat_sessions table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS chat_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT UNIQUE NOT NULL,
        tenant_id INTEGER NOT NULL,
        user_identifier TEXT NOT NULL,
        is_active BOOLEAN NOT NULL DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (tenant_id) REFERENCES tenants (id)
    )
    ''')
    
    # Create chat_messages table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS chat_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        is_from_user BOOLEAN NOT NULL DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (session_id) REFERENCES chat_sessions (id)
    )
    ''')
    
    conn.commit()
    conn.close()

# Initialize database at startup
init_db()

# Helper functions
def get_password_hash(password):
    """Hash a password"""
    return pwd_context.hash(password)

def verify_tenant_by_api_key(api_key: str):
    """Verify a tenant by API key"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, business_name FROM tenants WHERE api_key = ? AND is_active = 1", (api_key,))
    tenant = cursor.fetchone()
    conn.close()
    
    if not tenant:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    return tenant

# API endpoints
@app.post("/register", response_model=TenantResponse)
async def register_tenant(tenant: TenantCreate):
    """Register a new tenant"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if email already exists
    cursor.execute("SELECT id FROM tenants WHERE email = ?", (tenant.email,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Generate API key
    api_key = f"sk-{str(uuid.uuid4()).replace('-', '')}"
    
    # Hash password
    hashed_password = get_password_hash(tenant.password)
    
    # Insert tenant
    cursor.execute(
        "INSERT INTO tenants (business_name, email, hashed_password, industry, api_key) VALUES (?, ?, ?, ?, ?)",
        (tenant.business_name, tenant.email, hashed_password, tenant.industry, api_key)
    )
    
    tenant_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return {"tenant_id": tenant_id, "business_name": tenant.business_name, "api_key": api_key}

@app.post("/upload-knowledge-base")
async def upload_knowledge_base(
    file: UploadFile = File(...),
    name: str = Form(...),
    api_key: str = Header(..., alias="X-API-Key")
):
    """Upload a knowledge base document"""
    # Verify tenant
    tenant = verify_tenant_by_api_key(api_key)
    tenant_id = tenant["id"]
    
    # Save file
    file_extension = file.filename.split('.')[-1].lower()
    allowed_extensions = ["pdf", "doc", "docx", "txt", "csv", "xlsx"]
    if file_extension not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_extension}")
    
    # Create tenant directory if it doesn't exist
    tenant_dir = os.path.join(UPLOAD_DIR, f"tenant_{tenant_id}")
    os.makedirs(tenant_dir, exist_ok=True)
    
    # Generate unique filename
    unique_filename = f"{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join(tenant_dir, unique_filename)
    
    # Save file
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # TODO: Process document with vector embedding
    # This would call a function similar to processor.process_document from your existing code
    
    # For now, we'll just store the file info
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO knowledge_bases (tenant_id, name, file_path, file_type) VALUES (?, ?, ?, ?)",
        (tenant_id, name, file_path, file_extension)
    )
    kb_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return {"id": kb_id, "name": name, "file_type": file_extension}

@app.post("/upload-faqs")
async def upload_faqs(
    file: UploadFile = File(None),
    api_key: str = Header(..., alias="X-API-Key")
):
    """Upload FAQs from a CSV or Excel file"""
    # Verify tenant
    tenant = verify_tenant_by_api_key(api_key)
    tenant_id = tenant["id"]
    
    if not file:
        raise HTTPException(status_code=400, detail="No file provided")
    
    # Save file to temp directory
    file_extension = file.filename.split('.')[-1].lower()
    if file_extension not in ["csv", "xlsx", "xls"]:
        raise HTTPException(status_code=400, detail="File must be CSV or Excel")
    
    temp_file_path = os.path.join(TEMP_DIR, f"{uuid.uuid4()}_{file.filename}")
    with open(temp_file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Parse the file
    try:
        if file_extension == "csv":
            df = pd.read_csv(temp_file_path)
        else:
            df = pd.read_excel(temp_file_path)
        
        # Check for required columns
        if "question" not in df.columns or "answer" not in df.columns:
            os.remove(temp_file_path)
            raise HTTPException(status_code=400, detail="File must contain 'question' and 'answer' columns")
        
        # Insert FAQs into database
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # First, delete existing FAQs for this tenant
        cursor.execute("DELETE FROM faqs WHERE tenant_id = ?", (tenant_id,))
        
        # Insert new FAQs
        faqs_added = 0
        for _, row in df.iterrows():
            if pd.notna(row['question']) and pd.notna(row['answer']):
                cursor.execute(
                    "INSERT INTO faqs (tenant_id, question, answer) VALUES (?, ?, ?)",
                    (tenant_id, row['question'].strip(), row['answer'].strip())
                )
                faqs_added += 1
        
        conn.commit()
        conn.close()
        
        # Clean up
        os.remove(temp_file_path)
        
        return {"message": f"Successfully added {faqs_added} FAQs"}
    
    except Exception as e:
        # Clean up on error
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

@app.post("/add-faqs")
async def add_faqs(
    faqs: List[FAQ],
    api_key: str = Header(..., alias="X-API-Key")
):
    """Add FAQs manually"""
    # Verify tenant
    tenant = verify_tenant_by_api_key(api_key)
    tenant_id = tenant["id"]
    
    if not faqs:
        raise HTTPException(status_code=400, detail="No FAQs provided")
    
    # Insert FAQs into database
    conn = get_db_connection()
    cursor = conn.cursor()
    
    for faq in faqs:
        cursor.execute(
            "INSERT INTO faqs (tenant_id, question, answer) VALUES (?, ?, ?)",
            (tenant_id, faq.question.strip(), faq.answer.strip())
        )
    
    conn.commit()
    conn.close()
    
    return {"message": f"Successfully added {len(faqs)} FAQs"}

@app.post("/chat", response_model=MessageResponse)
async def chat(
    request: MessageRequest,
    api_key: str = Header(..., alias="X-API-Key")
):
    """Chat with the bot"""
    # Verify tenant
    tenant = verify_tenant_by_api_key(api_key)
    tenant_id = tenant["id"]
    
    # Get FAQs for the tenant
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT question, answer FROM faqs WHERE tenant_id = ?", (tenant_id,))
    faqs = cursor.fetchall()
    
    if not faqs:
        return {"response": "I'm sorry, but I don't have any information to help you with. Please contact support.", "session_id": "no-faqs"}
    
    # Simple FAQ matching
    default_response = "I'm sorry, I don't have information about that. Here are some topics I can help with:\n\n"
    default_response += "\n".join([f"- {faq['question']}" for faq in faqs[:5]])
    
    response = default_response
    
    # Try to match FAQ
    for faq in faqs:
        if any(keyword.lower() in request.message.lower() for keyword in faq["question"].lower().split()):
            response = faq["answer"]
            break
    
    # Create or get session
    session_id = hashlib.md5(f"{tenant_id}:{request.user_identifier}".encode()).hexdigest()
    
    # Check if session exists
    cursor.execute("SELECT id FROM chat_sessions WHERE session_id = ?", (session_id,))
    existing_session = cursor.fetchone()
    
    if not existing_session:
        # Create new session
        cursor.execute(
            "INSERT INTO chat_sessions (session_id, tenant_id, user_identifier) VALUES (?, ?, ?)",
            (session_id, tenant_id, request.user_identifier)
        )
        session_db_id = cursor.lastrowid
    else:
        session_db_id = existing_session["id"]
    
    # Store user message
    cursor.execute(
        "INSERT INTO chat_messages (session_id, content, is_from_user) VALUES (?, ?, 1)",
        (session_db_id, request.message)
    )
    
    # Store bot response
    cursor.execute(
        "INSERT INTO chat_messages (session_id, content, is_from_user) VALUES (?, ?, 0)",
        (session_db_id, response)
    )
    
    conn.commit()
    conn.close()
    
    return {"response": response, "session_id": session_id}

@app.get("/tenants/{api_key}/knowledge-bases")
async def get_knowledge_bases(api_key: str):
    """Get knowledge bases for a tenant"""
    # Verify tenant
    tenant = verify_tenant_by_api_key(api_key)
    tenant_id = tenant["id"]
    
    # Get knowledge bases
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, name, file_path, file_type, created_at FROM knowledge_bases WHERE tenant_id = ? ORDER BY created_at DESC",
        (tenant_id,)
    )
    kbs = cursor.fetchall()
    conn.close()
    
    # Convert rows to dictionaries
    result = []
    for kb in kbs:
        kb_dict = dict(kb)
        # Add file size
        if os.path.exists(kb_dict["file_path"]):
            kb_dict["file_size"] = os.path.getsize(kb_dict["file_path"])
        else:
            kb_dict["file_size"] = 0
        result.append(kb_dict)
    
    return result

@app.get("/tenants/{api_key}/faqs")
async def get_faqs(api_key: str):
    """Get FAQs for a tenant"""
    # Verify tenant
    tenant = verify_tenant_by_api_key(api_key)
    tenant_id = tenant["id"]
    
    # Get FAQs
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, question, answer, created_at FROM faqs WHERE tenant_id = ? ORDER BY id",
        (tenant_id,)
    )
    faqs = cursor.fetchall()
    conn.close()
    
    return [dict(faq) for faq in faqs]

@app.get("/tenants/{api_key}/conversations")
async def get_conversations(api_key: str):
    """Get conversations for a tenant"""
    # Verify tenant
    tenant = verify_tenant_by_api_key(api_key)
    tenant_id = tenant["id"]
    
    # Get conversations
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get sessions
    cursor.execute(
        """
        SELECT 
            cs.id, 
            cs.session_id, 
            cs.user_identifier, 
            cs.is_active,
            cs.created_at,
            (SELECT COUNT(*) FROM chat_messages WHERE session_id = cs.id) as message_count,
            (SELECT content FROM chat_messages WHERE session_id = cs.id AND is_from_user = 1 ORDER BY created_at DESC LIMIT 1) as last_user_message
        FROM 
            chat_sessions cs
        WHERE 
            cs.tenant_id = ?
        ORDER BY 
            cs.created_at DESC
        """,
        (tenant_id,)
    )
    
    conversations = cursor.fetchall()
    conn.close()
    
    return [dict(conv) for conv in conversations]

@app.get("/tenants/{api_key}/conversations/{session_id}/messages")
async def get_conversation_messages(api_key: str, session_id: str):
    """Get messages for a conversation"""
    # Verify tenant
    tenant = verify_tenant_by_api_key(api_key)
    tenant_id = tenant["id"]
    
    # Get session
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM chat_sessions WHERE session_id = ? AND tenant_id = ?",
        (session_id, tenant_id)
    )
    session = cursor.fetchone()
    
    if not session:
        conn.close()
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Get messages
    cursor.execute(
        "SELECT id, content, is_from_user, created_at FROM chat_messages WHERE session_id = ? ORDER BY created_at",
        (session["id"],)
    )
    messages = cursor.fetchall()
    conn.close()
    
    return [dict(msg) for msg in messages]

# Run the app
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8002))
    print(f"Starting Onboarding API on port {port}...")
    uvicorn.run("onboarding_api:app", host="0.0.0.0", port=port, reload=True)