import psycopg2
import sys

# Database connection string
DB_URL = "postgresql://chatbot_hhjv_user:dYXguSEwpwZl3Yt2R3ACsfvmM5lLIgSD@dpg-d10sp295pdvs73afujf0-a.oregon-postgres.render.com/chatbot_hhjv"

def add_website_migration():
    """Add website migration changes"""
    
    conn = None
    try:
        print("Connecting to database...")
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        
        print("Adding website migration...")
        
        # 1. Add 'website' to enum
        print("- Adding 'website' to documenttype enum...")
        try:
            cur.execute("ALTER TYPE documenttype ADD VALUE 'website';")
            print("  ✅ Added 'website' to enum")
        except psycopg2.Error as e:
            if "already exists" in str(e):
                print("  ℹ️  'website' already exists in enum")
            else:
                raise e
        
        # 2. Make file_path nullable
        print("- Making file_path nullable...")
        cur.execute("""
            ALTER TABLE knowledge_bases 
            ALTER COLUMN file_path DROP NOT NULL;
        """)
        
        # 3. Add website-specific columns (one by one to handle existing columns)
        website_columns = [
            ("base_url", "VARCHAR(500)"),
            ("crawl_depth", "INTEGER DEFAULT 3"),
            ("crawl_frequency_hours", "INTEGER DEFAULT 24"),
            ("last_crawled_at", "TIMESTAMP WITH TIME ZONE"),
            ("pages_crawled", "INTEGER DEFAULT 0"),
            ("include_patterns", "JSONB"),
            ("exclude_patterns", "JSONB")
        ]
        
        print("- Adding website columns...")
        for col_name, col_def in website_columns:
            try:
                cur.execute(f"ALTER TABLE knowledge_bases ADD COLUMN {col_name} {col_def};")
                print(f"  ✅ Added column: {col_name}")
            except psycopg2.Error as e:
                if "already exists" in str(e):
                    print(f"  ℹ️  Column {col_name} already exists")
                else:
                    raise e
        
        # 4. Add check constraint
        print("- Adding check constraint...")
        try:
            cur.execute("""
                ALTER TABLE knowledge_bases 
                ADD CONSTRAINT chk_file_or_url CHECK (
                    (document_type = 'website' AND base_url IS NOT NULL AND file_path IS NULL) OR
                    (document_type != 'website' AND file_path IS NOT NULL AND base_url IS NULL)
                );
            """)
            print("  ✅ Added check constraint")
        except psycopg2.Error as e:
            if "already exists" in str(e):
                print("  ℹ️  Check constraint already exists")
            else:
                raise e
        
        # 5. Add indexes
        print("- Adding indexes...")
        indexes = [
            ("idx_knowledge_bases_crawl_schedule", 
             "ON knowledge_bases (document_type, processing_status, last_crawled_at) WHERE document_type = 'website'"),
            ("idx_knowledge_bases_tenant_website", 
             "ON knowledge_bases (tenant_id, document_type) WHERE document_type = 'website'")
        ]
        
        for idx_name, idx_def in indexes:
            try:
                cur.execute(f"CREATE INDEX {idx_name} {idx_def};")
                print(f"  ✅ Added index: {idx_name}")
            except psycopg2.Error as e:
                if "already exists" in str(e):
                    print(f"  ℹ️  Index {idx_name} already exists")
                else:
                    raise e
        
        # Commit changes
        conn.commit()
        print("✅ Website migration added successfully!")
        
        # Verify the changes
        print("\nVerifying changes...")
        cur.execute("SELECT unnest(enum_range(NULL::documenttype));")
        enum_values = [row[0] for row in cur.fetchall()]
        print(f"Current enum values: {enum_values}")
        
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'knowledge_bases' 
            AND column_name IN ('base_url', 'crawl_depth', 'include_patterns', 'exclude_patterns');
        """)
        website_cols = [row[0] for row in cur.fetchall()]
        print(f"Website columns present: {website_cols}")
        
        if 'website' in enum_values and len(website_cols) >= 4:
            print("✅ Migration appears successful!")
        else:
            print("❌ Migration may have issues")
        
    except psycopg2.Error as e:
        print(f"❌ Database error: {e}")
        if conn:
            conn.rollback()
        sys.exit(1)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        if conn:
            conn.rollback()
        sys.exit(1)
        
    finally:
        if conn:
            conn.close()
            print("Database connection closed.")

if __name__ == "__main__":
    print("🚀 Adding website migration...")
    print("This will:")
    print("1. Add 'website' to documenttype enum")
    print("2. Make file_path nullable")
    print("3. Add website-specific columns")
    print("4. Add check constraints and indexes")
    print()
    
    confirm = input("Are you sure you want to continue? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Aborted.")
        sys.exit(0)
    
    add_website_migration()