#!/usr/bin/env python3
"""
Script to create pricing tables in the database
Run this script to fix the pricing/conversation limit system
"""

import os
import sys
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError

# Add your project root to Python path
# Adjust this path to match your project structure
sys.path.append('/Users/mac/Downloads/chatbot')

try:
    # Import your database models
    from app.database import Base, get_db
    
    # Try to import pricing models
    try:
        from app.pricing.models import Base as PricingBase
        print("✅ Successfully imported pricing models")
    except ImportError as e:
        print(f"❌ Could not import pricing models: {e}")
        print("This might be normal if pricing models don't exist yet")
        PricingBase = None
    
    # Try to import live chat models (they might have pricing-related tables)
    try:
        from app.live_chat.models import Base as LiveChatBase
        print("✅ Successfully imported live chat models")
    except ImportError as e:
        print(f"❌ Could not import live chat models: {e}")
        LiveChatBase = None

except ImportError as e:
    print(f"❌ Could not import app modules: {e}")
    print("Make sure you're running this from the correct directory")
    sys.exit(1)

# Database connection strings
DATABASES = {
    "postgresql": "postgresql://chatbot_hhjv_user:dYXguSEwpwZl3Yt2R3ACsfvmM5lLIgSD@dpg-d10sp295pdvs73afujf0-a.oregon-postgres.render.com/chatbot_hhjv",
    "sqlite": "sqlite:///./chatbot.db"
}

def create_engine_with_retry(database_url, max_retries=3):
    """Create database engine with retry logic"""
    for attempt in range(max_retries):
        try:
            engine = create_engine(database_url, echo=True)
            # Test the connection
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print(f"✅ Successfully connected to database")
            return engine
        except Exception as e:
            print(f"❌ Attempt {attempt + 1} failed: {e}")
            if attempt == max_retries - 1:
                raise
    return None

def inspect_existing_tables(engine):
    """Check what tables already exist"""
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    
    print(f"\n📋 Existing tables ({len(existing_tables)}):")
    for table in sorted(existing_tables):
        print(f"  - {table}")
    
    return existing_tables

def create_missing_pricing_tables(engine):
    """Create pricing-related tables that might be missing"""
    
    # First, let's create some basic pricing tables if they don't exist
    pricing_tables_sql = """
    -- Conversation usage tracking table
    CREATE TABLE IF NOT EXISTS conversation_usage (
        id SERIAL PRIMARY KEY,
        tenant_id INTEGER NOT NULL,
        user_identifier VARCHAR(255),
        platform VARCHAR(50) DEFAULT 'live_chat',
        conversation_count INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Tenant limits table  
    CREATE TABLE IF NOT EXISTS tenant_limits (
        id SERIAL PRIMARY KEY,
        tenant_id INTEGER NOT NULL UNIQUE,
        max_conversations_per_month INTEGER DEFAULT 1000,
        max_agents INTEGER DEFAULT 10,
        features_enabled TEXT DEFAULT '{}',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Usage tracking table
    CREATE TABLE IF NOT EXISTS usage_tracking (
        id SERIAL PRIMARY KEY,
        tenant_id INTEGER NOT NULL,
        resource_type VARCHAR(100) NOT NULL,
        resource_id VARCHAR(255),
        usage_count INTEGER DEFAULT 1,
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Create indexes for better performance
    CREATE INDEX IF NOT EXISTS idx_conversation_usage_tenant_id ON conversation_usage(tenant_id);
    CREATE INDEX IF NOT EXISTS idx_conversation_usage_created_at ON conversation_usage(created_at);
    CREATE INDEX IF NOT EXISTS idx_tenant_limits_tenant_id ON tenant_limits(tenant_id);
    CREATE INDEX IF NOT EXISTS idx_usage_tracking_tenant_id ON usage_tracking(tenant_id);
    CREATE INDEX IF NOT EXISTS idx_usage_tracking_period ON usage_tracking(period_start, period_end);
    """
    
    try:
        with engine.connect() as conn:
            # Execute each statement separately for better error handling
            statements = [stmt.strip() for stmt in pricing_tables_sql.split(';') if stmt.strip()]
            
            for stmt in statements:
                if stmt:
                    print(f"📝 Executing: {stmt[:50]}...")
                    conn.execute(text(stmt))
            
            conn.commit()
            print("✅ Successfully created pricing tables")
            return True
            
    except SQLAlchemyError as e:
        print(f"❌ Error creating pricing tables: {e}")
        return False

