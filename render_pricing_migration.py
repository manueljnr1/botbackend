#!/usr/bin/env python3
"""
Render Database Migration Script - Forces you to enter Render URL
"""

import os
import sys
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

def get_render_database_url():
    """Force user to enter Render database URL"""
    print("🚀 Render Database Migration")
    print("=" * 50)
    print("This script will migrate your RENDER database only.")
    print("\nPlease provide your Render external database URL:")
    print("Example: postgresql://user:pass@dpg-xxxxx-a.oregon-postgres.render.com:5432/database")
    
    db_url = input("\nRender Database URL: ").strip()
    
    if not db_url:
        print("❌ No database URL provided. Exiting.")
        return None
    
    if not db_url.startswith('postgresql://'):
        print("❌ Please provide a PostgreSQL URL (starts with postgresql://)")
        return None
    
    return db_url

def create_db_session(db_url):
    """Create database session"""
    try:
        engine = create_engine(db_url)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        session = SessionLocal()
        
        # Test connection
        session.execute(text("SELECT 1"))
        print("✅ Render database connection successful!")
        return session, engine
    except Exception as e:
        print(f"❌ Render database connection failed: {e}")
        return None, None

def backup_current_plans(session):
    """Create a backup of current pricing plans"""
    try:
        print("\n📋 Creating backup of current Render plans...")
        
        result = session.execute(text("""
            SELECT id, name, plan_type, price_monthly, price_yearly, 
                   max_messages_monthly, is_active, features
            FROM pricing_plans 
            WHERE is_active = true
        """))
        
        plans = result.fetchall()
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"render_backup_{timestamp}.sql"
        
        with open(backup_filename, 'w') as f:
            f.write("-- Render Database Backup\n")
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

def migrate_render_pricing(session):
    """Execute the pricing plan migration for Render (PostgreSQL)"""
    try:
        print("\n🔄 Starting Render pricing plan migration...")
        
        # 1. Deactivate old live chat plans
        print("1️⃣ Deactivating old live chat plans...")
        result = session.execute(text("""
            UPDATE pricing_plans 
            SET is_active = false 
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
                whatsapp_allowed = false,
                features = '["Custom Prompt", "Slack Integration", "Discord Integration", "Web Integration", "Advanced Analytics", "Bot Memory"]',
                display_order = 2
            WHERE plan_type = 'basic' AND is_active = true
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
                whatsapp_allowed = false,
                is_popular = true,
                features = '["Custom Prompt", "Slack Integration", "Discord Integration", "Web Integration", "Advanced Analytics", "Priority Support", "Bot Memory"]',
                display_order = 3
            WHERE plan_type = 'growth' AND is_active = true
        """))
        print("   ✅ Growth plan updated")
        
        # 4. Add Pro plan
        print("4️⃣ Adding Pro plan...")
        existing_pro = session.execute(text("""
            SELECT id FROM pricing_plans WHERE plan_type = 'pro'
        """)).fetchone()
        
        if not existing_pro:
            session.execute(text("""
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
                    true, true, true, true, false,
                    '["Custom Prompt", "Slack Integration", "Discord Integration", "Web Integration", "Advanced Analytics", "Priority Support", "Enhanced Bot Memory", "API Access"]',
                    true, false, false, 4,
                    NOW(), NOW()
                )
            """))
            print("   ✅ Pro plan created")
        else:
            print("   ℹ️ Pro plan already exists")
        
        # 5. Update Agency plan
        print("5️⃣ Updating Agency plan...")
        session.execute(text("""
            UPDATE pricing_plans 
            SET 
                whatsapp_allowed = false,
                features = '["Custom Prompt", "Slack Integration", "Discord Integration", "Web Integration", "Advanced Analytics", "Priority Support", "Enhanced Bot Memory", "API Access", "White Label", "Custom Integrations"]',
                display_order = 5
            WHERE plan_type = 'agency' AND is_active = true
        """))
        print("   ✅ Agency plan updated")
        
        # 6. Update Free plan
        print("6️⃣ Updating Free plan...")
        session.execute(text("""
            UPDATE pricing_plans 
            SET 
                whatsapp_allowed = false,
                display_order = 1
            WHERE plan_type = 'free' AND is_active = true
        """))
        print("   ✅ Free plan updated")
        
        session.commit()
        print("\n🎉 Render migration completed successfully!")
        
        return True
        
    except Exception as e:
        print(f"❌ Render migration failed: {e}")
        session.rollback()
        return False

def verify_render_migration(session):
    """Verify the migration was successful"""
    try:
        print("\n🔍 Verifying Render migration...")
        
        result = session.execute(text("""
            SELECT name, plan_type, price_monthly, max_messages_monthly, is_active, display_order
            FROM pricing_plans 
            WHERE is_active = true
            ORDER BY display_order
        """))
        
        plans = result.fetchall()
        
        print("\n📊 RENDER ACTIVE PLANS:")
        print("=" * 60)
        for plan in plans:
            print(f"• {plan.name}: ${plan.price_monthly}/month - {plan.max_messages_monthly:,} conversations")
        print("=" * 60)
        
        expected_plans = ['free', 'basic', 'growth', 'pro', 'agency']
        existing_types = [plan.plan_type for plan in plans]
        missing_plans = set(expected_plans) - set(existing_types)
        
        if missing_plans:
            print(f"⚠️ Missing plans: {missing_plans}")
            return False
        
        print("✅ All expected plans are present and active on Render!")
        return True
        
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return False

def main():
    """Main function"""
    
    # Force user to enter Render URL
    db_url = get_render_database_url()
    if not db_url:
        return False
    
    # Create database session
    session, engine = create_db_session(db_url)
    if not session:
        return False
    
    try:
        # Show which database we're updating
        host = db_url.split('@')[1].split('/')[0] if '@' in db_url else 'Unknown'
        print(f"\n⚠️ About to migrate RENDER database:")
        print(f"Host: {host}")
        
        if not backup_current_plans(session):
            print("⚠️ Backup failed. Continue anyway? (y/N): ", end="")
            if input().lower() != 'y':
                return False
        
        print("\nChanges to be made:")
        print("• Deactivate old live chat plans")
        print("• Update Basic: → $9.99, 2,000 conversations")
        print("• Update Growth: → $29, 5,000 conversations (popular)")
        print("• Add Pro: $59, 20,000 conversations")
        print("• Disable WhatsApp on all plans")
        
        confirm = input("\nProceed with RENDER migration? (y/N): ").lower()
        if confirm != 'y':
            print("❌ Render migration cancelled.")
            return False
        
        if not migrate_render_pricing(session):
            return False
        
        if not verify_render_migration(session):
            print("⚠️ Verification failed. Please check manually.")
            return False
        
        print("\n🎉 RENDER DATABASE MIGRATION COMPLETED!")
        print("✅ Both local and Render databases are now synchronized!")
        
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