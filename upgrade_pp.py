#!/usr/bin/env python3
"""
Direct PostgreSQL script to add tenant branding fields
Run this to add branding customization to your Render PostgreSQL database
"""

import psycopg2
import os
from datetime import datetime

# Your Render PostgreSQL connection string
DATABASE_URL = "postgresql://chatbot_hhjv_user:dYXguSEwpwZl3Yt2R3ACsfvmM5lLIgSD@dpg-d10sp295pdvs73afujf0-a.oregon-postgres.render.com/chatbot_hhjv"

def add_branding_fields():
    """Add branding fields to the tenants table"""
    
    try:
        # Connect to PostgreSQL
        print("🔌 Connecting to Render PostgreSQL...")
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        print("✅ Connected successfully!")
        
        # Check if tenants table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'tenants'
            );
        """)
        
        if not cursor.fetchone()[0]:
            print("❌ Error: 'tenants' table not found!")
            return False
        
        print("📋 Found 'tenants' table")
        
        # Check current columns
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'tenants' 
            AND table_schema = 'public'
            ORDER BY ordinal_position;
        """)
        
        existing_columns = [row[0] for row in cursor.fetchall()]
        print(f"📊 Current columns: {', '.join(existing_columns)}")
        
        # Define branding columns to add
        branding_columns = [
            ("primary_color", "VARCHAR(7) DEFAULT '#007bff'"),
            ("secondary_color", "VARCHAR(7) DEFAULT '#f0f4ff'"),
            ("text_color", "VARCHAR(7) DEFAULT '#222222'"),
            ("background_color", "VARCHAR(7) DEFAULT '#ffffff'"),
            ("user_bubble_color", "VARCHAR(7) DEFAULT '#007bff'"),
            ("bot_bubble_color", "VARCHAR(7) DEFAULT '#f0f4ff'"),
            ("border_color", "VARCHAR(7) DEFAULT '#e0e0e0'"),
            ("logo_image_url", "VARCHAR(500)"),
            ("logo_text", "VARCHAR(10)"),
            ("border_radius", "VARCHAR(20) DEFAULT '12px'"),
            ("widget_position", "VARCHAR(20) DEFAULT 'bottom-right'"),
            ("font_family", "VARCHAR(100) DEFAULT 'Inter, sans-serif'"),
            ("custom_css", "TEXT"),
            ("branding_updated_at", "TIMESTAMPTZ"),
            ("branding_version", "INTEGER DEFAULT 1")
        ]
        
        # Add columns that don't exist
        columns_added = 0
        for column_name, column_def in branding_columns:
            if column_name not in existing_columns:
                print(f"➕ Adding column: {column_name}")
                
                sql = f"ALTER TABLE tenants ADD COLUMN {column_name} {column_def};"
                cursor.execute(sql)
                columns_added += 1
            else:
                print(f"⏭️  Column already exists: {column_name}")
        
        if columns_added > 0:
            # Update existing tenants with default values
            print("🔄 Updating existing tenants with default branding...")
            
            cursor.execute("""
                UPDATE tenants 
                SET 
                    primary_color = COALESCE(primary_color, '#007bff'),
                    secondary_color = COALESCE(secondary_color, '#f0f4ff'),
                    text_color = COALESCE(text_color, '#222222'),
                    background_color = COALESCE(background_color, '#ffffff'),
                    user_bubble_color = COALESCE(user_bubble_color, '#007bff'),
                    bot_bubble_color = COALESCE(bot_bubble_color, '#f0f4ff'),
                    border_color = COALESCE(border_color, '#e0e0e0'),
                    border_radius = COALESCE(border_radius, '12px'),
                    widget_position = COALESCE(widget_position, 'bottom-right'),
                    font_family = COALESCE(font_family, 'Inter, sans-serif'),
                    branding_version = COALESCE(branding_version, 1)
                WHERE id IS NOT NULL;
            """)
            
            # Set logo_text from business_name
            cursor.execute("""
                UPDATE tenants 
                SET logo_text = UPPER(LEFT(COALESCE(business_name, name, 'AI'), 2))
                WHERE logo_text IS NULL OR logo_text = '';
            """)
            
            updated_count = cursor.rowcount
            print(f"✅ Updated {updated_count} existing tenants")
        
        # Commit changes
        conn.commit()
        
        # Verify the additions
        cursor.execute("""
            SELECT column_name, data_type, column_default
            FROM information_schema.columns 
            WHERE table_name = 'tenants' 
            AND table_schema = 'public'
            AND column_name LIKE ANY (ARRAY['%color%', '%logo%', '%branding%', '%widget%', '%border%', '%font%', '%css%'])
            ORDER BY column_name;
        """)
        
        new_columns = cursor.fetchall()
        print(f"\n🎨 Branding columns now in database:")
        for col_name, col_type, col_default in new_columns:
            default_str = f" (default: {col_default})" if col_default else ""
            print(f"   📌 {col_name}: {col_type}{default_str}")
        
        # Test with a sample tenant
        cursor.execute("""
            SELECT id, name, business_name, primary_color, logo_text, widget_position
            FROM tenants 
            LIMIT 3;
        """)
        
        sample_tenants = cursor.fetchall()
        print(f"\n📋 Sample tenant data:")
        for tenant in sample_tenants:
            tenant_id, name, business_name, primary_color, logo_text, widget_position = tenant
            print(f"   🏢 {name} ({business_name}): {primary_color}, logo='{logo_text}', pos={widget_position}")
        
        print(f"\n🎉 Successfully added {columns_added} branding columns!")
        print("🚀 Your tenants table is now ready for color customization!")
        
        return True
        
    except psycopg2.Error as e:
        print(f"❌ PostgreSQL Error: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()
        print("🔌 Database connection closed")

def test_connection():
    """Test if we can connect to the database"""
    try:
        print("🧪 Testing database connection...")
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        print(f"✅ Connected to: {version}")
        
        cursor.execute("SELECT COUNT(*) FROM tenants;")
        count = cursor.fetchone()[0]
        print(f"📊 Found {count} tenants in database")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Connection test failed: {e}")
        return False

if __name__ == "__main__":
    print("🎨 Tenant Branding Database Setup")
    print("=" * 50)
    
    # Test connection first
    if not test_connection():
        print("\n❌ Cannot connect to database. Please check your connection string.")
        exit(1)
    
    print("\n" + "=" * 50)
    
    # Add branding fields
    success = add_branding_fields()
    
    if success:
        print("\n🎉 SUCCESS! Your database is ready for tenant branding!")
        print("\nNext steps:")
        print("1. Update your Tenant model with the new fields")
        print("2. Update your /chatbot/tenant-info API endpoint") 
        print("3. Deploy your changes")
        print("4. Test the enhanced widget!")
    else:
        print("\n❌ Setup failed. Please check the error messages above.")

# Additional utility functions
def rollback_branding_fields():
    """Remove branding fields (if needed)"""
    branding_columns = [
        "primary_color", "secondary_color", "text_color", "background_color",
        "user_bubble_color", "bot_bubble_color", "border_color", "logo_image_url",
        "logo_text", "border_radius", "widget_position", "font_family",
        "custom_css", "branding_updated_at", "branding_version"
    ]
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        for column in branding_columns:
            try:
                cursor.execute(f"ALTER TABLE tenants DROP COLUMN IF EXISTS {column};")
                print(f"🗑️  Removed column: {column}")
            except:
                pass
        
        conn.commit()
        cursor.close()
        conn.close()
        print("✅ Rollback completed")
        
    except Exception as e:
        print(f"❌ Rollback failed: {e}")

def show_tenant_branding(tenant_id=None):
    """Show current branding for tenants"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        if tenant_id:
            cursor.execute("""
                SELECT id, name, business_name, primary_color, secondary_color, 
                       logo_text, logo_image_url, widget_position
                FROM tenants WHERE id = %s;
            """, (tenant_id,))
        else:
            cursor.execute("""
                SELECT id, name, business_name, primary_color, secondary_color,
                       logo_text, logo_image_url, widget_position
                FROM tenants LIMIT 5;
            """)
        
        tenants = cursor.fetchall()
        print("\n🎨 Current Tenant Branding:")
        print("-" * 80)
        
        for tenant in tenants:
            tid, name, business_name, primary, secondary, logo_text, logo_url, position = tenant
            print(f"ID: {tid} | {name} ({business_name})")
            print(f"   Colors: {primary} / {secondary}")
            print(f"   Logo: {logo_text} | URL: {logo_url or 'None'}")
            print(f"   Position: {position}")
            print("-" * 80)
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error showing branding: {e}")

# Uncomment these lines to run utility functions:
# rollback_branding_fields()  # To remove all branding fields
# show_tenant_branding()      # To see current branding
# show_tenant_branding(1)     # To see specific tenant branding