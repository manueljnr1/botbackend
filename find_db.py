# migrate_pricing_structure.py
"""
Database migration script for new conversation-based pricing structure
Run this script to migrate your database to the new pricing model
"""

import os
import sys
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'migration_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Database connection
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./chatbot.db")

def create_database_connection():
    """Create database connection"""
    try:
        engine = create_engine(DATABASE_URL)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        return engine, SessionLocal()
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        sys.exit(1)

def run_migration_sql(session, sql_statements):
    """Execute a list of SQL statements"""
    for i, sql in enumerate(sql_statements, 1):
        try:
            logger.info(f"Executing migration step {i}/{len(sql_statements)}")
            logger.debug(f"SQL: {sql[:100]}...")
            
            session.execute(text(sql))
            session.commit()
            
            logger.info(f"✅ Step {i} completed successfully")
            
        except Exception as e:
            logger.error(f"❌ Error in step {i}: {e}")
            session.rollback()
            raise e

def backup_critical_tables(session):
    """Create backup of critical pricing tables"""
    backup_tables = [
        "pricing_plans",
        "tenant_subscriptions", 
        "usage_logs",
        "billing_history"
    ]
    
    logger.info("🔄 Creating backup tables...")
    
    for table in backup_tables:
        try:
            backup_sql = f"""
            CREATE TABLE {table}_backup_{datetime.now().strftime('%Y%m%d')} AS 
            SELECT * FROM {table};
            """
            session.execute(text(backup_sql))
            session.commit()
            logger.info(f"✅ Backed up {table}")
        except Exception as e:
            logger.warning(f"⚠️ Could not backup {table}: {e}")

