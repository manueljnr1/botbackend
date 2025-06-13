# convert_to_super_tenant.py
"""
Simple script to convert an existing tenant to super tenant in PostgreSQL
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

def convert_tenant_to_super():
    """Convert a tenant to super tenant"""
    
    try:
        # Connect to database
        conn_params = parse_database_url(DATABASE_URL)
        conn = psycopg2.connect(**conn_params)
        cursor = conn.cursor()
        
        print("🔗 Connected to PostgreSQL database")
        
        # Get all tenants
        cursor.execute("""
            SELECT id, name, business_name, email, is_super_tenant 
            FROM tenants 
            WHERE is_active = true
            ORDER BY created_at
        """)
        tenants = cursor.fetchall()
        
        if not tenants:
            print("❌ No tenants found!")
            return
        
        print(f"\n📋 Available tenants:")
        for i, (tenant_id, name, business_name, email, is_super) in enumerate(tenants, 1):
            status = "🔓 SUPER" if is_super else "👤 Regular"
            print(f"   {i}. {name} ({business_name}) - {email} - {status}")
        
        # Get user choice
        try:
            choice = int(input(f"\nSelect tenant to make super tenant (1-{len(tenants)}): ")) - 1
            if choice < 0 or choice >= len(tenants):
                print("❌ Invalid choice!")
                return
        except ValueError:
            print("❌ Please enter a valid number!")
            return
        
        selected = tenants[choice]
        tenant_id, name, business_name, email, is_super = selected
        
        if is_super:
            print(f"⚠️ {name} is already a super tenant!")
            return
        
        # Confirm
        print(f"\n🎯 Selected: {name} ({business_name})")
        print(f"📧 Email: {email}")
        confirm = input("\n⚠️ Convert this tenant to super tenant? (y/N): ")
        
        if confirm.lower() != 'y':
            print("❌ Cancelled")
            return
        
        # Convert to super tenant
        print(f"\n🔄 Converting {name} to super tenant...")
        
        cursor.execute("""
            UPDATE tenants 
            SET is_super_tenant = true, can_impersonate = true 
            WHERE id = %s
        """, (tenant_id,))
        
        conn.commit()
        
        # Get API key for reference
        cursor.execute("SELECT api_key FROM tenants WHERE id = %s", (tenant_id,))
        api_key = cursor.fetchone()[0]
        
        print(f"✅ SUCCESS! {name} is now a super tenant!")
        print("=" * 50)
        print(f"🔓 SUPER TENANT DETAILS:")
        print(f"   👤 Name: {name}")
        print(f"   🏢 Business: {business_name}")
        print(f"   📧 Email: {email}")
        print(f"   🔐 API Key: {api_key}")
        print("\n🎉 SUPER POWERS ACTIVATED:")
        print("   ✅ Unlimited conversations")
        print("   ✅ Unlimited integrations")
        print("   ✅ Can impersonate other tenants")
        print("   ✅ Bypasses all payment restrictions")
        print("=" * 50)
        
    except psycopg2.Error as e:
        print(f"❌ Database error: {e}")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    print("🔓 CONVERT TENANT TO SUPER TENANT")
    print("=" * 40)
    convert_tenant_to_super()