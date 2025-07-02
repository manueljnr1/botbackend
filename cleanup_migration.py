#!/usr/bin/env python3
"""
Database Cleanup and Migration Script
Fixes incomplete migration and applies website crawling support.

Usage: python cleanup_migration.py
"""

import sqlite3
import os
import sys

def cleanup_and_migrate():
    """Clean up incomplete migration and apply website crawling support"""
    
    db_path = "./chatbot.db"
    
    if not os.path.exists(db_path):
        print(f"❌ Database not found: {db_path}")
        return False
    
    print(f"🧹 Cleaning up and migrating database: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Step 1: Clean up any leftover tables
        print("🧹 Cleaning up leftover tables...")
        cursor.execute("DROP TABLE IF EXISTS knowledge_bases_new;")
        cursor.execute("DROP TABLE IF EXISTS knowledge_bases_backup;")
        print("✅ Cleanup completed")
        
        # Step 2: Check current table structure
        print("📊 Checking current table structure...")
        cursor.execute("PRAGMA table_info(knowledge_bases);")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        print(f"Found {len(columns)} columns")
        
        # Step 3: Get current table schema
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='knowledge_bases';")
        current_schema = cursor.fetchone()[0]
        print("📋 Current schema analyzed")
        
        # Step 4: Check if website is already supported
        if "'website'" in current_schema:
            print("✅ Website document type already supported")
            website_supported = True
        else:
            print("⚠️  Website document type needs to be added")
            website_supported = False
        
        # Step 5: Check if file_path allows NULL
        if 'file_path TEXT NOT NULL' in current_schema:
            print("⚠️  file_path has NOT NULL constraint - needs fixing")
            file_path_nullable = False
        else:
            print("✅ file_path already allows NULL")
            file_path_nullable = True
        
        # Step 6: Only recreate table if needed
        if not website_supported or not file_path_nullable:
            print("🔧 Recreating table with proper constraints...")
            
            # Create backup
            cursor.execute("""
                CREATE TABLE knowledge_bases_backup AS 
                SELECT * FROM knowledge_bases;
            """)
            print("💾 Created backup table")
            
            # Create new table with correct schema
            cursor.execute("""
                CREATE TABLE knowledge_bases_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    file_path TEXT,  -- NULL allowed for websites
                    document_type TEXT NOT NULL CHECK (document_type IN ('pdf', 'doc', 'docx', 'txt', 'csv', 'xlsx', 'website')),
                    vector_store_id TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP,
                    processing_status TEXT DEFAULT 'pending' CHECK (processing_status IN ('pending', 'processing', 'completed', 'failed')),
                    processing_error TEXT,
                    processed_at TIMESTAMP,
                    base_url TEXT,
                    crawl_depth INTEGER DEFAULT 3,
                    crawl_frequency_hours INTEGER DEFAULT 24,
                    last_crawled_at TIMESTAMP,
                    pages_crawled INTEGER DEFAULT 0,
                    include_patterns TEXT,
                    exclude_patterns TEXT,
                    FOREIGN KEY (tenant_id) REFERENCES tenants (id)
                );
            """)
            print("✅ Created new table with website support")
            
            # Copy all data
            cursor.execute("""
                INSERT INTO knowledge_bases_new (
                    id, tenant_id, name, description, file_path, document_type,
                    vector_store_id, created_at, updated_at, processing_status,
                    processing_error, processed_at, base_url, crawl_depth,
                    crawl_frequency_hours, last_crawled_at, pages_crawled,
                    include_patterns, exclude_patterns
                )
                SELECT 
                    id, tenant_id, name, description, file_path, document_type,
                    vector_store_id, created_at, updated_at, processing_status,
                    processing_error, processed_at, base_url, crawl_depth,
                    crawl_frequency_hours, last_crawled_at, pages_crawled,
                    include_patterns, exclude_patterns
                FROM knowledge_bases;
            """)
            print("📋 Copied all existing data")
            
            # Replace old table
            cursor.execute("DROP TABLE knowledge_bases;")
            cursor.execute("ALTER TABLE knowledge_bases_new RENAME TO knowledge_bases;")
            print("🔄 Replaced old table")
            
            # Clean up backup
            cursor.execute("DROP TABLE knowledge_bases_backup;")
            print("🧹 Removed backup table")
        else:
            print("✅ Table already has correct schema")
        
        # Step 7: Test website functionality
        print("🧪 Testing website functionality...")
        try:
            # Test insert
            cursor.execute("""
                INSERT INTO knowledge_bases (
                    tenant_id, name, document_type, vector_store_id, base_url
                ) VALUES (999999, 'Test Website', 'website', 'test_vector_id_123', 'https://example.com');
            """)
            
            # Test select
            cursor.execute("SELECT id, name, document_type, base_url FROM knowledge_bases WHERE tenant_id = 999999;")
            test_row = cursor.fetchone()
            
            if test_row:
                print(f"✅ Website test successful: {test_row}")
                # Clean up test data
                cursor.execute("DELETE FROM knowledge_bases WHERE tenant_id = 999999;")
            else:
                print("❌ Website test failed - no data inserted")
                return False
                
        except sqlite3.Error as e:
            print(f"❌ Website test failed: {e}")
            return False
        
        # Step 8: Commit all changes
        conn.commit()
        print("\n🎉 Migration completed successfully!")
        
        # Step 9: Final verification
        print("\n🔍 Final verification:")
        cursor.execute("PRAGMA table_info(knowledge_bases);")
        final_columns = [row[1] for row in cursor.fetchall()]
        
        required_columns = ['base_url', 'crawl_depth', 'crawl_frequency_hours', 
                           'last_crawled_at', 'pages_crawled', 'include_patterns', 'exclude_patterns']
        
        for col in required_columns:
            if col in final_columns:
                print(f"✅ {col}")
            else:
                print(f"❌ Missing: {col}")
        
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='knowledge_bases';")
        final_schema = cursor.fetchone()[0]
        if "'website'" in final_schema:
            print("✅ Website document type supported")
        else:
            print("❌ Website document type missing")
        
        return True
        
    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        try:
            conn.rollback()
        except:
            pass
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False
    finally:
        conn.close()

def show_current_status():
    """Show current database status"""
    db_path = "./chatbot.db"
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("\n📊 Current Database Status:")
        print("-" * 30)
        
        # Count knowledge bases by type
        cursor.execute("SELECT document_type, COUNT(*) FROM knowledge_bases GROUP BY document_type;")
        for doc_type, count in cursor.fetchall():
            print(f"📄 {doc_type}: {count} knowledge bases")
        
        # Check for websites
        cursor.execute("SELECT COUNT(*) FROM knowledge_bases WHERE document_type = 'website';")
        website_count = cursor.fetchone()[0]
        print(f"🌐 Websites: {website_count}")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Could not check status: {e}")

if __name__ == "__main__":
    print("🚀 Database Cleanup and Migration Tool")
    print("=" * 40)
    
    if not os.path.exists("./chatbot.db"):
        print("❌ chatbot.db not found in current directory")
        print("Please run this script from your project root directory")
        sys.exit(1)
    
    success = cleanup_and_migrate()
    
    if success:
        show_current_status()
        print("\n🎉 All done! Website crawling is now ready.")
        print("\nNext steps:")
        print("1. Restart your FastAPI application")
        print("2. Test website crawling in your HTML interface")
        print("3. Try creating a website knowledge base")
    else:
        print("\n❌ Migration failed. Please check the errors above.")
        sys.exit(1)