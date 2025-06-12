#!/usr/bin/env python3
"""
Script to fix the migration error by marking the problematic migration as applied
"""

import os
import sys
import subprocess
import sqlite3

def check_tenant_table_structure():
    """Check the current structure of the tenants table"""
    try:
        conn = sqlite3.connect('./chatbot.db')
        cursor = conn.cursor()
        
        # Get table info
        cursor.execute("PRAGMA table_info(tenants)")
        columns = cursor.fetchall()
        
        print("📋 Current tenants table structure:")
        for col in columns:
            col_id, name, col_type, not_null, default, pk = col
            print(f"   - {name}: {col_type}")
        
        # Check if hashed_password column exists
        column_names = [col[1] for col in columns]
        has_hashed_password = 'hashed_password' in column_names
        
        conn.close()
        
        print(f"\n🔍 Does 'hashed_password' column exist? {'✅ Yes' if has_hashed_password else '❌ No'}")
        return has_hashed_password
        
    except Exception as e:
        print(f"❌ Error checking table structure: {e}")
        return None

def show_migration_content():
    """Show what the problematic migration is trying to do"""
    migration_file = None
    
    # Find the migration file
    versions_dir = "alembic/versions"
    if os.path.exists(versions_dir):
        for filename in os.listdir(versions_dir):
            if "8fddcbda175a" in filename:
                migration_file = os.path.join(versions_dir, filename)
                break
    
    if migration_file and os.path.exists(migration_file):
        print(f"\n📄 Migration file: {migration_file}")
        try:
            with open(migration_file, 'r') as f:
                content = f.read()
                
            # Show the upgrade function
            lines = content.split('\n')
            in_upgrade = False
            print("\n📝 Migration content:")
            for line in lines:
                if 'def upgrade():' in line:
                    in_upgrade = True
                elif 'def downgrade():' in line:
                    in_upgrade = False
                
                if in_upgrade:
                    print(f"   {line}")
                    
        except Exception as e:
            print(f"❌ Error reading migration file: {e}")
    else:
        print("❌ Could not find migration file")

def fix_migration_options():
    """Present options to fix the migration"""
    print("\n🔧 Options to fix this migration:")
    print("1. Mark migration as applied (if column was already removed)")
    print("2. Skip this migration and continue")
    print("3. Manually edit the migration file")
    print("4. Rollback to previous migration")
    
    while True:
        choice = input("\nChoose an option (1-4): ").strip()
        
        if choice == "1":
            return mark_migration_as_applied()
        elif choice == "2":
            return skip_migration()
        elif choice == "3":
            return show_manual_edit_instructions()
        elif choice == "4":
            return rollback_migration()
        else:
            print("❌ Invalid choice. Please enter 1, 2, 3, or 4.")

def mark_migration_as_applied():
    """Mark the problematic migration as already applied"""
    try:
        print("🏷️  Marking migration as applied...")
        
        # This tells Alembic that the migration was already applied
        result = subprocess.run(['alembic', 'stamp', '8fddcbda175a'], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Migration marked as applied!")
            print("📝 You can now proceed with creating new migrations")
            return True
        else:
            print("❌ Failed to mark migration as applied:")
            print(result.stderr)
            return False
            
    except Exception as e:
        print(f"❌ Error marking migration as applied: {e}")
        return False

def skip_migration():
    """Skip to the next migration"""
    print("⏭️  To skip this migration:")
    print("1. You can manually mark it as applied using: alembic stamp 8fddcbda175a")
    print("2. Or edit the migration file to remove the problematic operation")
    return False

def rollback_migration():
    """Rollback to previous migration"""
    try:
        print("⏪ Rolling back to previous migration...")
        
        result = subprocess.run(['alembic', 'downgrade', 'beb55976f2a4'], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Rolled back successfully!")
            print("📝 You're now on the previous migration")
            return True
        else:
            print("❌ Failed to rollback:")
            print(result.stderr)
            return False
            
    except Exception as e:
        print(f"❌ Error rolling back: {e}")
        return False

def show_manual_edit_instructions():
    """Show instructions for manually editing the migration"""
    print("\n📝 Manual Edit Instructions:")
    print("=" * 40)
    
    # Find the migration file
    versions_dir = "alembic/versions"
    migration_file = None
    
    if os.path.exists(versions_dir):
        for filename in os.listdir(versions_dir):
            if "8fddcbda175a" in filename:
                migration_file = os.path.join(versions_dir, filename)
                break
    
    if migration_file:
        print(f"1. Open file: {migration_file}")
        print("2. Find the upgrade() function")
        print("3. Comment out or remove this line:")
        print("   # op.drop_column('tenants', 'hashed_password')")
        print("4. Save the file")
        print("5. Run: alembic upgrade head")
    else:
        print("❌ Could not find migration file to edit")
    
    return False

def create_quick_fix_script():
    """Create a script to quickly fix the migration file"""
    script_content = '''#!/usr/bin/env python3
"""
Quick fix script to comment out the problematic line in the migration
"""

import os
import glob

def fix_migration_file():
    # Find the migration file
    pattern = "alembic/versions/*8fddcbda175a*"
    files = glob.glob(pattern)
    
    if not files:
        print("❌ Migration file not found")
        return False
    
    migration_file = files[0]
    print(f"📝 Fixing migration file: {migration_file}")
    
    try:
        with open(migration_file, 'r') as f:
            content = f.read()
        
        # Comment out the problematic line
        fixed_content = content.replace(
            "op.drop_column('tenants', 'hashed_password')",
            "# op.drop_column('tenants', 'hashed_password')  # Column doesn't exist, skipping"
        )
        
        with open(migration_file, 'w') as f:
            f.write(fixed_content)
        
        print("✅ Migration file fixed!")
        print("📝 You can now run: alembic upgrade head")
        return True
        
    except Exception as e:
        print(f"❌ Error fixing migration file: {e}")
        return False

if __name__ == "__main__":
    fix_migration_file()
'''
    
    with open('quick_fix_migration.py', 'w') as f:
        f.write(script_content)
    
    print("✅ Created quick_fix_migration.py")
    print("📝 Run: python quick_fix_migration.py")
    print("   Then: alembic upgrade head")

def main():
    """Main function"""
    print("🔧 Fixing Alembic Migration Error")
    print("=" * 40)
    
    print("❌ The migration failed because it's trying to drop a column that doesn't exist.")
    print("📋 Let's check your database structure first...")
    
    # Check table structure
    has_hashed_password = check_tenant_table_structure()
    
    # Show migration content
    show_migration_content()
    
    if has_hashed_password is False:
        print("\n💡 The 'hashed_password' column doesn't exist in your database.")
        print("   This means the migration is unnecessary for your current schema.")
        
        # Present fix options
        if fix_migration_options():
            print("\n🎉 Migration issue resolved!")
            print("📝 You can now proceed with creating the live chat migration.")
        else:
            print("\n📝 Manual fix required. See instructions above.")
            create_quick_fix_script()
    
    elif has_hashed_password is True:
        print("\n⚠️  The 'hashed_password' column exists but the migration is still failing.")
        print("   This might be a SQLite limitation with ALTER TABLE operations.")
        create_quick_fix_script()
    
    else:
        print("\n❌ Could not determine table structure.")
        create_quick_fix_script()

if __name__ == "__main__":
    main()
