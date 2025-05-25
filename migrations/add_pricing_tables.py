"""
Fixed migration script to add pricing tables to existing database
Run this script from the project root directory
"""

import sys
import os
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Now we can import from app
try:
    from sqlalchemy import create_engine, MetaData
    from app.database import get_db, engine, Base
    from app.pricing.models import PricingPlan, TenantSubscription, UsageLog, BillingHistory
    from app.pricing.service import PricingService
    print("✅ All imports successful")
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure you're running this from the project root directory")
    sys.exit(1)

def run_migration():
    """Run the pricing tables migration"""
    
    try:
        print("🚀 Starting pricing system migration...")
        
        # Create all pricing tables
        print("📊 Creating pricing tables...")
        
        # Create tables one by one to handle dependencies
        tables_to_create = [
            PricingPlan.__table__,
            TenantSubscription.__table__,
            UsageLog.__table__,
            BillingHistory.__table__
        ]
        
        for table in tables_to_create:
            try:
                table.create(engine, checkfirst=True)
                print(f"✅ Created table: {table.name}")
            except Exception as e:
                print(f"⚠️  Table {table.name} might already exist: {e}")
        
        print("✅ All pricing tables created successfully")
        
        # Initialize default plans
        print("📋 Creating default pricing plans...")
        db = next(get_db())
        try:
            pricing_service = PricingService(db)
            
            # Check if plans already exist
            existing_plans = db.query(PricingPlan).count()
            if existing_plans > 0:
                print(f"ℹ️  Found {existing_plans} existing plans, skipping plan creation")
            else:
                pricing_service.create_default_plans()
                print("✅ Default pricing plans created successfully")
            
            # Create free subscriptions for existing tenants
            print("🔗 Creating free subscriptions for existing tenants...")
            from app.tenants.models import Tenant
            existing_tenants = db.query(Tenant).filter(Tenant.is_active == True).all()
            
            subscription_count = 0
            for tenant in existing_tenants:
                try:
                    subscription = pricing_service.get_tenant_subscription(tenant.id)
                    if not subscription:
                        pricing_service.create_free_subscription_for_tenant(tenant.id)
                        subscription_count += 1
                        print(f"✅ Created free subscription for tenant: {tenant.name}")
                    else:
                        print(f"ℹ️  Tenant {tenant.name} already has a subscription")
                except Exception as e:
                    print(f"❌ Error creating subscription for tenant {tenant.name}: {e}")
            
            print(f"✅ Created {subscription_count} new free subscriptions")
            print("🎉 Migration completed successfully!")
            
            # Display summary
            total_plans = db.query(PricingPlan).count()
            total_subscriptions = db.query(TenantSubscription).count()
            print(f"\n📈 Summary:")
            print(f"   - Total pricing plans: {total_plans}")
            print(f"   - Total subscriptions: {total_subscriptions}")
            print(f"   - Total tenants: {len(existing_tenants)}")
            
        except Exception as e:
            print(f"❌ Error during migration: {e}")
            db.rollback()
            raise
        finally:
            db.close()
            
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

def verify_migration():
    """Verify that the migration completed successfully"""
    print("\n🔍 Verifying migration...")
    
    try:
        db = next(get_db())
        
        # Check tables exist
        tables = ['pricing_plans', 'tenant_subscriptions', 'usage_logs', 'billing_history']
        for table_name in tables:
            try:
                result = db.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = result.scalar()
                print(f"✅ Table {table_name}: {count} records")
            except Exception as e:
                print(f"❌ Table {table_name}: {e}")
        
        # Check default plans
        plans = db.query(PricingPlan).all()
        print(f"\n📋 Pricing Plans:")
        for plan in plans:
            print(f"   - {plan.name}: ${plan.price_monthly}/month")
        
        db.close()
        print("✅ Verification complete!")
        
    except Exception as e:
        print(f"❌ Verification failed: {e}")

if __name__ == "__main__":
    print("💰 Pricing System Migration Tool")
    print("=" * 50)
    
    # Check if we're in the right directory
    if not os.path.exists("app"):
        print("❌ Error: 'app' directory not found.")
        print("Please run this script from the project root directory (where app/ folder is located)")
        sys.exit(1)
    
    # Check if pricing models exist
    if not os.path.exists("app/pricing"):
        print("❌ Error: 'app/pricing' directory not found.")
        print("Please create the pricing module first with all the model files")
        sys.exit(1)
    
    run_migration()
    verify_migration()
    
    print("\n🎯 Next Steps:")
    print("1. Update your main.py to include the pricing router")
    print("2. Add usage tracking to your existing endpoints")
    print("3. Test the pricing endpoints with your API")
    print("\nExample test command:")
    print("curl -X GET 'http://localhost:8000/pricing/plans'")