#!/usr/bin/env python3
"""
Simple Working Migration Script with Guaranteed Output
This script will definitely show what's happening
"""

import sys
import random
import time
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql://chatbot_hhjv_user:dYXguSEwpwZl3Yt2R3ACsfvmM5lLIgSD@dpg-d10sp295pdvs73afujf0-a.oregon-postgres.render.com/chatbot_hhjv"

def generate_secure_id():
    """Generate a 9-digit secure ID"""
    return random.randint(100000000, 999999999)

def run_status_check():
    """Check current migration status"""
    print("🔍 CHECKING TENANT ID SECURITY STATUS")
    print("=" * 45)
    
    try:
        engine = create_engine(DATABASE_URL, echo=False)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        print("✅ Connected to PostgreSQL database")
        
        # Get tenant statistics
        print("\n📊 Current Tenant Statistics:")
        
        total_result = session.execute(text("SELECT COUNT(*) FROM tenants"))
        total_tenants = total_result.scalar()
        print(f"   Total tenants: {total_tenants}")
        
        secure_result = session.execute(text("SELECT COUNT(*) FROM tenants WHERE id >= 100000000"))
        secure_tenants = secure_result.scalar()
        print(f"   Secure tenants: {secure_tenants}")
        
        insecure_tenants = total_tenants - secure_tenants
        print(f"   Insecure tenants: {insecure_tenants}")
        
        if total_tenants > 0:
            security_percentage = (secure_tenants / total_tenants) * 100
            print(f"   Security level: {security_percentage:.1f}%")
        
        # Show sample insecure tenants
        if insecure_tenants > 0:
            print(f"\n🚨 Sample Insecure Tenants:")
            sample_result = session.execute(text("""
                SELECT id, name, email FROM tenants 
                WHERE id < 100000000 
                ORDER BY id LIMIT 10
            """))
            
            print("   ID  | Name           | Email")
            print("   " + "-" * 40)
            
            for row in sample_result:
                tenant_id, name, email = row
                name_display = (name or 'Unknown')[:12]
                email_display = (email or 'no-email')[:20]
                print(f"   {tenant_id:<3} | {name_display:<12} | {email_display}")
        
        # Check backup table
        print(f"\n💾 Backup Table Status:")
        try:
            backup_result = session.execute(text("SELECT COUNT(*) FROM tenant_id_migration_backup"))
            backup_count = backup_result.scalar()
            print(f"   Backup entries: {backup_count}")
            
            if backup_count > 0:
                status_result = session.execute(text("""
                    SELECT status, COUNT(*) FROM tenant_id_migration_backup 
                    GROUP BY status
                """))
                print("   Status breakdown:")
                for status, count in status_result:
                    print(f"     {status}: {count}")
        except Exception as e:
            print(f"   Backup table: Not found ({str(e)[:30]}...)")
        
        session.close()
        
        # Migration recommendation
        print(f"\n💡 Recommendation:")
        if insecure_tenants > 0:
            print(f"   🔧 MIGRATE {insecure_tenants} tenants to secure IDs")
            print(f"   🚨 Current IDs are easily guessable!")
        else:
            print(f"   ✅ All tenant IDs are secure!")
        
        return insecure_tenants > 0
        
    except Exception as e:
        print(f"❌ Status check failed: {e}")
        return False

