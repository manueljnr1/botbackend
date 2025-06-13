# delete_tenant.py
"""
Script to completely remove a tenant and all their data from PostgreSQL
⚠️ WARNING: This permanently deletes all tenant data!
"""

import psycopg2
from urllib.parse import urlparse

# PostgreSQL connection string
DATABASE_URL = "postgresql://chatbot_hhjv_user:dYXguSEwpwZl3Yt2R3ACsfvmM5lLIgSD@dpg-d10sp295pdvs73afujf0-a.oregon-postgres.render.com/chatbot_hhjv"

def parse_database_url(url):
    """Parse PostgreSQL URL into connection parameters"""
    parsed = urlparse(url)
    return {
        'host': parsed.hostname,
        'port': parsed.port or 5432,
        'database': parsed.path[1:],
        'user': parsed.username,
        'password': parsed.password
    }

def get_tenant_data_count(cursor, tenant_id):
    """Get count of related data for a tenant"""
    counts = {}
    
    # Tables that reference tenant_id
    tables_to_check = [
        ('chat_sessions', 'tenant_id'),
        ('chat_messages', 'session_id'),  # Via chat_sessions
        ('knowledge_bases', 'tenant_id'),
        ('faqs', 'tenant_id'),
        ('tenant_subscriptions', 'tenant_id'),
        ('usage_logs', 'tenant_id'),
        ('pending_feedback', 'tenant_id'),
        ('tenant_credentials', 'tenant_id'),
        ('conversation_sessions', 'tenant_id')
    ]
    
    for table, column in tables_to_check:
        try:
            if table == 'chat_messages':
                # Chat messages are linked via sessions
                cursor.execute(f"""
                    SELECT COUNT(*) FROM {table} 
                    WHERE session_id IN (
                        SELECT id FROM chat_sessions WHERE tenant_id = %s
                    )
                """, (tenant_id,))
            else:
                cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE {column} = %s", (tenant_id,))
            
            count = cursor.fetchone()[0]
            if count > 0:
                counts[table] = count
        except psycopg2.Error:
            # Table might not exist
            pass
    
    return counts

