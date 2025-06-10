#!/usr/bin/env python3
"""
Database Fix Script - Add Missing Columns
Run this to fix the pending_feedback table error
"""

import psycopg2
import sqlite3
import os

def create_pending_feedback_table(cursor):
    """Create pending_feedback table if it doesn't exist"""
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS pending_feedback (
        id SERIAL PRIMARY KEY,
        feedback_id VARCHAR UNIQUE,
        tenant_id INTEGER REFERENCES tenants(id),
        session_id VARCHAR REFERENCES chat_sessions(session_id),
        user_email VARCHAR,
        user_question TEXT,
        bot_response TEXT,
        conversation_context TEXT,
        tenant_email_sent BOOLEAN DEFAULT FALSE,
        tenant_email_id VARCHAR,
        tenant_response TEXT,
        user_notified BOOLEAN DEFAULT FALSE,
        user_email_id VARCHAR,
        form_accessed BOOLEAN DEFAULT FALSE,
        form_accessed_at TIMESTAMP,
        form_expired BOOLEAN DEFAULT FALSE,
        add_to_faq BOOLEAN DEFAULT FALSE,
        faq_question TEXT,
        faq_answer TEXT,
        faq_created BOOLEAN DEFAULT FALSE,
        status VARCHAR DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        tenant_notified_at TIMESTAMP,
        resolved_at TIMESTAMP
    );
    """
    cursor.execute(create_table_sql)
    print("✅ Created pending_feedback table")

def fix_postgresql():
    """Fix PostgreSQL database"""
    try:
        # Your PostgreSQL connection
        conn = psycopg2.connect(
            "postgresql://chatbot_hhjv_user:dYXguSEwpwZl3Yt2R3ACsfvmM5lLIgSD@dpg-d10sp295pdvs73afujf0-a.oregon-postgres.render.com/chatbot_hhjv"
        )
        cursor = conn.cursor()
        
        print("🔧 Fixing PostgreSQL database...")
        
        # First check if pending_feedback table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'pending_feedback'
            );
        """)
        table_exists = cursor.fetchone()[0]
        
        if not table_exists:
            print("📋 Creating pending_feedback table...")
            create_pending_feedback_table(cursor)
        else:
            print("📋 Adding missing columns to pending_feedback table...")
            # Add missing columns
            sql_commands = [
                "ALTER TABLE pending_feedback ADD COLUMN IF NOT EXISTS form_accessed BOOLEAN DEFAULT FALSE;",
                "ALTER TABLE pending_feedback ADD COLUMN IF NOT EXISTS form_accessed_at TIMESTAMP;",
                "ALTER TABLE pending_feedback ADD COLUMN IF NOT EXISTS form_expired BOOLEAN DEFAULT FALSE;",
                "ALTER TABLE pending_feedback ADD COLUMN IF NOT EXISTS add_to_faq BOOLEAN DEFAULT FALSE;",
                "ALTER TABLE pending_feedback ADD COLUMN IF NOT EXISTS faq_question TEXT;",
                "ALTER TABLE pending_feedback ADD COLUMN IF NOT EXISTS faq_answer TEXT;",
                "ALTER TABLE pending_feedback ADD COLUMN IF NOT EXISTS faq_created BOOLEAN DEFAULT FALSE;"
            ]
            
            for cmd in sql_commands:
                try:
                    cursor.execute(cmd)
                    print(f"✅ {cmd}")
                except Exception as e:
                    print(f"⚠️  {cmd} - {e}")
        
        # Add missing columns to chat_sessions
        print("📧 Adding email columns to chat_sessions...")
        email_commands = [
            "ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS email_captured_at TIMESTAMP;",
            "ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS email_expires_at TIMESTAMP;"
        ]
        
        for cmd in email_commands:
            try:
                cursor.execute(cmd)
                print(f"✅ {cmd}")
            except Exception as e:
                print(f"⚠️  {cmd} - {e}")
        
        conn.commit()
        cursor.close()
        conn.close()
        print("✅ PostgreSQL fix completed!")
        return True
        
    except Exception as e:
        print(f"❌ PostgreSQL error: {e}")
        return False

def fix_sqlite():
    """Fix SQLite database"""
    try:
        conn = sqlite3.connect("./chatbot.db")
        cursor = conn.cursor()
        
        print("🔧 Fixing SQLite database...")
        
        # SQLite doesn't support IF NOT EXISTS for ALTER TABLE
        # So we'll try each command and ignore errors for existing columns
        sql_commands = [
            "ALTER TABLE pending_feedback ADD COLUMN form_accessed BOOLEAN DEFAULT FALSE;",
            "ALTER TABLE pending_feedback ADD COLUMN form_accessed_at TIMESTAMP;",
            "ALTER TABLE pending_feedback ADD COLUMN form_expired BOOLEAN DEFAULT FALSE;",
            "ALTER TABLE pending_feedback ADD COLUMN add_to_faq BOOLEAN DEFAULT FALSE;",
            "ALTER TABLE pending_feedback ADD COLUMN faq_question TEXT;",
            "ALTER TABLE pending_feedback ADD COLUMN faq_answer TEXT;",
            "ALTER TABLE pending_feedback ADD COLUMN faq_created BOOLEAN DEFAULT FALSE;",
            "ALTER TABLE chat_sessions ADD COLUMN email_captured_at TIMESTAMP;",
            "ALTER TABLE chat_sessions ADD COLUMN email_expires_at TIMESTAMP;"
        ]
        
        for cmd in sql_commands:
            try:
                cursor.execute(cmd)
                print(f"✅ {cmd}")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    print(f"ℹ️  Column already exists: {cmd}")
                else:
                    print(f"⚠️  {cmd} - {e}")
        
        conn.commit()
        cursor.close()
        conn.close()
        print("✅ SQLite fix completed!")
        return True
        
    except Exception as e:
        print(f"❌ SQLite error: {e}")
        return False

if __name__ == "__main__":
    print("🔧 Database Fix Script")
    print("=" * 40)
    
    # Try PostgreSQL first
    if fix_postgresql():
        print("🎉 Database fixed! Your chatbot should work now.")
    else:
        print("❌ PostgreSQL fix failed. Trying SQLite...")
        if fix_sqlite():
            print("🎉 SQLite database fixed!")
        else:
            print("❌ Both database fixes failed.")
            print("💡 You may need to run the SQL commands manually.")