#!/usr/bin/env python3
"""
Simple Database Debug Script for Live Chat
Place this file as debug_db.py in your project root
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def find_database():
    """Find the database file or URL"""
    
    # Check environment variables first
    env_vars = ['DATABASE_URL', 'SQLALCHEMY_DATABASE_URL', 'DB_URL']
    for var in env_vars:
        if os.getenv(var):
            return os.getenv(var)
    
    # Look for common database files
    possible_files = [
        './chatbot.db',
        './app.db', 
        './database.db',
        './sql_app.db',
        './test.db'
    ]
    
    for db_file in possible_files:
        if os.path.exists(db_file):
            print(f"📁 Found database file: {db_file}")
            return f"sqlite:///{db_file}"
    
    # Try to get from app config
    try:
        # Try importing database config without models
        import importlib.util
        
        db_file = project_root / "app" / "database.py"
        if db_file.exists():
            spec = importlib.util.spec_from_file_location("database", db_file)
            database_module = importlib.util.module_from_spec(spec)
            
            with open(db_file, 'r') as f:
                content = f.read()
                
            # Look for database URL patterns in the file
            import re
            patterns = [
                r'sqlite:///[./]*(\w+\.db)',
                r'DATABASE_URL.*=.*["\']([^"\']+)["\']',
                r'SQLALCHEMY_DATABASE_URL.*=.*["\']([^"\']+)["\']'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, content)
                if match:
                    url = match.group(1) if 'sqlite' not in match.group(0) else match.group(0)
                    if url.endswith('.db') and not url.startswith('sqlite'):
                        url = f"sqlite:///./{url}"
                    return url
                    
    except Exception as e:
        print(f"Could not parse database config: {e}")
    
    return None

def debug_database_direct():
    """Debug database using direct SQL queries"""
    
    database_url = find_database()
    
    if not database_url:
        print("❌ Could not find database")
        print("\n💡 Please check manually:")
        print("1. Look for .db files in your project directory")
        print("2. Check your app/database.py file")
        print("3. Check environment variables")
        return
    
    try:
        from sqlalchemy import create_engine, text
        
        engine = create_engine(database_url)
        print(f"✅ Connected to: {database_url}")
        
        with engine.connect() as conn:
            
            # First, let's see what tables exist
            print("\n=== AVAILABLE TABLES ===")
            try:
                if 'sqlite' in database_url:
                    result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"))
                elif 'postgresql' in database_url:
                    result = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"))
                else:
                    result = conn.execute(text("SHOW TABLES"))
                
                tables = [row[0] for row in result.fetchall()]
                print(f"Tables found: {', '.join(tables)}")
                
                # Check if our tables exist
                required_tables = ['live_chats', 'chat_queue', 'agents', 'tenants']
                missing_tables = [t for t in required_tables if t not in tables]
                if missing_tables:
                    print(f"⚠️ Missing tables: {', '.join(missing_tables)}")
                    return
                    
            except Exception as e:
                print(f"Could not list tables: {e}")
                return
            
            # Check tenants first
            print("\n=== ALL TENANTS ===")
            try:
                result = conn.execute(text("SELECT id, name FROM tenants ORDER BY id"))
                tenants = result.fetchall()
                if tenants:
                    for tenant in tenants:
                        print(f"Tenant ID: {tenant[0]}, Name: {tenant[1]}")
                else:
                    print("No tenants found!")
                    return
            except Exception as e:
                print(f"Error querying tenants: {e}")
                return
            
            # Now check for each tenant
            for tenant_id, tenant_name in tenants:
                print(f"\n{'='*20} TENANT {tenant_id}: {tenant_name} {'='*20}")
                
                # Live chats
                print(f"\n--- LIVE CHATS (Tenant {tenant_id}) ---")
                try:
                    result = conn.execute(text("""
                        SELECT id, session_id, status, user_identifier, created_at, agent_id 
                        FROM live_chats 
                        WHERE tenant_id = :tenant_id 
                        ORDER BY created_at DESC 
                        LIMIT 5
                    """), {"tenant_id": tenant_id})
                    
                    chats = result.fetchall()
                    if chats:
                        for chat in chats:
                            print(f"  Chat ID: {chat[0]}, Session: {chat[1]}, Status: {chat[2]}")
                            print(f"    User: {chat[3]}, Agent ID: {chat[5]}, Created: {chat[4]}")
                    else:
                        print(f"  No live chats found for tenant {tenant_id}")
                except Exception as e:
                    print(f"  Error querying live_chats: {e}")
                
                # Queue entries
                print(f"\n--- QUEUE ENTRIES (Tenant {tenant_id}) ---")
                try:
                    result = conn.execute(text("""
                        SELECT cq.id, cq.chat_id, cq.position, cq.queued_at, lc.session_id, lc.user_identifier
                        FROM chat_queue cq
                        LEFT JOIN live_chats lc ON cq.chat_id = lc.id
                        WHERE cq.tenant_id = :tenant_id
                        ORDER BY cq.position
                    """), {"tenant_id": tenant_id})
                    
                    queue_entries = result.fetchall()
                    if queue_entries:
                        for entry in queue_entries:
                            print(f"  Queue ID: {entry[0]}, Chat ID: {entry[1]}, Position: {entry[2]}")
                            print(f"    Session: {entry[4]}, User: {entry[5]}, Queued: {entry[3]}")
                    else:
                        print(f"  No queue entries for tenant {tenant_id}")
                except Exception as e:
                    print(f"  Error querying queue: {e}")
                
                # Agents
                print(f"\n--- AGENTS (Tenant {tenant_id}) ---")
                try:
                    result = conn.execute(text("""
                        SELECT id, name, email, status, is_active, current_chat_count, max_concurrent_chats
                        FROM agents 
                        WHERE tenant_id = :tenant_id
                        ORDER BY id
                    """), {"tenant_id": tenant_id})
                    
                    agents = result.fetchall()
                    if agents:
                        for agent in agents:
                            print(f"  Agent ID: {agent[0]}, Name: {agent[1]}")
                            print(f"    Email: {agent[2]}, Status: {agent[3]}, Active: {agent[4]}")
                            print(f"    Current/Max Chats: {agent[5]}/{agent[6]}")
                    else:
                        print(f"  No agents found for tenant {tenant_id}")
                except Exception as e:
                    print(f"  Error querying agents: {e}")
    
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        print(f"Database URL attempted: {database_url}")

if __name__ == "__main__":
    print("🔍 Live Chat Database Debug Tool")
    print("=" * 50)
    debug_database_direct()