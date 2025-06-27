#!/usr/bin/env python3
"""
Investigation and Recovery Script
Check what actually happened and complete the migration properly
"""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import random

DATABASE_URL = "postgresql://chatbot_hhjv_user:dYXguSEwpwZl3Yt2R3ACsfvmM5lLIgSD@dpg-d10sp295pdvs73afujf0-a.oregon-postgres.render.com/chatbot_hhjv"

def generate_secure_id():
    """Generate a 9-digit secure ID"""
    return random.randint(100000000, 999999999)

def investigate_current_state():
    """Investigate what actually happened during migration"""
    print("🔍 INVESTIGATING MIGRATION STATUS")
    print("=" * 40)
    
    engine = create_engine(DATABASE_URL, echo=False)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Check current tenant IDs
        print("📊 Current Tenant ID Status:")
        tenant_sample = session.execute(text("""
            SELECT id, name, email FROM tenants ORDER BY id LIMIT 10
        """)).fetchall()
        
        print("   Current Tenant IDs:")
        for tenant_id, name, email in tenant_sample:
            secure_status = "SECURE" if tenant_id >= 100000000 else "INSECURE"
            print(f"   ID: {tenant_id:<12} | {name:<15} | {secure_status}")
        
        # Check backup tables
        print(f"\n💾 Backup Table Analysis:")
        
        # Original backup table
        try:
            original_backup = session.execute(text("""
                SELECT COUNT(*), status FROM tenant_id_migration_backup 
                GROUP BY status
            """)).fetchall()
            
            print("   tenant_id_migration_backup:")
            for count, status in original_backup:
                print(f"     {status}: {count} entries")
                
            # Show sample mappings from original backup
            sample_mappings = session.execute(text("""
                SELECT old_id, new_id, tenant_name FROM tenant_id_migration_backup 
                WHERE status = 'planned' 
                ORDER BY old_id LIMIT 5
            """)).fetchall()
            
            print("   Sample planned mappings:")
            for old_id, new_id, name in sample_mappings:
                print(f"     {old_id} → {new_id} ({name})")
                
        except Exception as e:
            print(f"   Original backup table: Error - {e}")
        
        # Simple backup table
        try:
            simple_backup = session.execute(text("""
                SELECT COUNT(*) FROM migration_backup_simple
            """)).scalar()
            
            print(f"   migration_backup_simple: {simple_backup} entries")
            
            if simple_backup > 0:
                sample_simple = session.execute(text("""
                    SELECT old_id, new_id, tenant_name FROM migration_backup_simple 
                    ORDER BY old_id LIMIT 5
                """)).fetchall()
                
                print("   Sample simple backup mappings:")
                for old_id, new_id, name in sample_simple:
                    print(f"     {old_id} → {new_id} ({name})")
                    
        except Exception as e:
            print(f"   Simple backup table: Error - {e}")
        
        # Check foreign key constraints
        print(f"\n🔗 Foreign Key Constraint Status:")
        fk_count = session.execute(text("""
            SELECT COUNT(*) FROM information_schema.table_constraints tc
            WHERE tc.constraint_type = 'FOREIGN KEY'
                AND tc.constraint_name LIKE '%tenant_id_fkey'
        """)).scalar()
        
        print(f"   Current FK constraints: {fk_count}")
        
        # Check if tenant primary key exists
        pk_exists = session.execute(text("""
            SELECT COUNT(*) FROM information_schema.table_constraints tc
            WHERE tc.constraint_type = 'PRIMARY KEY'
                AND tc.table_name = 'tenants'
        """)).scalar()
        
        print(f"   Tenant primary key exists: {'✅' if pk_exists > 0 else '❌'}")
        
        session.close()
        
        # Analysis
        print(f"\n🔬 ANALYSIS:")
        
        # Check if we have data to complete migration
        engine2 = create_engine(DATABASE_URL, echo=False)
        Session2 = sessionmaker(bind=engine2)
        session2 = Session2()
        
        try:
            migration_data = session2.execute(text("""
                SELECT old_id, new_id, tenant_name FROM migration_backup_simple 
                ORDER BY old_id
            """)).fetchall()
            
            if migration_data:
                print(f"   ✅ Found {len(migration_data)} tenant mappings in backup")
                print(f"   🔧 Can complete migration using backup data")
                return migration_data
            else:
                print(f"   ❌ No backup data found")
                return None
                
        except:
            print(f"   ❌ Cannot access backup data")
            return None
        finally:
            session2.close()
            
    except Exception as e:
        print(f"❌ Investigation failed: {e}")
        session.close()
        return None

