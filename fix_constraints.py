#!/usr/bin/env python3
"""
Fix Foreign Key Constraints After Migration
This script will clean up orphaned records and recreate missing FK constraints
"""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql://chatbot_hhjv_user:dYXguSEwpwZl3Yt2R3ACsfvmM5lLIgSD@dpg-d10sp295pdvs73afujf0-a.oregon-postgres.render.com/chatbot_hhjv"

def fix_foreign_key_constraints():
    """Fix the foreign key constraints that failed to recreate"""
    print("🔧 FIXING FOREIGN KEY CONSTRAINTS")
    print("=" * 40)
    
    engine = create_engine(DATABASE_URL, echo=False)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Step 1: Check current status
        print("📊 Step 1: Checking current tenant status...")
        
        tenant_stats = session.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN id < 100000000 THEN 1 END) as insecure,
                COUNT(CASE WHEN id >= 100000000 THEN 1 END) as secure
            FROM tenants
        """)).first()
        
        total, insecure, secure = tenant_stats
        print(f"   Total tenants: {total}")
        print(f"   Secure tenants: {secure}")
        print(f"   Insecure tenants: {insecure}")
        
        if insecure > 0:
            print(f"   ⚠️ Still have {insecure} insecure tenants!")
        else:
            print(f"   ✅ All tenants now have secure IDs!")
        
        # Step 2: Find orphaned records
        print("\n🔍 Step 2: Finding orphaned records...")
        
        tables_to_check = [
            'tenant_password_resets',
            'users', 
            'tenant_credentials',
            'knowledge_bases',
            'faqs',
            'chat_sessions',
            'tenant_subscriptions',
            'conversation_sessions',
            'booking_requests',
            'usage_logs',
            'billing_history',
            'live_chats',
            'pending_feedback',
            'conversations',
            'security_incidents',
            'conversation_tags',
            'conversation_transfers',
            'instagram_integrations',
            'telegram_integrations',
            'instagram_conversations',
            'instagram_webhook_events',
            'telegram_chats',
            'instagram_messages',
            'agents',
            'live_chat_settings',
            'live_chat_conversations',
            'agent_sessions',
            'chat_queue',
            'customer_profiles',
            'agent_tags',
            'smart_routing_log'
        ]
        
        orphaned_tables = []
        total_orphaned = 0
        
        for table in tables_to_check:
            try:
                # Check if table exists
                table_exists = session.execute(text(f"""
                    SELECT COUNT(*) FROM information_schema.tables 
                    WHERE table_name = '{table}'
                """)).scalar()
                
                if table_exists == 0:
                    continue
                
                # Check for orphaned records
                orphaned_count = session.execute(text(f"""
                    SELECT COUNT(*) FROM {table} 
                    WHERE tenant_id NOT IN (SELECT id FROM tenants)
                """)).scalar()
                
                if orphaned_count > 0:
                    orphaned_tables.append((table, orphaned_count))
                    total_orphaned += orphaned_count
                    print(f"   ⚠️ {table}: {orphaned_count} orphaned records")
                else:
                    print(f"   ✅ {table}: No orphaned records")
                    
            except Exception as e:
                print(f"   ❌ {table}: Error checking - {str(e)[:50]}...")
        
        print(f"\n📊 Summary: {total_orphaned} total orphaned records in {len(orphaned_tables)} tables")
        
        # Step 3: Clean up orphaned records
        if orphaned_tables:
            print("\n🧹 Step 3: Cleaning up orphaned records...")
            
            confirm = input("Delete orphaned records? (y/N): ").lower().strip()
            if confirm == 'y':
                cleaned_records = 0
                
                for table, count in orphaned_tables:
                    try:
                        result = session.execute(text(f"""
                            DELETE FROM {table} 
                            WHERE tenant_id NOT IN (SELECT id FROM tenants)
                        """))
                        deleted = result.rowcount
                        cleaned_records += deleted
                        print(f"   🗑️ {table}: Deleted {deleted} orphaned records")
                        
                    except Exception as e:
                        print(f"   ❌ {table}: Failed to clean - {str(e)[:50]}...")
                
                session.commit()
                print(f"   ✅ Cleaned {cleaned_records} orphaned records total")
            else:
                print("   ⏭️ Skipping cleanup")
        else:
            print("\n✅ Step 3: No orphaned records to clean!")
        
        # Step 4: Recreate missing foreign key constraints
        print("\n🔗 Step 4: Recreating missing foreign key constraints...")
        
        # Get tables that should have FK constraints but don't
        missing_fks = session.execute(text("""
            SELECT DISTINCT t.table_name
            FROM information_schema.tables t
            JOIN information_schema.columns c ON t.table_name = c.table_name
            WHERE c.column_name = 'tenant_id'
                AND t.table_schema = 'public'
                AND t.table_name != 'tenants'
                AND t.table_name NOT IN (
                    SELECT tc.table_name
                    FROM information_schema.table_constraints tc
                    WHERE tc.constraint_type = 'FOREIGN KEY'
                        AND tc.constraint_name LIKE '%tenant_id_fkey'
                )
            ORDER BY t.table_name
        """)).fetchall()
        
        print(f"   Found {len(missing_fks)} tables missing FK constraints:")
        
        recreated_count = 0
        failed_count = 0
        
        for (table_name,) in missing_fks:
            constraint_name = f"{table_name}_tenant_id_fkey"
            
            try:
                session.execute(text(f"""
                    ALTER TABLE {table_name} 
                    ADD CONSTRAINT {constraint_name}
                    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
                """))
                recreated_count += 1
                print(f"   ✅ {table_name}: Recreated FK constraint")
                
            except Exception as e:
                failed_count += 1
                print(f"   ❌ {table_name}: Failed - {str(e)[:60]}...")
        
        session.commit()
        
        print(f"\n📊 FK Recreation Summary:")
        print(f"   ✅ Successfully recreated: {recreated_count}")
        print(f"   ❌ Failed to recreate: {failed_count}")
        
        # Step 5: Verify final state
        print("\n🔍 Step 5: Final verification...")
        
        # Check FK constraint count
        final_fk_count = session.execute(text("""
            SELECT COUNT(*) FROM information_schema.table_constraints tc
            WHERE tc.constraint_type = 'FOREIGN KEY'
                AND tc.constraint_name LIKE '%tenant_id_fkey'
        """)).scalar()
        
        print(f"   Current FK constraints: {final_fk_count}")
        
        # Check for any remaining integrity issues
        remaining_issues = 0
        for table in ['users', 'knowledge_bases', 'faqs', 'chat_sessions']:
            try:
                table_exists = session.execute(text(f"""
                    SELECT COUNT(*) FROM information_schema.tables 
                    WHERE table_name = '{table}'
                """)).scalar()
                
                if table_exists == 0:
                    continue
                
                orphaned = session.execute(text(f"""
                    SELECT COUNT(*) FROM {table} 
                    WHERE tenant_id NOT IN (SELECT id FROM tenants)
                """)).scalar()
                
                if orphaned > 0:
                    remaining_issues += orphaned
                    print(f"   ⚠️ {table}: {orphaned} remaining orphaned records")
                    
            except Exception as e:
                print(f"   ❌ {table}: Verification error")
        
        if remaining_issues == 0:
            print(f"   ✅ No remaining integrity issues!")
        else:
            print(f"   ⚠️ {remaining_issues} remaining orphaned records")
        
        # Final status
        print(f"\n🎉 FOREIGN KEY CONSTRAINT FIX COMPLETED!")
        print(f"   Database integrity: {'✅ GOOD' if remaining_issues == 0 else '⚠️ NEEDS ATTENTION'}")
        print(f"   FK constraints: {final_fk_count} active")
        
        session.close()
        return True
        
    except Exception as e:
        print(f"❌ FK fix failed: {e}")
        session.rollback()
        session.close()
        return False

def verify_migration_success():
    """Verify that the migration was successful"""
    print("\n🔍 MIGRATION SUCCESS VERIFICATION")
    print("=" * 40)
    
    engine = create_engine(DATABASE_URL, echo=False)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Check tenant ID security
        security_stats = session.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN id >= 100000000 THEN 1 END) as secure,
                MIN(id) as min_id,
                MAX(id) as max_id
            FROM tenants
        """)).first()
        
        total, secure, min_id, max_id = security_stats
        security_percentage = (secure / total * 100) if total > 0 else 0
        
        print(f"📊 Security Status:")
        print(f"   Total tenants: {total}")
        print(f"   Secure tenants: {secure}")
        print(f"   Security level: {security_percentage:.1f}%")
        print(f"   ID range: {min_id} - {max_id}")
        
        # Show sample migrated tenants
        print(f"\n📋 Sample Migrated Tenants:")
        samples = session.execute(text("""
            SELECT id, name, email FROM tenants 
            WHERE id >= 100000000 
            ORDER BY id LIMIT 10
        """)).fetchall()
        
        print("   New Secure ID | Name         | Email")
        print("   " + "-" * 50)
        for tenant_id, name, email in samples:
            name_short = (name or 'Unknown')[:12]
            email_short = (email or 'unknown')[:20]
            print(f"   {tenant_id}  | {name_short:<12} | {email_short}")
        
        # Check backup data
        backup_count = session.execute(text("""
            SELECT COUNT(*) FROM migration_backup_simple
        """)).scalar()
        
        print(f"\n💾 Backup Information:")
        print(f"   Backup records: {backup_count}")
        print(f"   Backup table: migration_backup_simple")
        
        if security_percentage == 100:
            print(f"\n🎉 MIGRATION FULLY SUCCESSFUL!")
            print(f"   ✅ All tenant IDs are now secure")
            print(f"   ✅ No sequential IDs remaining") 
            print(f"   ✅ Enumeration attacks prevented")
        else:
            print(f"\n⚠️ MIGRATION PARTIALLY SUCCESSFUL")
            remaining = total - secure
            print(f"   🚨 {remaining} tenants still have insecure IDs")
        
        session.close()
        
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        session.close()

if __name__ == "__main__":
    try:
        print("🔧 FOREIGN KEY CONSTRAINT REPAIR TOOL")
        print("=" * 50)
        
        # Fix FK constraints
        success = fix_foreign_key_constraints()
        
        if success:
            # Verify migration success
            verify_migration_success()
        
        print(f"\n" + "=" * 50)
        print("Repair complete!")
        
    except KeyboardInterrupt:
        print(f"\n⚠️ Repair interrupted by user")
    except Exception as e:
        print(f"\n❌ Repair failed: {e}")