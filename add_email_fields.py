#!/usr/bin/env python3
"""
Script to add missing columns to your SQLite database
"""

import sqlite3
import os

# Find your database file
possible_db_files = [
    "chatbot.db",
    "app.db", 
    "database.db",
    "sqlite.db",
    "chat.db"
]

def find_database():
    """Find the SQLite database file"""
    for db_file in possible_db_files:
        if os.path.exists(db_file):
            return db_file
    
    # Look in common directories
    for root, dirs, files in os.walk("."):
        for file in files:
            if file.endswith(".db"):
                return os.path.join(root, file)
    
    return None

def add_missing_columns():
    """Add missing columns to the database"""
    db_file = find_database()
    
    if not db_file:
        print("❌ Could not find SQLite database file")
        print("Please check these common names:", possible_db_files)
        return False
    
    print(f"📁 Found database: {db_file}")
    
    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        
        # Check existing columns
        cursor.execute("PRAGMA table_info(tenants);")
        existing_columns = [column[1] for column in cursor.fetchall()]
        print(f"📋 Existing tenant columns: {existing_columns}")
        
        # Add missing columns to tenants table
        columns_to_add = [
            ("company_name", "VARCHAR(255)"),
            ("feedback_email", "VARCHAR(255)"),
            ("from_email", "VARCHAR(255)"),
            ("enable_feedback_system", "BOOLEAN DEFAULT 1")
        ]
        
        for col_name, col_type in columns_to_add:
            if col_name not in existing_columns:
                try:
                    cursor.execute(f"ALTER TABLE tenants ADD COLUMN {col_name} {col_type};")
                    print(f"✅ Added column: tenants.{col_name}")
                except sqlite3.OperationalError as e:
                    if "duplicate column name" in str(e):
                        print(f"⚠️  Column already exists: tenants.{col_name}")
                    else:
                        print(f"❌ Error adding tenants.{col_name}: {e}")
            else:
                print(f"⚠️  Column already exists: tenants.{col_name}")
        
        # Check chat_sessions table
        cursor.execute("PRAGMA table_info(chat_sessions);")
        session_columns = [column[1] for column in cursor.fetchall()]
        print(f"📋 Existing chat_sessions columns: {session_columns}")
        
        # Add user_email to chat_sessions if missing
        if "user_email" not in session_columns:
            try:
                cursor.execute("ALTER TABLE chat_sessions ADD COLUMN user_email VARCHAR(255);")
                print("✅ Added column: chat_sessions.user_email")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e):
                    print("⚠️  Column already exists: chat_sessions.user_email")
                else:
                    print(f"❌ Error adding chat_sessions.user_email: {e}")
        else:
            print("⚠️  Column already exists: chat_sessions.user_email")
        
        # Commit changes
        conn.commit()
        conn.close()
        
        print("\n🎉 Database update completed!")
        print("You can now restart your server.")
        
        return True
        
    except Exception as e:
        print(f"❌ Error updating database: {e}")
        return False

if __name__ == "__main__":
    print("🔧 Fixing database schema...")
    add_missing_columns()