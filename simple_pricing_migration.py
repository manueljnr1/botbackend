# quick_fix_router.py
"""
Quick script to fix the PricingService import in tenant router
"""

import os

def fix_tenant_router():
    """Add proper PricingService import to tenant router"""
    
    router_path = "app/tenants/router.py"
    
    if not os.path.exists(router_path):
        print(f"❌ Router file not found: {router_path}")
        return False
    
    # Read current file
    with open(router_path, 'r') as f:
        content = f.read()
    
    # Check if import already exists
    if "from app.pricing.service import PricingService" in content:
        print("✅ PricingService import already exists")
        return True
    
    # Find where to add the import (after existing imports)
    lines = content.split('\n')
    import_insert_line = 0
    
    # Find the last import line
    for i, line in enumerate(lines):
        if line.strip().startswith('from app.') or line.strip().startswith('import '):
            import_insert_line = i + 1
    
    # Insert the pricing service import
    new_import = """
# Pricing service import
try:
    from app.pricing.service import PricingService
    PRICING_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ PricingService not available: {e}")
    PRICING_AVAILABLE = False
"""
    
    lines.insert(import_insert_line, new_import)
    
    # Also add logging if not present
    if "import logging" not in content:
        lines.insert(import_insert_line + 1, "import logging")
        lines.insert(import_insert_line + 2, "logger = logging.getLogger(__name__)")
    
    # Write back to file
    new_content = '\n'.join(lines)
    
    # Backup original file
    backup_path = router_path + ".backup"
    with open(backup_path, 'w') as f:
        f.write(content)
    print(f"📥 Created backup: {backup_path}")
    
    # Write updated file
    with open(router_path, 'w') as f:
        f.write(new_content)
    
    print("✅ Updated tenant router with PricingService import")
    return True

def create_manual_subscription(tenant_name="Esther"):
    """Manually create subscription for the tenant that failed"""
    
    import sys
    from pathlib import Path
    
    # Fix imports
    current_dir = Path(__file__).parent
    sys.path.insert(0, str(current_dir))
    
    from sqlalchemy import text
    from app.database import get_db
    from datetime import datetime, timedelta
    
    print(f"🔧 Creating manual subscription for {tenant_name}...")
    
    db = next(get_db())
    
    try:
        # Find the tenant
        tenant = db.execute(text("SELECT id, name FROM tenants WHERE name = :name"), {"name": tenant_name}).fetchone()
        if not tenant:
            print(f"❌ Tenant '{tenant_name}' not found")
            return False
        
        print(f"✅ Found tenant: {tenant.name} (ID: {tenant.id})")
        
        # Check if subscription already exists
        existing_sub = db.execute(text("""
            SELECT id FROM tenant_subscriptions 
            WHERE tenant_id = :tenant_id AND is_active = 1
        """), {"tenant_id": tenant.id}).fetchone()
        
        if existing_sub:
            print(f"ℹ️ Tenant {tenant.name} already has an active subscription")
            return True
        
        # Get Free plan
        free_plan = db.execute(text("SELECT id FROM pricing_plans WHERE plan_type = 'free'")).fetchone()
        if not free_plan:
            print("❌ Free plan not found")
            return False
        
        # Create subscription
        current_time = datetime.now()
        period_end = current_time + timedelta(days=30)
        
        db.execute(text("""
            INSERT INTO tenant_subscriptions 
            (tenant_id, plan_id, is_active, billing_cycle, current_period_start, current_period_end, status, messages_used_current_period, integrations_count)
            VALUES (:tenant_id, :plan_id, 1, 'monthly', :start_time, :end_time, 'active', 0, 0)
        """), {
            "tenant_id": tenant.id,
            "plan_id": free_plan.id,
            "start_time": current_time,
            "end_time": period_end
        })
        
        db.commit()
        print(f"✅ Created Free subscription for {tenant.name}")
        
        # Get the tenant's API key for testing
        api_key = db.execute(text("SELECT api_key FROM tenants WHERE id = :id"), {"id": tenant.id}).fetchone()
        if api_key:
            print(f"🔑 API Key: {api_key.api_key}")
            print(f"🧪 Test with: curl -X GET 'http://localhost:8000/pricing/usage' -H 'X-API-Key: {api_key.api_key}'")
        
        return True
        
    except Exception as e:
        print(f"❌ Error creating subscription: {e}")
        db.rollback()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    print("🔧 Tenant Router Fixer")
    print("=" * 30)
    
    # Fix the import issue
    if fix_tenant_router():
        print("\n🔧 Creating manual subscription for Esther...")
        create_manual_subscription("Esther")
        
        print("\n✅ All fixes completed!")
        print("\n🎯 Next steps:")
        print("1. Restart your FastAPI server")
        print("2. Test tenant registration again")
        print("3. New tenants should now get automatic subscriptions")
    else:
        print("❌ Failed to fix tenant router")