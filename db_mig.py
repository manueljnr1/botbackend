#!/usr/bin/env python3
"""
PostgreSQL Database Migration Script for Supabase
Add email confirmation fields to tenants table
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import os
import sys
from datetime import datetime

# Database configuration
DATABASE_URL = "postgresql://postgres.hkamqejkluurrnrfgskg:IqcUKwYmnUskG4RV@aws-0-us-east-2.pooler.supabase.com:6543/postgres"

def connect_to_db():
    """Connect to PostgreSQL database"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False  # We want to control transactions
        return conn
    except Exception as e:
        print(f"❌ Failed to connect to database: {e}")
        return None

def check_column_exists(cursor, table_name, column_name):
    """Check if a column exists in the table"""
    cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = %s AND column_name = %s
    """, (table_name, column_name))
    return cursor.fetchone() is not None

def run_migration():
    """Add email confirmation fields to tenants table"""
    
    conn = connect_to_db()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        print("📊 Starting PostgreSQL migration: Add email confirmation fields to tenants")
        
        # Check if tenants table exists
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_name = 'tenants'
        """)
        if not cursor.fetchone():
            print("❌ Tenants table not found!")
            return False
        
        # Check current tenant count
        cursor.execute("SELECT COUNT(*) as count FROM tenants")
        tenant_count = cursor.fetchone()['count']
        print(f"📋 Found {tenant_count} tenants in the database")
        
        # Check if migration already done
        if check_column_exists(cursor, 'tenants', 'email_confirmed'):
            print("⚠️ Email confirmation fields already exist. Skipping migration.")
            return True
        
        print("➕ Adding email confirmation fields...")
        
        # Begin transaction
        cursor.execute("BEGIN")
        
        # Add columns one by one with better error handling
        columns_to_add = [
            ("email_confirmed", "BOOLEAN NOT NULL DEFAULT FALSE"),
            ("email_confirmation_sent_at", "TIMESTAMPTZ"),
            ("registration_completed_at", "TIMESTAMPTZ"),
            ("email_confirmation_token", "TEXT"),
            ("confirmation_attempts", "INTEGER NOT NULL DEFAULT 0"),
            ("last_confirmation_attempt", "TIMESTAMPTZ")
        ]
        
        for column_name, column_def in columns_to_add:
            try:
                print(f"   Adding column: {column_name}")
                cursor.execute(f"ALTER TABLE tenants ADD COLUMN {column_name} {column_def}")
                print(f"   ✅ Added: {column_name}")
            except Exception as e:
                print(f"   ❌ Failed to add {column_name}: {e}")
                raise
        
        print("✅ All fields added successfully")
        
        # Update existing active tenants to be email_confirmed=TRUE (backward compatibility)
        print("📝 Updating existing active tenants...")
        cursor.execute("""
            UPDATE tenants 
            SET email_confirmed = TRUE 
            WHERE is_active = TRUE
        """)
        updated_count = cursor.rowcount
        print(f"📝 Updated {updated_count} existing active tenants to email_confirmed=TRUE")
        
        # Add indexes for better performance
        print("📊 Adding indexes...")
        try:
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tenants_email_confirmed ON tenants(email_confirmed)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tenants_confirmation_sent_at ON tenants(email_confirmation_sent_at)")
            print("✅ Indexes added successfully")
        except Exception as e:
            print(f"⚠️ Failed to add indexes (not critical): {e}")
        
        # Add comments
        print("📝 Adding column comments...")
        comments = [
            ("email_confirmed", "Whether the tenant has confirmed their email address"),
            ("email_confirmation_sent_at", "When the email confirmation was last sent"),
            ("registration_completed_at", "When the tenant completed their registration (after email confirmation)"),
            ("email_confirmation_token", "Token used for email confirmation (optional tracking)"),
            ("confirmation_attempts", "Number of email confirmation attempts"),
            ("last_confirmation_attempt", "Last time a confirmation email was requested")
        ]
        
        for column_name, comment in comments:
            try:
                cursor.execute(f"COMMENT ON COLUMN tenants.{column_name} IS %s", (comment,))
            except Exception as e:
                print(f"⚠️ Failed to add comment for {column_name}: {e}")
        
        # Commit transaction
        conn.commit()
        print("✅ Migration completed successfully!")
        
        # Verify the changes
        print("\n📋 Verifying migration...")
        cursor.execute("""
            SELECT 
                column_name, 
                data_type, 
                is_nullable, 
                column_default
            FROM information_schema.columns 
            WHERE table_name = 'tenants' 
                AND column_name IN (
                    'email_confirmed', 
                    'email_confirmation_sent_at', 
                    'registration_completed_at',
                    'email_confirmation_token',
                    'confirmation_attempts',
                    'last_confirmation_attempt'
                )
            ORDER BY column_name
        """)
        
        print("\n📊 New columns added:")
        for row in cursor.fetchall():
            nullable = "NULL" if row['is_nullable'] == 'YES' else "NOT NULL"
            default = row['column_default'] or "None"
            print(f"   {row['column_name']} ({row['data_type']}) - {nullable} - Default: {default}")
        
        # Final verification
        cursor.execute("""
            SELECT 
                COUNT(*) as total_tenants,
                COUNT(*) FILTER (WHERE email_confirmed = TRUE) as confirmed_tenants,
                COUNT(*) FILTER (WHERE email_confirmed = FALSE) as unconfirmed_tenants
            FROM tenants
        """)
        stats = cursor.fetchone()
        print(f"\n📈 Final stats:")
        print(f"   Total tenants: {stats['total_tenants']}")
        print(f"   Confirmed: {stats['confirmed_tenants']}")
        print(f"   Unconfirmed: {stats['unconfirmed_tenants']}")
        
        return True
        
    except psycopg2.Error as e:
        print(f"❌ PostgreSQL error: {e}")
        if conn:
            conn.rollback()
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def rollback_migration():
    """Remove email confirmation fields from tenants table"""
    
    conn = connect_to_db()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        
        print("🔄 Rolling back migration: Remove email confirmation fields")
        
        # Check if columns exist
        if not check_column_exists(cursor, 'tenants', 'email_confirmed'):
            print("⚠️ Email confirmation fields don't exist. Nothing to rollback.")
            return True
        
        # Begin transaction
        cursor.execute("BEGIN")
        
        # Drop columns
        columns_to_drop = [
            'last_confirmation_attempt',
            'confirmation_attempts', 
            'email_confirmation_token',
            'registration_completed_at',
            'email_confirmation_sent_at',
            'email_confirmed'
        ]
        
        for column_name in columns_to_drop:
            try:
                print(f"   Dropping column: {column_name}")
                cursor.execute(f"ALTER TABLE tenants DROP COLUMN IF EXISTS {column_name}")
                print(f"   ✅ Dropped: {column_name}")
            except Exception as e:
                print(f"   ❌ Failed to drop {column_name}: {e}")
                raise
        
        # Drop indexes
        print("📊 Dropping indexes...")
        try:
            cursor.execute("DROP INDEX IF EXISTS idx_tenants_email_confirmed")
            cursor.execute("DROP INDEX IF EXISTS idx_tenants_confirmation_sent_at")
            print("✅ Indexes dropped successfully")
        except Exception as e:
            print(f"⚠️ Failed to drop indexes: {e}")
        
        # Commit transaction
        conn.commit()
        print("✅ Rollback completed successfully!")
        
        return True
        
    except psycopg2.Error as e:
        print(f"❌ PostgreSQL error during rollback: {e}")
        if conn:
            conn.rollback()
        return False
    except Exception as e:
        print(f"❌ Unexpected error during rollback: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def test_connection():
    """Test database connection"""
    conn = connect_to_db()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT version()")
        version = cursor.fetchone()[0]
        print(f"✅ Connected to PostgreSQL: {version}")
        
        cursor.execute("SELECT COUNT(*) FROM tenants")
        count = cursor.fetchone()[0]
        print(f"📊 Found {count} tenants in database")
        
        return True
    except Exception as e:
        print(f"❌ Connection test failed: {e}")
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    print("🐘 PostgreSQL Migration Script - Email Confirmation Fields")
    print("=" * 60)
    
    # Check if psycopg2 is installed
    try:
        import psycopg2
    except ImportError:
        print("❌ psycopg2 not installed. Install it with:")
        print("   pip install psycopg2-binary")
        sys.exit(1)
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "test":
            print("🔍 Testing database connection...")
            success = test_connection()
        elif sys.argv[1] == "rollback":
            print("🔄 Running rollback migration...")
            success = rollback_migration()
        else:
            print("❌ Unknown command. Use: python script.py [test|rollback]")
            sys.exit(1)
    else:
        print("▶️ Running forward migration...")
        success = run_migration()
    
    if success:
        print("\n🎉 Operation completed successfully!")
        sys.exit(0)
    else:
        print("\n💥 Operation failed!")
        sys.exit(1)