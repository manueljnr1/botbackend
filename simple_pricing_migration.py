#!/usr/bin/env python3
"""
Debug what's in the database
"""

import sqlite3

def debug_sqlite():
    """Check what's in SQLite database"""
    try:
        conn = sqlite3.connect("./chatbot.db")
        cursor = conn.cursor()
        
        print("🔍 Checking SQLite database...")
        
        # Check if pending_feedback table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pending_feedback';")
        table_exists = cursor.fetchone()
        
        if not table_exists:
            print("❌ pending_feedback table doesn't exist!")
            return
        
        print("✅ pending_feedback table exists")
        
        # Check table structure
        cursor.execute("PRAGMA table_info(pending_feedback);")
        columns = cursor.fetchall()
        print(f"\n📋 Table columns ({len(columns)}):")
        for col in columns:
            print(f"  - {col[1]} ({col[2]})")
        
        # Check all records
        cursor.execute("SELECT feedback_id, tenant_id, user_question, status FROM pending_feedback;")
        records = cursor.fetchall()
        
        print(f"\n📊 Found {len(records)} records:")
        for record in records:
            print(f"  ID: {record[0]}")
            print(f"  Tenant: {record[1]}")
            print(f"  Question: {record[2]}")
            print(f"  Status: {record[3]}")
            print("  ---")
        
        conn.close()
        
        if records:
            test_id = records[0][0]
            print(f"\n🔗 Try this URL: http://localhost:8000/chatbot/feedback/form/{test_id}")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    debug_sqlite()