import psycopg2

DB_URL = "postgresql://chatbot_hhjv_user:dYXguSEwpwZl3Yt2R3ACsfvmM5lLIgSD@dpg-d10sp295pdvs73afujf0-a.oregon-postgres.render.com/chatbot_hhjv"

def execute_sql(sql_commands):
    """Execute SQL commands one by one with fresh connections"""
    
    for i, sql in enumerate(sql_commands, 1):
        print(f"Step {i}: {sql[:50]}...")
        
        conn = None
        try:
            # Fresh connection for each command
            conn = psycopg2.connect(DB_URL)
            conn.autocommit = True
            cur = conn.cursor()
            
            cur.execute(sql)
            print(f"  ✅ Success")
            
        except psycopg2.Error as e:
            if "already exists" in str(e) or "does not exist" in str(e):
                print(f"  ℹ️  Already done: {e}")
            else:
                print(f"  ❌ Error: {e}")
                
        finally:
            if conn:
                conn.close()

if __name__ == "__main__":
    print("🔧 Running simple migration fix...")
    
    # SQL commands to run one by one
    commands = [
        "ALTER TYPE documenttype ADD VALUE 'website';",  # Add this first
        "ALTER TABLE knowledge_bases ALTER COLUMN file_path DROP NOT NULL;",
        "ALTER TABLE knowledge_bases ADD COLUMN base_url VARCHAR(500);",
        "ALTER TABLE knowledge_bases ADD COLUMN crawl_depth INTEGER DEFAULT 3;", 
        "ALTER TABLE knowledge_bases ADD COLUMN crawl_frequency_hours INTEGER DEFAULT 24;",
        "ALTER TABLE knowledge_bases ADD COLUMN last_crawled_at TIMESTAMP WITH TIME ZONE;",
        "ALTER TABLE knowledge_bases ADD COLUMN pages_crawled INTEGER DEFAULT 0;",
        "ALTER TABLE knowledge_bases ADD COLUMN include_patterns JSONB;",
        "ALTER TABLE knowledge_bases ADD COLUMN exclude_patterns JSONB;"
    ]
    
    execute_sql(commands)
    
    print("\n✅ Migration fix completed!")
    print("Now try your website endpoint again.")