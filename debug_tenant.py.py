# debug_tenant.py - Run this to check your tenant data

import sqlite3
import sys
import os

def debug_tenant_data(tenant_id=1, db_path="./chatbot.db"):
    """Debug tenant data and Slack configuration"""
    
    if not os.path.exists(db_path):
        print(f"❌ Database file {db_path} does not exist!")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        print(f"🔍 DEBUGGING TENANT {tenant_id}")
        print("=" * 50)
        
        # Check if tenant exists
        cursor.execute("SELECT * FROM tenants WHERE id = ?", (tenant_id,))
        tenant = cursor.fetchone()
        
        if not tenant:
            print(f"❌ Tenant {tenant_id} does not exist!")
            
            # Show all tenants
            cursor.execute("SELECT id, name, is_active FROM tenants")
            all_tenants = cursor.fetchall()
            print(f"\n📋 Available tenants:")
            for t in all_tenants:
                print(f"   ID: {t[0]}, Name: {t[1]}, Active: {t[2]}")
            return
        
        # Get column names
        cursor.execute("PRAGMA table_info(tenants);")
        columns = [col[1] for col in cursor.fetchall()]
        
        # Create tenant dict
        tenant_dict = dict(zip(columns, tenant))
        
        print(f"✅ Found tenant {tenant_id}")
        print(f"   Name: {tenant_dict.get('name', 'N/A')}")
        print(f"   Active: {tenant_dict.get('is_active', 'N/A')}")
        print(f"   API Key: {tenant_dict.get('api_key', 'N/A')}")
        
        # Check Slack fields
        print(f"\n🔍 SLACK CONFIGURATION:")
        slack_fields = [
            "slack_enabled",
            "slack_bot_token", 
            "slack_signing_secret",
            "slack_app_id",
            "slack_client_id",
            "slack_client_secret",
            "slack_team_id",
            "slack_bot_user_id"
        ]
        
        missing_fields = []
        for field in slack_fields:
            if field in tenant_dict:
                value = tenant_dict[field]
                if field in ["slack_bot_token", "slack_signing_secret", "slack_client_secret"]:
                    # Mask sensitive fields
                    display_value = f"{'SET' if value else 'NOT SET'}"
                else:
                    display_value = value
                print(f"   {field}: {display_value}")
            else:
                missing_fields.append(field)
                print(f"   {field}: ❌ MISSING")
        
        if missing_fields:
            print(f"\n❌ MISSING SLACK FIELDS: {missing_fields}")
            print("💡 Run the Slack migration: python migrations/add_slack.py")
        else:
            print(f"\n✅ All Slack fields present")
        
        # Check if properly configured
        if tenant_dict.get('slack_enabled') and tenant_dict.get('slack_bot_token') and tenant_dict.get('slack_signing_secret'):
            print(f"✅ Slack is properly configured for tenant {tenant_id}")
        else:
            print(f"❌ Slack is NOT properly configured:")
            print(f"   - Enabled: {tenant_dict.get('slack_enabled', False)}")
            print(f"   - Has Bot Token: {bool(tenant_dict.get('slack_bot_token'))}")
            print(f"   - Has Signing Secret: {bool(tenant_dict.get('slack_signing_secret'))}")
        
        # Show webhook URL
        print(f"\n🔗 WEBHOOK URL:")
        print(f"   http://localhost:8000/api/slack/webhook/{tenant_id}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()

def fix_tenant_slack_enabled(tenant_id=1, db_path="./chatbot.db"):
    """Fix tenant slack_enabled field if it's not set properly"""
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        print(f"🔧 Fixing Slack configuration for tenant {tenant_id}")
        
        # Enable Slack for this tenant
        cursor.execute("""
            UPDATE tenants 
            SET slack_enabled = 1 
            WHERE id = ? AND slack_bot_token IS NOT NULL AND slack_signing_secret IS NOT NULL
        """, (tenant_id,))
        
        affected_rows = cursor.rowcount
        conn.commit()
        
        if affected_rows > 0:
            print(f"✅ Enabled Slack for tenant {tenant_id}")
        else:
            print(f"❌ Could not enable Slack - check if bot token and signing secret are set")
        
    except Exception as e:
        print(f"❌ Error fixing tenant: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        tenant_id = int(sys.argv[1])
    else:
        tenant_id = 1
    
    print("🔍 TENANT DEBUG TOOL")
    print("=" * 50)
    
    # Debug tenant data
    debug_tenant_data(tenant_id)
    
    # Ask if user wants to fix
    response = input(f"\nWould you like to try to fix Slack configuration for tenant {tenant_id}? (y/n): ")
    
    if response.lower() in ['y', 'yes']:
        fix_tenant_slack_enabled(tenant_id)
        print("\n" + "=" * 50)
        print("AFTER FIX:")
        debug_tenant_data(tenant_id)