def setup_default_tenant_limits(engine, tenant_id=324112833):
    """Set up default limits for your tenant"""
    
    insert_sql = """
    INSERT INTO tenant_limits (tenant_id, max_conversations_per_month, max_agents, features_enabled)
    VALUES (:tenant_id, 10000, 50, '{"live_chat": true, "analytics": true}')
    ON CONFLICT (tenant_id) 
    DO UPDATE SET 
        max_conversations_per_month = EXCLUDED.max_conversations_per_month,
        max_agents = EXCLUDED.max_agents,
        features_enabled = EXCLUDED.features_enabled,
        updated_at = CURRENT_TIMESTAMP;
    """
    
    try:
        with engine.connect() as conn:
            result = conn.execute(text(insert_sql), {"tenant_id": tenant_id})
            conn.commit()
            print(f"✅ Set up default limits for tenant {tenant_id}")
            return True
    except SQLAlchemyError as e:
        print(f"❌ Error setting up tenant limits: {e}")
        return False

def create_tables_from_models(engine):
    """Create tables using SQLAlchemy models if available"""
    try:
        # Create all tables from Base
        Base.metadata.create_all(bind=engine)
        print("✅ Created tables from main Base")
        
        # Create pricing tables if available
        if PricingBase:
            PricingBase.metadata.create_all(bind=engine)
            print("✅ Created tables from PricingBase")
        
        # Create live chat tables if available
        if LiveChatBase:
            LiveChatBase.metadata.create_all(bind=engine)
            print("✅ Created tables from LiveChatBase")
            
        return True
    except Exception as e:
        print(f"❌ Error creating tables from models: {e}")
        return False

def main():
    print("🚀 Starting pricing tables setup...")
    print("=" * 50)
    
    # Choose database (default to PostgreSQL for production)
    db_choice = input("Which database? (1) PostgreSQL [default] (2) SQLite: ").strip()
    
    if db_choice == "2":
        database_url = DATABASES["sqlite"]
        print("📂 Using SQLite database")
    else:
        database_url = DATABASES["postgresql"]
        print("🐘 Using PostgreSQL database")
    
    try:
        # Create database engine
        print(f"\n🔌 Connecting to database...")
        engine = create_engine_with_retry(database_url)
        
        # Inspect existing tables
        existing_tables = inspect_existing_tables(engine)
        
        # Check if pricing tables already exist
        pricing_table_names = ['conversation_usage', 'tenant_limits', 'usage_tracking']
        missing_tables = [table for table in pricing_table_names if table not in existing_tables]
        
        if missing_tables:
            print(f"\n🔧 Missing pricing tables: {missing_tables}")
            
            # Method 1: Try to create from SQLAlchemy models
            print("\n📋 Method 1: Creating tables from SQLAlchemy models...")
            if create_tables_from_models(engine):
                print("✅ Successfully created tables from models")
            else:
                print("⚠️ Model creation failed, trying SQL method...")
                
                # Method 2: Create using raw SQL
                print("\n📋 Method 2: Creating tables using SQL...")
                if create_missing_pricing_tables(engine):
                    print("✅ Successfully created tables using SQL")
                else:
                    print("❌ Both methods failed")
                    return False
        else:
            print("✅ All pricing tables already exist")
        
        # Set up default tenant limits
        print(f"\n⚙️ Setting up default limits for tenant 324112833...")
        setup_default_tenant_limits(engine)
        
        # Final verification
        print(f"\n🔍 Final verification...")
        final_tables = inspect_existing_tables(engine)
        
        # Check if our required tables exist
        success = all(table in final_tables for table in pricing_table_names)
        
        if success:
            print("\n🎉 SUCCESS! All pricing tables are ready.")
            print("\n📋 You can now test the live chat endpoint:")
            print("curl -X 'POST' \\")
            print("  'https://botbackend-qtbf.onrender.com/live-chat/start-chat' \\")
            print("  -H 'X-API-Key: sk-f37356b62211465ea3d2efb5e537799a' \\")
            print("  -H 'Content-Type: application/json' \\")
            print("  -d '{\"customer_identifier\": \"test123\", \"customer_name\": \"Test User\"}'")
        else:
            print("\n❌ FAILED! Some pricing tables are still missing.")
            print("Missing tables:", [t for t in pricing_table_names if t not in final_tables])
        
        return success
        
    except Exception as e:
        print(f"\n💥 Fatal error: {e}")
        print(f"Error type: {type(e).__name__}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)