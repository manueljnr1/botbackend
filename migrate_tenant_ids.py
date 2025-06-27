"""
Simple Tenant ID Migration Runner
Ready-to-use script for your specific database connections
"""

import os
import sys
import logging
from pathlib import Path

# Add your app to Python path
sys.path.append(str(Path(__file__).parent))

# Import the migration class
from migrations.secure_tenant_id_migration import SecureTenantIDMigration

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Your database URLs
POSTGRESQL_URL = "postgresql://chatbot_hhjv_user:dYXguSEwpwZl3Yt2R3ACsfvmM5lLIgSD@dpg-d10sp295pdvs73afujf0-a.oregon-postgres.render.com/chatbot_hhjv"
SQLITE_URL = "sqlite:///./chatbot.db"


def migrate_postgresql(dry_run=True):
    """Migrate PostgreSQL database"""
    logger.info("🐘 POSTGRESQL MIGRATION")
    logger.info("=" * 50)
    
    migration = SecureTenantIDMigration(POSTGRESQL_URL)
    return migration.run_migration(dry_run=dry_run)


def migrate_sqlite(dry_run=True):
    """Migrate SQLite database"""
    logger.info("🗃️ SQLITE MIGRATION")
    logger.info("=" * 50)
    
    migration = SecureTenantIDMigration(SQLITE_URL)
    return migration.run_migration(dry_run=dry_run)


def main():
    """Interactive migration runner"""
    print("🔐 Secure Tenant ID Migration Tool")
    print("=" * 40)
    print()
    
    # Ask which database
    print("Which database would you like to migrate?")
    print("1. PostgreSQL (Production)")
    print("2. SQLite (Local)")
    print("3. Both")
    print()
    
    while True:
        choice = input("Enter choice (1-3): ").strip()
        if choice in ['1', '2', '3']:
            break
        print("Invalid choice. Please enter 1, 2, or 3.")
    
    # Ask about dry run
    print()
    print("Migration mode:")
    print("1. Dry Run (Preview only - SAFE)")
    print("2. Execute Migration (WILL MODIFY DATABASE)")
    print()
    
    while True:
        mode_choice = input("Enter mode (1-2): ").strip()
        if mode_choice in ['1', '2']:
            break
        print("Invalid choice. Please enter 1 or 2.")
    
    dry_run = mode_choice == '1'
    
    if not dry_run:
        print()
        print("⚠️ WARNING: You are about to modify the database!")
        print("⚠️ This will change tenant IDs and all foreign key references!")
        print("⚠️ Ensure you have a backup before proceeding!")
        print()
        confirm = input("Type 'CONFIRM' to proceed with actual migration: ").strip()
        
        if confirm != 'CONFIRM':
            print("Migration cancelled.")
            return
    
    print()
    print(f"Starting migration in {'DRY RUN' if dry_run else 'EXECUTION'} mode...")
    print()
    
    success = True
    
    try:
        if choice in ['1', '3']:  # PostgreSQL
            success = migrate_postgresql(dry_run=dry_run)
            if not success:
                print("❌ PostgreSQL migration failed!")
                return
        
        if choice in ['2', '3']:  # SQLite
            if choice == '3':
                print()  # Add spacing between migrations
            success = migrate_sqlite(dry_run=dry_run)
            if not success:
                print("❌ SQLite migration failed!")
                return
        
        if success:
            print()
            print("🎉 MIGRATION COMPLETED SUCCESSFULLY!")
            if dry_run:
                print("💡 This was a dry run - no changes were made.")
                print("💡 Run again and choose 'Execute Migration' to apply changes.")
            else:
                print("✅ Database has been updated with secure tenant IDs.")
                print("🔍 Please test your application to ensure everything works correctly.")
    
    except KeyboardInterrupt:
        print("\n⚠️ Migration interrupted by user.")
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")


