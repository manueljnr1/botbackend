#!/usr/bin/env python3
"""
Fix database schema mismatch for live chat tables
This script will add missing columns to your existing tables
"""

import sqlite3
import os
import sys

def check_database_exists():
    """Check if database exists"""
    if not os.path.exists('./chatbot.db'):
        print("❌ Database file './chatbot.db' not found")
        return False
    return True

def get_table_columns(cursor, table_name):
    """Get existing columns for a table"""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    return [col[1] for col in columns]  # Column names are at index 1

def fix_agents_table(cursor):
    """Fix the agents table by adding missing columns"""
    print("🔧 Fixing agents table...")
    
    existing_columns = get_table_columns(cursor, 'agents')
    print(f"   Existing columns: {existing_columns}")
    
    # Define expected columns and their types
    expected_columns = {
        'total_conversations': 'INTEGER DEFAULT 0',
        'avg_response_time_seconds': 'INTEGER DEFAULT 0'
    }
    
    # Add missing columns
    for column, column_def in expected_columns.items():
        if column not in existing_columns:
            try:
                cursor.execute(f"ALTER TABLE agents ADD COLUMN {column} {column_def}")
                print(f"   ✅ Added column: {column}")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e):
                    print(f"   ⚠️  Column {column} already exists")
                else:
                    print(f"   ❌ Error adding {column}: {e}")
        else:
            print(f"   ✅ Column {column} already exists")

def fix_conversations_table(cursor):
    """Fix the conversations table by adding missing columns"""
    print("🔧 Fixing conversations table...")
    
    # Check if table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='conversations'")
    if not cursor.fetchone():
        print("   ⚠️  Conversations table doesn't exist - this is expected if migration hasn't run")
        return
    
    existing_columns = get_table_columns(cursor, 'conversations')
    print(f"   Existing columns: {existing_columns}")
    
    # Define expected columns that might be missing
    expected_columns = {
        'queue_time_seconds': 'INTEGER DEFAULT 0',
        'first_response_time_seconds': 'INTEGER',
        'resolution_time_seconds': 'INTEGER',
        'satisfaction_rating': 'INTEGER'
    }
    
    # Add missing columns
    for column, column_def in expected_columns.items():
        if column not in existing_columns:
            try:
                cursor.execute(f"ALTER TABLE conversations ADD COLUMN {column} {column_def}")
                print(f"   ✅ Added column: {column}")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e):
                    print(f"   ⚠️  Column {column} already exists")
                else:
                    print(f"   ❌ Error adding {column}: {e}")

def update_agent_defaults(cursor):
    """Update existing agents with default values"""
    print("🔧 Updating agent default values...")
    
    try:
        # Set default values for existing agents
        cursor.execute("UPDATE agents SET total_conversations = 0 WHERE total_conversations IS NULL")
        cursor.execute("UPDATE agents SET avg_response_time_seconds = 0 WHERE avg_response_time_seconds IS NULL")
        cursor.execute("UPDATE agents SET department = 'general' WHERE department IS NULL")
        cursor.execute("UPDATE agents SET is_active = 1 WHERE is_active IS NULL")
        cursor.execute("UPDATE agents SET max_concurrent_chats = 3 WHERE max_concurrent_chats IS NULL")
        cursor.execute("UPDATE agents SET status = 'OFFLINE' WHERE status IS NULL")
        
        print("   ✅ Updated default values for existing agents")
        
    except sqlite3.OperationalError as e:
        print(f"   ⚠️  Error updating defaults: {e}")

def show_table_structure(cursor, table_name):
    """Show the structure of a table"""
    print(f"\n📋 {table_name} table structure:")
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    
    for col in columns:
        col_id, name, col_type, not_null, default, pk = col
        pk_str = " (PRIMARY KEY)" if pk else ""
        null_str = " NOT NULL" if not_null else ""
        default_str = f" DEFAULT {default}" if default else ""
        
        print(f"   - {name}: {col_type}{null_str}{default_str}{pk_str}")

def main():
    """Main function to fix database schema"""
    print("🔧 Fixing Live Chat Database Schema")
    print("=" * 40)
    
    # Check if database exists
    if not check_database_exists():
        print("Please make sure your database exists first")
        sys.exit(1)
    
    try:
        # Connect to database
        conn = sqlite3.connect('./chatbot.db')
        cursor = conn.cursor()
        
        # Check which tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in cursor.fetchall()]
        print(f"📋 Existing tables: {tables}")
        
        # Fix agents table (this is the main issue)
        if 'agents' in tables:
            fix_agents_table(cursor)
            update_agent_defaults(cursor)
            show_table_structure(cursor, 'agents')
        else:
            print("⚠️  Agents table doesn't exist - run the live chat migration first")
        
        # Fix conversations table if it exists
        if 'conversations' in tables:
            fix_conversations_table(cursor)
            show_table_structure(cursor, 'conversations')
        
        # Commit changes
        conn.commit()
        print("\n✅ Database schema fixes applied successfully!")
        
        # Test a query on agents table
        print("\n🧪 Testing agents table query...")
        cursor.execute("SELECT COUNT(*) FROM agents")
        count = cursor.fetchone()[0]
        print(f"   Found {count} agents in database")
        
        if count > 0:
            cursor.execute("SELECT id, name, status, total_conversations FROM agents LIMIT 3")
            agents = cursor.fetchall()
            print("   Sample agents:")
            for agent in agents:
                print(f"     ID: {agent[0]}, Name: {agent[1]}, Status: {agent[2]}, Total Chats: {agent[3]}")
        
        conn.close()
        
        print("\n🎉 Schema fix completed!")
        print("📝 You can now restart your server and test the live chat system")
        
    except Exception as e:
        print(f"❌ Error fixing database schema: {e}")
        return False
    
    return True

# ===========================
# ALTERNATIVE: Quick SQL Fix
# ===========================

def quick_sql_fix():
    """Quick SQL commands to fix the schema"""
    
    sql_commands = [
        "-- Add missing columns to agents table",
        "ALTER TABLE agents ADD COLUMN total_conversations INTEGER DEFAULT 0;",
        "ALTER TABLE agents ADD COLUMN avg_response_time_seconds INTEGER DEFAULT 0;",
        "",
        "-- Update existing agents with default values", 
        "UPDATE agents SET total_conversations = 0 WHERE total_conversations IS NULL;",
        "UPDATE agents SET avg_response_time_seconds = 0 WHERE avg_response_time_seconds IS NULL;",
        "UPDATE agents SET department = 'general' WHERE department IS NULL;",
        "UPDATE agents SET is_active = 1 WHERE is_active IS NULL;",
        "UPDATE agents SET max_concurrent_chats = 3 WHERE max_concurrent_chats IS NULL;",
        "UPDATE agents SET status = 'OFFLINE' WHERE status IS NULL;",
        "",
        "-- Verify the fix",
        "SELECT id, name, status, total_conversations, avg_response_time_seconds FROM agents;"
    ]
    
    print("📝 SQL commands to fix schema manually:")
    print("=" * 40)
    
    for cmd in sql_commands:
        print(cmd)
    
    print("\n💡 To run these manually:")
    print("1. sqlite3 ./chatbot.db")
    print("2. Copy and paste the SQL commands above")
    print("3. Type .quit to exit")

if __name__ == "__main__":
    print("Choose an option:")
    print("1. Auto-fix database schema (recommended)")
    print("2. Show SQL commands for manual fix")
    
    choice = input("\nEnter choice (1 or 2): ").strip()
    
    if choice == "1":
        main()
    elif choice == "2":
        quick_sql_fix()
    else:
        print("Invalid choice")