def delete_tenant_completely():
    """Completely delete a tenant and all their data"""
    
    try:
        # Connect to database
        conn_params = parse_database_url(DATABASE_URL)
        conn = psycopg2.connect(**conn_params)
        cursor = conn.cursor()
        
        print("🔗 Connected to PostgreSQL database")
        
        # Get all tenants
        cursor.execute("""
            SELECT id, name, business_name, email, is_super_tenant, created_at
            FROM tenants 
            WHERE is_active = true
            ORDER BY created_at
        """)
        tenants = cursor.fetchall()
        
        if not tenants:
            print("❌ No tenants found!")
            return
        
        print(f"\n📋 Available tenants:")
        for i, (tenant_id, name, business_name, email, is_super, created_at) in enumerate(tenants, 1):
            status = "🔓 SUPER" if is_super else "👤 Regular"
            print(f"   {i}. {name} ({business_name}) - {email} - {status} - Created: {created_at.date()}")
        
        # Get user choice
        try:
            choice = int(input(f"\nSelect tenant to DELETE (1-{len(tenants)}): ")) - 1
            if choice < 0 or choice >= len(tenants):
                print("❌ Invalid choice!")
                return
        except ValueError:
            print("❌ Please enter a valid number!")
            return
        
        selected = tenants[choice]
        tenant_id, name, business_name, email, is_super, created_at = selected
        
        print(f"\n🎯 Selected for DELETION:")
        print(f"   👤 Name: {name}")
        print(f"   🏢 Business: {business_name}")
        print(f"   📧 Email: {email}")
        print(f"   🔓 Super Tenant: {'Yes' if is_super else 'No'}")
        print(f"   📅 Created: {created_at}")
        
        # Get data counts
        print(f"\n📊 Checking related data...")
        data_counts = get_tenant_data_count(cursor, tenant_id)
        
        if data_counts:
            print(f"📋 Data to be deleted:")
            for table, count in data_counts.items():
                print(f"   • {table}: {count} records")
        else:
            print("   ✅ No related data found")
        
        # Multiple confirmations for safety
        print(f"\n⚠️ ⚠️ ⚠️  DANGER ZONE  ⚠️ ⚠️ ⚠️")
        print(f"This will PERMANENTLY DELETE:")
        print(f"• Tenant: {name} ({business_name})")
        print(f"• Email: {email}")
        print(f"• ALL conversations and chat history")
        print(f"• ALL knowledge bases and FAQs")
        print(f"• ALL subscription and billing data")
        print(f"• ALL usage logs and analytics")
        print(f"• This action CANNOT be undone!")
        
        # First confirmation
        confirm1 = input(f"\nType 'DELETE' to confirm you want to delete {name}: ")
        if confirm1 != 'DELETE':
            print("❌ Cancelled - confirmation text didn't match")
            return
        
        # Second confirmation
        confirm2 = input(f"Type the tenant name '{name}' to double confirm: ")
        if confirm2 != name:
            print("❌ Cancelled - tenant name didn't match")
            return
        
        # Final confirmation
        confirm3 = input(f"Final confirmation - type 'YES DELETE EVERYTHING' to proceed: ")
        if confirm3 != 'YES DELETE EVERYTHING':
            print("❌ Cancelled - final confirmation failed")
            return
        
        print(f"\n🗑️ DELETING TENANT: {name}")
        print("=" * 50)
        
        # Start deletion process
        try:
            # Delete in reverse order of dependencies
            
            # 1. Delete chat messages (via sessions)
            if 'chat_messages' in data_counts:
                print(f"🗑️ Deleting chat messages...")
                cursor.execute("""
                    DELETE FROM chat_messages 
                    WHERE session_id IN (
                        SELECT id FROM chat_sessions WHERE tenant_id = %s
                    )
                """, (tenant_id,))
                print(f"   ✅ Deleted {cursor.rowcount} chat messages")
            
            # 2. Delete chat sessions
            if 'chat_sessions' in data_counts:
                print(f"🗑️ Deleting chat sessions...")
                cursor.execute("DELETE FROM chat_sessions WHERE tenant_id = %s", (tenant_id,))
                print(f"   ✅ Deleted {cursor.rowcount} chat sessions")
            
            # 3. Delete conversation sessions
            if 'conversation_sessions' in data_counts:
                print(f"🗑️ Deleting conversation sessions...")
                cursor.execute("DELETE FROM conversation_sessions WHERE tenant_id = %s", (tenant_id,))
                print(f"   ✅ Deleted {cursor.rowcount} conversation sessions")
            
            # 4. Delete pending feedback
            if 'pending_feedback' in data_counts:
                print(f"🗑️ Deleting pending feedback...")
                cursor.execute("DELETE FROM pending_feedback WHERE tenant_id = %s", (tenant_id,))
                print(f"   ✅ Deleted {cursor.rowcount} pending feedback records")
            
            # 5. Delete usage logs
            if 'usage_logs' in data_counts:
                print(f"🗑️ Deleting usage logs...")
                cursor.execute("DELETE FROM usage_logs WHERE tenant_id = %s", (tenant_id,))
                print(f"   ✅ Deleted {cursor.rowcount} usage logs")
            
            # 6. Delete tenant subscriptions
            if 'tenant_subscriptions' in data_counts:
                print(f"🗑️ Deleting subscriptions...")
                cursor.execute("DELETE FROM tenant_subscriptions WHERE tenant_id = %s", (tenant_id,))
                print(f"   ✅ Deleted {cursor.rowcount} subscriptions")
            
            # 7. Delete FAQs
            if 'faqs' in data_counts:
                print(f"🗑️ Deleting FAQs...")
                cursor.execute("DELETE FROM faqs WHERE tenant_id = %s", (tenant_id,))
                print(f"   ✅ Deleted {cursor.rowcount} FAQs")
            
            # 8. Delete knowledge bases
            if 'knowledge_bases' in data_counts:
                print(f"🗑️ Deleting knowledge bases...")
                cursor.execute("DELETE FROM knowledge_bases WHERE tenant_id = %s", (tenant_id,))
                print(f"   ✅ Deleted {cursor.rowcount} knowledge bases")
            
            # 9. Delete tenant credentials
            if 'tenant_credentials' in data_counts:
                print(f"🗑️ Deleting tenant credentials...")
                cursor.execute("DELETE FROM tenant_credentials WHERE tenant_id = %s", (tenant_id,))
                print(f"   ✅ Deleted {cursor.rowcount} credential records")
            
            # 10. Finally delete the tenant
            print(f"🗑️ Deleting tenant record...")
            cursor.execute("DELETE FROM tenants WHERE id = %s", (tenant_id,))
            print(f"   ✅ Deleted tenant record")
            
            # Commit all changes
            conn.commit()
            
            print("=" * 50)
            print(f"✅ TENANT COMPLETELY DELETED!")
            print(f"🗑️ Tenant '{name}' and all associated data has been permanently removed")
            print(f"📊 Total tables affected: {len(data_counts) + 1}")
            print("=" * 50)
            
        except psycopg2.Error as e:
            print(f"❌ Error during deletion: {e}")
            conn.rollback()
            print("🔄 All changes rolled back - no data was deleted")
            
    except psycopg2.Error as e:
        print(f"❌ Database error: {e}")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

def list_tenants_only():
    """Just list tenants without deleting"""
    
    try:
        conn_params = parse_database_url(DATABASE_URL)
        conn = psycopg2.connect(**conn_params)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, name, business_name, email, is_super_tenant, created_at
            FROM tenants 
            WHERE is_active = true
            ORDER BY created_at
        """)
        tenants = cursor.fetchall()
        
        if not tenants:
            print("📋 No tenants found")
            return
        
        print(f"\n📋 Current tenants ({len(tenants)}):")
        for tenant_id, name, business_name, email, is_super, created_at in tenants:
            status = "🔓 SUPER" if is_super else "👤 Regular"
            print(f"   • {name} ({business_name}) - {email} - {status}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    import sys
    
    print("🗑️ TENANT DELETION TOOL")
    print("=" * 40)
    print("⚠️ WARNING: This permanently deletes ALL tenant data!")
    
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        list_tenants_only()
    else:
        print("\nOptions:")
        print("  python delete_tenant.py        - Delete a tenant")
        print("  python delete_tenant.py list   - Just list tenants")
        
        choice = input("\nProceed with deletion? (y/N): ")
        if choice.lower() == 'y':
            delete_tenant_completely()
        else:
            print("❌ Cancelled")