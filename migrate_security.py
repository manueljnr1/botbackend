#!/usr/bin/env python3
"""
Universal Database Migration Script
Adds security fields to both SQLite and PostgreSQL databases
"""

import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
import sys
import os
from urllib.parse import urlparse

# Database URLs
SQLITE_URL = "sqlite:///./chatbot.db"
POSTGRES_URL = "postgresql://chatbot_hhjv_user:dYXguSEwpwZl3Yt2R3ACsfvmM5lLIgSD@dpg-d10sp295pdvs73afujf0-a.oregon-postgres.render.com/chatbot_hhjv"

def parse_postgres_url(url):
    """Parse PostgreSQL URL into connection parameters"""
    parsed = urlparse(url)
    return {
        'host': parsed.hostname,
        'port': parsed.port or 5432,
        'database': parsed.path[1:],  # Remove leading slash
        'user': parsed.username,
        'password': parsed.password
    }

def migrate_sqlite():
    """Add security fields to SQLite database"""
    print("🔧 Migrating SQLite database...")
    
    # Extract database path from SQLite URL
    db_path = SQLITE_URL.replace("sqlite:///", "")
    
    if not os.path.exists(db_path):
        print(f"❌ SQLite database not found at: {db_path}")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if tenants table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tenants'")
        if not cursor.fetchone():
            print("❌ Tenants table not found in SQLite database")
            return False
        
        print("📋 Adding security fields to tenants table...")
        
        # Add security fields to tenants table (one by one to handle existing columns)
        security_fields = [
            ("system_prompt", "TEXT"),
            ("system_prompt_validated", "BOOLEAN DEFAULT FALSE"),
            ("system_prompt_updated_at", "DATETIME"),
            ("security_level", "VARCHAR(20) DEFAULT 'standard'"),
            ("allow_custom_prompts", "BOOLEAN DEFAULT TRUE"),
            ("security_notifications_enabled", "BOOLEAN DEFAULT TRUE")
        ]
        
        for field_name, field_type in security_fields:
            try:
                cursor.execute(f'ALTER TABLE tenants ADD COLUMN {field_name} {field_type}')
                print(f"  ✅ Added {field_name}")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e):
                    print(f"  ⚠️ {field_name} already exists, skipping...")
                else:
                    print(f"  ❌ Error adding {field_name}: {e}")
        
        print("📋 Creating security_incidents table...")
        
        # Create security_incidents table
        try:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS security_incidents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id INTEGER NOT NULL,
                    session_id VARCHAR(255),
                    user_identifier VARCHAR(255) NOT NULL,
                    platform VARCHAR(50) DEFAULT 'web',
                    risk_type VARCHAR(50) NOT NULL,
                    user_message TEXT NOT NULL,
                    security_response TEXT NOT NULL,
                    matched_patterns TEXT,
                    severity_score INTEGER DEFAULT 1,
                    detected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    reviewed BOOLEAN DEFAULT FALSE,
                    reviewer_notes TEXT,
                    FOREIGN KEY(tenant_id) REFERENCES tenants(id)
                )
            ''')
            print("  ✅ security_incidents table created")
            
            # Create indexes for better performance
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_security_incidents_tenant_detected ON security_incidents(tenant_id, detected_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_security_incidents_risk_type ON security_incidents(risk_type)')
            print("  ✅ Security indexes created")
            
        except sqlite3.Error as e:
            print(f"  ❌ Error creating security_incidents table: {e}")
        
        conn.commit()
        print("✅ SQLite migration completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ SQLite migration failed: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()

def migrate_postgresql():
    """Add security fields to PostgreSQL database"""
    print("🔧 Migrating PostgreSQL database...")
    
    try:
        # Parse connection parameters
        conn_params = parse_postgres_url(POSTGRES_URL)
        
        # Connect to PostgreSQL
        conn = psycopg2.connect(**conn_params)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Check if tenants table exists
        cursor.execute("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name = 'tenants'
        """)
        if not cursor.fetchone():
            print("❌ Tenants table not found in PostgreSQL database")
            return False
        
        print("📋 Adding security fields to tenants table...")
        
        # Add security fields to tenants table
        security_fields = [
            ("system_prompt", "TEXT"),
            ("system_prompt_validated", "BOOLEAN DEFAULT FALSE"),
            ("system_prompt_updated_at", "TIMESTAMP"),
            ("security_level", "VARCHAR(20) DEFAULT 'standard'"),
            ("allow_custom_prompts", "BOOLEAN DEFAULT TRUE"),
            ("security_notifications_enabled", "BOOLEAN DEFAULT TRUE")
        ]
        
        for field_name, field_type in security_fields:
            try:
                # Check if column already exists
                cursor.execute("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name = 'tenants' AND column_name = %s
                """, (field_name,))
                
                if cursor.fetchone():
                    print(f"  ⚠️ {field_name} already exists, skipping...")
                else:
                    cursor.execute(f'ALTER TABLE tenants ADD COLUMN {field_name} {field_type}')
                    print(f"  ✅ Added {field_name}")
            except psycopg2.Error as e:
                print(f"  ❌ Error adding {field_name}: {e}")
        
        print("📋 Creating security_incidents table...")
        
        # Create security_incidents table
        try:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS security_incidents (
                    id SERIAL PRIMARY KEY,
                    tenant_id INTEGER NOT NULL,
                    session_id VARCHAR(255),
                    user_identifier VARCHAR(255) NOT NULL,
                    platform VARCHAR(50) DEFAULT 'web',
                    risk_type VARCHAR(50) NOT NULL,
                    user_message TEXT NOT NULL,
                    security_response TEXT NOT NULL,
                    matched_patterns TEXT,
                    severity_score INTEGER DEFAULT 1,
                    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    reviewed BOOLEAN DEFAULT FALSE,
                    reviewer_notes TEXT,
                    FOREIGN KEY(tenant_id) REFERENCES tenants(id)
                )
            ''')
            print("  ✅ security_incidents table created")
            
            # Create indexes for better performance
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_security_incidents_tenant_detected ON security_incidents(tenant_id, detected_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_security_incidents_risk_type ON security_incidents(risk_type)')
            print("  ✅ Security indexes created")
            
        except psycopg2.Error as e:
            print(f"  ❌ Error creating security_incidents table: {e}")
        
        conn.commit()
        print("✅ PostgreSQL migration completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ PostgreSQL migration failed: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()

def verify_migration(db_type, connection_info):
    """Verify that migration was successful"""
    print(f"🔍 Verifying {db_type} migration...")
    
    try:
        if db_type == "SQLite":
            db_path = SQLITE_URL.replace("sqlite:///", "")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Check tenants table columns
            cursor.execute("PRAGMA table_info(tenants)")
            columns = [row[1] for row in cursor.fetchall()]
            
            # Check security_incidents table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='security_incidents'")
            security_table_exists = cursor.fetchone() is not None
            
        else:  # PostgreSQL
            conn_params = parse_postgres_url(POSTGRES_URL)
            conn = psycopg2.connect(**conn_params)
            cursor = conn.cursor()
            
            # Check tenants table columns
            cursor.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'tenants' ORDER BY column_name
            """)
            columns = [row[0] for row in cursor.fetchall()]
            
            # Check security_incidents table
            cursor.execute("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = 'security_incidents'
            """)
            security_table_exists = cursor.fetchone() is not None
        
        # Check for required security fields
        required_fields = [
            'system_prompt', 'system_prompt_validated', 'system_prompt_updated_at',
            'security_level', 'allow_custom_prompts', 'security_notifications_enabled'
        ]
        
        missing_fields = [field for field in required_fields if field not in columns]
        
        if missing_fields:
            print(f"  ❌ Missing fields in tenants table: {missing_fields}")
            return False
        
        if not security_table_exists:
            print(f"  ❌ security_incidents table not found")
            return False
        
        print(f"  ✅ All security fields present in tenants table")
        print(f"  ✅ security_incidents table exists")
        print(f"  ✅ {db_type} migration verification passed!")
        return True
        
    except Exception as e:
        print(f"  ❌ {db_type} verification failed: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()

def main():
    """Main migration function"""
    print("🚀 Starting database migration for security features...")
    print("=" * 60)
    
    # Migration results
    sqlite_success = False
    postgres_success = False
    
    # Migrate SQLite
    try:
        sqlite_success = migrate_sqlite()
        if sqlite_success:
            verify_migration("SQLite", SQLITE_URL)
    except Exception as e:
        print(f"❌ SQLite migration error: {e}")
    
    print("\n" + "=" * 60)
    
    # Migrate PostgreSQL
    try:
        postgres_success = migrate_postgresql()
        if postgres_success:
            verify_migration("PostgreSQL", POSTGRES_URL)
    except Exception as e:
        print(f"❌ PostgreSQL migration error: {e}")
    
    print("\n" + "=" * 60)
    print("📊 MIGRATION SUMMARY:")
    print(f"  SQLite:     {'✅ SUCCESS' if sqlite_success else '❌ FAILED'}")
    print(f"  PostgreSQL: {'✅ SUCCESS' if postgres_success else '❌ FAILED'}")
    
    if sqlite_success and postgres_success:
        print("\n🎉 All migrations completed successfully!")
        print("Your security system is now ready to use!")
    elif sqlite_success or postgres_success:
        print("\n⚠️ Partial success - some databases migrated successfully")
    else:
        print("\n💥 All migrations failed - please check the errors above")
    
    return sqlite_success and postgres_success

if __name__ == "__main__":
    # Install required packages if not available
    try:
        import psycopg2
    except ImportError:
        print("❌ psycopg2 not installed. Install with: pip install psycopg2-binary")
        sys.exit(1)
    
    success = main()
    sys.exit(0 if success else 1)