#!/usr/bin/env python3
"""
Direct Update Migration - Just Update the IDs
Simplest approach that actually works
"""

import random
import argparse
import sqlalchemy as sa
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


def generate_secure_id():
    """Generate secure 9-digit random ID"""
    return random.randint(100000000, 999999999)


def get_all_tenant_mappings(session):
    """Generate new IDs for all tenants at once"""
    # Get all insecure tenants
    tenants = session.execute(
        text("SELECT id, name FROM tenants WHERE id < 100000000 ORDER BY id")
    ).fetchall()
    
    if not tenants:
        return {}
    
    # Generate all new IDs
    mappings = {}
    used_ids = set()
    
    for old_id, name in tenants:
        # Generate unique new ID
        attempts = 0
        while attempts < 100:
            new_id = generate_secure_id()
            
            # Check if already used or exists in database
            if new_id not in used_ids:
                existing = session.execute(
                    text("SELECT 1 FROM tenants WHERE id = :id"), 
                    {"id": new_id}
                ).fetchone()
                
                if not existing:
                    mappings[old_id] = new_id
                    used_ids.add(new_id)
                    break
            
            attempts += 1
        
        if attempts >= 100:
            raise Exception(f"Could not generate unique ID for tenant {name}")
    
    return mappings


def direct_update_migration(session, mappings):
    """Update tenant IDs directly by changing constraints temporarily"""
    
    print(f"🔄 Starting direct ID updates...")
    
    total_success = 0
    total_failed = 0
    
    # Get list of all tables that reference tenants.id
    fk_tables = [
        'users', 'tenant_credentials', 'tenant_password_resets',
        'knowledge_bases', 'faqs', 'chat_sessions', 'tenant_subscriptions',
        'agents', 'conversations', 'customer_profiles', 'usage_logs',
        'billing_history', 'booking_requests', 'chat_queue',
        'conversation_sessions', 'conversation_tags', 'conversation_transfers',
        'agent_tags', 'live_chat_settings'
    ]
    
    try:
        # Drop FK constraints temporarily (this might fail, but we'll try)
        print("🔓 Attempting to drop foreign key constraints...")
        dropped_constraints = []
        
        for table in fk_tables:
            try:
                # Get constraint names
                constraints = session.execute(text(f"""
                    SELECT constraint_name 
                    FROM information_schema.table_constraints 
                    WHERE table_name = '{table}' 
                    AND constraint_type = 'FOREIGN KEY'
                    AND constraint_name LIKE '%tenant%'
                """)).fetchall()
                
                for (constraint_name,) in constraints:
                    try:
                        session.execute(text(f"ALTER TABLE {table} DROP CONSTRAINT {constraint_name}"))
                        dropped_constraints.append((table, constraint_name))
                        print(f"   ✅ Dropped {table}.{constraint_name}")
                    except Exception:
                        pass  # Might not have permission
                        
            except Exception:
                pass  # Table might not exist
        
        session.commit()
        
        # Update tenant IDs
        print(f"\n📝 Updating tenant IDs...")
        for old_id, new_id in mappings.items():
            try:
                result = session.execute(
                    text("UPDATE tenants SET id = :new_id WHERE id = :old_id"),
                    {"new_id": new_id, "old_id": old_id}
                )
                if result.rowcount > 0:
                    print(f"   ✅ Tenant {old_id} -> {new_id}")
                    total_success += 1
                else:
                    print(f"   ❌ No tenant found with ID {old_id}")
                    total_failed += 1
            except Exception as e:
                print(f"   ❌ Failed to update {old_id}: {e}")
                total_failed += 1
        
        session.commit()
        
        # Update foreign key references
        print(f"\n🔗 Updating foreign key references...")
        total_fk_updates = 0
        
        for table in fk_tables:
            table_updates = 0
            for old_id, new_id in mappings.items():
                try:
                    # Try tenant_id column
                    result = session.execute(
                        text(f"UPDATE {table} SET tenant_id = :new_id WHERE tenant_id = :old_id"),
                        {"new_id": new_id, "old_id": old_id}
                    )
                    table_updates += result.rowcount
                    
                    # Try other possible FK columns
                    try:
                        result2 = session.execute(
                            text(f"UPDATE {table} SET invited_by = :new_id WHERE invited_by = :old_id"),
                            {"new_id": new_id, "old_id": old_id}
                        )
                        table_updates += result2.rowcount
                    except:
                        pass
                        
                except Exception:
                    pass  # Table/column might not exist
            
            if table_updates > 0:
                print(f"   ✅ {table}: {table_updates} records")
                total_fk_updates += table_updates
        
        session.commit()
        
        # Recreate dropped constraints (best effort)
        print(f"\n🔒 Recreating foreign key constraints...")
        for table, constraint_name in dropped_constraints:
            try:
                # This is complex and might fail, but we try
                session.execute(text(f"""
                    ALTER TABLE {table} 
                    ADD CONSTRAINT {constraint_name} 
                    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
                """))
                print(f"   ✅ Recreated {table}.{constraint_name}")
            except Exception as e:
                print(f"   ⚠️ Could not recreate {table}.{constraint_name}: {e}")
        
        session.commit()
        
        return total_success, total_failed, total_fk_updates
        
    except Exception as e:
        session.rollback()
        raise e


