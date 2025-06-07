#!/usr/bin/env python3
"""
Quick diagnostic script to check what's in your pricing_plans table
"""

import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

def get_database_url():
    """Get database URL from environment or prompt user"""
    db_url = os.getenv('DATABASE_URL')
    
    if not db_url:
        print("Please provide your database connection string:")
        print("Local SQLite example: sqlite:///./your_database.db")
        db_url = input("Database URL: ").strip()
    
    return db_url

def check_database():
    """Check what's currently in the database"""
    
    db_url = get_database_url()
    
    try:
        engine = create_engine(db_url)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        session = SessionLocal()
        
        print("🔍 Checking your pricing_plans table...")
        print("=" * 60)
        
        # Get ALL plans (both active and inactive)
        result = session.execute(text("""
            SELECT id, name, plan_type, price_monthly, max_messages_monthly, 
                   is_active, display_order, created_at
            FROM pricing_plans 
            ORDER BY display_order, id
        """))
        
        plans = result.fetchall()
        
        if not plans:
            print("❌ No plans found in the database!")
            return
        
        print("📊 ALL PLANS IN DATABASE:")
        print("-" * 60)
        for plan in plans:
            status = "✅ ACTIVE" if plan.is_active else "❌ INACTIVE"
            print(f"ID: {plan.id} | {plan.name} ({plan.plan_type}) | ${plan.price_monthly}/month")
            print(f"   Conversations: {plan.max_messages_monthly} | Order: {plan.display_order} | {status}")
            print(f"   Created: {plan.created_at}")
            print("-" * 60)
        
        # Check only active plans
        active_result = session.execute(text("""
            SELECT name, plan_type, price_monthly, max_messages_monthly, display_order
            FROM pricing_plans 
            WHERE is_active = 1
            ORDER BY display_order
        """))
        
        active_plans = active_result.fetchall()
        
        print(f"\n📊 ACTIVE PLANS ({len(active_plans)} found):")
        print("-" * 60)
        for plan in active_plans:
            print(f"• {plan.name}: ${plan.price_monthly}/month - {plan.max_messages_monthly:,} conversations (Order: {plan.display_order})")
        
        # Check for missing expected plans
        expected_plans = ['free', 'basic', 'growth', 'pro', 'agency']
        existing_types = [plan.plan_type for plan in active_plans]
        missing_plans = set(expected_plans) - set(existing_types)
        
        if missing_plans:
            print(f"\n⚠️ MISSING PLANS: {missing_plans}")
            print("\nThese plans need to be created. Let me show you what to do...")
        else:
            print(f"\n✅ All expected plans are present!")
        
        session.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    check_database()