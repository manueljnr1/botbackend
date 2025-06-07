#!/usr/bin/env python3
"""
Fix script for Render database - Reactivate missing plans
"""

import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

def get_render_database_url():
    """Get Render database URL"""
    print("🔧 Render Database Fix Script")
    print("=" * 50)
    print("This will fix the missing Basic, Growth, and Agency plans on Render.")
    print("\nPlease provide your Render external database URL:")
    
    db_url = input("\nRender Database URL: ").strip()
    
    if not db_url:
        print("❌ No database URL provided. Exiting.")
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

def diagnose_render_database(session):
    """Check what's currently in the Render database"""
    try:
        print("\n🔍 Checking Render database...")
        
        # Get ALL plans
        result = session.execute(text("""
            SELECT id, name, plan_type, price_monthly, max_messages_monthly, 
                   is_active, display_order
            FROM pricing_plans 
            ORDER BY id
        """))
        
        plans = result.fetchall()
        
        print("\n📊 ALL PLANS IN RENDER DATABASE:")
        print("-" * 60)
        for plan in plans:
            status = "✅ ACTIVE" if plan.is_active else "❌ INACTIVE"
            print(f"ID: {plan.id} | {plan.name} ({plan.plan_type}) | ${plan.price_monthly}/month | {status}")
        
        # Show active plans
        active_result = session.execute(text("""
            SELECT name, plan_type, price_monthly, is_active
            FROM pricing_plans 
            WHERE is_active = true
            ORDER BY display_order
        """))
        
        active_plans = active_result.fetchall()
        
        print(f"\n📊 ACTIVE PLANS ({len(active_plans)} found):")
        print("-" * 60)
        for plan in active_plans:
            print(f"• {plan.name}: ${plan.price_monthly}/month")
        
        return plans
        
    except Exception as e:
        print(f"❌ Error checking database: {e}")
        return []

def fix_render_plans(session):
    """Fix the inactive plans on Render"""
    try:
        print("\n🔧 Fixing Render pricing plans...")
        
        # 1. Reactivate Basic plan
        print("1️⃣ Reactivating Basic plan...")
        result = session.execute(text("""
            UPDATE pricing_plans 
            SET 
                is_active = true,
                price_monthly = 9.99,
                price_yearly = 99.00,
                max_messages_monthly = 2000,
                display_order = 2,
                updated_at = NOW()
            WHERE plan_type = 'basic'
        """))
        print(f"   ✅ Basic plan updated ({result.rowcount} rows affected)")
        
        # 2. Reactivate Growth plan
        print("2️⃣ Reactivating Growth plan...")
        result = session.execute(text("""
            UPDATE pricing_plans 
            SET 
                is_active = true,
                price_monthly = 29.00,
                price_yearly = 290.00,
                max_messages_monthly = 5000,
                is_popular = true,
                display_order = 3,
                updated_at = NOW()
            WHERE plan_type = 'growth'
        """))
        print(f"   ✅ Growth plan updated ({result.rowcount} rows affected)")
        
        # 3. Reactivate Agency plan
        print("3️⃣ Reactivating Agency plan...")
        result = session.execute(text("""
            UPDATE pricing_plans 
            SET 
                is_active = true,
                display_order = 5,
                updated_at = NOW()
            WHERE plan_type = 'agency'
        """))
        print(f"   ✅ Agency plan updated ({result.rowcount} rows affected)")
        
        # 4. Fix Free plan order
        print("4️⃣ Fixing Free plan order...")
        result = session.execute(text("""
            UPDATE pricing_plans 
            SET 
                display_order = 1,
                updated_at = NOW()
            WHERE plan_type = 'free'
        """))
        print(f"   ✅ Free plan updated ({result.rowcount} rows affected)")
        
        # 5. Fix Pro plan order
        print("5️⃣ Fixing Pro plan order...")
        result = session.execute(text("""
            UPDATE pricing_plans 
            SET 
                display_order = 4,
                updated_at = NOW()
            WHERE plan_type = 'pro'
        """))
        print(f"   ✅ Pro plan updated ({result.rowcount} rows affected)")
        
        # Commit changes
        session.commit()
        print("\n🎉 All Render plans fixed!")
        
        return True
        
    except Exception as e:
        print(f"❌ Error fixing plans: {e}")
        session.rollback()
        return False

def verify_render_fix(session):
    """Verify all plans are now active"""
    try:
        print("\n🔍 Verifying Render fix...")
        
        result = session.execute(text("""
            SELECT name, plan_type, price_monthly, max_messages_monthly, is_active, display_order
            FROM pricing_plans 
            WHERE is_active = true
            ORDER BY display_order
        """))
        
        plans = result.fetchall()
        
        print("\n📊 FINAL RENDER ACTIVE PLANS:")
        print("=" * 60)
        for plan in plans:
            print(f"• {plan.name}: ${plan.price_monthly}/month - {plan.max_messages_monthly:,} conversations")
        print("=" * 60)
        
        # Check all expected plans
        expected_plans = ['free', 'basic', 'growth', 'pro', 'agency']
        existing_types = [plan.plan_type for plan in plans]
        missing_plans = set(expected_plans) - set(existing_types)
        
        if missing_plans:
            print(f"\n❌ Still missing plans: {missing_plans}")
            
            # Show what plans we DO have
            print(f"✅ Found plans: {existing_types}")
            return False
        else:
            print(f"\n✅ ALL 5 EXPECTED PLANS ARE NOW ACTIVE ON RENDER!")
            return True
        
    except Exception as e:
        print(f"❌ Verification error: {e}")
        return False

def main():
    """Main function"""
    
    # Get Render URL
    db_url = get_render_database_url()
    if not db_url:
        return False
    
    # Connect to database
    session, engine = create_db_session(db_url)
    if not session:
        return False
    
    try:
        # Show current state
        plans = diagnose_render_database(session)
        if not plans:
            return False
        
        # Ask for confirmation
        print(f"\n⚠️ About to fix pricing plans on Render database")
        print("This will reactivate Basic, Growth, and Agency plans.")
        
        confirm = input("\nProceed with Render fixes? (y/N): ").lower()
        if confirm != 'y':
            print("❌ Render fix cancelled.")
            return False
        
        # Fix the plans
        if not fix_render_plans(session):
            return False
        
        # Verify the fix
        if not verify_render_fix(session):
            print("⚠️ Fix verification failed. Some plans may still be missing.")
            return False
        
        print("\n🎉 RENDER DATABASE SUCCESSFULLY FIXED!")
        print("✅ Both your local SQLite and Render PostgreSQL databases")
        print("   now have the same pricing structure!")
        
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