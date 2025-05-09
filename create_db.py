#!/usr/bin/env python3
"""
Direct database table creation script to fix 'no such table' errors
"""
import sqlite3
import os

# Database file path
DB_FILE = "./chatbot.db"

# Create database dir if it doesn't exist
if not os.path.exists(os.path.dirname(DB_FILE)):
    os.makedirs(os.path.dirname(DB_FILE))

# Connect to SQLite database (creates it if it doesn't exist)
conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

# Create tenants table
cursor.execute('''
CREATE TABLE IF NOT EXISTS tenants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    api_key TEXT UNIQUE NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
)
''')

# Create knowledge_bases table
cursor.execute('''
CREATE TABLE IF NOT EXISTS knowledge_bases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    file_path TEXT NOT NULL,
    document_type TEXT NOT NULL,
    vector_store_id TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
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
    updated_at TIMESTAMP,
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
    updated_at TIMESTAMP,
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

# Create users table
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    username TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    is_admin BOOLEAN NOT NULL DEFAULT 0,
    tenant_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id) REFERENCES tenants (id)
)
''')

# Create a test tenant
cursor.execute('''
INSERT OR IGNORE INTO tenants (name, description, api_key)
VALUES ("Test Tenant", "Test tenant for development", "sk-test-tenant-api-key")
''')

# Create a test FAQ
cursor.execute('''
INSERT OR IGNORE INTO faqs (tenant_id, question, answer)
VALUES (
    (SELECT id FROM tenants WHERE name = "Test Tenant"),
    "What is this chatbot?",
    "This is a multi-tenant AI customer support chatbot powered by GPT-4."
)
''')

# Commit changes and close connection
conn.commit()
print("Database tables created successfully!")
print("Created test tenant with API key: sk-test-tenant-api-key")
conn.close()