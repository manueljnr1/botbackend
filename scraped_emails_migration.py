#!/usr/bin/env python3
"""
Migration Script: Add scraped_emails table
Supports both PostgreSQL and SQLite
"""

import os
import sys
import logging
from pathlib import Path
from sqlalchemy import create_engine, text, MetaData, inspect
from sqlalchemy.exc import SQLAlchemyError

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database URLs
POSTGRESQL_URL = "postgresql://chatbot_hhjv_user:dYXguSEwpwZl3Yt2R3ACsfvmM5lLIgSD@dpg-d10sp295pdvs73afujf0-a.oregon-postgres.render.com/chatbot_hhjv"
SQLITE_URL = "sqlite:///./chatbot.db"

def get_database_type(database_url: str) -> str:
    """Determine database type from URL"""
    if database_url.startswith('postgresql'):
        return 'postgresql'
    elif database_url.startswith('sqlite'):
        return 'sqlite'
    else:
        raise ValueError(f"Unsupported database type: {database_url}")

def get_create_table_sql(db_type: str) -> str:
    """Get appropriate CREATE TABLE SQL for database type"""
    
    if db_type == 'postgresql':
        return """
        CREATE TABLE IF NOT EXISTS scraped_emails (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            email VARCHAR(254) NOT NULL,
            email_hash VARCHAR(32) UNIQUE NOT NULL,
            source VARCHAR(50) NOT NULL,
            capture_method VARCHAR(50) NOT NULL,
            session_id VARCHAR(255) REFERENCES chat_sessions(session_id) ON DELETE SET NULL,
            user_agent TEXT,
            referrer_url TEXT,
            ip_address VARCHAR(45),
            consent_given BOOLEAN DEFAULT FALSE NOT NULL,
            verified BOOLEAN DEFAULT FALSE NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
        );
        """
    
    elif db_type == 'sqlite':
        return """
        CREATE TABLE IF NOT EXISTS scraped_emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            email VARCHAR(254) NOT NULL,
            email_hash VARCHAR(32) UNIQUE NOT NULL,
            source VARCHAR(50) NOT NULL,
            capture_method VARCHAR(50) NOT NULL,
            session_id VARCHAR(255) REFERENCES chat_sessions(session_id) ON DELETE SET NULL,
            user_agent TEXT,
            referrer_url TEXT,
            ip_address VARCHAR(45),
            consent_given BOOLEAN DEFAULT 0 NOT NULL,
            verified BOOLEAN DEFAULT 0 NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
        );
        """

def get_create_indexes_sql(db_type: str) -> list:
    """Get index creation SQL statements"""
    
    base_indexes = [
        "CREATE INDEX IF NOT EXISTS idx_scraped_emails_tenant_id ON scraped_emails(tenant_id);",
        "CREATE INDEX IF NOT EXISTS idx_scraped_emails_email ON scraped_emails(email);",
        "CREATE INDEX IF NOT EXISTS idx_scraped_emails_session_id ON scraped_emails(session_id);",
        "CREATE INDEX IF NOT EXISTS idx_scraped_emails_created_at ON scraped_emails(created_at);",
        "CREATE INDEX IF NOT EXISTS idx_scraped_emails_source ON scraped_emails(source);",
        "CREATE INDEX IF NOT EXISTS idx_scraped_emails_verified ON scraped_emails(verified);"
    ]
    
    return base_indexes

def check_table_exists(engine, table_name: str) -> bool:
    """Check if table exists in database"""
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        return table_name in tables
    except Exception as e:
        logger.error(f"Error checking table existence: {e}")
        return False

def check_required_tables(engine, db_type: str) -> bool:
    """Check if required parent tables exist"""
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        required_tables = ['tenants', 'chat_sessions']
        missing_tables = [table for table in required_tables if table not in tables]
        
        if missing_tables:
            logger.error(f"❌ Missing required tables: {missing_tables}")
            return False
        
        logger.info(f"✅ All required parent tables exist")
        return True
        
    except Exception as e:
        logger.error(f"Error checking required tables: {e}")
        return False

