#!/usr/bin/env python3
"""
Database Migration Script: Add allowed_origins column to tenants table
Supports both SQLite and PostgreSQL (Supabase)
"""

import sqlite3
import psycopg2
from psycopg2 import sql
import sys
import os
from urllib.parse import urlparse

# Database configurations
SQLITE_PATH = "./chatbot.db"
POSTGRESQL_URL = "postgresql://postgres.hkamqejkluurrnrfgskg:IqcUKwYmnUskG4RV@aws-0-us-east-2.pooler.supabase.com:6543/postgres"

def parse_postgresql_url(url):
    """Parse PostgreSQL URL into connection parameters"""
    parsed = urlparse(url)
    return {
        'host': parsed.hostname,
        'port': parsed.port,
        'database': parsed.path[1:],  # Remove leading '/'
        'user': parsed.username,
        'password': parsed.password
    }

def check_column_exists_sqlite(cursor, table_name, column_name):
    """Check if column exists in SQLite table"""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    return column_name in columns

def check_column_exists_postgresql(cursor, table_name, column_name):
    """Check if column exists in PostgreSQL table"""
    cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = %s AND column_name = %s
    """, (table_name, column_name))
    return cursor.fetchone() is not None

def add_column_sqlite():
    """Add allowed_origins column to SQLite database"""
    print("🔧 Processing SQLite database...")
    
    try:
        # Check if file exists
        if not os.path.exists(SQLITE_PATH):
            print(f"❌ SQLite database not found at: {SQLITE_PATH}")
            return False
        
        # Connect to SQLite
        conn = sqlite3.connect(SQLITE_PATH)
        cursor = conn.cursor()
        
        # Check if tenants table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tenants'")
        if not cursor.fetchone():
            print("❌ Tenants table not found in SQLite database")
            conn.close()
            return False
        
        # Check if column already exists
        if check_column_exists_sqlite(cursor, 'tenants', 'allowed_origins'):
            print("✅ Column 'allowed_origins' already exists in SQLite tenants table")
            conn.close()
            return True
        
        # Add the column
        cursor.execute("ALTER TABLE tenants ADD COLUMN allowed_origins TEXT")
        conn.commit()
        
        print("✅ Successfully added 'allowed_origins' column to SQLite tenants table")
        
        # Verify the column was added
        cursor.execute("PRAGMA table_info(tenants)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'allowed_origins' in columns:
            print("✅ Column verified in SQLite database")
        else:
            print("❌ Column verification failed in SQLite database")
            return False
        
        conn.close()
        return True
        
    except sqlite3.Error as e:
        print(f"❌ SQLite error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error with SQLite: {e}")
        return False

def add_column_postgresql():
    """Add allowed_origins column to PostgreSQL database"""
    print("🔧 Processing PostgreSQL (Supabase) database...")
    
    try:
        # Parse connection URL
        conn_params = parse_postgresql_url(POSTGRESQL_URL)
        
        # Connect to PostgreSQL
        conn = psycopg2.connect(**conn_params)
        cursor = conn.cursor()
        
        # Check if tenants table exists
        cursor.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'tenants')")
        if not cursor.fetchone()[0]:
            print("❌ Tenants table not found in PostgreSQL database")
            conn.close()
            return False
        
        # Check if column already exists
        if check_column_exists_postgresql(cursor, 'tenants', 'allowed_origins'):
            print("✅ Column 'allowed_origins' already exists in PostgreSQL tenants table")
            conn.close()
            return True
        
        # Add the column
        cursor.execute("ALTER TABLE tenants ADD COLUMN allowed_origins TEXT")
        conn.commit()
        
        print("✅ Successfully added 'allowed_origins' column to PostgreSQL tenants table")
        
        # Verify the column was added
        if check_column_exists_postgresql(cursor, 'tenants', 'allowed_origins'):
            print("✅ Column verified in PostgreSQL database")
        else:
            print("❌ Column verification failed in PostgreSQL database")
            return False
        
        conn.close()
        return True
        
    except psycopg2.Error as e:
        print(f"❌ PostgreSQL error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error with PostgreSQL: {e}")
        return False

def main():
    """Main migration function"""
    print("🚀 Starting database migration: Adding 'allowed_origins' column to tenants table")
    print("=" * 70)
    
    sqlite_success = False
    postgresql_success = False
    
    # Process SQLite
    print("\n1️⃣ SQLite Migration:")
    sqlite_success = add_column_sqlite()
    
    # Process PostgreSQL
    print("\n2️⃣ PostgreSQL Migration:")
    postgresql_success = add_column_postgresql()
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 Migration Summary:")
    print(f"   SQLite:     {'✅ Success' if sqlite_success else '❌ Failed'}")
    print(f"   PostgreSQL: {'✅ Success' if postgresql_success else '❌ Failed'}")
    
    if sqlite_success and postgresql_success:
        print("\n🎉 All migrations completed successfully!")
        print("\n📝 Next steps:")
        print("   1. Restart your FastAPI application")
        print("   2. Test the new CORS functionality")
        print("   3. Add allowed_origins for your tenants")
        return 0
    else:
        print("\n⚠️  Some migrations failed. Please check the errors above.")
        return 1

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚡ Migration interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        sys.exit(1)