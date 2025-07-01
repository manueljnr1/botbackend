#!/usr/bin/env python3
"""
Fixed migration script for adding website crawling support
Handles PostgreSQL enum commit issue and SQLite table existence check
"""

import os
import sys
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import SQLAlchemyError

# Database URLs
POSTGRESQL_URL = "postgresql://chatbot_hhjv_user:dYXguSEwpwZl3Yt2R3ACsfvmM5lLIgSD@dpg-d10sp295pdvs73afujf0-a.oregon-postgres.render.com/chatbot_hhjv"
SQLITE_URL = "sqlite:///./chatbot.db"


def run_postgresql_migration():
    """Run PostgreSQL migration with proper transaction handling"""
    print("Running PostgreSQL migration...")
    
    engine = create_engine(POSTGRESQL_URL)
    
    # Step 1: Add enum value (needs separate transaction)
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TYPE documenttype ADD VALUE 'website'"))
            conn.commit()
            print("✅ Added 'website' to DocumentType enum")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("⚠️  'website' enum value already exists")
            else:
                print(f"❌ Failed to add enum value: {e}")
                return
    
    # Step 2: Add columns and constraints (new transaction)
    with engine.connect() as conn:
        with conn.begin():
            try:
                # Check if columns already exist
                inspector = inspect(engine)
                columns = [col['name'] for col in inspector.get_columns('knowledge_bases')]
                
                if 'base_url' in columns:
                    print("⚠️  Website columns already exist!")
                    return
                
                # Add new columns
                migrations = [
                    "ALTER TABLE knowledge_bases ADD COLUMN base_url VARCHAR(500)",
                    "ALTER TABLE knowledge_bases ADD COLUMN crawl_depth INTEGER DEFAULT 3",
                    "ALTER TABLE knowledge_bases ADD COLUMN crawl_frequency_hours INTEGER DEFAULT 24", 
                    "ALTER TABLE knowledge_bases ADD COLUMN last_crawled_at TIMESTAMP WITH TIME ZONE",
                    "ALTER TABLE knowledge_bases ADD COLUMN pages_crawled INTEGER DEFAULT 0",
                    "ALTER TABLE knowledge_bases ADD COLUMN include_patterns JSONB",
                    "ALTER TABLE knowledge_bases ADD COLUMN exclude_patterns JSONB"
                ]
                
                for migration in migrations:
                    conn.execute(text(migration))
                    print(f"✅ Added column")
                
                # Make file_path nullable
                conn.execute(text("ALTER TABLE knowledge_bases ALTER COLUMN file_path DROP NOT NULL"))
                print("✅ Made file_path nullable")
                
                # Add check constraint
                constraint_sql = """
                ALTER TABLE knowledge_bases 
                ADD CONSTRAINT chk_file_or_url CHECK (
                    (document_type = 'website' AND base_url IS NOT NULL AND file_path IS NULL) OR
                    (document_type != 'website' AND file_path IS NOT NULL AND base_url IS NULL)
                )
                """
                conn.execute(text(constraint_sql))
                print("✅ Added check constraint")
                
                # Add indexes
                index_sql = [
                    """CREATE INDEX idx_knowledge_bases_crawl_schedule 
                       ON knowledge_bases (document_type, processing_status, last_crawled_at) 
                       WHERE document_type = 'website'""",
                    """CREATE INDEX idx_knowledge_bases_tenant_website 
                       ON knowledge_bases (tenant_id, document_type) 
                       WHERE document_type = 'website'"""
                ]
                
                for sql in index_sql:
                    conn.execute(text(sql))
                    print(f"✅ Created index")
                
                print("\n🎉 PostgreSQL migration completed successfully!")
                
            except SQLAlchemyError as e:
                print(f"❌ Migration failed: {e}")
                raise