def quick_status_check():
    """Quick check of current tenant ID security status"""
    print("🔍 TENANT ID SECURITY STATUS")
    print("=" * 40)
    
    try:
        # Check PostgreSQL
        print("\n🐘 PostgreSQL Status:")
        pg_migration = SecureTenantIDMigration(POSTGRESQL_URL)
        with pg_migration.get_session() as session:
            # Count total tenants
            total_result = session.execute(pg_migration.engine.execute("SELECT COUNT(*) FROM tenants"))
            total_tenants = total_result.scalar()
            
            # Count secure tenants (9-digit IDs)
            secure_result = session.execute(pg_migration.engine.execute("SELECT COUNT(*) FROM tenants WHERE id >= 100000000"))
            secure_tenants = secure_result.scalar()
            
            insecure_tenants = total_tenants - secure_tenants
            security_percentage = (secure_tenants / total_tenants * 100) if total_tenants > 0 else 100
            
            print(f"   Total tenants: {total_tenants}")
            print(f"   Secure tenants: {secure_tenants}")
            print(f"   Insecure tenants: {insecure_tenants}")
            print(f"   Security level: {security_percentage:.1f}%")
            
            if insecure_tenants > 0:
                print(f"   Status: 🚨 NEEDS MIGRATION")
            else:
                print(f"   Status: ✅ SECURE")
    
    except Exception as e:
        print(f"   Error checking PostgreSQL: {e}")
    
    try:
        # Check SQLite
        print("\n🗃️ SQLite Status:")
        sqlite_migration = SecureTenantIDMigration(SQLITE_URL)
        with sqlite_migration.get_session() as session:
            # Count total tenants
            total_result = session.execute(sqlite_migration.engine.execute("SELECT COUNT(*) FROM tenants"))
            total_tenants = total_result.scalar()
            
            # Count secure tenants (9-digit IDs)
            secure_result = session.execute(sqlite_migration.engine.execute("SELECT COUNT(*) FROM tenants WHERE id >= 100000000"))
            secure_tenants = secure_result.scalar()
            
            insecure_tenants = total_tenants - secure_tenants
            security_percentage = (secure_tenants / total_tenants * 100) if total_tenants > 0 else 100
            
            print(f"   Total tenants: {total_tenants}")
            print(f"   Secure tenants: {secure_tenants}")
            print(f"   Insecure tenants: {insecure_tenants}")
            print(f"   Security level: {security_percentage:.1f}%")
            
            if insecure_tenants > 0:
                print(f"   Status: 🚨 NEEDS MIGRATION")
            else:
                print(f"   Status: ✅ SECURE")
    
    except Exception as e:
        print(f"   Error checking SQLite: {e}")


def rollback_migration():
    """Rollback a previous migration"""
    print("🔄 MIGRATION ROLLBACK")
    print("=" * 40)
    print()
    print("⚠️ WARNING: This will attempt to restore original tenant IDs!")
    print("⚠️ This is a complex operation - ensure you understand the implications!")
    print()
    
    # Ask which database
    print("Which database would you like to rollback?")
    print("1. PostgreSQL")
    print("2. SQLite")
    print()
    
    while True:
        choice = input("Enter choice (1-2): ").strip()
        if choice in ['1', '2']:
            break
        print("Invalid choice. Please enter 1 or 2.")
    
    print()
    confirm = input("Type 'ROLLBACK' to confirm rollback operation: ").strip()
    
    if confirm != 'ROLLBACK':
        print("Rollback cancelled.")
        return
    
    try:
        if choice == '1':
            migration = SecureTenantIDMigration(POSTGRESQL_URL)
            success = migration.rollback_migration()
        else:
            migration = SecureTenantIDMigration(SQLITE_URL)
            success = migration.rollback_migration()
        
        if success:
            print("✅ Rollback completed successfully!")
        else:
            print("❌ Rollback failed!")
    
    except Exception as e:
        print(f"❌ Rollback error: {e}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == 'status':
            quick_status_check()
        elif command == 'rollback':
            rollback_migration()
        elif command == 'migrate':
            main()
        else:
            print("Usage:")
            print("  python migrate_tenant_ids.py status    - Check current security status")
            print("  python migrate_tenant_ids.py migrate   - Run migration")
            print("  python migrate_tenant_ids.py rollback  - Rollback migration")
    else:
        # Interactive mode
        print("Select an option:")
        print("1. Check Security Status")
        print("2. Run Migration")
        print("3. Rollback Migration")
        print("4. Exit")
        print()
        
        while True:
            choice = input("Enter choice (1-4): ").strip()
            
            if choice == '1':
                quick_status_check()
                break
            elif choice == '2':
                main()
                break
            elif choice == '3':
                rollback_migration()
                break
            elif choice == '4':
                print("Goodbye!")
                break
            else:
                print("Invalid choice. Please enter 1-4.")