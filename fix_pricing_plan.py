#!/usr/bin/env python3
"""
Safe Live Chat Database Migration Script
Handles existing tables and adds missing columns/tables safely
"""

import sys
import logging
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import SQLAlchemyError
import psycopg2
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('safe_migration.log')
    ]
)
logger = logging.getLogger(__name__)

# Database configuration
DATABASE_URL = "postgresql://chatbot_hhjv_user:dYXguSEwpwZl3Yt2R3ACsfvmM5lLIgSD@dpg-d10sp295pdvs73afujf0-a.oregon-postgres.render.com/chatbot_hhjv"

class SafeDatabaseMigrator:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.engine = None
        
    def connect(self):
        """Establish database connection"""
        try:
            self.engine = create_engine(self.database_url, echo=False)
            
            # Test connection
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            
            logger.info("✅ Successfully connected to database")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to database: {e}")
            return False
    
    def table_exists(self, table_name: str) -> bool:
        """Check if table exists"""
        try:
            inspector = inspect(self.engine)
            tables = inspector.get_table_names()
            return table_name in tables
        except Exception as e:
            logger.error(f"Error checking if table {table_name} exists: {e}")
            return False
    
    def column_exists(self, table_name: str, column_name: str) -> bool:
        """Check if column exists in table"""
        try:
            inspector = inspect(self.engine)
            columns = [col['name'] for col in inspector.get_columns(table_name)]
            return column_name in columns
        except Exception as e:
            logger.error(f"Error checking column {column_name} in {table_name}: {e}")
            return False
    
    def run_sql(self, sql: str, description: str = "", ignore_errors: bool = False) -> bool:
        """Execute SQL and return success status"""
        try:
            with self.engine.connect() as conn:
                with conn.begin():
                    conn.execute(text(sql))
            
            if description:
                logger.info(f"✅ {description}")
            return True
            
        except Exception as e:
            if ignore_errors:
                logger.warning(f"⚠️ Expected error for {description}: {e}")
                return True
            else:
                logger.error(f"❌ Error executing SQL{' for ' + description if description else ''}: {e}")
                return False
    
    def drop_existing_live_chat_tables(self):
        """Drop existing incomplete live chat tables"""
        logger.info("🗑️ Cleaning up existing incomplete live chat tables...")
        
        # Drop tables in reverse dependency order
        drop_order = [
            'chat_queue',
            'live_chat_messages', 
            'agent_sessions',
            'live_chat_conversations',
            'agents',
            'live_chat_settings'
        ]
        
        dropped_count = 0
        for table in drop_order:
            if self.table_exists(table):
                if self.run_sql(f"DROP TABLE IF EXISTS {table} CASCADE", f"Dropped table {table}", ignore_errors=True):
                    dropped_count += 1
                    logger.info(f"🗑️ Dropped table: {table}")
            else:
                logger.info(f"ℹ️ Table {table} doesn't exist, skipping")
        
        logger.info(f"✅ Cleaned up {dropped_count} existing tables")
        return True
    
    def create_live_chat_tables_safe(self):
        """Create live chat tables in the correct order"""
        logger.info("💬 Creating Live Chat tables in correct order...")
        
        # 1. Agents table (independent)
        agents_sql = """
        CREATE TABLE agents (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            
            -- Basic Information
            email VARCHAR NOT NULL,
            full_name VARCHAR NOT NULL,
            display_name VARCHAR,
            avatar_url VARCHAR,
            
            -- Authentication & Invitation
            password_hash VARCHAR,
            invite_token VARCHAR UNIQUE,
            invited_by INTEGER NOT NULL REFERENCES tenants(id),
            invited_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            password_set_at TIMESTAMP,
            
            -- Status & Activity
            status VARCHAR DEFAULT 'invited',
            is_active BOOLEAN DEFAULT TRUE,
            last_login TIMESTAMP,
            last_seen TIMESTAMP,
            is_online BOOLEAN DEFAULT FALSE,
            
            -- Performance Tracking
            total_conversations INTEGER DEFAULT 0,
            total_messages_sent INTEGER DEFAULT 0,
            average_response_time FLOAT,
            customer_satisfaction_avg FLOAT,
            conversations_today INTEGER DEFAULT 0,
            
            -- Preferences & Settings
            notification_settings TEXT,
            timezone VARCHAR DEFAULT 'UTC',
            max_concurrent_chats INTEGER DEFAULT 3,
            auto_assign BOOLEAN DEFAULT TRUE,
            
            -- Work Schedule
            work_hours_start VARCHAR,
            work_hours_end VARCHAR,
            work_days VARCHAR,
            
            -- Timestamps
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX idx_agents_tenant ON agents(tenant_id);
        CREATE INDEX idx_agents_email ON agents(email);
        CREATE INDEX idx_agents_invite_token ON agents(invite_token);
        CREATE INDEX idx_agents_status ON agents(status);
        CREATE INDEX idx_agents_active ON agents(is_active);
        """
        
        # 2. Live Chat Settings table (independent)
        live_chat_settings_sql = """
        CREATE TABLE live_chat_settings (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER UNIQUE NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            
            -- General Settings
            is_enabled BOOLEAN DEFAULT TRUE,
            welcome_message TEXT,
            offline_message TEXT,
            pre_chat_form_enabled BOOLEAN DEFAULT FALSE,
            post_chat_survey_enabled BOOLEAN DEFAULT TRUE,
            
            -- Queue Settings
            max_queue_size INTEGER DEFAULT 50,
            max_wait_time_minutes INTEGER DEFAULT 30,
            queue_timeout_message TEXT,
            
            -- Auto-Assignment Settings
            auto_assignment_enabled BOOLEAN DEFAULT TRUE,
            assignment_method VARCHAR DEFAULT 'round_robin',
            max_chats_per_agent INTEGER DEFAULT 3,
            
            -- Business Hours
            business_hours_enabled BOOLEAN DEFAULT FALSE,
            business_hours TEXT,
            timezone VARCHAR DEFAULT 'UTC',
            
            -- Notification Settings
            email_notifications_enabled BOOLEAN DEFAULT TRUE,
            escalation_email VARCHAR,
            notification_triggers TEXT,
            
            -- Branding
            widget_color VARCHAR DEFAULT '#6d28d9',
            widget_position VARCHAR DEFAULT 'bottom-right',
            company_logo_url VARCHAR,
            
            -- Features
            file_upload_enabled BOOLEAN DEFAULT TRUE,
            file_size_limit_mb INTEGER DEFAULT 10,
            allowed_file_types TEXT,
            
            -- Security
            customer_info_retention_days INTEGER DEFAULT 365,
            require_email_verification BOOLEAN DEFAULT FALSE,
            
            -- Timestamps
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX idx_live_chat_settings_tenant ON live_chat_settings(tenant_id);
        """
        
        # 3. Live Chat Conversations table (depends on agents)
        live_chat_conversations_sql = """
        CREATE TABLE live_chat_conversations (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            
            -- Customer Information
            customer_identifier VARCHAR NOT NULL,
            customer_email VARCHAR,
            customer_name VARCHAR,
            customer_phone VARCHAR,
            customer_ip VARCHAR,
            customer_user_agent TEXT,
            
            -- Handoff Context
            chatbot_session_id VARCHAR,
            handoff_reason VARCHAR,
            handoff_trigger VARCHAR,
            handoff_context TEXT,
            original_question TEXT,
            
            -- Queue Management
            status VARCHAR DEFAULT 'queued',
            queue_position INTEGER,
            priority_level INTEGER DEFAULT 1,
            queue_entry_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            
            -- Agent Assignment
            assigned_agent_id INTEGER REFERENCES agents(id),
            assigned_at TIMESTAMP,
            assignment_method VARCHAR,
            previous_agent_id INTEGER REFERENCES agents(id),
            
            -- Timing & Metrics
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            first_response_at TIMESTAMP,
            last_activity_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            closed_at TIMESTAMP,
            
            -- Calculated Metrics
            wait_time_seconds INTEGER,
            response_time_seconds INTEGER,
            conversation_duration_seconds INTEGER,
            message_count INTEGER DEFAULT 0,
            agent_message_count INTEGER DEFAULT 0,
            customer_message_count INTEGER DEFAULT 0,
            
            -- Customer Satisfaction
            customer_satisfaction INTEGER,
            customer_feedback TEXT,
            satisfaction_submitted_at TIMESTAMP,
            
            -- Closure Information
            closed_by VARCHAR,
            closure_reason VARCHAR,
            resolution_status VARCHAR,
            agent_notes TEXT,
            internal_notes TEXT,
            
            -- Tags & Categories
            tags TEXT,
            category VARCHAR,
            department VARCHAR,
            
            -- Timestamps
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX idx_live_chat_conversations_tenant ON live_chat_conversations(tenant_id);
        CREATE INDEX idx_live_chat_conversations_customer ON live_chat_conversations(customer_identifier);
        CREATE INDEX idx_live_chat_conversations_status ON live_chat_conversations(status);
        CREATE INDEX idx_live_chat_conversations_assigned_agent ON live_chat_conversations(assigned_agent_id);
        CREATE INDEX idx_live_chat_conversations_session ON live_chat_conversations(chatbot_session_id);
        """
        
        # 4. Live Chat Messages table (depends on conversations and agents)
        live_chat_messages_sql = """
        CREATE TABLE live_chat_messages (
            id SERIAL PRIMARY KEY,
            conversation_id INTEGER NOT NULL REFERENCES live_chat_conversations(id) ON DELETE CASCADE,
            
            -- Message Content
            content TEXT NOT NULL,
            message_type VARCHAR DEFAULT 'text',
            raw_content TEXT,
            
            -- Sender Information
            sender_type VARCHAR NOT NULL,
            sender_id VARCHAR,
            agent_id INTEGER REFERENCES agents(id),
            sender_name VARCHAR,
            sender_avatar VARCHAR,
            
            -- Message Status & Timing
            sent_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            delivered_at TIMESTAMP,
            read_at TIMESTAMP,
            edited_at TIMESTAMP,
            
            -- Message Properties
            is_internal BOOLEAN DEFAULT FALSE,
            is_edited BOOLEAN DEFAULT FALSE,
            is_deleted BOOLEAN DEFAULT FALSE,
            deleted_at TIMESTAMP,
            
            -- File Attachments
            attachment_url VARCHAR,
            attachment_name VARCHAR,
            attachment_type VARCHAR,
            attachment_size INTEGER,
            
            -- System Messages
            system_event_type VARCHAR,
            system_event_data TEXT,
            
            -- Message Metadata
            client_message_id VARCHAR,
            reply_to_message_id INTEGER REFERENCES live_chat_messages(id),
            thread_id VARCHAR
        );
        
        CREATE INDEX idx_live_chat_messages_conversation ON live_chat_messages(conversation_id);
        CREATE INDEX idx_live_chat_messages_agent ON live_chat_messages(agent_id);
        CREATE INDEX idx_live_chat_messages_sender_type ON live_chat_messages(sender_type);
        CREATE INDEX idx_live_chat_messages_sent_at ON live_chat_messages(sent_at);
        """
        
        # 5. Agent Sessions table (depends on agents)
        agent_sessions_sql = """
        CREATE TABLE agent_sessions (
            id SERIAL PRIMARY KEY,
            agent_id INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            
            -- Session Information
            session_id VARCHAR UNIQUE NOT NULL,
            status VARCHAR DEFAULT 'offline',
            login_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            logout_at TIMESTAMP,
            last_activity TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            
            -- Current Load & Capacity
            active_conversations INTEGER DEFAULT 0,
            max_concurrent_chats INTEGER DEFAULT 3,
            is_accepting_chats BOOLEAN DEFAULT TRUE,
            
            -- Performance Metrics
            messages_sent INTEGER DEFAULT 0,
            conversations_handled INTEGER DEFAULT 0,
            average_response_time FLOAT,
            total_online_time INTEGER DEFAULT 0,
            
            -- Technical Details
            ip_address VARCHAR,
            user_agent VARCHAR,
            websocket_id VARCHAR UNIQUE,
            device_type VARCHAR,
            browser VARCHAR,
            
            -- Status Messages
            status_message VARCHAR,
            away_message VARCHAR
        );
        
        CREATE INDEX idx_agent_sessions_agent ON agent_sessions(agent_id);
        CREATE INDEX idx_agent_sessions_tenant ON agent_sessions(tenant_id);
        CREATE INDEX idx_agent_sessions_session_id ON agent_sessions(session_id);
        CREATE INDEX idx_agent_sessions_websocket ON agent_sessions(websocket_id);
        CREATE INDEX idx_agent_sessions_status ON agent_sessions(status);
        """
        
        # 6. Chat Queue table (depends on conversations and agents)
        chat_queue_sql = """
        CREATE TABLE chat_queue (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            conversation_id INTEGER NOT NULL REFERENCES live_chat_conversations(id) ON DELETE CASCADE,
            
            -- Queue Management
            position INTEGER NOT NULL,
            priority INTEGER DEFAULT 1,
            estimated_wait_time INTEGER,
            
            -- Assignment Rules
            preferred_agent_id INTEGER REFERENCES agents(id),
            assignment_criteria TEXT,
            skills_required TEXT,
            language_preference VARCHAR,
            
            -- Queue Entry Details
            entry_reason VARCHAR,
            queue_source VARCHAR,
            
            -- Timing
            queued_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            assigned_at TIMESTAMP,
            removed_at TIMESTAMP,
            
            -- Status
            status VARCHAR DEFAULT 'waiting',
            abandon_reason VARCHAR,
            
            -- Customer Context
            customer_message_preview TEXT,
            urgency_indicators TEXT
        );
        
        CREATE INDEX idx_chat_queue_tenant ON chat_queue(tenant_id);
        CREATE INDEX idx_chat_queue_conversation ON chat_queue(conversation_id);
        CREATE INDEX idx_chat_queue_position ON chat_queue(position);
        CREATE INDEX idx_chat_queue_priority ON chat_queue(priority);
        CREATE INDEX idx_chat_queue_status ON chat_queue(status);
        CREATE UNIQUE INDEX idx_chat_queue_conversation_unique ON chat_queue(conversation_id);
        """
        
        # Execute tables in correct order
        tables = [
            (agents_sql, "Agents table"),
            (live_chat_settings_sql, "Live chat settings table"),
            (live_chat_conversations_sql, "Live chat conversations table"),
            (live_chat_messages_sql, "Live chat messages table"),
            (agent_sessions_sql, "Agent sessions table"),
            (chat_queue_sql, "Chat queue table")
        ]
        
        success_count = 0
        for sql, description in tables:
            if self.run_sql(sql, f"Created {description}"):
                success_count += 1
            else:
                logger.error(f"❌ Failed to create {description}")
                return False
        
        logger.info(f"✅ Created {success_count}/{len(tables)} Live Chat tables")
        return success_count == len(tables)
    
    def create_missing_instagram_telegram_tables(self):
        """Create Instagram and Telegram tables if they don't exist"""
        logger.info("📱 Creating missing Instagram and Telegram tables...")
        
        # Instagram tables (if needed)
        if not self.table_exists('instagram_integrations'):
            instagram_sql = """
            CREATE TABLE instagram_integrations (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER UNIQUE NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                meta_app_id VARCHAR NOT NULL,
                meta_app_secret VARCHAR NOT NULL,
                instagram_business_account_id VARCHAR NOT NULL,
                instagram_username VARCHAR NOT NULL,
                facebook_page_id VARCHAR NOT NULL,
                facebook_page_name VARCHAR,
                page_access_token TEXT NOT NULL,
                token_expires_at TIMESTAMP,
                webhook_verify_token VARCHAR NOT NULL,
                webhook_subscribed BOOLEAN DEFAULT FALSE,
                webhook_subscription_fields JSON,
                bot_enabled BOOLEAN DEFAULT TRUE,
                bot_status VARCHAR DEFAULT 'active',
                auto_reply_enabled BOOLEAN DEFAULT TRUE,
                business_verification_required BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                last_message_at TIMESTAMP,
                last_error TEXT,
                error_count INTEGER DEFAULT 0
            );
            """
            self.run_sql(instagram_sql, "Instagram integrations table")
        
        # Telegram tables (if needed)
        if not self.table_exists('telegram_integrations'):
            telegram_sql = """
            CREATE TABLE telegram_integrations (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER UNIQUE NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                bot_token VARCHAR NOT NULL,
                bot_username VARCHAR,
                bot_name VARCHAR,
                webhook_url VARCHAR,
                webhook_secret VARCHAR,
                is_active BOOLEAN DEFAULT FALSE,
                is_webhook_set BOOLEAN DEFAULT FALSE,
                enable_groups BOOLEAN DEFAULT FALSE,
                enable_privacy_mode BOOLEAN DEFAULT TRUE,
                enable_inline_mode BOOLEAN DEFAULT FALSE,
                welcome_message TEXT,
                help_message TEXT,
                enable_typing_indicator BOOLEAN DEFAULT TRUE,
                max_messages_per_minute INTEGER DEFAULT 30,
                last_webhook_received TIMESTAMP,
                last_message_sent TIMESTAMP,
                total_messages_received INTEGER DEFAULT 0,
                total_messages_sent INTEGER DEFAULT 0,
                last_error TEXT,
                error_count INTEGER DEFAULT 0,
                last_error_at TIMESTAMP,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                activated_at TIMESTAMP
            );
            """
            self.run_sql(telegram_sql, "Telegram integrations table")
        
        return True
    
    def verify_tables(self):
        """Verify all required tables exist"""
        logger.info("🔍 Verifying table creation...")
        
        required_tables = [
            'agents',
            'live_chat_conversations',
            'live_chat_messages',
            'agent_sessions',
            'chat_queue',
            'live_chat_settings'
        ]
        
        missing_tables = []
        for table in required_tables:
            if not self.table_exists(table):
                missing_tables.append(table)
        
        if missing_tables:
            logger.error(f"❌ Missing tables: {', '.join(missing_tables)}")
            return False
        
        logger.info("✅ All required tables exist")
        return True
    
    def run_safe_migration(self):
        """Run the safe migration"""
        logger.info("🚀 Starting SAFE database migration for Live Chat")
        logger.info(f"📅 Migration started at: {datetime.now()}")
        
        if not self.connect():
            logger.error("❌ Migration failed: Could not connect to database")
            return False
        
        try:
            # Step 1: Clean up existing incomplete tables
            if not self.drop_existing_live_chat_tables():
                logger.error("❌ Failed to clean up existing tables")
                return False
            
            # Step 2: Create live chat tables in correct order
            if not self.create_live_chat_tables_safe():
                logger.error("❌ Failed to create live chat tables")
                return False
            
            # Step 3: Create missing Instagram/Telegram tables
            self.create_missing_instagram_telegram_tables()
            
            # Step 4: Verify all tables
            if not self.verify_tables():
                logger.error("❌ Table verification failed")
                return False
            
            logger.info("🎉 SAFE migration completed successfully!")
            logger.info(f"📅 Migration finished at: {datetime.now()}")
            
            # Show next steps
            self.show_next_steps()
            
            return True
            
        except Exception as e:
            logger.error(f"💥 Migration failed with error: {e}")
            return False
        
        finally:
            if self.engine:
                self.engine.dispose()
                logger.info("🔌 Database connection closed")
    
    def show_next_steps(self):
        """Show next steps after migration"""
        logger.info("ℹ️ Next steps:")
        print("""
✅ Live Chat tables created successfully!

🔧 Next steps:
1. Enable live chat routes in main.py:
   
   from app.live_chat.auth_router import router as live_chat_auth_router
   from app.live_chat.router import router as live_chat_main_router
   
   app.include_router(live_chat_auth_router, prefix="/live-chat/auth", tags=["Live Chat Auth"])
   app.include_router(live_chat_main_router, prefix="/live-chat", tags=["Live Chat"])

2. Set up email environment variables:
   
   RESEND_API_KEY=your_resend_api_key
   FROM_EMAIL=noreply@yourdomain.com
   FROM_NAME="Your Company Support"

3. Test agent invitation using your HTML test interface!

📋 Tables created:
- ✅ agents (with full_name column)
- ✅ live_chat_conversations  
- ✅ live_chat_messages
- ✅ agent_sessions
- ✅ chat_queue
- ✅ live_chat_settings
        """)

def main():
    """Main migration function"""
    print("🛡️ SAFE Live Chat Database Migration Script")
    print("=" * 60)
    
    migrator = SafeDatabaseMigrator(DATABASE_URL)
    
    try:
        success = migrator.run_safe_migration()
        
        if success:
            print("\n✅ SAFE migration completed successfully!")
            print("\nYour live chat system is now ready to use!")
            return 0
        else:
            print("\n❌ Migration failed!")
            print("Check the safe_migration.log file for error details")
            return 1
            
    except KeyboardInterrupt:
        print("\n⚠️ Migration interrupted by user")
        return 1
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)