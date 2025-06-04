#!/usr/bin/env python3
"""
Database Migration Script: Rename contact_email to email
Database: chatbot.db (SQLite)
"""

import sqlite3
import os
import sys
from datetime import datetime

# Database configuration
DATABASE_PATH = "chatbot.db"
BACKUP_PATH = f"chatbot_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"

def create_backup():
    """Create a backup of the database before migration"""
    print(f"📋 Creating backup: {BACKUP_PATH}")
    try:
        # Copy the database file
        import shutil
        shutil.copy2(DATABASE_PATH, BACKUP_PATH)
        print(f"✅ Backup created successfully: {BACKUP_PATH}")
        return True
    except Exception as e:
        print(f"❌ Backup failed: {e}")
        return False

def check_database_exists():
    """Check if the database exists"""
    if not os.path.exists(DATABASE_PATH):
        print(f"❌ Database not found: {DATABASE_PATH}")
        print("Please make sure you're running this script from the correct directory.")
        return False
    return True

def check_table_structure(cursor):
    """Check current table structure"""
    print("🔍 Checking current table structure...")
    
    try:
        # Get table info
        cursor.execute("PRAGMA table_info(tenants)")
        columns = cursor.fetchall()
        
        print("📊 Current tenants table columns:")
        for col in columns:
            print(f"  - {col[1]} ({col[2]}) {'NOT NULL' if col[3] else 'NULLABLE'}")
        
        # Check if contact_email exists
        contact_email_exists = any(col[1] == 'contact_email' for col in columns)
        email_exists = any(col[1] == 'email' for col in columns)
        
        return contact_email_exists, email_exists, columns
        
    except sqlite3.Error as e:
        print(f"❌ Error checking table structure: {e}")
        return False, False, []

def count_records_with_contact_email(cursor):
    """Count how many records have contact_email data"""
    try:
        cursor.execute("SELECT COUNT(*) FROM tenants WHERE contact_email IS NOT NULL")
        count = cursor.fetchone()[0]
        print(f"📊 Found {count} tenants with contact_email data")
        return count
    except sqlite3.Error as e:
        print(f"❌ Error counting records: {e}")
        return 0