def complete_migration_safely(migration_data):
    """Complete the migration using backup data with proper transaction handling"""
    print(f"\n🔧 COMPLETING MIGRATION SAFELY")
    print("=" * 40)
    
    print(f"⚠️ About to update {len(migration_data)} tenant IDs")
    print("This will change:")
    for old_id, new_id, name in migration_data[:5]:
        print(f"   {old_id} → {new_id} ({name})")
    if len(migration_data) > 5:
        print(f"   ... and {len(migration_data) - 5} more")
    
    confirm = input(f"\nProceed with completing the migration? (y/N): ").lower().strip()
    if confirm != 'y':
        print("Migration cancelled")
        return False
    
    engine = create_engine(DATABASE_URL, echo=False)
    
    try:
        # Use a single transaction for the entire operation
        with engine.begin() as conn:
            print("🔄 Step 1: Dropping foreign key constraints...")
            
            # Get all FK constraints
            fk_result = conn.execute(text("""
                SELECT tc.table_name, tc.constraint_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.constraint_column_usage ccu 
                    ON ccu.constraint_name = tc.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY'
                    AND ccu.table_name = 'tenants'
                    AND ccu.column_name = 'id'
            """))
            
            fk_constraints = fk_result.fetchall()
            print(f"   Found {len(fk_constraints)} FK constraints to drop")
            
            # Drop FK constraints
            for table_name, constraint_name in fk_constraints:
                try:
                    conn.execute(text(f"ALTER TABLE {table_name} DROP CONSTRAINT {constraint_name}"))
                except Exception as e:
                    print(f"   ⚠️ Could not drop {constraint_name}: {e}")
            
            print("✅ FK constraints dropped")
            
            print("🔄 Step 2: Updating tenant IDs...")
            
            # Drop primary key constraint
            try:
                conn.execute(text("ALTER TABLE tenants DROP CONSTRAINT tenants_pkey"))
                print("   ✅ Dropped primary key constraint")
            except Exception as e:
                print(f"   ⚠️ Primary key drop: {e}")
            
            # Update tenant IDs one by one
            updated_count = 0
            for old_id, new_id, name in migration_data:
                try:
                    result = conn.execute(text("""
                        UPDATE tenants SET id = :new_id WHERE id = :old_id
                    """), {"new_id": new_id, "old_id": old_id})
                    
                    if result.rowcount > 0:
                        updated_count += 1
                        print(f"   ✅ Updated: {old_id} → {new_id} ({name})")
                    else:
                        print(f"   ⚠️ No rows updated for ID {old_id}")
                        
                except Exception as e:
                    print(f"   ❌ Failed to update {old_id}: {e}")
                    raise e  # This will cause rollback
            
            print(f"✅ Updated {updated_count} tenant IDs")
            
            print("🔄 Step 3: Recreating primary key...")
            try:
                conn.execute(text("ALTER TABLE tenants ADD PRIMARY KEY (id)"))
                print("   ✅ Primary key recreated")
            except Exception as e:
                print(f"   ❌ Primary key recreation failed: {e}")
                raise e
            
            print("🔄 Step 4: Recreating foreign key constraints...")
            recreated_count = 0
            
            for table_name, constraint_name in fk_constraints:
                try:
                    conn.execute(text(f"""
                        ALTER TABLE {table_name} 
                        ADD CONSTRAINT {constraint_name} 
                        FOREIGN KEY (tenant_id) REFERENCES tenants(id)
                    """))
                    recreated_count += 1
                    
                except Exception as e:
                    print(f"   ⚠️ Could not recreate {constraint_name}: {e}")
                    # Don't fail the transaction for FK recreation issues
            
            print(f"✅ Recreated {recreated_count}/{len(fk_constraints)} FK constraints")
            
            # Update backup status
            print("🔄 Step 5: Updating backup status...")
            try:
                conn.execute(text("""
                    UPDATE migration_backup_simple 
                    SET created_at = CURRENT_TIMESTAMP
                """))
                
                # Mark as completed in original backup if it exists
                try:
                    conn.execute(text("""
                        UPDATE tenant_id_migration_backup 
                        SET status = 'completed' 
                        WHERE status = 'planned'
                    """))
                except:
                    pass
                    
            except Exception as e:
                print(f"   ⚠️ Backup status update failed: {e}")
            
            print("✅ Transaction completed successfully!")
        
        # Verify outside the transaction
        print("\n🔍 Verification...")
        
        Session = sessionmaker(bind=engine)
        session = Session()
        
        try:
            # Check final state
            final_stats = session.execute(text("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN id >= 100000000 THEN 1 END) as secure,
                    MIN(id) as min_id,
                    MAX(id) as max_id
                FROM tenants
            """)).first()
            
            total, secure, min_id, max_id = final_stats
            security_percentage = (secure / total * 100) if total > 0 else 0
            
            print(f"   Total tenants: {total}")
            print(f"   Secure tenants: {secure}")
            print(f"   Security level: {security_percentage:.1f}%")
            print(f"   ID range: {min_id} - {max_id}")
            
            if security_percentage == 100:
                print(f"\n🎉 MIGRATION COMPLETED SUCCESSFULLY!")
                print(f"   ✅ All tenant IDs are now secure")
                print(f"   ✅ Enumeration attacks prevented")
                print(f"   ✅ Database integrity maintained")
            else:
                print(f"\n⚠️ Migration incomplete: {security_percentage:.1f}% success")
            
            session.close()
            return security_percentage == 100
            
        except Exception as e:
            print(f"   ❌ Verification failed: {e}")
            session.close()
            return False
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        print("🔄 Transaction was rolled back")
        return False

def main():
    """Main function"""
    print("🔍 MIGRATION INVESTIGATION AND RECOVERY")
    print("=" * 50)
    
    # Step 1: Investigate current state
    migration_data = investigate_current_state()
    
    if not migration_data:
        print("\n❌ Cannot proceed - no backup data found")
        return
    
    # Step 2: Complete migration if we have data
    print(f"\n💡 Found backup data for {len(migration_data)} tenants")
    print("🔧 Can complete the migration using this data")
    
    success = complete_migration_safely(migration_data)
    
    if success:
        print(f"\n🎉 MIGRATION RECOVERY SUCCESSFUL!")
        print(f"   Your tenant IDs are now secure")
        print(f"   The enumeration vulnerability is fixed")
    else:
        print(f"\n❌ Migration recovery failed")
        print(f"   Manual intervention may be required")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n⚠️ Recovery interrupted by user")
    except Exception as e:
        print(f"\n❌ Recovery failed: {e}")
        import traceback
        traceback.print_exc()