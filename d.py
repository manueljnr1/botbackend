#!/usr/bin/env python3
"""
SQLite Database Runner for Chatbot System
Usage: python sqlite_runner.py [command]
"""

import sqlite3
import sys
import os
import json
from datetime import datetime
from pathlib import Path

class ChatbotDBRunner:
    def __init__(self, db_path="./chatbot.db"):
        self.db_path = db_path
        self.conn = None
    
    def connect(self):
        """Connect to SQLite database"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row  # Enable dict-like access
            print(f"✅ Connected to database: {self.db_path}")
            return True
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            return False
    
    def disconnect(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            print("📡 Database connection closed")
    
    def execute_query(self, query, params=None):
        """Execute a query and return results"""
        try:
            cursor = self.conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            if query.strip().upper().startswith('SELECT'):
                return cursor.fetchall()
            else:
                self.conn.commit()
                return cursor.rowcount
        except Exception as e:
            print(f"❌ Query failed: {e}")
            return None
    
    def show_tables(self):
        """Show all tables in database"""
        query = "SELECT name FROM sqlite_master WHERE type='table'"
        tables = self.execute_query(query)
        
        print("\n📊 Database Tables:")
        print("-" * 30)
        for table in tables:
            print(f"  • {table['name']}")
        print()
    
    def describe_table(self, table_name):
        """Show table structure"""
        query = f"PRAGMA table_info({table_name})"
        columns = self.execute_query(query)
        
        print(f"\n🏗️  Table Structure: {table_name}")
        print("-" * 50)
        print(f"{'Column':<20} {'Type':<15} {'Not Null':<8} {'Default'}")
        print("-" * 50)
        
        for col in columns:
            null_str = "YES" if col['notnull'] else "NO"
            default = col['dflt_value'] if col['dflt_value'] else ""
            print(f"{col['name']:<20} {col['type']:<15} {null_str:<8} {default}")
        print()
    
    def show_tenants(self):
        """Show all tenants"""
        query = "SELECT id, name, business_name, email, is_active FROM tenants"
        tenants = self.execute_query(query)
        
        print("\n👥 Tenants:")
        print("-" * 80)
        print(f"{'ID':<5} {'Name':<20} {'Business':<25} {'Email':<25} {'Active'}")
        print("-" * 80)
        
        for tenant in tenants:
            active = "✅" if tenant['is_active'] else "❌"
            print(f"{tenant['id']:<5} {tenant['name']:<20} {tenant['business_name']:<25} {tenant['email']:<25} {active}")
        print()
    
    def show_chat_sessions(self, limit=10, tenant_id=None):
        """Show recent chat sessions"""
        query = """
        SELECT cs.session_id, cs.user_identifier, cs.created_at, cs.is_active,
               t.name as tenant_name, 
               COUNT(cm.id) as message_count
        FROM chat_sessions cs
        LEFT JOIN tenants t ON cs.tenant_id = t.id
        LEFT JOIN chat_messages cm ON cs.id = cm.session_id
        """
        
        params = []
        if tenant_id:
            query += " WHERE cs.tenant_id = ?"
            params.append(tenant_id)
        
        query += " GROUP BY cs.id ORDER BY cs.created_at DESC LIMIT ?"
        params.append(limit)
        
        sessions = self.execute_query(query, params)
        
        print(f"\n💬 Recent Chat Sessions (Last {limit}):")
        print("-" * 100)
        print(f"{'Session ID':<15} {'User':<20} {'Tenant':<15} {'Messages':<8} {'Created':<20} {'Active'}")
        print("-" * 100)
        
        for session in sessions:
            active = "✅" if session['is_active'] else "❌"
            created = session['created_at'][:19] if session['created_at'] else "Unknown"
            print(f"{session['session_id']:<15} {session['user_identifier']:<20} {session['tenant_name']:<15} {session['message_count']:<8} {created:<20} {active}")
        print()
    
    def show_messages(self, session_id):
        """Show messages for a specific session"""
        query = """
        SELECT content, is_from_user, created_at
        FROM chat_messages cm
        JOIN chat_sessions cs ON cm.session_id = cs.id
        WHERE cs.session_id = ?
        ORDER BY cm.created_at
        """
        
        messages = self.execute_query(query, [session_id])
        
        print(f"\n💬 Messages for Session: {session_id}")
        print("-" * 80)
        
        for msg in messages:
            role = "👤 User" if msg['is_from_user'] else "🤖 Bot"
            timestamp = msg['created_at'][:19] if msg['created_at'] else "Unknown"
            content = msg['content'][:60] + "..." if len(msg['content']) > 60 else msg['content']
            print(f"{timestamp} {role}: {content}")
        print()
    
    def show_analytics_summary(self):
        """Show analytics summary"""
        queries = {
            "Total Tenants": "SELECT COUNT(*) as count FROM tenants",
            "Active Tenants": "SELECT COUNT(*) as count FROM tenants WHERE is_active = 1",
            "Total Sessions": "SELECT COUNT(*) as count FROM chat_sessions",
            "Active Sessions": "SELECT COUNT(*) as count FROM chat_sessions WHERE is_active = 1",
            "Total Messages": "SELECT COUNT(*) as count FROM chat_messages",
            "Today's Sessions": "SELECT COUNT(*) as count FROM chat_sessions WHERE date(created_at) = date('now')",
        }
        
        print("\n📊 Analytics Summary:")
        print("-" * 40)
        
        for label, query in queries.items():
            result = self.execute_query(query)
            count = result[0]['count'] if result else 0
            print(f"{label:<20}: {count:>10,}")
        print()
    
    def create_analytics_table(self):
        """Create the analytics table if it doesn't exist"""
        query = """
        CREATE TABLE IF NOT EXISTS conversation_analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE NOT NULL,
            tenant_id INTEGER NOT NULL,
            conversation_category TEXT,
            conversation_sentiment TEXT,
            conversation_topics TEXT,
            user_rating INTEGER CHECK(user_rating >= 1 AND user_rating <= 5),
            user_feedback TEXT,
            user_journey_stage TEXT,
            conversation_flow TEXT,
            analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            analysis_version TEXT DEFAULT 'v1.0',
            FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id),
            FOREIGN KEY (tenant_id) REFERENCES tenants(id)
        )
        """
        
        result = self.execute_query(query)
        if result is not None:
            print("✅ Analytics table created/verified")
        
        # Also add location columns to chat_sessions if they don't exist
        location_queries = [
            "ALTER TABLE chat_sessions ADD COLUMN user_country TEXT",
            "ALTER TABLE chat_sessions ADD COLUMN user_city TEXT", 
            "ALTER TABLE chat_sessions ADD COLUMN user_region TEXT"
        ]
        
        for query in location_queries:
            try:
                self.execute_query(query)
            except:
                pass  # Column might already exist
        
        print("✅ Location columns added to chat_sessions")
    
    def interactive_mode(self):
        """Interactive SQL mode"""
        print("\n🔧 Interactive SQL Mode (type 'exit' to quit)")
        print("Available shortcuts:")
        print("  tables    - Show all tables")
        print("  tenants   - Show tenants")
        print("  sessions  - Show recent sessions")
        print("  analytics - Show analytics summary")
        print("  exit      - Exit interactive mode")
        print()
        
        while True:
            try:
                query = input("SQL> ").strip()
                
                if query.lower() == 'exit':
                    break
                elif query.lower() == 'tables':
                    self.show_tables()
                elif query.lower() == 'tenants':
                    self.show_tenants()
                elif query.lower() == 'sessions':
                    self.show_chat_sessions()
                elif query.lower() == 'analytics':
                    self.show_analytics_summary()
                elif query:
                    result = self.execute_query(query)
                    if result is not None:
                        if isinstance(result, list):
                            for row in result[:20]:  # Limit to 20 rows
                                print(dict(row))
                        else:
                            print(f"Affected rows: {result}")
                    print()
                    
            except KeyboardInterrupt:
                print("\n👋 Exiting interactive mode...")
                break
            except Exception as e:
                print(f"❌ Error: {e}")
    
    def backup_database(self, backup_path=None):
        """Create database backup"""
        if not backup_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"chatbot_backup_{timestamp}.db"
        
        try:
            # Simple file copy for SQLite
            import shutil
            shutil.copy2(self.db_path, backup_path)
            print(f"✅ Database backed up to: {backup_path}")
        except Exception as e:
            print(f"❌ Backup failed: {e}")

