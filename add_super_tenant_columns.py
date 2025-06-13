# add_super_tenant_columns.py
"""
Script to add super tenant columns to existing SQLite database
Run this to add the necessary columns to your tenants table
"""

import sqlite3
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def add_super_tenant_columns():
    """Add super tenant columns to the tenants table"""
    
    # Connect to the database
    db_path = "./chatbot.db"
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print(f"🔗 Connected to database: {db_path}")
        
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(tenants)")
        columns = [column[1] for column in cursor.fetchall()]
        
        print(f"📋 Current columns in tenants table: {columns}")
        
        # Add is_super_tenant column
        if 'is_super_tenant' not in columns:
            print("➕ Adding is_super_tenant column...")
            cursor.execute("""
                ALTER TABLE tenants 
                ADD COLUMN is_super_tenant BOOLEAN DEFAULT FALSE
            """)
            print("✅ Added is_super_tenant column")
        else:
            print("ℹ️ is_super_tenant column already exists")
        
        # Add can_impersonate column
        if 'can_impersonate' not in columns:
            print("➕ Adding can_impersonate column...")
            cursor.execute("""
                ALTER TABLE tenants 
                ADD COLUMN can_impersonate BOOLEAN DEFAULT FALSE
            """)
            print("✅ Added can_impersonate column")
        else:
            print("ℹ️ can_impersonate column already exists")
        
        # Add impersonating_tenant_id column
        if 'impersonating_tenant_id' not in columns:
            print("➕ Adding impersonating_tenant_id column...")
            cursor.execute("""
                ALTER TABLE tenants 
                ADD COLUMN impersonating_tenant_id INTEGER
            """)
            print("✅ Added impersonating_tenant_id column")
        else:
            print("ℹ️ impersonating_tenant_id column already exists")
        
        # Commit the changes
        conn.commit()
        
        # Verify the changes
        cursor.execute("PRAGMA table_info(tenants)")
        new_columns = [column[1] for column in cursor.fetchall()]
        
        print(f"\n📋 Updated columns in tenants table: {new_columns}")
        
        # Check if all required columns are present
        required_columns = ['is_super_tenant', 'can_impersonate', 'impersonating_tenant_id']
        missing_columns = [col for col in required_columns if col not in new_columns]
        
        if not missing_columns:
            print("\n✅ All super tenant columns added successfully!")
            print("🎉 Your database is ready for super tenant functionality")
        else:
            print(f"\n❌ Missing columns: {missing_columns}")
            return False
        
        return True
        
    except sqlite3.Error as e:
        print(f"❌ SQLite error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False
    finally:
        if conn:
            conn.close()
            print("🔒 Database connection closed")

def create_first_super_tenant():
    """Create your first super tenant from existing tenant"""
    
    db_path = "./chatbot.db"
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("\n🔍 Looking for existing tenants...")
        
        # Get all existing tenants
        cursor.execute("""
            SELECT id, name, business_name, email, is_super_tenant 
            FROM tenants 
            WHERE is_active = 1
        """)
        tenants = cursor.fetchall()
        
        if not tenants:
            print("❌ No tenants found in database")
            return False
        
        print(f"\n📋 Found {len(tenants)} tenant(s):")
        for i, (tenant_id, name, business_name, email, is_super) in enumerate(tenants, 1):
            status = "🔓 SUPER" if is_super else "👤 Regular"
            print(f"   {i}. {name} ({business_name}) - {email} - {status}")
        
        # Ask user to select which tenant to make super
        try:
            choice = int(input(f"\nSelect tenant to make super tenant (1-{len(tenants)}): ")) - 1
            if choice < 0 or choice >= len(tenants):
                print("❌ Invalid choice!")
                return False
        except ValueError:
            print("❌ Invalid input!")
            return False
        
        selected_tenant = tenants[choice]
        tenant_id, name, business_name, email, is_super = selected_tenant
        
        if is_super:
            print(f"⚠️ {name} is already a super tenant!")
            return True
        
        # Confirm the choice
        confirm = input(f"\n⚠️ Make {name} ({business_name}) a super tenant? (y/N): ")
        if confirm.lower() != 'y':
            print("❌ Cancelled")
            return False
        
        print(f"\n🔄 Converting {name} to super tenant...")
        
        # Update the tenant to super tenant
        cursor.execute("""
            UPDATE tenants 
            SET is_super_tenant = 1, can_impersonate = 1 
            WHERE id = ?
        """, (tenant_id,))
        
        conn.commit()
        
        # Verify the update
        cursor.execute("SELECT name, is_super_tenant, can_impersonate FROM tenants WHERE id = ?", (tenant_id,))
        result = cursor.fetchone()
        
        if result and result[1] and result[2]:  # is_super_tenant and can_impersonate
            print(f"✅ Successfully converted {result[0]} to super tenant!")
            print(f"🔓 Super tenant privileges:")
            print(f"   ✅ Unlimited conversations")
            print(f"   ✅ Unlimited integrations") 
            print(f"   ✅ Can impersonate other tenants")
            print(f"   ✅ Bypasses all payment restrictions")
            
            # Get the API key for easy reference
            cursor.execute("SELECT api_key FROM tenants WHERE id = ?", (tenant_id,))
            api_key = cursor.fetchone()[0]
            print(f"\n🔐 API Key: {api_key}")
            print("💡 Use this API key to access unlimited features!")
            
            return True
        else:
            print("❌ Failed to update tenant")
            return False
        
    except sqlite3.Error as e:
        print(f"❌ SQLite error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False
    finally:
        if conn:
            conn.close()

def list_super_tenants():
    """List all current super tenants"""
    
    db_path = "./chatbot.db"
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("\n🔍 Looking for super tenants...")
        
        cursor.execute("""
            SELECT id, name, business_name, email, api_key, created_at, can_impersonate
            FROM tenants 
            WHERE is_super_tenant = 1 AND is_active = 1
        """)
        super_tenants = cursor.fetchall()
        
        if not super_tenants:
            print("📋 No super tenants found")
            return
        
        print(f"\n🔓 Found {len(super_tenants)} super tenant(s):")
        print("=" * 80)
        
        for tenant_id, name, business_name, email, api_key, created_at, can_impersonate in super_tenants:
            print(f"🆔 ID: {tenant_id}")
            print(f"👤 Name: {name}")
            print(f"🏢 Business: {business_name}")
            print(f"📧 Email: {email}")
            print(f"🔐 API Key: {api_key}")
            print(f"🎭 Can Impersonate: {'Yes' if can_impersonate else 'No'}")
            print(f"📅 Created: {created_at}")
            print("-" * 80)
        
    except sqlite3.Error as e:
        print(f"❌ SQLite error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
    finally:
        if conn:
            conn.close()

def verify_database_structure():
    """Verify that the database has the correct structure"""
    
    db_path = "./chatbot.db"
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("🔍 Verifying database structure...")
        
        # Check tenants table structure
        cursor.execute("PRAGMA table_info(tenants)")
        columns = cursor.fetchall()
        
        print(f"\n📋 Tenants table structure:")
        for col_id, name, col_type, not_null, default_value, pk in columns:
            print(f"   {name}: {col_type} {'(NOT NULL)' if not_null else ''} {'(PK)' if pk else ''}")
        
        # Check for required super tenant columns
        column_names = [col[1] for col in columns]
        required_columns = ['is_super_tenant', 'can_impersonate', 'impersonating_tenant_id']
        
        print(f"\n✅ Super tenant columns status:")
        for col in required_columns:
            status = "✅ Present" if col in column_names else "❌ Missing"
            print(f"   {col}: {status}")
        
        # Count tenants
        cursor.execute("SELECT COUNT(*) FROM tenants WHERE is_active = 1")
        total_tenants = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM tenants WHERE is_super_tenant = 1 AND is_active = 1")
        super_tenants = cursor.fetchone()[0]
        
        print(f"\n📊 Tenant statistics:")
        print(f"   Total active tenants: {total_tenants}")
        print(f"   Super tenants: {super_tenants}")
        print(f"   Regular tenants: {total_tenants - super_tenants}")
        
    except sqlite3.Error as e:
        print(f"❌ SQLite error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    import sys
    
    print("🔓 SUPER TENANT DATABASE SETUP")
    print("=" * 50)
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "add-columns":
            add_super_tenant_columns()
        elif command == "create-super":
            create_first_super_tenant()
        elif command == "list":
            list_super_tenants()
        elif command == "verify":
            verify_database_structure()
        else:
            print(f"❌ Unknown command: {command}")
            print("Available commands: add-columns, create-super, list, verify")
    else:
        print("Available commands:")
        print("  python add_super_tenant_columns.py add-columns  - Add super tenant columns")
        print("  python add_super_tenant_columns.py create-super - Create first super tenant")
        print("  python add_super_tenant_columns.py list         - List all super tenants")
        print("  python add_super_tenant_columns.py verify       - Verify database structure")
        print()
        
        # Interactive mode
        command = input("Select operation (add-columns/create-super/list/verify): ").lower().strip()
        
        if command == "add-columns":
            success = add_super_tenant_columns()
            if success:
                create_super = input("\nWould you like to create your first super tenant now? (y/N): ")
                if create_super.lower() == 'y':
                    create_first_super_tenant()
        elif command == "create-super":
            create_first_super_tenant()
        elif command == "list":
            list_super_tenants()
        elif command == "verify":
            verify_database_structure()
        else:
            print("❌ Invalid command!")