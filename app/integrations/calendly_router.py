"""
Simple migration script for conversation-based pricing
This version avoids complex imports and focuses on database changes only
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# Fix the Python path
current_dir = Path(__file__).parent
project_root = current_dir.parent if current_dir.name == 'migrations' else current_dir

if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

os.chdir(project_root)

# Simple imports only
try:
    from sqlalchemy import create_engine, text
    from app.database import get_db, engine
    print("✅ Basic imports successful")
except ImportError as e:
    print(f"❌ Import error: {e}")
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

def check_table_exists(db, table_name):
    """Check if a table exists"""
    try:
        result = db.execute(text(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'"))
        return result.fetchone() is not None
    except:
        return False

def check_column_exists(db, table_name, column_name):
    """Check if a column exists in a table"""
    try:
        result = db.execute(text(f"PRAGMA table_info({table_name})"))
        columns = [row[1] for row in result.fetchall()]
        return column_name in columns
    except:
        return False

def run_safe_sql(db, sql, description):
    """Run SQL with error handling"""
    try:
        db.execute(text(sql))
        db.commit()
        print(f"   ✅ {description}")
        return True
    except Exception as e:
        if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
            print(f"   ℹ️ {description} (already exists)")
            return True
        else:
            print(f"   ❌ {description}: {e}")
            return False

def create_pricing_tables():
    """Create basic pricing tables if they don't exist"""
    print("🏗️ Creating pricing tables...")
    
    db = next(get_db())
    
    try:
        # Create pricing_plans table
        pricing_plans_sql = """
        CREATE TABLE IF NOT EXISTS pricing_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(255) UNIQUE NOT NULL,
            plan_type VARCHAR(255) NOT NULL,
            price_monthly DECIMAL(10,2) DEFAULT 0.00,
            price_yearly DECIMAL(10,2) DEFAULT 0.00,
            max_integrations INTEGER DEFAULT 1,
            max_messages_monthly INTEGER DEFAULT 100,
            custom_prompt_allowed BOOLEAN DEFAULT FALSE,
            website_api_allowed BOOLEAN DEFAULT TRUE,
            slack_allowed BOOLEAN DEFAULT FALSE,
            discord_allowed BOOLEAN DEFAULT FALSE,
            whatsapp_allowed BOOLEAN DEFAULT FALSE,
            features TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        run_safe_sql(db, pricing_plans_sql, "pricing_plans table")
        
        # Create tenant_subscriptions table
        subscriptions_sql = """
        CREATE TABLE IF NOT EXISTS tenant_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            plan_id INTEGER NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            billing_cycle VARCHAR(255) DEFAULT 'monthly',
            current_period_start TIMESTAMP NOT NULL,
            current_period_end TIMESTAMP NOT NULL,
            messages_used_current_period INTEGER DEFAULT 0,
            integrations_count INTEGER DEFAULT 0,
            stripe_subscription_id VARCHAR(255),
            status VARCHAR(255) DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id),
            FOREIGN KEY (plan_id) REFERENCES pricing_plans(id)
        )
        """
        run_safe_sql(db, subscriptions_sql, "tenant_subscriptions table")
        
        # Create usage_logs table
        usage_logs_sql = """
        CREATE TABLE IF NOT EXISTS usage_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscription_id INTEGER NOT NULL,
            tenant_id INTEGER NOT NULL,
            usage_type VARCHAR(255) NOT NULL,
            count INTEGER DEFAULT 1,
            integration_type VARCHAR(255),
            extra_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (subscription_id) REFERENCES tenant_subscriptions(id),
            FOREIGN KEY (tenant_id) REFERENCES tenants(id)
        )
        """
        run_safe_sql(db, usage_logs_sql, "usage_logs table")
        
        # Create billing_history table
        billing_history_sql = """
        CREATE TABLE IF NOT EXISTS billing_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            subscription_id INTEGER NOT NULL,
            amount DECIMAL(10,2) NOT NULL,
            currency VARCHAR(255) DEFAULT 'USD',
            billing_period_start TIMESTAMP NOT NULL,
            billing_period_end TIMESTAMP NOT NULL,
            stripe_invoice_id VARCHAR(255),
            payment_status VARCHAR(255) DEFAULT 'pending',
            payment_date TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id),
            FOREIGN KEY (subscription_id) REFERENCES tenant_subscriptions(id)
        )
        """
        run_safe_sql(db, billing_history_sql, "billing_history table")
        
        return True
        
    except Exception as e:
        print(f"❌ Error creating pricing tables: {e}")
        db.rollback()
        return False
    finally:
        db.close()

def add_new_columns():
    """Add new columns for conversation-based pricing"""
    print("📊 Adding new columns for conversation-based pricing...")
    
    db = next(get_db())
    
    try:
        # Add columns to pricing_plans
        new_columns = [
            ("pricing_plans", "is_addon", "ALTER TABLE pricing_plans ADD COLUMN is_addon BOOLEAN DEFAULT FALSE"),
            ("pricing_plans", "is_popular", "ALTER TABLE pricing_plans ADD COLUMN is_popular BOOLEAN DEFAULT FALSE"),
            ("pricing_plans", "display_order", "ALTER TABLE pricing_plans ADD COLUMN display_order INTEGER DEFAULT 0"),
            
            # Add columns to tenant_subscriptions
            ("tenant_subscriptions", "active_addons", "ALTER TABLE tenant_subscriptions ADD COLUMN active_addons TEXT"),
            ("tenant_subscriptions", "stripe_customer_id", "ALTER TABLE tenant_subscriptions ADD COLUMN stripe_customer_id TEXT"),
            
            # Add columns to usage_logs
            ("usage_logs", "session_id", "ALTER TABLE usage_logs ADD COLUMN session_id TEXT"),
            ("usage_logs", "user_identifier", "ALTER TABLE usage_logs ADD COLUMN user_identifier TEXT"),
            ("usage_logs", "platform", "ALTER TABLE usage_logs ADD COLUMN platform TEXT"),
            
            # Add columns to billing_history
            ("billing_history", "plan_name", "ALTER TABLE billing_history ADD COLUMN plan_name TEXT"),
            ("billing_history", "conversations_included", "ALTER TABLE billing_history ADD COLUMN conversations_included INTEGER"),
            ("billing_history", "conversations_used", "ALTER TABLE billing_history ADD COLUMN conversations_used INTEGER"),
            ("billing_history", "addons_included", "ALTER TABLE billing_history ADD COLUMN addons_included TEXT"),
            ("billing_history", "stripe_charge_id", "ALTER TABLE billing_history ADD COLUMN stripe_charge_id TEXT"),
            ("billing_history", "payment_method", "ALTER TABLE billing_history ADD COLUMN payment_method TEXT"),
        ]
        
        for table_name, column_name, sql in new_columns:
            if check_table_exists(db, table_name):
                if not check_column_exists(db, table_name, column_name):
                    run_safe_sql(db, sql, f"Added {column_name} to {table_name}")
                else:
                    print(f"   ℹ️ Column {column_name} already exists in {table_name}")
            else:
                print(f"   ⚠️ Table {table_name} doesn't exist, skipping column {column_name}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error adding columns: {e}")
        db.rollback()
        return False
    finally:
        db.close()

def create_conversation_sessions_table():
    """Create conversation sessions table for 24-hour tracking"""
    print("💬 Creating conversation_sessions table...")
    
    db = next(get_db())
    
    try:
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
        
        run_safe_sql(db, conversation_table_sql, "conversation_sessions table")
        
        # Create indexes
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_conversation_sessions_tenant_user ON conversation_sessions(tenant_id, user_identifier)",
            "CREATE INDEX IF NOT EXISTS idx_conversation_sessions_activity ON conversation_sessions(last_activity)",
            "CREATE INDEX IF NOT EXISTS idx_conversation_sessions_billing ON conversation_sessions(tenant_id, counted_for_billing)",
        ]
        
        for index_sql in indexes:
            run_safe_sql(db, index_sql, "Index created")
        
        return True
        
    except Exception as e:
        print(f"❌ Error creating conversation_sessions table: {e}")
        db.rollback()
        return False
    finally:
        db.close()

def insert_default_plans():
    """Insert or update default pricing plans"""
    print("📋 Creating default pricing plans...")
    
    db = next(get_db())
    
    try:
        # Define the new pricing plans
        plans = [
            {
                'name': 'Free',
                'plan_type': 'free',
                'price_monthly': 0.00,
                'price_yearly': 0.00,
                'max_integrations': -1,
                'max_messages_monthly': 50,
                'custom_prompt_allowed': 1,
                'website_api_allowed': 1,
                'slack_allowed': 1,
                'discord_allowed': 1,
                'whatsapp_allowed': 0,
                'features': '["Custom Prompt", "Slack Integration", "Discord Integration", "Web Integration", "Bot Memory"]',
                'is_popular': 0,
                'display_order': 0
            },
            {
                'name': 'Basic',
                'plan_type': 'basic',
                'price_monthly': 19.00,
                'price_yearly': 190.00,
                'max_integrations': -1,
                'max_messages_monthly': 500,
                'custom_prompt_allowed': 1,
                'website_api_allowed': 1,
                'slack_allowed': 1,
                'discord_allowed': 1,
                'whatsapp_allowed': 0,
                'features': '["Custom Prompt", "Slack Integration", "Discord Integration", "Web Integration", "Advanced Analytics", "Bot Memory"]',
                'is_popular': 0,
                'display_order': 1
            },
            {
                'name': 'Growth',
                'plan_type': 'growth',
                'price_monthly': 39.00,
                'price_yearly': 390.00,
                'max_integrations': -1,
                'max_messages_monthly': 5000,
                'custom_prompt_allowed': 1,
                'website_api_allowed': 1,
                'slack_allowed': 1,
                'discord_allowed': 1,
                'whatsapp_allowed': 0,
                'features': '["Custom Prompt", "Slack Integration", "Discord Integration", "Web Integration", "Advanced Analytics", "Priority Support", "Bot Memory"]',
                'is_popular': 1,
                'display_order': 2
            },
            {
                'name': 'Agency',
                'plan_type': 'agency',
                'price_monthly': 99.00,
                'price_yearly': 990.00,
                'max_integrations': -1,
                'max_messages_monthly': 50000,
                'custom_prompt_allowed': 1,
                'website_api_allowed': 1,
                'slack_allowed': 1,
                'discord_allowed': 1,
                'whatsapp_allowed': 1,
                'features': '["Custom Prompt", "Slack Integration", "Discord Integration", "Web Integration", "Advanced Analytics", "Priority Support", "Live Chat Integration", "Bot Memory", "WhatsApp Integration"]',
                'is_popular': 0,
                'display_order': 3
            },
            {
                'name': 'Live Chat Add-on',
                'plan_type': 'livechat_addon',
                'price_monthly': 30.00,
                'price_yearly': 300.00,
                'max_integrations': -1,
                'max_messages_monthly': 5000,
                'custom_prompt_allowed': 1,
                'website_api_allowed': 1,
                'slack_allowed': 1,
                'discord_allowed': 1,
                'whatsapp_allowed': 1,
                'features': '["Live Chat Integration", "5000 conversations"]',
                'is_addon': 1,
                'is_popular': 0,
                'display_order': 10
            }
        ]
        
        for plan in plans:
            # Check if plan exists
            check_sql = f"SELECT id FROM pricing_plans WHERE plan_type = '{plan['plan_type']}'"
            result = db.execute(text(check_sql)).fetchone()
            
            if result:
                # Update existing plan
                plan_id = result[0]
                update_fields = []
                for key, value in plan.items():
                    if key != 'plan_type':
                        if isinstance(value, str):
                            update_fields.append(f"{key} = '{value}'")
                        else:
                            update_fields.append(f"{key} = {value}")
                
                update_sql = f"UPDATE pricing_plans SET {', '.join(update_fields)} WHERE id = {plan_id}"
                run_safe_sql(db, update_sql, f"Updated {plan['name']} plan")
            else:
                # Insert new plan
                columns = list(plan.keys())
                values = []
                for value in plan.values():
                    if isinstance(value, str):
                        values.append(f"'{value}'")
                    else:
                        values.append(str(value))
                
                insert_sql = f"INSERT INTO pricing_plans ({', '.join(columns)}) VALUES ({', '.join(values)})"
                run_safe_sql(db, insert_sql, f"Created {plan['name']} plan")
        
        return True
        
    except Exception as e:
        print(f"❌ Error creating plans: {e}")
        db.rollback()
        return False
    finally:
        db.close()

def create_free_subscriptions():
    """Create free subscriptions for existing tenants"""
    print("🔗 Creating free subscriptions for existing tenants...")
    
    db = next(get_db())
    
    try:
        # Get free plan ID
        free_plan = db.execute(text("SELECT id FROM pricing_plans WHERE plan_type = 'free'")).fetchone()
        if not free_plan:
            print("   ❌ Free plan not found")
            return False
        
        free_plan_id = free_plan[0]
        
        # Get tenants without subscriptions
        tenants_without_subs = db.execute(text("""
            SELECT t.id, t.name FROM tenants t 
            LEFT JOIN tenant_subscriptions ts ON t.id = ts.tenant_id AND ts.is_active = 1
            WHERE ts.id IS NULL AND t.is_active = 1
        """)).fetchall()
        
        print(f"   Found {len(tenants_without_subs)} tenants without subscriptions")
        
        from datetime import datetime, timedelta
        current_time = datetime.now()
        period_end = current_time + timedelta(days=30)
        
        for tenant_id, tenant_name in tenants_without_subs:
            insert_sql = f"""
            INSERT INTO tenant_subscriptions 
            (tenant_id, plan_id, is_active, billing_cycle, current_period_start, current_period_end, status)
            VALUES ({tenant_id}, {free_plan_id}, 1, 'monthly', '{current_time}', '{period_end}', 'active')
            """
            run_safe_sql(db, insert_sql, f"Created subscription for {tenant_name}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error creating subscriptions: {e}")
        db.rollback()
        return False
    finally:
        db.close()

def verify_migration():
    """Verify the migration worked"""
    print("\n🔍 Verifying migration...")
    
    db = next(get_db())
    
    try:
        # Check tables exist
        tables = ['pricing_plans', 'tenant_subscriptions', 'usage_logs', 'billing_history', 'conversation_sessions']
        for table in tables:
            if check_table_exists(db, table):
                count = db.execute(text(f"SELECT COUNT(*) FROM {table}")).fetchone()[0]
                print(f"   ✅ {table}: {count} records")
            else:
                print(f"   ❌ {table}: Missing")
        
        # Show pricing plans
        plans = db.execute(text("SELECT name, plan_type, price_monthly, max_messages_monthly FROM pricing_plans ORDER BY display_order")).fetchall()
        print(f"\n📋 Pricing Plans ({len(plans)} total):")
        for name, plan_type, price, conversations in plans:
            print(f"   - {name} ({plan_type}): ${price}/month - {conversations} conversations")
        
        # Show subscriptions
        subs = db.execute(text("SELECT COUNT(*) FROM tenant_subscriptions WHERE is_active = 1")).fetchone()[0]
        print(f"\n🔗 Active Subscriptions: {subs}")
        
        return True
        
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return False
    finally:
        db.close()

def main():
    """Main migration function"""
    print("💬 Simple Conversation-Based Pricing Migration")
    print("=" * 50)
    
    if not os.path.exists("app"):
        print("❌ Error: Run this from the project root directory")
        sys.exit(1)
    
    print("\n⚠️ This will update your pricing to conversation-based billing:")
    print("   - Free: 50 conversations (now includes Slack, Discord, Custom Prompts)")
    print("   - Basic: $19/month, 500 conversations + Analytics")
    print("   - Growth: $39/month, 5,000 conversations + Priority Support")
    print("   - Agency: $99/month, 50,000 conversations + Live Chat + WhatsApp")
    
    confirm = input("\nProceed? (yes/no): ").lower().strip()
    if confirm != 'yes':
        print("Migration cancelled")
        sys.exit(0)
    
    print("\n📥 Step 1: Creating backup...")
    backup_path = backup_database()
    
    print("\n🏗️ Step 2: Creating pricing tables...")
    if not create_pricing_tables():
        sys.exit(1)
    
    print("\n📊 Step 3: Adding new columns...")
    if not add_new_columns():
        sys.exit(1)
    
    print("\n💬 Step 4: Creating conversation tracking table...")
    if not create_conversation_sessions_table():
        sys.exit(1)
    
    print("\n📋 Step 5: Setting up pricing plans...")
    if not insert_default_plans():
        sys.exit(1)
    
    print("\n🔗 Step 6: Creating tenant subscriptions...")
    if not create_free_subscriptions():
        sys.exit(1)
    
    if not verify_migration():
        sys.exit(1)
    
    print("\n🎉 Migration completed successfully!")
    if backup_path:
        print(f"💾 Backup saved: {backup_path}")
    
    print("\n🎯 Next Steps:")
    print("1. Update your pricing service code")
    print("2. Update chatbot endpoints to track conversations")
    print("3. Test the new pricing system")
    print("4. Update frontend to show conversations instead of messages")

if __name__ == "__main__":
    main()