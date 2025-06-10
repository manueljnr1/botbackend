import psycopg2
import urllib.parse as urlparse

# Updated connection string
POSTGRES_URL = "postgresql://chatbot_hhjv_user:dYXguSEwpwZl3Yt2R3ACsfvmM5lLIgSD@dpg-d10sp295pdvs73afujf0-a.oregon-postgres.render.com/chatbot_hhjv"

def quick_migrate():
    try:
        # Parse URL
        url = urlparse.urlparse(POSTGRES_URL)
        
        # Connect with SSL
        conn = psycopg2.connect(
            database=url.path[1:],
            user=url.username,
            password=url.password,
            host=url.hostname,
            port=url.port or 5432,
            sslmode='require'
        )
        
        cursor = conn.cursor()
        
        # Run migration
        migration_sql = """
        BEGIN;
        ALTER TABLE pending_feedback 
        ADD COLUMN IF NOT EXISTS form_accessed BOOLEAN DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS form_accessed_at TIMESTAMP,
        ADD COLUMN IF NOT EXISTS form_expired BOOLEAN DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS add_to_faq BOOLEAN DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS faq_created BOOLEAN DEFAULT FALSE;
        CREATE INDEX IF NOT EXISTS idx_pending_feedback_form_status 
        ON pending_feedback(feedback_id, form_expired, form_accessed);
        UPDATE pending_feedback 
        SET form_accessed = COALESCE(form_accessed, FALSE), 
            form_expired = COALESCE(form_expired, FALSE), 
            add_to_faq = COALESCE(add_to_faq, FALSE), 
            faq_created = COALESCE(faq_created, FALSE);
        COMMIT;
        """
        
        cursor.execute(migration_sql)
        print("✅ Migration completed successfully!")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    quick_migrate()