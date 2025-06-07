#!/usr/bin/env python3
"""
Database Migration Script for Pricing Plan Updates
Works with both SQLite (local) and PostgreSQL (Render)
"""

import os
import sys
from decimal import Decimal
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError

def get_database_url():
    """Get database URL from environment or prompt user"""
    
    # Try to get from environment first
    db_url = os.getenv('DATABASE_URL')
    
    if not db_url:
        print("DATABASE_URL not found in environment variables.")
        print("\nPlease provide your database connection string:")
        print("Local SQLite example: sqlite:///./your_database.db")
        print("Local PostgreSQL example: postgresql://username:password@localhost:5432/database_name")
        print("Render example: postgresql://username:password@dpg-xxxxx-a.oregon-postgres.render.com:5432/database_name")
        db_url = input("\nDatabase URL: ").strip()
    
    # Handle postgres:// vs postgresql:// URL issue
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)
    
    return db_url

def detect_database_type(db_url):
    """Detect if we're using SQLite or PostgreSQL"""
    if db_url.startswith('sqlite'):
        return 'sqlite'
    elif db_url.startswith('postgresql'):
        return 'postgresql'
    else:
        return 'unknown'

def create_db_session(db_url):
    """Create database session"""
    try:
        engine = create_engine(db_url)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        session = SessionLocal()
        
        # Test connection
        session.execute(text("SELECT 1"))
        db_type = detect_database_type(db_url)
        print(f"✅ Database connection successful! (Type: {db_type})")
        return session, engine, db_type
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return None, None, None

def backup_current_plans(session):
    """Create a backup of current pricing plans"""
    try:
        print("\n📋 Creating backup of current plans...")
        
        # Get current plans
        result = session.execute(text("""
            SELECT id, name, plan_type, price_monthly, price_yearly, 
                   max_messages_monthly, is_active, features
            FROM pricing_plans 
            WHERE is_active = 1
        """))
        
        plans = result.fetchall()
        
        # Save to file with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"pricing_plans_backup_{timestamp}.sql"
        
        with open(backup_filename, 'w') as f:
            f.write("-- Pricing Plans Backup\n")
            f.write(f"-- Created: {datetime.now()}\n\n")
            
            for plan in plans:
                f.write(f"-- Plan: {plan.name}\n")
                f.write(f"UPDATE pricing_plans SET ")
                f.write(f"price_monthly = {plan.price_monthly}, ")
                f.write(f"price_yearly = {plan.price_yearly}, ")
                f.write(f"max_messages_monthly = {plan.max_messages_monthly} ")
                f.write(f"WHERE plan_type = '{plan.plan_type}';\n\n")
        
        print(f"✅ Backup saved to: {backup_filename}")
        return True
        
    except Exception as e:
        print(f"❌ Backup failed: {e}")
        return False

def get_current_timestamp(db_type):
    """Get current timestamp function based on database type"""
    if db_type == 'sqlite':
        return "datetime('now')"
    elif db_type == 'postgresql':
        return "NOW()"
    else:
        return "datetime('now')"  # Default to SQLite format