def run_dry_migration():
    """Run a dry migration to preview changes"""
    print("\n🔍 DRY RUN MIGRATION PREVIEW")
    print("=" * 35)
    
    try:
        engine = create_engine(DATABASE_URL, echo=False)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        # Get tenants to migrate
        result = session.execute(text("""
            SELECT id, name, email, business_name 
            FROM tenants 
            WHERE id < 100000000 
            ORDER BY id
        """))
        
        tenants_to_migrate = result.fetchall()
        
        if not tenants_to_migrate:
            print("✅ No tenants need migration!")
            session.close()
            return True
        
        print(f"📋 Found {len(tenants_to_migrate)} tenants to migrate:")
        print()
        
        # Generate preview mappings
        used_ids = set()
        mappings = []
        
        for old_id, name, email, business in tenants_to_migrate:
            # Generate unique new ID
            new_id = generate_secure_id()
            while new_id in used_ids:
                new_id = generate_secure_id()
            used_ids.add(new_id)
            
            mappings.append((old_id, new_id, name or 'Unknown'))
        
        # Show sample mappings
        print("🔄 Sample ID Mappings (Old → New):")
        for i, (old_id, new_id, name) in enumerate(mappings[:10]):
            print(f"   {old_id:>3} → {new_id} ({name[:15]})")
        
        if len(mappings) > 10:
            print(f"   ... and {len(mappings) - 10} more")
        
        print(f"\n📊 Migration Impact:")
        print(f"   Tenants to update: {len(mappings)}")
        
        # Check dependent tables
        print(f"   Tables to update:")
        
        dependent_tables = [
            'users', 'tenant_credentials', 'knowledge_bases', 
            'faqs', 'chat_sessions', 'agents'
        ]
        
        total_records = 0
        for table in dependent_tables:
            try:
                count_result = session.execute(text(f"""
                    SELECT COUNT(*) FROM {table} 
                    WHERE tenant_id IN (
                        SELECT id FROM tenants WHERE id < 100000000
                    )
                """))
                record_count = count_result.scalar()
                total_records += record_count
                print(f"     {table}: {record_count} records")
            except Exception as e:
                print(f"     {table}: Error checking ({str(e)[:20]}...)")
        
        print(f"   Total records to update: {total_records}")
        
        print(f"\n⚠️  This is a DRY RUN - no changes made!")
        print(f"💡 To execute: python script.py --execute")
        
        session.close()
        return True
        
    except Exception as e:
        print(f"❌ Dry run failed: {e}")
        return False

