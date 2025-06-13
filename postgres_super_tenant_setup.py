import psycopg2

DATABASE_URL = "postgresql://chatbot_hhjv_user:dYXguSEwpwZl3Yt2R3ACsfvmM5lLIgSD@dpg-d10sp295pdvs73afujf0-a.oregon-postgres.render.com/chatbot_hhjv"

try:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True  # Important: avoid transaction locks
    cursor = conn.cursor()
    
    print("Connected to database")
    
    # Add columns one by one with autocommit
    try:
        cursor.execute("ALTER TABLE tenants ADD COLUMN is_super_tenant BOOLEAN DEFAULT FALSE")
        print("✅ Added is_super_tenant")
    except psycopg2.errors.DuplicateColumn:
        print("ℹ️ is_super_tenant already exists")
    
    try:
        cursor.execute("ALTER TABLE tenants ADD COLUMN can_impersonate BOOLEAN DEFAULT FALSE")
        print("✅ Added can_impersonate")
    except psycopg2.errors.DuplicateColumn:
        print("ℹ️ can_impersonate already exists")
    
    try:
        cursor.execute("ALTER TABLE tenants ADD COLUMN impersonating_tenant_id INTEGER")
        print("✅ Added impersonating_tenant_id")
    except psycopg2.errors.DuplicateColumn:
        print("ℹ️ impersonating_tenant_id already exists")
    
    print("✅ All columns added successfully!")
    
except Exception as e:
    print(f"Error: {e}")
finally:
    if 'conn' in locals():
        conn.close()