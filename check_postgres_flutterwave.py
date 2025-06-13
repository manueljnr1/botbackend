# check_postgres_flutterwave.py
"""
Check if Flutterwave columns exist in PostgreSQL and add if missing
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

def check_and_add_flutterwave_columns():
    """Check if Flutterwave columns exist and add if missing"""
    
    try:
        # Connect to PostgreSQL
        conn_params = parse_database_url(DATABASE_URL)
        conn = psycopg2.connect(**conn_params)
        cursor = conn.cursor()
        
        print("🔗 Connected to PostgreSQL database")
        
        # Check if tenant_subscriptions table exists
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_name = 'tenant_subscriptions' AND table_schema = 'public'
        """)
        table_exists = cursor.fetchone()
        
        if not table_exists:
            print("⚠️ tenant_subscriptions table does not exist yet")
            print("   This is normal if you haven't created subscriptions yet")
            return
        
        # Check current columns in tenant_subscriptions
        cursor.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns 
            WHERE table_name = 'tenant_subscriptions' AND table_schema = 'public'
            ORDER BY ordinal_position
        """)
        columns = cursor.fetchall()
        
        print(f"\n📋 Current tenant_subscriptions table structure:")
        column_names = []
        for col_name, data_type, nullable in columns:
            column_names.append(col_name)
            print(f"   {col_name}: {data_type} ({'NULL' if nullable == 'YES' else 'NOT NULL'})")
        
        # Check for Flutterwave columns
        flutterwave_columns = [
            'flutterwave_tx_ref',
            'flutterwave_flw_ref', 
            'flutterwave_customer_id'
        ]
        
        missing_columns = [col for col in flutterwave_columns if col not in column_names]
        
        if not missing_columns:
            print(f"\n✅ All Flutterwave columns are present!")
            for col in flutterwave_columns:
                print(f"   ✅ {col}")
            return True
        
        print(f"\n⚠️ Missing Flutterwave columns: {missing_columns}")
        
        # Ask if user wants to add them
        add_columns = input("\nAdd missing Flutterwave columns? (y/N): ")
        if add_columns.lower() != 'y':
            print("❌ Cancelled")
            return False
        
        # Add missing columns
        for col_name in missing_columns:
            print(f"➕ Adding {col_name} column...")
            cursor.execute(f"""
                ALTER TABLE tenant_subscriptions 
                ADD COLUMN {col_name} VARCHAR(255)
            """)
            print(f"✅ Added {col_name}")
        
        conn.commit()
        
        # Verify additions
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'tenant_subscriptions' AND table_schema = 'public'
            AND column_name IN ('flutterwave_tx_ref', 'flutterwave_flw_ref', 'flutterwave_customer_id')
        """)
        added_columns = [row[0] for row in cursor.fetchall()]
        
        print(f"\n✅ Successfully added Flutterwave columns:")
        for col in added_columns:
            print(f"   ✅ {col}")
        
        return True
        
    except psycopg2.Error as e:
        print(f"❌ PostgreSQL error: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()
            print("🔒 Database connection closed")

def check_all_pricing_tables():
    """Check all pricing-related tables structure"""
    
    try:
        conn_params = parse_database_url(DATABASE_URL)
        conn = psycopg2.connect(**conn_params)
        cursor = conn.cursor()
        
        print("🔍 Checking all pricing-related tables...")
        
        pricing_tables = [
            'pricing_plans',
            'tenant_subscriptions', 
            'usage_logs',
            'billing_history',
            'conversation_sessions'
        ]
        
        for table in pricing_tables:
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_name = %s AND table_schema = 'public'
            """, (table,))
            
            if cursor.fetchone():
                cursor.execute("""
                    SELECT column_name, data_type
                    FROM information_schema.columns 
                    WHERE table_name = %s AND table_schema = 'public'
                    ORDER BY ordinal_position
                """, (table,))
                columns = cursor.fetchall()
                
                print(f"\n📋 {table}:")
                for col_name, data_type in columns:
                    print(f"   • {col_name}: {data_type}")
            else:
                print(f"\n❌ {table}: Table does not exist")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    import sys
    
    print("💳 FLUTTERWAVE COLUMNS CHECKER")
    print("=" * 40)
    
    if len(sys.argv) > 1 and sys.argv[1] == "check-all":
        check_all_pricing_tables()
    else:
        print("Options:")
        print("  python check_postgres_flutterwave.py           - Check/add Flutterwave columns")
        print("  python check_postgres_flutterwave.py check-all - Check all pricing tables")
        print()
        
        check_and_add_flutterwave_columns()