def main():
    """Main function with command line interface"""
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
    else:
        command = "interactive"
    
    db = ChatbotDBRunner()
    
    if not db.connect():
        return
    
    try:
        if command == "tables":
            db.show_tables()
        elif command == "tenants":
            db.show_tenants()
        elif command == "sessions":
            limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
            db.show_chat_sessions(limit)
        elif command == "messages":
            if len(sys.argv) < 3:
                print("Usage: python sqlite_runner.py messages <session_id>")
                return
            session_id = sys.argv[2]
            db.show_messages(session_id)
        elif command == "describe":
            if len(sys.argv) < 3:
                print("Usage: python sqlite_runner.py describe <table_name>")
                return
            table_name = sys.argv[2]
            db.describe_table(table_name)
        elif command == "analytics":
            db.show_analytics_summary()
        elif command == "backup":
            backup_path = sys.argv[2] if len(sys.argv) > 2 else None
            db.backup_database(backup_path)
        elif command == "setup":
            db.create_analytics_table()
        elif command == "interactive":
            db.interactive_mode()
        else:
            print("Available commands:")
            print("  tables                    - Show all tables")
            print("  tenants                   - Show all tenants")
            print("  sessions [limit]          - Show recent chat sessions")
            print("  messages <session_id>     - Show messages for session")
            print("  describe <table_name>     - Show table structure")
            print("  analytics                 - Show analytics summary")
            print("  setup                     - Create analytics tables")
            print("  backup [filename]         - Backup database")
            print("  interactive               - Interactive SQL mode")
    
    finally:
        db.disconnect()

if __name__ == "__main__":
    main()