def run_migration(database_url: str) -> bool:
    """Run migration for specified database"""
    try:
        logger.info(f"🔄 Starting migration for: {database_url[:30]}...")
        
        # Determine database type
        db_type = get_database_type(database_url)
        logger.info(f"📊 Database type: {db_type}")
        
        # Create engine
        engine = create_engine(database_url)
        
        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            logger.info(f"✅ Database connection successful")
        
        # Check if required parent tables exist
        if not check_required_tables(engine, db_type):
            logger.error(f"❌ Cannot proceed without required parent tables")
            return False
        
        # Check if table already exists
        if check_table_exists(engine, 'scraped_emails'):
            logger.info(f"⚠️ Table 'scraped_emails' already exists, skipping creation")
            return True
        
        # Create table
        create_table_sql = get_create_table_sql(db_type)
        
        with engine.begin() as conn:
            logger.info(f"📝 Creating scraped_emails table...")
            conn.execute(text(create_table_sql))
            logger.info(f"✅ Table created successfully")
            
            # Create indexes
            indexes = get_create_indexes_sql(db_type)
            logger.info(f"📇 Creating {len(indexes)} indexes...")
            
            for index_sql in indexes:
                try:
                    conn.execute(text(index_sql))
                except Exception as e:
                    logger.warning(f"⚠️ Index creation warning: {e}")
            
            logger.info(f"✅ Indexes created successfully")
        
        # Verify table creation
        if check_table_exists(engine, 'scraped_emails'):
            logger.info(f"🎉 Migration completed successfully for {db_type}")
            return True
        else:
            logger.error(f"❌ Table verification failed")
            return False
            
    except SQLAlchemyError as e:
        logger.error(f"❌ Database error during migration: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error during migration: {e}")
        return False

def get_table_info(database_url: str) -> dict:
    """Get information about the scraped_emails table"""
    try:
        engine = create_engine(database_url)
        db_type = get_database_type(database_url)
        
        if not check_table_exists(engine, 'scraped_emails'):
            return {"exists": False}
        
        inspector = inspect(engine)
        columns = inspector.get_columns('scraped_emails')
        indexes = inspector.get_indexes('scraped_emails')
        
        with engine.connect() as conn:
            count_result = conn.execute(text("SELECT COUNT(*) FROM scraped_emails"))
            row_count = count_result.scalar()
        
        return {
            "exists": True,
            "database_type": db_type,
            "columns": [{"name": col["name"], "type": str(col["type"])} for col in columns],
            "indexes": [idx["name"] for idx in indexes],
            "row_count": row_count
        }
        
    except Exception as e:
        logger.error(f"Error getting table info: {e}")
        return {"exists": False, "error": str(e)}

def main():
    """Main migration function"""
    print("🚀 Email Scraper Migration Script")
    print("=" * 50)
    
    # Determine which database to migrate
    current_db_url = settings.DATABASE_URL
    
    success_count = 0
    total_count = 0
    
    # Migration targets
    migration_targets = [
        ("PostgreSQL (Production)", POSTGRESQL_URL),
        ("SQLite (Development)", SQLITE_URL)
    ]
    
    # If current database is one of our targets, prioritize it
    if current_db_url in [POSTGRESQL_URL, SQLITE_URL]:
        print(f"📍 Current database detected: {current_db_url[:30]}...")
        if run_migration(current_db_url):
            success_count += 1
        total_count += 1
    else:
        # Run migrations for both databases
        for name, db_url in migration_targets:
            print(f"\n🎯 Migrating {name}...")
            total_count += 1
            
            if run_migration(db_url):
                success_count += 1
            else:
                logger.error(f"❌ Migration failed for {name}")
    
    # Summary
    print(f"\n📊 Migration Summary:")
    print(f"✅ Successful: {success_count}/{total_count}")
    
    if success_count == total_count:
        print(f"🎉 All migrations completed successfully!")
        
        # Show table info for current database
        print(f"\n📋 Table Information:")
        table_info = get_table_info(current_db_url)
        if table_info.get("exists"):
            print(f"Database Type: {table_info.get('database_type')}")
            print(f"Columns: {len(table_info.get('columns', []))}")
            print(f"Indexes: {len(table_info.get('indexes', []))}")
            print(f"Current Rows: {table_info.get('row_count', 0)}")
        
        return True
    else:
        print(f"❌ Some migrations failed. Check logs above.")
        return False

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print(f"\n⏹️ Migration cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"💥 Fatal error: {e}")
        sys.exit(1)