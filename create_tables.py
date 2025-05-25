# create_tables.py - Run this script to create live chat tables
import sqlite3
import os
import sys

# Path to your database file (adjust if different)
DB_PATH = "app.db"

def create_live_chat_tables():
    """Create all live chat tables in SQLite database"""
    
    print("🔧 Creating live chat tables...")
    
    # Check if database exists
    if not os.path.exists(DB_PATH):
        print(f"⚠️  Database file {DB_PATH} not found. Creating new database...")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Create agents table
        print("📋 Creating agents table...")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            name VARCHAR NOT NULL,
            email VARCHAR NOT NULL,
            avatar_url VARCHAR,
            department VARCHAR DEFAULT 'general',
            skills TEXT,
            status VARCHAR DEFAULT 'offline',
            is_active BOOLEAN DEFAULT 1,
            max_concurrent_chats INTEGER DEFAULT 3,
            current_chat_count INTEGER DEFAULT 0,
            total_chats_handled INTEGER DEFAULT 0,
            average_response_time INTEGER DEFAULT 0,
            customer_satisfaction_rating REAL DEFAULT 0.0,
            last_seen DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME,
            FOREIGN KEY (tenant_id) REFERENCES tenants (id)
        )
        """)
        
        # Create live_chats table
        print("💬 Creating live_chats table...")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS live_chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id VARCHAR UNIQUE NOT NULL,
            tenant_id INTEGER NOT NULL,
            user_identifier VARCHAR NOT NULL,
            user_name VARCHAR,
            user_email VARCHAR,
            platform VARCHAR DEFAULT 'web',
            agent_id INTEGER,
            assigned_at DATETIME,
            status VARCHAR DEFAULT 'waiting',
            subject VARCHAR,
            priority VARCHAR DEFAULT 'normal',
            department VARCHAR,
            chatbot_session_id VARCHAR,
            handoff_reason TEXT,
            bot_context TEXT,
            queue_time INTEGER DEFAULT 0,
            first_response_time INTEGER,
            resolution_time INTEGER,
            customer_satisfaction INTEGER,
            started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            ended_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME,
            FOREIGN KEY (tenant_id) REFERENCES tenants (id),
            FOREIGN KEY (agent_id) REFERENCES agents (id)
        )
        """)
        
        # Create live_chat_messages table
        print("📝 Creating live_chat_messages table...")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS live_chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            message_type VARCHAR DEFAULT 'text',
            file_url VARCHAR,
            is_from_user BOOLEAN DEFAULT 1,
            agent_id INTEGER,
            sender_name VARCHAR,
            is_internal BOOLEAN DEFAULT 0,
            read_by_user BOOLEAN DEFAULT 0,
            read_by_agent BOOLEAN DEFAULT 0,
            read_at DATETIME,
            platform_message_id VARCHAR,
            platform_metadata TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME,
            FOREIGN KEY (chat_id) REFERENCES live_chats (id),
            FOREIGN KEY (agent_id) REFERENCES agents (id)
        )
        """)
        
        # Create agent_sessions table
        print("🔐 Creating agent_sessions table...")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER NOT NULL,
            session_token VARCHAR UNIQUE,
            ip_address VARCHAR,
            user_agent VARCHAR,
            status VARCHAR DEFAULT 'online',
            last_activity DATETIME DEFAULT CURRENT_TIMESTAMP,
            logged_in_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            logged_out_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (agent_id) REFERENCES agents (id)
        )
        """)
        
        # Create chat_queue table
        print("📋 Creating chat_queue table...")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL UNIQUE,
            position INTEGER NOT NULL,
            estimated_wait_time INTEGER,
            department VARCHAR,
            priority VARCHAR DEFAULT 'normal',
            preferred_agent_id INTEGER,
            required_skills TEXT,
            queued_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tenant_id) REFERENCES tenants (id),
            FOREIGN KEY (chat_id) REFERENCES live_chats (id),
            FOREIGN KEY (preferred_agent_id) REFERENCES agents (id)
        )
        """)
        
        # Create indexes for better performance
        print("🚀 Creating indexes...")
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_agents_tenant_id ON agents (tenant_id)",
            "CREATE INDEX IF NOT EXISTS idx_agents_status ON agents (status)",
            "CREATE INDEX IF NOT EXISTS idx_agents_email ON agents (email)",
            "CREATE INDEX IF NOT EXISTS idx_live_chats_session_id ON live_chats (session_id)",
            "CREATE INDEX IF NOT EXISTS idx_live_chats_user_identifier ON live_chats (user_identifier)",
            "CREATE INDEX IF NOT EXISTS idx_live_chats_status ON live_chats (status)",
            "CREATE INDEX IF NOT EXISTS idx_live_chats_tenant_id ON live_chats (tenant_id)",
            "CREATE INDEX IF NOT EXISTS idx_live_chat_messages_chat_id ON live_chat_messages (chat_id)",
            "CREATE INDEX IF NOT EXISTS idx_live_chat_messages_created_at ON live_chat_messages (created_at)",
            "CREATE INDEX IF NOT EXISTS idx_chat_queue_tenant_id ON chat_queue (tenant_id)",
            "CREATE INDEX IF NOT EXISTS idx_chat_queue_position ON chat_queue (position)",
            "CREATE INDEX IF NOT EXISTS idx_agent_sessions_agent_id ON agent_sessions (agent_id)",
            "CREATE INDEX IF NOT EXISTS idx_agent_sessions_token ON agent_sessions (session_token)"
        ]
        
        for index_sql in indexes:
            cursor.execute(index_sql)
        
        # Commit all changes
        conn.commit()
        print("✅ All live chat tables created successfully!")
        
        # Verify tables were created
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND (
                name LIKE '%chat%' OR 
                name = 'agents' OR 
                name LIKE '%agent%'
            )
            ORDER BY name
        """)
        tables = cursor.fetchall()
        
        print(f"\n📊 Created/verified tables:")
        for table in tables:
            print(f"  ✓ {table[0]}")
        
        # Show table counts
        print(f"\n📈 Current table counts:")
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table[0]}")
            count = cursor.fetchone()[0]
            print(f"  📋 {table[0]}: {count} records")
        
        print(f"\n🎉 Database setup complete! Tables created in: {DB_PATH}")
        
    except Exception as e:
        print(f"❌ Error creating tables: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()
    
    return True

def verify_tables():
    """Verify that all tables exist and have correct structure"""
    print("\n🔍 Verifying table structure...")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    expected_tables = [
        'agents',
        'live_chats', 
        'live_chat_messages',
        'agent_sessions',
        'chat_queue'
    ]
    
    try:
        for table in expected_tables:
            cursor.execute(f"PRAGMA table_info({table})")
            columns = cursor.fetchall()
            
            if columns:
                print(f"  ✓ {table}: {len(columns)} columns")
            else:
                print(f"  ❌ {table}: Table not found!")
                
    except Exception as e:
        print(f"❌ Error verifying tables: {e}")
    finally:
        conn.close()

def main():
    """Main function to run the table creation"""
    print("🚀 Live Chat Database Setup")
    print("=" * 40)
    
    # Check if database file exists
    if os.path.exists(DB_PATH):
        print(f"📁 Using existing database: {DB_PATH}")
    else:
        print(f"📁 Creating new database: {DB_PATH}")
    
    # Create tables
    success = create_live_chat_tables()
    
    if success:
        # Verify tables
        verify_tables()
        
        print("\n" + "=" * 40)
        print("✅ SETUP COMPLETE!")
        print("🔥 You can now start your FastAPI server")
        print("🌐 Test the live chat at: http://localhost:8000/docs")
        
    else:
        print("\n" + "=" * 40)
        print("❌ SETUP FAILED!")
        print("Check the error messages above and try again.")
        sys.exit(1)

if __name__ == "__main__":
    main()