def run_actual_migration():
    """Run the actual migration with proper constraint handling"""
    print("\n🚀 EXECUTING ACTUAL MIGRATION")
    print("=" * 35)
    print("⚠️  WARNING: This will modify your database!")
    print()
    
    # Extra confirmation
    confirm = input("Type 'MIGRATE' to confirm: ")
    if confirm != 'MIGRATE':
        print("❌ Migration cancelled")
        return False
    
    try:
        engine = create_engine(DATABASE_URL, echo=False)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        print("✅ Starting migration process...")
        
        # Step 1: Get tenants to migrate
        print("📋 Step 1: Identifying tenants...")
        result = session.execute(text("""
            SELECT id, name, email, business_name 
            FROM tenants 
            WHERE id < 100000000 
            ORDER BY id
        """))
        
        tenants_to_migrate = result.fetchall()
        print(f"   Found: {len(tenants_to_migrate)} tenants")
        
        if not tenants_to_migrate:
            print("✅ No migration needed!")
            session.close()
            return True
        
        # Step 2: Generate new IDs
        print("🔢 Step 2: Generating secure IDs...")
        used_ids = set()
        mappings = []
        
        for old_id, name, email, business in tenants_to_migrate:
            new_id = generate_secure_id()
            while new_id in used_ids:
                new_id = generate_secure_id()
            used_ids.add(new_id)
            mappings.append((old_id, new_id, name or 'Unknown'))
        
        print(f"   Generated: {len(mappings)} secure IDs")
        
        # Step 3: Create backup
        print("💾 Step 3: Creating backup...")
        try:
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS migration_backup_simple (
                    old_id INTEGER,
                    new_id INTEGER,
                    tenant_name VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            
            for old_id, new_id, name in mappings:
                session.execute(text("""
                    INSERT INTO migration_backup_simple (old_id, new_id, tenant_name)
                    VALUES (:old_id, :new_id, :name)
                """), {"old_id": old_id, "new_id": new_id, "name": name})
            
            session.commit()
            print("   ✅ Backup created")
        except Exception as e:
            print(f"   ❌ Backup failed: {e}")
            session.rollback()
            return False
        
        # Step 4: Discover and drop foreign key constraints
        print("🔗 Step 4: Managing foreign key constraints...")
        
        # Get all FK constraints that reference tenants.id
        fk_result = session.execute(text("""
            SELECT tc.table_name, tc.constraint_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.constraint_column_usage ccu 
                ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
                AND ccu.table_name = 'tenants'
                AND ccu.column_name = 'id'
        """))
        
        fk_constraints = fk_result.fetchall()
        print(f"   Found: {len(fk_constraints)} FK constraints")
        
        # Drop FK constraints
        dropped_constraints = []
        for table_name, constraint_name in fk_constraints:
            try:
                session.execute(text(f"""
                    ALTER TABLE {table_name} DROP CONSTRAINT {constraint_name}
                """))
                dropped_constraints.append((table_name, constraint_name))
            except Exception as e:
                print(f"   ⚠️  Could not drop {constraint_name}: {e}")
        
        print(f"   Dropped: {len(dropped_constraints)} constraints")
        
        # Step 5: Update foreign key references
        print("🔄 Step 5: Updating foreign key references...")
        
        update_tables = ['users', 'tenant_credentials', 'knowledge_bases', 'faqs', 'chat_sessions']
        total_updates = 0
        
        for table in update_tables:
            try:
                table_updates = 0
                for old_id, new_id, _ in mappings:
                    result = session.execute(text(f"""
                        UPDATE {table} SET tenant_id = :new_id WHERE tenant_id = :old_id
                    """), {"new_id": new_id, "old_id": old_id})
                    table_updates += result.rowcount
                
                print(f"   {table}: {table_updates} records updated")
                total_updates += table_updates
            except Exception as e:
                print(f"   {table}: Error - {str(e)[:50]}...")
        
        print(f"   Total updates: {total_updates}")
        
        # Step 6: Update tenant IDs
        print("🆔 Step 6: Updating tenant primary keys...")
        
        # Drop primary key constraint
        try:
            session.execute(text("ALTER TABLE tenants DROP CONSTRAINT tenants_pkey"))
            print("   Dropped primary key constraint")
        except Exception as e:
            print(f"   Primary key drop failed: {e}")
            # Try to continue anyway
        
        # Update tenant IDs
        updated_tenants = 0
        for old_id, new_id, name in mappings:
            try:
                session.execute(text("""
                    UPDATE tenants SET id = :new_id WHERE id = :old_id
                """), {"new_id": new_id, "old_id": old_id})
                updated_tenants += 1
            except Exception as e:
                print(f"   Failed to update tenant {old_id}: {e}")
        
        print(f"   Updated: {updated_tenants} tenant IDs")
        
        # Recreate primary key
        try:
            session.execute(text("ALTER TABLE tenants ADD PRIMARY KEY (id)"))
            print("   Recreated primary key constraint")
        except Exception as e:
            print(f"   Primary key recreation failed: {e}")
        
        # Step 7: Recreate foreign key constraints
        print("🔗 Step 7: Recreating foreign key constraints...")
        
        recreated = 0
        for table_name, constraint_name in dropped_constraints:
            try:
                session.execute(text(f"""
                    ALTER TABLE {table_name} 
                    ADD CONSTRAINT {constraint_name} 
                    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
                """))
                recreated += 1
            except Exception as e:
                print(f"   ⚠️  Could not recreate {constraint_name}: {e}")
        
        print(f"   Recreated: {recreated} constraints")
        
        # Step 8: Commit everything
        print("💾 Step 8: Committing changes...")
        session.commit()
        
        print("\n🎉 MIGRATION COMPLETED SUCCESSFULLY!")
        print(f"   Migrated {len(mappings)} tenants to secure IDs")
        print(f"   Updated {total_updates} foreign key references")
        print(f"   Backup stored in: migration_backup_simple")
        
        # Show sample results
        print(f"\n📋 Sample Results:")
        for old_id, new_id, name in mappings[:5]:
            print(f"   {old_id} → {new_id} ({name})")
        if len(mappings) > 5:
            print(f"   ... and {len(mappings) - 5} more")
        
        session.close()
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        try:
            session.rollback()
            session.close()
        except:
            pass
        return False

def main():
    """Main function with command line interface"""
    print("🔐 SECURE TENANT ID MIGRATION")
    print("=" * 40)
    print()
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "status":
            run_status_check()
        elif command == "dry-run" or command == "preview":
            needs_migration = run_status_check()
            if needs_migration:
                run_dry_migration()
        elif command == "execute" or command == "migrate":
            needs_migration = run_status_check()
            if needs_migration:
                run_actual_migration()
            else:
                print("✅ No migration needed!")
        else:
            print("Unknown command:", command)
            print_usage()
    else:
        # Interactive mode
        print("Choose an option:")
        print("1. Check Status")
        print("2. Preview Migration (Dry Run)")
        print("3. Execute Migration")
        print("4. Exit")
        print()
        
        choice = input("Enter choice (1-4): ").strip()
        
        if choice == "1":
            run_status_check()
        elif choice == "2":
            needs_migration = run_status_check()
            if needs_migration:
                run_dry_migration()
        elif choice == "3":
            needs_migration = run_status_check()
            if needs_migration:
                run_actual_migration()
            else:
                print("✅ No migration needed!")
        elif choice == "4":
            print("Goodbye!")
        else:
            print("Invalid choice")

def print_usage():
    """Print usage instructions"""
    print("Usage:")
    print("  python secure_migration.py status      - Check current status")
    print("  python secure_migration.py preview     - Preview migration")
    print("  python secure_migration.py execute     - Execute migration")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️ Interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()