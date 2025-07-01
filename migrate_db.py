#!/usr/bin/env python3
"""
Database Migration Script for Website Crawling Support
Adds website enum value and required columns to knowledge_bases table
"""

import os
import sys
import psycopg2
import sqlite3
from urllib.parse import urlparse

# Database URLs
PRODUCTION_URL = "postgresql://chatbot_hhjv_user:dYXguSEwpwZl3Yt2R3ACsfvmM5lLIgSD@dpg-d10sp295pdvs73afujf0-a.oregon-postgres.render.com/chatbot_hhjv"
SQLITE_URL = "sqlite:///./chatbot.db"

def migrate_postgresql(db_url=None):
    """Migrate PostgreSQL database"""
    url = db_url or PRODUCTION_URL
    print(f"🔄 Migrating PostgreSQL database: {url.split('@')[1].split('/')[0]}...")
    
    try:
        # Parse connection URL
        parsed = urlparse(url)
        
        # Connect to PostgreSQL
        conn = psycopg2.connect(
            host=parsed.hostname,
            database=parsed.path[1:],  # Remove leading slash
            user=parsed.username,
            password=parsed.password,
            port=parsed.port or 5432
        )
        
        cursor = conn.cursor()
        
        print("✅ Connected to PostgreSQL")
        
        # Check if 'website' enum value already exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT 1 FROM pg_enum 
                WHERE enumlabel = 'website' 
                AND enumtypid = (
                    SELECT oid FROM pg_type WHERE typname = 'documenttype'
                )
            );
        """)
        
        enum_exists = cursor.fetchone()[0]
        
        if not enum_exists:
            print("📝 Adding 'website' to documenttype enum...")
            cursor.execute("ALTER TYPE documenttype ADD VALUE 'website';")
            print("✅ Added 'website' enum value")
        else:
            print("ℹ️  'website' enum value already exists")
        
        # Add website-specific columns
        website_columns = [
            ("base_url", "VARCHAR(500)"),
            ("crawl_depth", "INTEGER DEFAULT 3"),
            ("crawl_frequency_hours", "INTEGER DEFAULT 24"),
            ("last_crawled_at", "TIMESTAMP WITH TIME ZONE"),
            ("pages_crawled", "INTEGER DEFAULT 0"),
            ("include_patterns", "JSONB"),
            ("exclude_patterns", "JSONB")
        ]
        
        for column_name, column_type in website_columns:
            # Check if column exists
            cursor.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'knowledge_bases' 
                    AND column_name = %s
                );
            """, (column_name,))
            
            column_exists = cursor.fetchone()[0]
            
            if not column_exists:
                print(f"📝 Adding column '{column_name}'...")
                cursor.execute(f"ALTER TABLE knowledge_bases ADD COLUMN {column_name} {column_type};")
                print(f"✅ Added column '{column_name}'")
            else:
                print(f"ℹ️  Column '{column_name}' already exists")
        
        # Make file_path nullable
        print("📝 Making file_path column nullable...")
        try:
            cursor.execute("ALTER TABLE knowledge_bases ALTER COLUMN file_path DROP NOT NULL;")
            print("✅ Made file_path nullable")
        except Exception as e:
            if "does not exist" in str(e):
                print("ℹ️  file_path constraint already removed")
            else:
                print(f"⚠️  Could not modify file_path: {e}")
        
        # Add indexes for performance
        indexes = [
            ("idx_knowledge_bases_crawl_schedule", 
             "CREATE INDEX IF NOT EXISTS idx_knowledge_bases_crawl_schedule ON knowledge_bases (document_type, processing_status, last_crawled_at) WHERE document_type = 'website';"),
            ("idx_knowledge_bases_tenant_website", 
             "CREATE INDEX IF NOT EXISTS idx_knowledge_bases_tenant_website ON knowledge_bases (tenant_id, document_type) WHERE document_type = 'website';")
        ]
        
        for index_name, index_sql in indexes:
            print(f"📝 Creating index '{index_name}'...")
            cursor.execute(index_sql)
            print(f"✅ Created index '{index_name}'")
        
        # Commit changes
        conn.commit()
        print("✅ PostgreSQL migration completed successfully!")
        
    except Exception as e:
        print(f"❌ PostgreSQL migration failed: {e}")
        if 'conn' in locals():
            conn.rollback()
        return False
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()
    
    return True

def migrate_sqlite():
    """Migrate SQLite database"""
    print("🔄 Migrating SQLite database...")
    
    try:
        # Connect to SQLite
        conn = sqlite3.connect("./chatbot.db")
        cursor = conn.cursor()
        
        print("✅ Connected to SQLite")
        
        # SQLite doesn't have ENUMs, so we just add columns
        website_columns = [
            ("base_url", "TEXT"),
            ("crawl_depth", "INTEGER DEFAULT 3"),
            ("crawl_frequency_hours", "INTEGER DEFAULT 24"),
            ("last_crawled_at", "TIMESTAMP"),
            ("pages_crawled", "INTEGER DEFAULT 0"),
            ("include_patterns", "TEXT"),  # JSON as TEXT in SQLite
            ("exclude_patterns", "TEXT")
        ]
        
        for column_name, column_type in website_columns:
            try:
                print(f"📝 Adding column '{column_name}'...")
                cursor.execute(f"ALTER TABLE knowledge_bases ADD COLUMN {column_name} {column_type};")
                print(f"✅ Added column '{column_name}'")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    print(f"ℹ️  Column '{column_name}' already exists")
                else:
                    raise
        
        # Add indexes
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_knowledge_bases_crawl_schedule ON knowledge_bases (document_type, processing_status, last_crawled_at);",
            "CREATE INDEX IF NOT EXISTS idx_knowledge_bases_tenant_website ON knowledge_bases (tenant_id, document_type);"
        ]
        
        for index_sql in indexes:
            cursor.execute(index_sql)
        
        print("✅ Created indexes")
        
        # Commit changes
        conn.commit()
        print("✅ SQLite migration completed successfully!")
        
    except Exception as e:
        print(f"❌ SQLite migration failed: {e}")
        return False
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()
    
    return True

def main():
    """Main migration function"""
    print("🚀 Starting database migration for website crawling support...\n")
    
    # Check which database to migrate
    if len(sys.argv) > 1:
        db_type = sys.argv[1].lower()
    else:
        print("Please specify database type:")
        print("  python migrate_db.py production    # Migrate production DB")
        print("  python migrate_db.py postgresql    # Migrate local PostgreSQL")
        print("  python migrate_db.py sqlite        # Migrate SQLite")
        return
    
    success = True
    
    if db_type == "production":
        print("🎯 Migrating PRODUCTION database...")
        success &= migrate_postgresql(PRODUCTION_URL)
    elif db_type in ["postgresql", "postgres"]:
        print("🏠 Migrating LOCAL PostgreSQL...")
        # Use local connection
        success &= migrate_postgresql("postgresql://localhost/your_local_db")
    elif db_type == "sqlite":
        success &= migrate_sqlite()
    else:
        print(f"❌ Unknown database type: {db_type}")
        return
    
    print()
    
    if success:
        print("🎉 Migration completed successfully!")
        if db_type == "production":
            print("\n📋 Next steps:")
            print("1. Your production database is now ready")
            print("2. Test the /knowledge-base/website endpoint")
            print("3. Create your first website knowledge base!")
        else:
            print("\n📋 Next steps:")
            print("1. Restart your FastAPI application")
            print("2. Test the endpoints")
    else:
        print("❌ Migration failed. Please check the errors above.")
        sys.exit(1)

if __name__ == "__main__":
    main()