def main():
    """Main migration function"""
    
    logger.info("🚀 Starting pricing structure migration...")
    logger.info(f"Database URL: {DATABASE_URL}")
    
    # Get user confirmation
    confirmation = input("\n⚠️ This will modify your database structure. Have you backed up your database? (yes/no): ")
    if confirmation.lower() != 'yes':
        logger.info("Migration cancelled by user")
        sys.exit(0)
    
    engine, session = create_database_connection()
    
    try:
        # Create backups
        backup_critical_tables(session)
        
        # Define migration SQL statements
        migration_steps = [
            # Step 1: Add new columns to pricing_plans
            """
            ALTER TABLE pricing_plans ADD COLUMN IF NOT EXISTS is_addon BOOLEAN DEFAULT FALSE;
            """,
            
            """
            ALTER TABLE pricing_plans ADD COLUMN IF NOT EXISTS is_popular BOOLEAN DEFAULT FALSE;
            """,
            
            """
            ALTER TABLE pricing_plans ADD COLUMN IF NOT EXISTS display_order INTEGER DEFAULT 0;
            """,
            
            # Step 2: Update tenant subscriptions
            """
            ALTER TABLE tenant_subscriptions ADD COLUMN IF NOT EXISTS active_addons TEXT;
            """,
            
            """
            ALTER TABLE tenant_subscriptions ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(255);
            """,
            
            # Step 3: Create conversation sessions table
            """
            CREATE TABLE IF NOT EXISTS conversation_sessions (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER NOT NULL,
                user_identifier VARCHAR(255) NOT NULL,
                platform VARCHAR(50) NOT NULL,
                started_at TIMESTAMP NOT NULL DEFAULT NOW(),
                last_activity TIMESTAMP NOT NULL DEFAULT NOW(),
                is_active BOOLEAN DEFAULT TRUE,
                message_count INTEGER DEFAULT 0,
                duration_minutes INTEGER DEFAULT 0,
                counted_for_billing BOOLEAN DEFAULT FALSE,
                billing_period_start TIMESTAMP,
                extra_data TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );
            """,
            
            # Step 4: Add foreign key constraint for conversation_sessions
            """
            ALTER TABLE conversation_sessions 
            ADD CONSTRAINT IF NOT EXISTS fk_conversation_sessions_tenant 
            FOREIGN KEY (tenant_id) REFERENCES tenants(id);
            """,
            
            # Step 5: Create indexes for performance
            """
            CREATE INDEX IF NOT EXISTS idx_conversation_sessions_tenant_user 
            ON conversation_sessions(tenant_id, user_identifier);
            """,
            
            """
            CREATE INDEX IF NOT EXISTS idx_conversation_sessions_activity 
            ON conversation_sessions(last_activity);
            """,
            
            """
            CREATE INDEX IF NOT EXISTS idx_conversation_sessions_billing 
            ON conversation_sessions(tenant_id, counted_for_billing, billing_period_start);
            """,
            
            # Step 6: Enhanced usage logs
            """
            ALTER TABLE usage_logs ADD COLUMN IF NOT EXISTS session_id VARCHAR(255);
            """,
            
            """
            ALTER TABLE usage_logs ADD COLUMN IF NOT EXISTS user_identifier VARCHAR(255);
            """,
            
            """
            ALTER TABLE usage_logs ADD COLUMN IF NOT EXISTS platform VARCHAR(50);
            """,
            
            # Step 7: Enhanced billing history
            """
            ALTER TABLE billing_history ADD COLUMN IF NOT EXISTS plan_name VARCHAR(255);
            """,
            
            """
            ALTER TABLE billing_history ADD COLUMN IF NOT EXISTS conversations_included INTEGER;
            """,
            
            """
            ALTER TABLE billing_history ADD COLUMN IF NOT EXISTS conversations_used INTEGER;
            """,
            
            """
            ALTER TABLE billing_history ADD COLUMN IF NOT EXISTS addons_included TEXT;
            """,
            
            """
            ALTER TABLE billing_history ADD COLUMN IF NOT EXISTS stripe_charge_id VARCHAR(255);
            """,
            
            """
            ALTER TABLE billing_history ADD COLUMN IF NOT EXISTS payment_method VARCHAR(50);
            """,
            
            # Step 8: Update existing plans to new structure
            """
            UPDATE pricing_plans SET 
                max_integrations = -1,
                custom_prompt_allowed = TRUE,
                slack_allowed = TRUE,
                discord_allowed = TRUE
            WHERE plan_type IN ('free', 'basic', 'pro');
            """,
            
            # Step 9: Update Pro plan to Agency and adjust limits
            """
            UPDATE pricing_plans SET 
                name = 'Agency',
                plan_type = 'agency',
                max_messages_monthly = 50000
            WHERE plan_type = 'pro';
            """,
            
            # Step 10: Update Basic plan pricing and limits
            """
            UPDATE pricing_plans SET 
                price_monthly = 19.00,
                price_yearly = 190.00,
                max_messages_monthly = 500
            WHERE plan_type = 'basic';
            """,
            
            # Step 11: Update Free plan limits
            """
            UPDATE pricing_plans SET 
                max_messages_monthly = 50
            WHERE plan_type = 'free';
            """
        ]
        
        # Run migration steps
        logger.info(f"🔄 Running {len(migration_steps)} migration steps...")
        run_migration_sql(session, migration_steps)
        
        # Verify migration
        logger.info("🔍 Verifying migration...")
        
        # Check if conversation_sessions table exists
        result = session.execute(text("""
            SELECT COUNT(*) as count FROM information_schema.tables 
            WHERE table_name = 'conversation_sessions';
        """)).fetchone()
        
        if result and result.count > 0:
            logger.info("✅ conversation_sessions table created successfully")
        else:
            logger.warning("⚠️ conversation_sessions table may not have been created")
        
        # Check updated pricing plans
        plans_result = session.execute(text("""
            SELECT name, plan_type, max_messages_monthly, custom_prompt_allowed, slack_allowed 
            FROM pricing_plans 
            WHERE is_active = TRUE;
        """)).fetchall()
        
        logger.info("📊 Current pricing plans after migration:")
        for plan in plans_result:
            logger.info(f"  - {plan.name} ({plan.plan_type}): {plan.max_messages_monthly} conversations, "
                       f"Custom Prompts: {plan.custom_prompt_allowed}, Slack: {plan.slack_allowed}")
        
        logger.info("🎉 Migration completed successfully!")
        logger.info("\n📋 Next steps:")
        logger.info("1. Deploy updated pricing service code")
        logger.info("2. Run: POST /pricing/initialize-defaults to create new plans") 
        logger.info("3. Test conversation tracking functionality")
        logger.info("4. Update frontend to show conversation limits")
        
    except Exception as e:
        logger.error(f"💥 Migration failed: {e}")
        logger.error("Database has been rolled back to previous state")
        session.rollback()
        sys.exit(1)
        
    finally:
        session.close()

if __name__ == "__main__":
    main()