def run_sqlite_migration():
    """Run SQLite migration with table existence check"""
    print("Running SQLite migration...")
    
    engine = create_engine(SQLITE_URL)
    
    with engine.connect() as conn:
        with conn.begin():
            try:
                # Check if knowledge_bases table exists
                inspector = inspect(engine)
                tables = inspector.get_table_names()
                
                if 'knowledge_bases' not in tables:
                    print("⚠️  knowledge_bases table doesn't exist. Creating fresh table...")
                    # Create table from scratch
                    create_fresh_table(conn)
                    return
                
                # Check if migration already applied
                columns = [col['name'] for col in inspector.get_columns('knowledge_bases')]
                
                if 'base_url' in columns:
                    print("⚠️  Migration already applied!")
                    return
                
                # Create new table with updated schema
                create_table_sql = """
                CREATE TABLE knowledge_bases_new (
                    id INTEGER PRIMARY KEY,
                    tenant_id INTEGER,
                    name VARCHAR,
                    description TEXT,
                    file_path VARCHAR,
                    base_url VARCHAR(500),
                    document_type VARCHAR CHECK (document_type IN ('pdf', 'doc', 'docx', 'txt', 'csv', 'xlsx', 'website')),
                    vector_store_id VARCHAR UNIQUE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME,
                    processing_status VARCHAR CHECK (processing_status IN ('pending', 'processing', 'completed', 'failed')) DEFAULT 'pending',
                    processing_error TEXT,
                    processed_at DATETIME,
                    crawl_depth INTEGER DEFAULT 3,
                    crawl_frequency_hours INTEGER DEFAULT 24,
                    last_crawled_at DATETIME,
                    pages_crawled INTEGER DEFAULT 0,
                    include_patterns JSON,
                    exclude_patterns JSON,
                    FOREIGN KEY (tenant_id) REFERENCES tenants (id),
                    CHECK (
                        (document_type = 'website' AND base_url IS NOT NULL AND file_path IS NULL) OR
                        (document_type != 'website' AND file_path IS NOT NULL AND base_url IS NULL)
                    )
                )
                """
                conn.execute(text(create_table_sql))
                print("✅ Created new table with website support")
                
                # Copy existing data
                copy_sql = """
                INSERT INTO knowledge_bases_new (
                    id, tenant_id, name, description, file_path, document_type, 
                    vector_store_id, created_at, updated_at, processing_status, 
                    processing_error, processed_at
                )
                SELECT 
                    id, tenant_id, name, description, file_path, document_type,
                    vector_store_id, created_at, updated_at, processing_status,
                    processing_error, processed_at
                FROM knowledge_bases
                """
                conn.execute(text(copy_sql))
                print("✅ Copied existing data")
                
                # Drop old table and rename new one
                conn.execute(text("DROP TABLE knowledge_bases"))
                conn.execute(text("ALTER TABLE knowledge_bases_new RENAME TO knowledge_bases"))
                print("✅ Replaced old table")
                
                # Create indexes
                create_indexes(conn)
                
                print("\n🎉 SQLite migration completed successfully!")
                
            except SQLAlchemyError as e:
                print(f"❌ Migration failed: {e}")
                raise


def create_fresh_table(conn):
    """Create knowledge_bases table from scratch"""
    create_table_sql = """
    CREATE TABLE knowledge_bases (
        id INTEGER PRIMARY KEY,
        tenant_id INTEGER,
        name VARCHAR,
        description TEXT,
        file_path VARCHAR,
        base_url VARCHAR(500),
        document_type VARCHAR CHECK (document_type IN ('pdf', 'doc', 'docx', 'txt', 'csv', 'xlsx', 'website')),
        vector_store_id VARCHAR UNIQUE,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME,
        processing_status VARCHAR CHECK (processing_status IN ('pending', 'processing', 'completed', 'failed')) DEFAULT 'pending',
        processing_error TEXT,
        processed_at DATETIME,
        crawl_depth INTEGER DEFAULT 3,
        crawl_frequency_hours INTEGER DEFAULT 24,
        last_crawled_at DATETIME,
        pages_crawled INTEGER DEFAULT 0,
        include_patterns JSON,
        exclude_patterns JSON,
        FOREIGN KEY (tenant_id) REFERENCES tenants (id),
        CHECK (
            (document_type = 'website' AND base_url IS NOT NULL AND file_path IS NULL) OR
            (document_type != 'website' AND file_path IS NOT NULL AND base_url IS NULL)
        )
    )
    """
    conn.execute(text(create_table_sql))
    print("✅ Created fresh knowledge_bases table")
    
    create_indexes(conn)
    print("✅ Created indexes")


def create_indexes(conn):
    """Create indexes for knowledge_bases table"""
    index_sql = [
        "CREATE INDEX idx_knowledge_bases_crawl_schedule ON knowledge_bases (document_type, processing_status, last_crawled_at)",
        "CREATE INDEX idx_knowledge_bases_tenant_website ON knowledge_bases (tenant_id, document_type)",
        "CREATE INDEX ix_knowledge_bases_id ON knowledge_bases (id)",
        "CREATE INDEX ix_knowledge_bases_name ON knowledge_bases (name)",
        "CREATE UNIQUE INDEX ix_knowledge_bases_vector_store_id ON knowledge_bases (vector_store_id)"
    ]
    
    for sql in index_sql:
        try:
            conn.execute(text(sql))
        except Exception as e:
            if "already exists" not in str(e).lower():
                print(f"⚠️  Index creation warning: {e}")


def check_database_connection(db_url):
    """Test database connection"""
    try:
        engine = create_engine(db_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✅ Database connection successful")
        return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False


def main():
    """Main migration runner"""
    print("🚀 Starting database migration for website crawling support\n")
    
    # Determine which database to migrate
    if len(sys.argv) > 1:
        db_type = sys.argv[1].lower()
    else:
        db_type = input("Enter database type (postgresql/sqlite): ").lower()
    
    if db_type in ['postgresql', 'postgres', 'pg']:
        print("Testing PostgreSQL connection...")
        if check_database_connection(POSTGRESQL_URL):
            run_postgresql_migration()
        else:
            print("❌ Cannot connect to PostgreSQL database")
            sys.exit(1)
    elif db_type in ['sqlite', 'sqlite3']:
        print("Testing SQLite connection...")
        if check_database_connection(SQLITE_URL):
            run_sqlite_migration()
        else:
            print("❌ Cannot connect to SQLite database")
            sys.exit(1)
    else:
        print("❌ Invalid database type. Use 'postgresql' or 'sqlite'")
        sys.exit(1)


if __name__ == "__main__":
    main()