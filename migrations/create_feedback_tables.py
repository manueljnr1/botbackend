# Create this file: app/migrations/create_feedback_tables.py
import sys
import os

# Add the parent directory to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


"""
Database migration to create smart feedback system tables
Run this script to add the missing pending_feedback table
"""

from sqlalchemy import create_engine, text
# Replace with a valid configuration source
from app.config import settings  # Assuming settings is defined in app/config.py
from app.database import Base
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create the SQL for the pending_feedback table
CREATE_PENDING_FEEDBACK_TABLE = """
CREATE TABLE IF NOT EXISTS pending_feedback (
    id INTEGER PRIMARY KEY,
    feedback_id VARCHAR UNIQUE NOT NULL,
    tenant_id INTEGER NOT NULL,
    session_id VARCHAR,
    user_email VARCHAR,
    user_question TEXT,
    bot_response TEXT,
    conversation_context TEXT,
    tenant_email_sent BOOLEAN DEFAULT 0,
    tenant_response TEXT,
    user_notified BOOLEAN DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    resolved_at DATETIME,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id)
);
"""

# Index for better performance
CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_pending_feedback_tenant_id ON pending_feedback(tenant_id);",
    "CREATE INDEX IF NOT EXISTS idx_pending_feedback_feedback_id ON pending_feedback(feedback_id);",
    "CREATE INDEX IF NOT EXISTS idx_pending_feedback_user_notified ON pending_feedback(user_notified);",
    "CREATE INDEX IF NOT EXISTS idx_pending_feedback_created_at ON pending_feedback(created_at);"
]

def run_migration():
    """Run the migration to create feedback tables"""
    try:
        # Create engine
        engine = create_engine(settings.DATABASE_URL)
        
        logger.info("🚀 Starting smart feedback system migration...")
        
        with engine.connect() as conn:
            # Create the pending_feedback table
            logger.info("📋 Creating pending_feedback table...")
            conn.execute(text(CREATE_PENDING_FEEDBACK_TABLE))
            
            # Create indexes
            logger.info("🔍 Creating indexes...")
            for index_sql in CREATE_INDEXES:
                conn.execute(text(index_sql))
            
            # Commit changes
            conn.commit()
            
        logger.info("✅ Smart feedback system migration completed successfully!")
        logger.info("📊 Tables created:")
        logger.info("   - pending_feedback (for tracking feedback requests)")
        logger.info("🔍 Indexes created for better performance")
        
        return True
        
    except Exception as e:
        logger.error(f"💥 Migration failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def verify_migration():
    """Verify that the migration was successful"""
    try:
        engine = create_engine(settings.DATABASE_URL)
        
        with engine.connect() as conn:
            # Check if table exists and get its structure
            result = conn.execute(text("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='pending_feedback'
            """))
            
            if result.fetchone():
                logger.info("✅ pending_feedback table exists")
                
                # Get table info
                result = conn.execute(text("PRAGMA table_info(pending_feedback)"))
                columns = result.fetchall()
                
                logger.info("📋 Table structure:")
                for col in columns:
                    logger.info(f"   - {col[1]} ({col[2]})")
                
                return True
            else:
                logger.error("❌ pending_feedback table not found")
                return False
                
    except Exception as e:
        logger.error(f"💥 Verification failed: {e}")
        return False

if __name__ == "__main__":
    print("🔧 Smart Feedback System Migration")
    print("=" * 50)
    
    success = run_migration()
    
    if success:
        print("\n🎉 Migration completed successfully!")
        print("\nVerifying migration...")
        verify_migration()
        print("\n✅ You can now use the smart feedback system!")
    else:
        print("\n❌ Migration failed. Check the logs above.")


# Alternative: Quick SQL script if you prefer to run manually
# Save this as: feedback_tables.sql

MANUAL_SQL_SCRIPT = """
-- Smart Feedback System Tables
-- Run this SQL directly in your database if preferred

-- Create pending_feedback table
CREATE TABLE IF NOT EXISTS pending_feedback (
    id INTEGER PRIMARY KEY,
    feedback_id VARCHAR UNIQUE NOT NULL,
    tenant_id INTEGER NOT NULL,
    session_id VARCHAR,
    user_email VARCHAR,
    user_question TEXT,
    bot_response TEXT,
    conversation_context TEXT,
    tenant_email_sent BOOLEAN DEFAULT 0,
    tenant_response TEXT,
    user_notified BOOLEAN DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    resolved_at DATETIME,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id)
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_pending_feedback_tenant_id ON pending_feedback(tenant_id);
CREATE INDEX IF NOT EXISTS idx_pending_feedback_feedback_id ON pending_feedback(feedback_id);
CREATE INDEX IF NOT EXISTS idx_pending_feedback_user_notified ON pending_feedback(user_notified);
CREATE INDEX IF NOT EXISTS idx_pending_feedback_created_at ON pending_feedback(created_at);

-- Verify table creation
SELECT 'pending_feedback table created successfully' as status;
SELECT name FROM sqlite_master WHERE type='table' AND name='pending_feedback';
"""