#!/usr/bin/env python3
"""
Cleanup and Migration Script
Cleans up any failed migration attempts and runs a fresh migration
"""

import sqlite3
import psycopg2
import sys
import urllib.parse as urlparse

POSTGRES_DB = "postgresql://chatbot_hhjv_user:dYXguSEwpwZl3Yt2R3ACsfvmM5lLIgSD@dpg-d10sp295pdvs73afujf0-a.oregon-postgres.render.com/chatbot_hhjv"

def cleanup_postgresql():
    """Clean up any failed PostgreSQL migration attempts"""
    print("🧹 Cleaning up PostgreSQL...")
    
    try:
        url = urlparse.urlparse(POSTGRES_DB)
        conn = psycopg2.connect(
            host=url.hostname,
            port=url.port,
            database=url.path[1:],
            user=url.username,
            password=url.password,
            sslmode='require'
        )
        
        cursor = conn.cursor()
        
        # Drop the columns if they exist
        print("🗑️  Dropping existing columns...")
        cursor.execute("""
            ALTER TABLE knowledge_bases 
            DROP COLUMN IF EXISTS processing_status,
            DROP COLUMN IF EXISTS processing_error,
            DROP COLUMN IF EXISTS processed_at
        """)
        
        # Drop the enum type if it exists
        print("🗑️  Dropping enum type...")
        cursor.execute("DROP TYPE IF EXISTS processingstatus CASCADE")
        
        # Drop the index if it exists
        cursor.execute("DROP INDEX IF EXISTS idx_knowledge_bases_processing_status")
        
        conn.commit()
        conn.close()
        
        print("✅ PostgreSQL cleanup completed")
        return True
        
    except Exception as e:
        print(f"❌ PostgreSQL cleanup failed: {e}")
        return False

def fresh_postgresql_migration():
    """Run a fresh PostgreSQL migration"""
    print("🔧 Running fresh PostgreSQL migration...")
    
    try:
        url = urlparse.urlparse(POSTGRES_DB)
        conn = psycopg2.connect(
            host=url.hostname,
            port=url.port,
            database=url.path[1:],
            user=url.username,
            password=url.password,
            sslmode='require'
        )
        
        cursor = conn.cursor()
        
        # Create enum type with UPPERCASE values to match Python enum
        print("📝 Creating enum type...")
        cursor.execute("""
            CREATE TYPE processingstatus AS ENUM ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')
        """)
        
        # Add columns
        print("📝 Adding columns...")
        cursor.execute("""
            ALTER TABLE knowledge_bases 
            ADD COLUMN processing_status processingstatus DEFAULT 'PENDING'
        """)
        
        cursor.execute("""
            ALTER TABLE knowledge_bases 
            ADD COLUMN processing_error TEXT
        """)
        
        cursor.execute("""
            ALTER TABLE knowledge_bases 
            ADD COLUMN processed_at TIMESTAMP
        """)
        
        # Update existing records
        print("🔄 Updating existing records...")
        cursor.execute("""
            UPDATE knowledge_bases 
            SET processing_status = 'COMPLETED', 
                processed_at = updated_at 
            WHERE vector_store_id IS NOT NULL AND vector_store_id != ''
        """)
        
        # Create index
        cursor.execute("""
            CREATE INDEX idx_knowledge_bases_processing_status 
            ON knowledge_bases(processing_status)
        """)
        
        # Verify
        cursor.execute("SELECT COUNT(*) FROM knowledge_bases WHERE processing_status = 'COMPLETED'")
        updated_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT processing_status, COUNT(*) FROM knowledge_bases GROUP BY processing_status")
        status_counts = cursor.fetchall()
        
        conn.commit()
        conn.close()
        
        print(f"✅ PostgreSQL migration completed!")
        print(f"   - Updated {updated_count} existing records to 'COMPLETED' status")
        print(f"   - Status distribution: {status_counts}")
        
        return True
        
    except Exception as e:
        print(f"❌ PostgreSQL migration failed: {e}")
        return False

def main():
    """Main cleanup and migration function"""
    print("🚀 Starting cleanup and fresh migration")
    print("=" * 50)
    
    # Clean up PostgreSQL
    if not cleanup_postgresql():
        print("❌ Cleanup failed, aborting")
        return False
    
    # Run fresh migration
    if not fresh_postgresql_migration():
        print("❌ Migration failed")
        return False
    
    print("\n" + "=" * 50)
    print("🎉 Cleanup and migration completed successfully!")
    print("\n💡 Next steps:")
    print("   1. Restart your FastAPI application")
    print("   2. Test the chatbot functionality")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)