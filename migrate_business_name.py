# migrate_render.py
import psycopg2

DATABASE_URL = "postgresql://chatbot_hhjv_user:dYXguSEwpwZl3Yt2R3ACsfvmM5lLIgSD@dpg-d10sp295pdvs73afujf0-a.oregon-postgres.render.com/chatbot_hhjv"

try:
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    cursor.execute("ALTER TABLE chat_sessions ADD COLUMN email_captured_at TIMESTAMP")
    cursor.execute("ALTER TABLE chat_sessions ADD COLUMN email_expires_at TIMESTAMP")
    cursor.execute("CREATE INDEX idx_chat_sessions_email_captured_at ON chat_sessions(email_captured_at)")
    cursor.execute("CREATE INDEX idx_chat_sessions_email_expires_at ON chat_sessions(email_expires_at)")
    
    conn.commit()
    print("✅ Render PostgreSQL columns added successfully!")
except psycopg2.errors.DuplicateColumn:
    print("✅ Columns already exist in Render database")
except Exception as e:
    print(f"❌ Render Error: {e}")
finally:
    if conn:
        conn.close()