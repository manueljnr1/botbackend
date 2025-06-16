#!/usr/bin/env python3
"""
SQLite Live Chat Tables Creation Script
Creates all tables needed for the live chat system in chatbot.db
"""

import sqlite3
import os
from datetime import datetime

# Database configuration
DATABASE_PATH = "./chatbot.db"

def create_live_chat_tables():
    """Create all live chat tables in SQLite database"""
    
    # Connect to database
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    print(f"🔗 Connected to database: {DATABASE_PATH}")
    
    try:
        # =====================================================================
        # 1. EXTEND EXISTING AGENTS TABLE
        # =====================================================================
        
        print("📋 Extending agents table...")
        
        # Check if agents table exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='agents'
        """)
        
        if cursor.fetchone():
            print("✅ Agents table exists, adding new columns...")
            
            # Add new columns to existing agents table (SQLite doesn't support multiple ADD COLUMN)
            new_columns = [
                ("email", "VARCHAR"),
                ("full_name", "VARCHAR"),
                ("display_name", "VARCHAR"),
                ("avatar_url", "VARCHAR"),
                ("password_hash", "VARCHAR"),
                ("invite_token", "VARCHAR"),
                ("invited_by", "INTEGER"),
                ("invited_at", "DATETIME"),
                ("password_set_at", "DATETIME"),
                ("status", "VARCHAR DEFAULT 'invited'"),
                ("is_active", "BOOLEAN DEFAULT 1"),
                ("last_login", "DATETIME"),
                ("last_seen", "DATETIME"),
                ("is_online", "BOOLEAN DEFAULT 0"),
                ("total_conversations", "INTEGER DEFAULT 0"),
                ("total_messages_sent", "INTEGER DEFAULT 0"),
                ("average_response_time", "REAL"),
                ("customer_satisfaction_avg", "REAL"),
                ("conversations_today", "INTEGER DEFAULT 0"),
                ("notification_settings", "TEXT"),
                ("timezone", "VARCHAR DEFAULT 'UTC'"),
                ("max_concurrent_chats", "INTEGER DEFAULT 3"),
                ("auto_assign", "BOOLEAN DEFAULT 1"),
                ("work_hours_start", "VARCHAR"),
                ("work_hours_end", "VARCHAR"),
                ("work_days", "VARCHAR"),
                ("created_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
                ("updated_at", "DATETIME DEFAULT CURRENT_TIMESTAMP")
            ]
            
            for column_name, column_type in new_columns:
                try:
                    cursor.execute(f"ALTER TABLE agents ADD COLUMN {column_name} {column_type}")
                    print(f"  ✅ Added column: {column_name}")
                except sqlite3.OperationalError as e:
                    if "duplicate column name" in str(e).lower():
                        print(f"  ⚠️  Column {column_name} already exists")
                    else:
                        print(f"  ❌ Error adding {column_name}: {e}")
        else:
            print("🆕 Creating new agents table...")
            cursor.execute("""
                CREATE TABLE agents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id INTEGER NOT NULL,
                    email VARCHAR,
                    full_name VARCHAR,
                    display_name VARCHAR,
                    avatar_url VARCHAR,
                    password_hash VARCHAR,
                    invite_token VARCHAR,
                    invited_by INTEGER,
                    invited_at DATETIME,
                    password_set_at DATETIME,
                    status VARCHAR DEFAULT 'invited',
                    is_active BOOLEAN DEFAULT 1,
                    last_login DATETIME,
                    last_seen DATETIME,
                    is_online BOOLEAN DEFAULT 0,
                    total_conversations INTEGER DEFAULT 0,
                    total_messages_sent INTEGER DEFAULT 0,
                    average_response_time REAL,
                    customer_satisfaction_avg REAL,
                    conversations_today INTEGER DEFAULT 0,
                    notification_settings TEXT,
                    timezone VARCHAR DEFAULT 'UTC',
                    max_concurrent_chats INTEGER DEFAULT 3,
                    auto_assign BOOLEAN DEFAULT 1,
                    work_hours_start VARCHAR,
                    work_hours_end VARCHAR,
                    work_days VARCHAR,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
                    FOREIGN KEY (invited_by) REFERENCES tenants(id)
                )
            """)
            print("✅ Created agents table")
        
        # =====================================================================
        # 2. CREATE LIVE CHAT CONVERSATIONS TABLE
        # =====================================================================
        
        print("📋 Creating live_chat_conversations table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS live_chat_conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL,
                customer_identifier VARCHAR NOT NULL,
                customer_email VARCHAR,
                customer_name VARCHAR,
                customer_phone VARCHAR,
                customer_ip VARCHAR,
                customer_user_agent TEXT,
                chatbot_session_id VARCHAR,
                handoff_reason VARCHAR,
                handoff_trigger VARCHAR,
                handoff_context TEXT,
                original_question TEXT,
                status VARCHAR NOT NULL DEFAULT 'queued',
                queue_position INTEGER,
                priority_level INTEGER NOT NULL DEFAULT 1,
                queue_entry_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                assigned_agent_id INTEGER,
                assigned_at DATETIME,
                assignment_method VARCHAR,
                previous_agent_id INTEGER,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                first_response_at DATETIME,
                last_activity_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                closed_at DATETIME,
                wait_time_seconds INTEGER,
                response_time_seconds INTEGER,
                conversation_duration_seconds INTEGER,
                message_count INTEGER NOT NULL DEFAULT 0,
                agent_message_count INTEGER NOT NULL DEFAULT 0,
                customer_message_count INTEGER NOT NULL DEFAULT 0,
                customer_satisfaction INTEGER,
                customer_feedback TEXT,
                satisfaction_submitted_at DATETIME,
                closed_by VARCHAR,
                closure_reason VARCHAR,
                resolution_status VARCHAR,
                agent_notes TEXT,
                internal_notes TEXT,
                tags TEXT,
                category VARCHAR,
                department VARCHAR,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id),
                FOREIGN KEY (assigned_agent_id) REFERENCES agents(id),
                FOREIGN KEY (previous_agent_id) REFERENCES agents(id)
            )
        """)
        print("✅ Created live_chat_conversations table")
        
        # =====================================================================
        # 3. CREATE LIVE CHAT MESSAGES TABLE
        # =====================================================================
        
        print("📋 Creating live_chat_messages table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS live_chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                message_type VARCHAR NOT NULL DEFAULT 'text',
                raw_content TEXT,
                sender_type VARCHAR NOT NULL,
                sender_id VARCHAR,
                agent_id INTEGER,
                sender_name VARCHAR,
                sender_avatar VARCHAR,
                sent_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                delivered_at DATETIME,
                read_at DATETIME,
                edited_at DATETIME,
                is_internal BOOLEAN NOT NULL DEFAULT 0,
                is_edited BOOLEAN NOT NULL DEFAULT 0,
                is_deleted BOOLEAN NOT NULL DEFAULT 0,
                deleted_at DATETIME,
                attachment_url VARCHAR,
                attachment_name VARCHAR,
                attachment_type VARCHAR,
                attachment_size INTEGER,
                system_event_type VARCHAR,
                system_event_data TEXT,
                client_message_id VARCHAR,
                reply_to_message_id INTEGER,
                thread_id VARCHAR,
                FOREIGN KEY (conversation_id) REFERENCES live_chat_conversations(id),
                FOREIGN KEY (agent_id) REFERENCES agents(id),
                FOREIGN KEY (reply_to_message_id) REFERENCES live_chat_messages(id)
            )
        """)
        print("✅ Created live_chat_messages table")
        
        # =====================================================================
        # 4. CREATE AGENT SESSIONS TABLE
        # =====================================================================
        
        print("📋 Creating agent_sessions table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id INTEGER NOT NULL,
                tenant_id INTEGER NOT NULL,
                session_id VARCHAR NOT NULL UNIQUE,
                status VARCHAR NOT NULL DEFAULT 'offline',
                login_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                logout_at DATETIME,
                last_activity DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                active_conversations INTEGER NOT NULL DEFAULT 0,
                max_concurrent_chats INTEGER NOT NULL DEFAULT 3,
                is_accepting_chats BOOLEAN NOT NULL DEFAULT 1,
                messages_sent INTEGER NOT NULL DEFAULT 0,
                conversations_handled INTEGER NOT NULL DEFAULT 0,
                average_response_time REAL,
                total_online_time INTEGER NOT NULL DEFAULT 0,
                ip_address VARCHAR,
                user_agent VARCHAR,
                websocket_id VARCHAR UNIQUE,
                device_type VARCHAR,
                browser VARCHAR,
                status_message VARCHAR,
                away_message VARCHAR,
                FOREIGN KEY (agent_id) REFERENCES agents(id),
                FOREIGN KEY (tenant_id) REFERENCES tenants(id)
            )
        """)
        print("✅ Created agent_sessions table")
        
        # =====================================================================
        # 5. CREATE CHAT QUEUE TABLE
        # =====================================================================
        
        print("📋 Creating chat_queue table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL,
                conversation_id INTEGER NOT NULL UNIQUE,
                position INTEGER NOT NULL,
                priority INTEGER NOT NULL DEFAULT 1,
                estimated_wait_time INTEGER,
                preferred_agent_id INTEGER,
                assignment_criteria TEXT,
                skills_required TEXT,
                language_preference VARCHAR,
                entry_reason VARCHAR,
                queue_source VARCHAR,
                queued_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                assigned_at DATETIME,
                removed_at DATETIME,
                status VARCHAR NOT NULL DEFAULT 'waiting',
                abandon_reason VARCHAR,
                customer_message_preview TEXT,
                urgency_indicators TEXT,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id),
                FOREIGN KEY (conversation_id) REFERENCES live_chat_conversations(id),
                FOREIGN KEY (preferred_agent_id) REFERENCES agents(id)
            )
        """)
        print("✅ Created chat_queue table")
        
        # =====================================================================
        # 6. CREATE CONVERSATION TRANSFERS TABLE
        # =====================================================================
        
        print("📋 Creating conversation_transfers table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversation_transfers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                tenant_id INTEGER NOT NULL,
                from_agent_id INTEGER NOT NULL,
                to_agent_id INTEGER,
                transfer_reason VARCHAR,
                transfer_notes TEXT,
                status VARCHAR NOT NULL DEFAULT 'pending',
                initiated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at DATETIME,
                conversation_summary TEXT,
                customer_context TEXT,
                FOREIGN KEY (conversation_id) REFERENCES live_chat_conversations(id),
                FOREIGN KEY (tenant_id) REFERENCES tenants(id),
                FOREIGN KEY (from_agent_id) REFERENCES agents(id),
                FOREIGN KEY (to_agent_id) REFERENCES agents(id)
            )
        """)
        print("✅ Created conversation_transfers table")
        
        # =====================================================================
        # 7. CREATE CONVERSATION TAGS TABLE
        # =====================================================================
        
        print("📋 Creating conversation_tags table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversation_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL,
                name VARCHAR NOT NULL,
                color VARCHAR,
                description VARCHAR,
                usage_count INTEGER NOT NULL DEFAULT 0,
                created_by_agent_id INTEGER,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id),
                FOREIGN KEY (created_by_agent_id) REFERENCES agents(id)
            )
        """)
        print("✅ Created conversation_tags table")
        
        # =====================================================================
        # 8. CREATE LIVE CHAT SETTINGS TABLE
        # =====================================================================
        
        print("📋 Creating live_chat_settings table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS live_chat_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL UNIQUE,
                is_enabled BOOLEAN NOT NULL DEFAULT 1,
                welcome_message TEXT,
                offline_message TEXT,
                pre_chat_form_enabled BOOLEAN NOT NULL DEFAULT 0,
                post_chat_survey_enabled BOOLEAN NOT NULL DEFAULT 1,
                max_queue_size INTEGER NOT NULL DEFAULT 50,
                max_wait_time_minutes INTEGER NOT NULL DEFAULT 30,
                queue_timeout_message TEXT,
                auto_assignment_enabled BOOLEAN NOT NULL DEFAULT 1,
                assignment_method VARCHAR NOT NULL DEFAULT 'round_robin',
                max_chats_per_agent INTEGER NOT NULL DEFAULT 3,
                business_hours_enabled BOOLEAN NOT NULL DEFAULT 0,
                business_hours TEXT,
                timezone VARCHAR NOT NULL DEFAULT 'UTC',
                email_notifications_enabled BOOLEAN NOT NULL DEFAULT 1,
                escalation_email VARCHAR,
                notification_triggers TEXT,
                widget_color VARCHAR NOT NULL DEFAULT '#6d28d9',
                widget_position VARCHAR NOT NULL DEFAULT 'bottom-right',
                company_logo_url VARCHAR,
                file_upload_enabled BOOLEAN NOT NULL DEFAULT 1,
                file_size_limit_mb INTEGER NOT NULL DEFAULT 10,
                allowed_file_types TEXT,
                customer_info_retention_days INTEGER NOT NULL DEFAULT 365,
                require_email_verification BOOLEAN NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id)
            )
        """)
        print("✅ Created live_chat_settings table")
        
        # =====================================================================
        # 9. CREATE INDEXES FOR PERFORMANCE
        # =====================================================================
        
        print("📋 Creating indexes...")
        
        indexes = [
            # Agents table indexes
            ("idx_agents_tenant_id", "agents", "tenant_id"),
            ("idx_agents_email", "agents", "email"),
            ("idx_agents_status", "agents", "status"),
            ("idx_agents_invite_token", "agents", "invite_token"),
            ("idx_agents_is_online", "agents", "is_online"),
            
            # Live chat conversations indexes
            ("idx_live_chat_conversations_tenant_id", "live_chat_conversations", "tenant_id"),
            ("idx_live_chat_conversations_customer_id", "live_chat_conversations", "customer_identifier"),
            ("idx_live_chat_conversations_status", "live_chat_conversations", "status"),
            ("idx_live_chat_conversations_assigned_agent", "live_chat_conversations", "assigned_agent_id"),
            ("idx_live_chat_conversations_created_at", "live_chat_conversations", "created_at"),
            ("idx_live_chat_conversations_chatbot_session", "live_chat_conversations", "chatbot_session_id"),
            
            # Live chat messages indexes
            ("idx_live_chat_messages_conversation_id", "live_chat_messages", "conversation_id"),
            ("idx_live_chat_messages_sent_at", "live_chat_messages", "sent_at"),
            ("idx_live_chat_messages_sender_type", "live_chat_messages", "sender_type"),
            
            # Agent sessions indexes
            ("idx_agent_sessions_agent_id", "agent_sessions", "agent_id"),
            ("idx_agent_sessions_session_id", "agent_sessions", "session_id"),
            ("idx_agent_sessions_websocket_id", "agent_sessions", "websocket_id"),
            ("idx_agent_sessions_status", "agent_sessions", "status"),
            
            # Chat queue indexes
            ("idx_chat_queue_tenant_id", "chat_queue", "tenant_id"),
            ("idx_chat_queue_status", "chat_queue", "status"),
            ("idx_chat_queue_position", "chat_queue", "position"),
            ("idx_chat_queue_priority", "chat_queue", "priority"),
            
            # Conversation transfers indexes
            ("idx_conversation_transfers_conversation_id", "conversation_transfers", "conversation_id"),
            ("idx_conversation_transfers_from_agent", "conversation_transfers", "from_agent_id"),
            ("idx_conversation_transfers_to_agent", "conversation_transfers", "to_agent_id"),
            
            # Conversation tags indexes
            ("idx_conversation_tags_tenant_id", "conversation_tags", "tenant_id"),
            ("idx_conversation_tags_name", "conversation_tags", "name")
        ]
        
        for index_name, table_name, column_name in indexes:
            try:
                cursor.execute(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name}({column_name})")
                print(f"  ✅ Created index: {index_name}")
            except sqlite3.Error as e:
                print(f"  ⚠️  Index {index_name} error: {e}")
        
        # =====================================================================
        # 10. COMMIT CHANGES
        # =====================================================================
        
        conn.commit()
        print("\n🎉 All live chat tables created successfully!")
        
        # =====================================================================
        # 11. VERIFY TABLES
        # =====================================================================
        
        print("\n📊 Verifying tables...")
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name LIKE '%live_chat%' OR name = 'agents'
            ORDER BY name
        """)
        
        tables = cursor.fetchall()
        print(f"📋 Found {len(tables)} live chat related tables:")
        for table in tables:
            print(f"  ✅ {table[0]}")
        
        # =====================================================================
        # 12. CREATE SAMPLE DATA (OPTIONAL)
        # =====================================================================
        
        create_sample = input("\n❓ Create sample test data? (y/N): ").lower().strip()
        if create_sample == 'y':
            create_sample_data(cursor)
            conn.commit()
            print("✅ Sample data created!")
        
    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        conn.rollback()
        raise
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()
        print(f"\n🔐 Database connection closed")


def create_sample_data(cursor):
    """Create sample test data for development"""
    print("🎭 Creating sample test data...")
    
    # Sample live chat settings
    cursor.execute("""
        INSERT OR IGNORE INTO live_chat_settings (
            tenant_id, welcome_message, offline_message
        ) VALUES (
            1, 
            'Hi! How can we help you today?',
            'We are currently offline. Please leave a message and we will get back to you soon!'
        )
    """)
    
    # Sample agent (if tenant_id 1 exists)
    cursor.execute("""
        INSERT OR IGNORE INTO agents (
            tenant_id, email, full_name, display_name, status
        ) VALUES (
            1, 
            'test.agent@example.com',
            'Test Agent',
            'Test',
            'invited'
        )
    """)
    
    print("  ✅ Sample live chat settings created")
    print("  ✅ Sample test agent created")


def check_database_exists():
    """Check if database file exists"""
    if os.path.exists(DATABASE_PATH):
        print(f"✅ Database file found: {DATABASE_PATH}")
        return True
    else:
        print(f"🆕 Creating new database: {DATABASE_PATH}")
        return False


def backup_database():
    """Create a backup of the database before modifications"""
    if os.path.exists(DATABASE_PATH):
        backup_path = f"{DATABASE_PATH}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        import shutil
        shutil.copy2(DATABASE_PATH, backup_path)
        print(f"💾 Database backed up to: {backup_path}")
        return backup_path
    return None


def main():
    """Main function"""
    print("=" * 60)
    print("🚀 LIVE CHAT TABLES CREATION SCRIPT")
    print("=" * 60)
    print(f"📁 Database: {DATABASE_PATH}")
    print(f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # Check if database exists
    db_exists = check_database_exists()
    
    if db_exists:
        # Create backup
        backup_path = backup_database()
        
        # Ask for confirmation
        proceed = input("\n⚠️  Database exists. Proceed with modifications? (y/N): ").lower().strip()
        if proceed != 'y':
            print("❌ Operation cancelled by user")
            return
    
    try:
        # Create tables
        create_live_chat_tables()
        
        print("\n" + "=" * 60)
        print("🎉 LIVE CHAT TABLES SETUP COMPLETE!")
        print("=" * 60)
        print("📋 Next steps:")
        print("  1. Update your models.py imports")
        print("  2. Test the agent invitation system")
        print("  3. Set up your email service (Resend)")
        print("  4. Configure your frontend URLs")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Setup failed: {e}")
        if db_exists and 'backup_path' in locals():
            print(f"💾 Database backup available at: {backup_path}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())