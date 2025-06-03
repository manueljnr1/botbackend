"""
Fixed migration script to upgrade pricing tables to conversation-based model
Run this script from the project root directory or migrations folder
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# Fix the Python path to find the app module
current_dir = Path(__file__).parent
project_root = current_dir.parent if current_dir.name == 'migrations' else current_dir

# Add project root to Python path
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

print(f"🔍 Current directory: {current_dir}")
print(f"📁 Project root: {project_root}")
print(f"🐍 Python path: {sys.path[:3]}")

# Change to project root directory
os.chdir(project_root)
print(f"📂 Changed working directory to: {os.getcwd()}")

# Now we can import from app
try:
    from sqlalchemy import create_engine, MetaData, text
    from app.database import get_db, engine, Base
    from app.pricing.models import PricingPlan, TenantSubscription, UsageLog, BillingHistory
    from app.pricing.service import PricingService
    print("✅ All imports successful")
except ImportError as e:
    print(f"❌ Import error: {e}")
    print(f"Current working directory: {os.getcwd()}")
    print(f"Contents of current directory: {os.listdir('.')}")
    
    # Check if app directory exists
    if os.path.exists("app"):
        print(f"📁 Found app directory, contents: {os.listdir('app')}")
    else:
        print("❌ 'app' directory not found!")
        
    print("\nTroubleshooting:")
    print("1. Make sure you're in the correct project directory")
    print("2. Check that the 'app' folder exists")
    print("3. Verify your virtual environment is activated")
    sys.exit(1)

def backup_database():
    """Create a backup of the current database"""
    try:
        import shutil
        db_path = "./chatbot.db"
        backup_path = f"./chatbot_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        
        if os.path.exists(db_path):
            shutil.copy2(db_path, backup_path)
            print(f"✅ Database backed up to: {backup_path}")
            return backup_path
        else:
            print("⚠️ Database file not found, proceeding without backup")
            return None
    except Exception as e:
        print(f"❌ Backup failed: {e}")
        return None

def check_current_schema():
    """Check what tables and columns currently exist"""
    print("🔍 Checking current database schema...")
    
    db = next(get_db())
    
    try:
        # Check existing tables
        result = db.execute(text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"))
        tables = [row[0] for row in result.fetchall()]
        print(f"📊 Found tables: {tables}")
        
        # Check pricing_plans table structure if it exists
        if 'pricing_plans' in tables:
            result = db.execute(text("PRAGMA table_info(pricing_plans)"))
            columns = [row[1] for row in result.fetchall()]
            print(f"📋 pricing_plans columns: {columns}")
        
        return tables
        
    except Exception as e:
        print(f"❌ Error checking schema: {e}")
        return []
    finally:
        db.close()

def create_missing_tables():
    """Create any missing pricing tables"""
    print("🏗️ Creating missing pricing tables...")
    
    try:
        # Create all pricing tables
        tables_to_create = [
            PricingPlan.__table__,
            TenantSubscription.__table__,
            UsageLog.__table__,
            BillingHistory.__table__
        ]
        
        for table in tables_to_create:
            try:
                table.create(engine, checkfirst=True)
                print(f"✅ Ensured table exists: {table.name}")
            except Exception as e:
                print(f"⚠️ Issue with table {table.name}: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error creating tables: {e}")
        return False

def run_schema_updates():
    """Add new columns and tables for conversation-based pricing"""
    print("🔄 Updating database schema for conversation-based pricing...")
    
    db = next(get_db())
    
    try:
        # Schema updates with error handling for existing columns
        schema_updates = [
            # Add new columns to pricing_plans (with individual try-catch)
            ("pricing_plans", "is_addon", "ALTER TABLE pricing_plans ADD COLUMN is_addon BOOLEAN DEFAULT FALSE"),
            ("pricing_plans", "is_popular", "ALTER TABLE pricing_plans ADD COLUMN is_popular BOOLEAN DEFAULT FALSE"), 
            ("pricing_plans", "display_order", "ALTER TABLE pricing_plans ADD COLUMN display_order INTEGER DEFAULT 0"),
            
            # Update tenant subscriptions
            ("tenant_subscriptions", "active_addons", "ALTER TABLE tenant_subscriptions ADD COLUMN active_addons TEXT"),
            ("tenant_subscriptions", "stripe_customer_id", "ALTER TABLE tenant_subscriptions ADD COLUMN stripe_customer_id TEXT"),
            
            # Enhanced usage logs
            ("usage_logs", "session_id", "ALTER TABLE usage_logs ADD COLUMN session_id TEXT"),
            ("usage_logs", "user_identifier", "ALTER TABLE usage_logs ADD COLUMN user_identifier TEXT"),
            ("usage_logs", "platform", "ALTER TABLE usage_logs ADD COLUMN platform TEXT"),
            
            # Enhanced billing history
            ("billing_history", "plan_name", "ALTER TABLE billing_history ADD COLUMN plan_name TEXT"),
            ("billing_history", "conversations_included", "ALTER TABLE billing_history ADD COLUMN conversations_included INTEGER"),
            ("billing_history", "conversations_used", "ALTER TABLE billing_history ADD COLUMN conversations_used INTEGER"),
            ("billing_history", "addons_included", "ALTER TABLE billing_history ADD COLUMN addons_included TEXT"),
            ("billing_history", "stripe_charge_id", "ALTER TABLE billing_history ADD COLUMN stripe_charge_id TEXT"),
            ("billing_history", "payment_method", "ALTER TABLE billing_history ADD COLUMN payment_method TEXT"),
        ]
        
        print("   Adding new columns...")
        for table_name, column_name, sql in schema_updates:
            try:
                db.execute(text(sql))
                db.commit()
                print(f"   ✅ Added {column_name} to {table_name}")
            except Exception as e:
                if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                    print(f"   ℹ️ Column {column_name} already exists in {table_name}")
                else:
                    print(f"   ⚠️ Failed to add {column_name} to {table_name}: {e}")
        
        # Create conversation sessions table
        print("   Creating conversation_sessions table...")
        conversation_table_sql = """
        CREATE TABLE IF NOT EXISTS conversation_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            user_identifier TEXT NOT NULL,
            platform TEXT NOT NULL,
            started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_activity TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE,
            message_count INTEGER DEFAULT 0,
            duration_minutes INTEGER DEFAULT 0,
            counted_for_billing BOOLEAN DEFAULT FALSE,
            billing_period_start TIMESTAMP,
            extra_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id)
        )
        """
        
        db.execute(text(conversation_table_sql))
        db.commit()
        print("   ✅ conversation_sessions table created")
        
        # Create indexes
        print("   Creating indexes...")
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_conversation_sessions_tenant_user ON conversation_sessions(tenant_id, user_identifier)",
            "CREATE INDEX IF NOT EXISTS idx_conversation_sessions_activity ON conversation_sessions(last_activity)",
            "CREATE INDEX IF NOT EXISTS idx_conversation_sessions_billing ON conversation_sessions(tenant_id, counted_for_billing)",
        ]
        
        for index_sql in indexes:
            try:
                db.execute(text(index_sql))
                db.commit()
                print(f"   ✅ Created index")
            except Exception as e:
                print(f"   ⚠️ Index creation issue: {e}")
        
        print("✅ Schema updates completed")
        return True
        
    except Exception as e:
        print(f"❌ Schema update failed: {e}")
        db.rollback()
        return False
    finally:
        db.close()

def update_existing_plans():
    """Update existing pricing plans to new conversation-based structure"""
    print("📊 Updating existing pricing plans...")
    
    db = next(get_db())
    
    try:
        # Check if we have any existing plans first
        existing_plans = db.query(PricingPlan).all()
        print(f"   Found {len(existing_plans)} existing plans")
        
        if len(existing_plans) == 0:
            print("   No existing plans found, will create new ones")
            return True
        
        # Update existing plans
        updates = [
            # Enable features for all plans
            """
            UPDATE pricing_plans SET 
                max_integrations = -1,
                custom_prompt_allowed = 1,
                slack_allowed = 1,
                discord_allowed = 1
            WHERE plan_type IN ('free', 'basic', 'pro')
            """,
            
            # Update Free plan
            """
            UPDATE pricing_plans SET 
                max_messages_monthly = 50
            WHERE plan_type = 'free'
            """,
            
            # Update Basic plan
            """
            UPDATE pricing_plans SET 
                price_monthly = 19.00,
                price_yearly = 190.00,
                max_messages_monthly = 500,
                features = '["Custom Prompt", "Slack Integration", "Discord Integration", "Web Integration", "Advanced Analytics", "Bot Memory"]'
            WHERE plan_type = 'basic'
            """,
            
            # Convert Pro to Agency
            """
            UPDATE pricing_plans SET 
                name = 'Agency',
                plan_type = 'agency',
                price_monthly = 99.00,
                price_yearly = 990.00,
                max_messages_monthly = 50000,
                whatsapp_allowed = 1,
                features = '["Custom Prompt", "Slack Integration", "Discord Integration", "Web Integration", "Advanced Analytics", "Priority Support", "Live Chat Integration", "Bot Memory", "WhatsApp Integration"]'
            WHERE plan_type = 'pro'
            """,
        ]
        
        for i, update_sql in enumerate(updates, 1):
            try:
                result = db.execute(text(update_sql))
                rows_affected = result.rowcount
                db.commit()
                print(f"   ✅ Update {i}: Modified {rows_affected} plan(s)")
            except Exception as e:
                print(f"   ❌ Update {i} failed: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ Plan updates failed: {e}")
        db.rollback()
        return False
    finally:
        db.close()

def create_new_plans():
    """Create new pricing plans and ensure all plans exist"""
    print("🆕 Creating/updating all pricing plans...")
    
    db = next(get_db())
    
    try:
        pricing_service = PricingService(db)
        
        # Use the updated service to create default plans
        pricing_service.create_default_plans()
        
        # Update display order and flags
        updates = [
            "UPDATE pricing_plans SET display_order = 0 WHERE plan_type = 'free'",
            "UPDATE pricing_plans SET display_order = 1 WHERE plan_type = 'basic'", 
            "UPDATE pricing_plans SET display_order = 2, is_popular = 1 WHERE plan_type = 'growth'",
            "UPDATE pricing_plans SET display_order = 3 WHERE plan_type = 'agency'",
            "UPDATE pricing_plans SET display_order = 10, is_addon = 1 WHERE plan_type = 'livechat_addon'",
        ]
        
        for update in updates:
            try:
                db.execute(text(update))
                db.commit()
            except Exception as e:
                print(f"   ⚠️ Update issue: {e}")
        
        print("✅ All plans created/updated successfully")
        return True
        
    except Exception as e:
        print(f"❌ Creating plans failed: {e}")
        db.rollback()
        return False
    finally:
        db.close()

def verify_migration():
    """Verify migration success"""
    print("\n🔍 Verifying migration...")
    
    try:
        db = next(get_db())
        
        # Check all tables exist
        result = db.execute(text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"))
        tables = [row[0] for row in result.fetchall()]
        
        required_tables = ['pricing_plans', 'tenant_subscriptions', 'usage_logs', 'billing_history', 'conversation_sessions']
        missing_tables = [t for t in required_tables if t not in tables]
        
        if missing_tables:
            print(f"❌ Missing tables: {missing_tables}")
            return False
        else:
            print(f"✅ All required tables exist: {required_tables}")
        
        # Check updated plans
        plans = db.query(PricingPlan).filter(PricingPlan.is_active == True).order_by(PricingPlan.display_order).all()
        print(f"\n📋 Current Pricing Plans ({len(plans)} total):")
        
        for plan in plans:
            addon_text = " (Add-on)" if getattr(plan, 'is_addon', False) else ""
            popular_text = " ⭐" if getattr(plan, 'is_popular', False) else ""
            print(f"   - {plan.name}{addon_text}{popular_text}: ${plan.price_monthly}/month")
            print(f"     Conversations: {plan.max_messages_monthly}, Integrations: {'Unlimited' if plan.max_integrations == -1 else plan.max_integrations}")
        
        db.close()
        print("\n✅ Migration verification successful!")
        return True
        
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return False

def run_migration():
    """Run the complete migration process"""
    print("💬 Conversation-Based Pricing Migration")
    print("=" * 50)
    
    # Display current working directory info
    print(f"📂 Working directory: {os.getcwd()}")
    print(f"📁 Contents: {os.listdir('.')}")
    
    # Check if we have the necessary files
    if not os.path.exists("app"):
        print("❌ Error: 'app' directory not found in current directory")
        print("Please run this script from your project root directory")
        sys.exit(1)
    
    # Get user confirmation
    print("\n⚠️ This migration will update your pricing structure to conversation-based billing:")
    print("   - Add new database columns and conversation tracking")
    print("   - Update existing pricing plans")
    print("   - Create backup of current database")
    
    confirm = input("\nProceed with migration? (yes/no): ").lower().strip()
    if confirm != 'yes':
        print("Migration cancelled")
        sys.exit(0)
    
    # Step 1: Backup
    print("\n📥 Step 1: Creating database backup...")
    backup_path = backup_database()
    
    # Step 2: Check current state
    print("\n🔍 Step 2: Checking current database state...")
    existing_tables = check_current_schema()
    
    # Step 3: Create missing tables
    print("\n🏗️ Step 3: Creating missing pricing tables...")
    if not create_missing_tables():
        print("❌ Failed to create tables")
        sys.exit(1)
    
    # Step 4: Schema updates
    print("\n🔄 Step 4: Updating schema for conversation tracking...")
    if not run_schema_updates():
        print("❌ Schema updates failed")
        sys.exit(1)
    
    # Step 5: Update existing plans
    print("\n📊 Step 5: Updating existing pricing plans...")
    if not update_existing_plans():
        print("❌ Plan updates failed")
        sys.exit(1)
    
    # Step 6: Create new plans
    print("\n🆕 Step 6: Creating new pricing plans...")
    if not create_new_plans():
        print("❌ New plan creation failed")
        sys.exit(1)
    
    # Step 7: Verify
    if not verify_migration():
        print("❌ Migration verification failed")
        sys.exit(1)
    
    print("\n🎉 Migration completed successfully!")
    print(f"💾 Database backup saved at: {backup_path}")
    
    print("\n🎯 Next Steps:")
    print("1. Update your endpoints to use conversation tracking")
    print("2. Deploy the updated pricing code")
    print("3. Test the new conversation-based billing")
    print("4. Update your frontend to show conversations instead of messages")
    print("\n📖 Remember: A conversation = any interaction within 24 hours")

if __name__ == "__main__":
    run_migration()