def migrate_database():
    """Main migration function"""
    print("🚀 Starting database migration: contact_email → email")
    print("=" * 60)
    
    # Check if database exists
    if not check_database_exists():
        return False
    
    # Create backup
    if not create_backup():
        print("❌ Migration aborted - backup failed")
        return False
    
    try:
        # Connect to database
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Check current structure
        contact_email_exists, email_exists, columns = check_table_structure(cursor)
        
        if not contact_email_exists:
            print("⚠️ contact_email column not found. Nothing to migrate.")
            return True
        
        if email_exists:
            print("⚠️ email column already exists. Checking if migration is needed...")
            
            # Check if email column has data
            cursor.execute("SELECT COUNT(*) FROM tenants WHERE email IS NOT NULL")
            email_count = cursor.fetchone()[0]
            
            if email_count > 0:
                print(f"✅ Email column already has {email_count} records. Migration may already be done.")
                response = input("Do you want to continue anyway? (y/N): ")
                if response.lower() != 'y':
                    print("Migration cancelled.")
                    return True
        
        # Count records to migrate
        record_count = count_records_with_contact_email(cursor)
        
        if record_count == 0:
            print("⚠️ No records with contact_email found. Nothing to migrate.")
            return True
        
        print(f"\n🔄 Starting migration of {record_count} records...")
        
        # Step 1: Add email column if it doesn't exist
        if not email_exists:
            print("📝 Step 1: Adding email column...")
            cursor.execute("ALTER TABLE tenants ADD COLUMN email TEXT")
            print("✅ Email column added")
        else:
            print("📝 Step 1: Email column already exists, skipping...")
        
        # Step 2: Copy data from contact_email to email
        print("📝 Step 2: Copying data from contact_email to email...")
        cursor.execute("""
            UPDATE tenants 
            SET email = contact_email 
            WHERE contact_email IS NOT NULL 
            AND (email IS NULL OR email = '')
        """)
        updated_rows = cursor.rowcount
        print(f"✅ Copied {updated_rows} records from contact_email to email")
        
        # Step 3: Make email NOT NULL (only if all records have email now)
        print("📝 Step 3: Checking if we can make email NOT NULL...")
        cursor.execute("SELECT COUNT(*) FROM tenants WHERE email IS NULL OR email = ''")
        null_email_count = cursor.fetchone()[0]
        
        if null_email_count == 0:
            print("📝 Step 3a: All records have email. Making email NOT NULL...")
            # SQLite doesn't support ALTER COLUMN directly, so we need to recreate the table
            
            # Get current table schema
            cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='tenants'")
            create_sql = cursor.fetchone()[0]
            
            print("⚠️ Note: SQLite requires table recreation to add NOT NULL constraint.")
            print("This will happen in a future migration. For now, email column is added and populated.")
            
        else:
            print(f"⚠️ Step 3: {null_email_count} records still have NULL email. Skipping NOT NULL constraint.")
        
        # Step 4: Create index on email
        print("📝 Step 4: Creating index on email column...")
        try:
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tenants_email ON tenants (email)")
            print("✅ Index created on email column")
        except sqlite3.Error as e:
            print(f"⚠️ Index creation warning: {e}")
        
        # Commit changes
        conn.commit()
        
        # Verify migration
        print("\n🔍 Verifying migration...")
        cursor.execute("SELECT COUNT(*) FROM tenants WHERE email IS NOT NULL")
        final_count = cursor.fetchone()[0]
        print(f"✅ Final verification: {final_count} records now have email")
        
        # Show sample data
        print("\n📊 Sample migrated data:")
        cursor.execute("SELECT id, name, contact_email, email FROM tenants WHERE email IS NOT NULL LIMIT 5")
        samples = cursor.fetchall()
        for sample in samples:
            print(f"  ID: {sample[0]}, Name: {sample[1]}, contact_email: {sample[2]}, email: {sample[3]}")
        
        conn.close()
        
        print("\n" + "=" * 60)
        print("✅ Migration completed successfully!")
        print(f"📁 Backup available at: {BACKUP_PATH}")
        print("\n📋 Next steps:")
        print("1. Update your Tenant model to use 'email' instead of 'contact_email'")
        print("2. Update your router code to use 'email' field")
        print("3. Test your application thoroughly")
        print("4. Once confirmed working, you can drop the contact_email column")
        
        return True
        
    except sqlite3.Error as e:
        print(f"❌ Database error during migration: {e}")
        print("Rolling back...")
        conn.rollback()
        return False
    
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False
    
    finally:
        if 'conn' in locals():
            conn.close()

def rollback_migration():
    """Rollback function to restore from backup"""
    print("🔄 Rolling back migration...")
    
    # Find the latest backup
    import glob
    backups = glob.glob("chatbot_backup_*.db")
    if not backups:
        print("❌ No backup files found!")
        return False
    
    latest_backup = max(backups, key=os.path.getctime)
    print(f"📁 Found latest backup: {latest_backup}")
    
    response = input(f"Restore from {latest_backup}? (y/N): ")
    if response.lower() == 'y':
        try:
            import shutil
            shutil.copy2(latest_backup, DATABASE_PATH)
            print("✅ Database restored from backup")
            return True
        except Exception as e:
            print(f"❌ Restore failed: {e}")
            return False
    else:
        print("Rollback cancelled")
        return False

def main():
    """Main function"""
    print("🔧 Database Migration Tool")
    print("Contact Email → Email Migration")
    print("=" * 40)
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--rollback":
            rollback_migration()
            return
        elif sys.argv[1] == "--help":
            print("Usage:")
            print("  python migrate_email.py           # Run migration")
            print("  python migrate_email.py --rollback # Rollback to backup")
            print("  python migrate_email.py --help     # Show this help")
            return
    
    print(f"Database: {DATABASE_PATH}")
    print(f"Current directory: {os.getcwd()}")
    
    # Confirm before proceeding
    response = input("\nProceed with migration? (y/N): ")
    if response.lower() != 'y':
        print("Migration cancelled.")
        return
    
    # Run migration
    success = migrate_database()
    
    if success:
        print("\n🎉 Migration completed successfully!")
    else:
        print("\n💥 Migration failed!")
        print("Your backup is safe. Check the errors above.")

if __name__ == "__main__":
    main()