def migrate_pricing_plans(session, db_type):
    """Execute the pricing plan migration"""
    try:
        print("\n🔄 Starting pricing plan migration...")
        
        # Get timestamp function for this database type
        timestamp_func = get_current_timestamp(db_type)
        
        # 1. Deactivate old live chat plans
        print("1️⃣ Deactivating old live chat plans...")
        result = session.execute(text("""
            UPDATE pricing_plans 
            SET is_active = 0 
            WHERE plan_type IN ('livechat_lite', 'livechat_addon')
        """))
        print(f"   Deactivated {result.rowcount} live chat plans")
        
        # 2. Update Basic plan
        print("2️⃣ Updating Basic plan...")
        session.execute(text("""
            UPDATE pricing_plans 
            SET 
                price_monthly = 9.99,
                price_yearly = 99.00,
                max_messages_monthly = 2000,
                whatsapp_allowed = 0,
                features = '["Custom Prompt", "Slack Integration", "Discord Integration", "Web Integration", "Advanced Analytics", "Bot Memory"]',
                display_order = 2
            WHERE plan_type = 'basic' AND is_active = 1
        """))
        print("   ✅ Basic plan updated")
        
        # 3. Update Growth plan
        print("3️⃣ Updating Growth plan...")
        session.execute(text("""
            UPDATE pricing_plans 
            SET 
                price_monthly = 29.00,
                price_yearly = 290.00,
                max_messages_monthly = 5000,
                whatsapp_allowed = 0,
                is_popular = 1,
                features = '["Custom Prompt", "Slack Integration", "Discord Integration", "Web Integration", "Advanced Analytics", "Priority Support", "Bot Memory"]',
                display_order = 3
            WHERE plan_type = 'growth' AND is_active = 1
        """))
        print("   ✅ Growth plan updated")
        
        # 4. Check if Pro plan exists, if not create it
        print("4️⃣ Adding Pro plan...")
        existing_pro = session.execute(text("""
            SELECT id FROM pricing_plans WHERE plan_type = 'pro'
        """)).fetchone()
        
        if not existing_pro:
            # Use proper timestamp function based on database type
            insert_sql = f"""
                INSERT INTO pricing_plans (
                    name, plan_type, price_monthly, price_yearly, 
                    max_integrations, max_messages_monthly,
                    custom_prompt_allowed, website_api_allowed, 
                    slack_allowed, discord_allowed, whatsapp_allowed,
                    features, is_active, is_addon, is_popular, display_order,
                    created_at, updated_at
                ) VALUES (
                    'Pro', 'pro', 59.00, 590.00,
                    -1, 20000,
                    1, 1, 1, 1, 0,
                    '["Custom Prompt", "Slack Integration", "Discord Integration", "Web Integration", "Advanced Analytics", "Priority Support", "Enhanced Bot Memory", "API Access"]',
                    1, 0, 0, 4,
                    {timestamp_func}, {timestamp_func}
                )
            """
            session.execute(text(insert_sql))
            print("   ✅ Pro plan created")
        else:
            print("   ℹ️ Pro plan already exists")
        
        # 5. Update Agency plan
        print("5️⃣ Updating Agency plan...")
        session.execute(text("""
            UPDATE pricing_plans 
            SET 
                whatsapp_allowed = 0,
                features = '["Custom Prompt", "Slack Integration", "Discord Integration", "Web Integration", "Advanced Analytics", "Priority Support", "Enhanced Bot Memory", "API Access", "White Label", "Custom Integrations"]',
                display_order = 5
            WHERE plan_type = 'agency' AND is_active = 1
        """))
        print("   ✅ Agency plan updated")
        
        # 6. Update Free plan
        print("6️⃣ Updating Free plan...")
        session.execute(text("""
            UPDATE pricing_plans 
            SET 
                whatsapp_allowed = 0,
                display_order = 1
            WHERE plan_type = 'free' AND is_active = 1
        """))
        print("   ✅ Free plan updated")
        
        # Commit all changes
        session.commit()
        print("\n🎉 Migration completed successfully!")
        
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        session.rollback()
        return False

def verify_migration(session):
    """Verify the migration was successful"""
    try:
        print("\n🔍 Verifying migration...")
        
        result = session.execute(text("""
            SELECT name, plan_type, price_monthly, max_messages_monthly, is_active, display_order
            FROM pricing_plans 
            WHERE is_active = 1
            ORDER BY display_order
        """))
        
        plans = result.fetchall()
        
        print("\n📊 Current active plans:")
        print("=" * 60)
        for plan in plans:
            print(f"• {plan.name}: ${plan.price_monthly}/month - {plan.max_messages_monthly:,} conversations")
        
        print("=" * 60)
        
        # Check expected plans exist
        expected_plans = ['free', 'basic', 'growth', 'pro', 'agency']
        existing_types = [plan.plan_type for plan in plans]
        
        missing_plans = set(expected_plans) - set(existing_types)
        if missing_plans:
            print(f"⚠️ Missing plans: {missing_plans}")
            return False
        
        print("✅ All expected plans are present and active")
        return True
        
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return False

def main():
    """Main migration function"""
    print("🚀 Pricing Plan Migration Script")
    print("=" * 50)
    
    # Get database URL
    db_url = get_database_url()
    if not db_url:
        print("❌ No database URL provided. Exiting.")
        return False
    
    # Create database session
    session, engine, db_type = create_db_session(db_url)
    if not session:
        return False
    
    try:
        # Create backup
        if not backup_current_plans(session):
            print("⚠️ Backup failed. Continue anyway? (y/N): ", end="")
            if input().lower() != 'y':
                return False
        
        # Confirm migration
        print(f"\n⚠️ About to migrate pricing plans in database:")
        if 'sqlite' in db_url:
            print(f"Database: Local SQLite Database")
        elif '@' in db_url:
            print(f"Database: {db_url.split('@')[1]}")
        else:
            print(f"Database: {db_type}")
            
        print("\nChanges to be made:")
        print("• Deactivate old live chat plans")
        print("• Update Basic: $19 → $9.99, 500 → 2,000 conversations")
        print("• Update Growth: $39 → $29, mark as popular")
        print("• Add Pro: $59, 20,000 conversations")
        print("• Disable WhatsApp on all plans")
        
        confirm = input("\nProceed with migration? (y/N): ").lower()
        if confirm != 'y':
            print("❌ Migration cancelled by user.")
            return False
        
        # Execute migration
        if not migrate_pricing_plans(session, db_type):
            return False
        
        # Verify migration
        if not verify_migration(session):
            print("⚠️ Migration verification failed. Please check manually.")
            return False
        
        print("\n🎉 Migration completed successfully!")
        if db_type == 'sqlite':
            print("\nNext: Run the same script with your Render database URL")
        else:
            print("\nNext steps:")
            print("1. Update your application code with new plan types")
            print("2. Test the pricing endpoints")
            print("3. Update your frontend to show new plans")
        
        return True
        
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False
    
    finally:
        session.close()
        if engine:
            engine.dispose()

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)