def simple_update_only(session, mappings):
    """Simplest approach - just update what we can"""
    
    print(f"🔄 Simple update approach...")
    
    # Just update tenants table and any tables we can
    success = 0
    failed = 0
    
    for old_id, new_id in mappings.items():
        print(f"   Updating {old_id} -> {new_id}...")
        
        # Try to update tenant directly (will fail if FK constraints exist)
        try:
            session.execute(
                text("UPDATE tenants SET id = :new_id WHERE id = :old_id"),
                {"new_id": new_id, "old_id": old_id}
            )
            session.commit()
            print(f"   ✅ Success")
            success += 1
        except Exception as e:
            session.rollback()
            print(f"   ❌ Failed: {e}")
            failed += 1
    
    return success, failed, 0


def main():
    parser = argparse.ArgumentParser(description="Direct update migration")
    parser.add_argument('--database', required=True, help='Database URL')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes only')
    parser.add_argument('--apply', action='store_true', help='Apply changes')
    parser.add_argument('--simple', action='store_true', help='Use simple update approach')
    args = parser.parse_args()
    
    if not (args.dry_run or args.apply):
        print("❌ Use --dry-run or --apply")
        return
    
    # Connect
    try:
        engine = create_engine(args.database)
        Session = sessionmaker(bind=engine)
        print(f"🔗 Connected to database")
        
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return
    
    session = Session()
    
    # Generate mappings
    try:
        mappings = get_all_tenant_mappings(session)
    except Exception as e:
        print(f"❌ Failed to generate mappings: {e}")
        session.close()
        return
    
    if not mappings:
        print("✅ All tenant IDs are already secure!")
        session.close()
        return
    
    print(f"📊 Will migrate {len(mappings)} tenants")
    
    if args.dry_run:
        print("\n🔍 DRY RUN Preview:")
        for old_id, new_id in list(mappings.items())[:5]:
            tenant_name = session.execute(
                text("SELECT name FROM tenants WHERE id = :id"), 
                {"id": old_id}
            ).fetchone()[0]
            print(f"   {tenant_name}: {old_id:,} -> {new_id:,}")
        
        if len(mappings) > 5:
            print(f"   ... and {len(mappings) - 5} more")
        
        print(f"\n💡 Use --apply to perform migration")
        if args.simple:
            print(f"💡 Using --simple will attempt basic update only")
        
    elif args.apply:
        print(f"\n⚠️  DIRECT UPDATE MIGRATION:")
        print(f"   • Will migrate {len(mappings)} tenants")
        print(f"   • Will attempt to handle FK constraints")
        print(f"   • This is PERMANENT")
        
        confirm = input("\n   Proceed? (yes/no): ")
        
        if confirm.lower() != 'yes':
            print("❌ Migration cancelled")
            session.close()
            return
        
        try:
            if args.simple:
                success, failed, fk_updates = simple_update_only(session, mappings)
            else:
                success, failed, fk_updates = direct_update_migration(session, mappings)
            
            print(f"\n🎉 MIGRATION RESULTS:")
            print(f"   ✅ Successful: {success}")
            print(f"   ❌ Failed: {failed}")
            print(f"   🔗 FK Updates: {fk_updates}")
            
            if success > 0:
                print(f"\n🔒 Tenant IDs updated to 9-digit secure format!")
                
        except Exception as e:
            print(f"\n❌ Migration failed: {e}")
    
    session.close()


if __name__ == "__main__":
    main()