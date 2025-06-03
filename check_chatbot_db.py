#!/usr/bin/env python3
"""
Quick admin creator that handles ID constraints properly
"""

import sqlite3
import bcrypt

def create_admin_quick():
    """Create admin with proper error handling"""
    
    # Your details
    username = "Emmanuel"
    email = "Emmanuel.ba@yahoo.com"
    name = "Emmanuel Ajayi"
    password = "Emmanuel12!"
    
    # Hash password
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    conn = sqlite3.connect('chatbot.db')
    cursor = conn.cursor()
    
    try:
        # Check table structure
        cursor.execute("PRAGMA table_info(admins);")
        columns = cursor.fetchall()
        print("📊 Table structure:")
        for col in columns:
            col_name, col_type, not_null, default, pk = col[1], col[2], col[3], col[4], col[5]
            print(f"   {col_name}: {col_type} {'(PK)' if pk else ''} {'NOT NULL' if not_null else ''}")
        
        # Check if ID is auto-increment
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='admins';")
        table_sql = cursor.fetchone()[0]
        print(f"\n📋 Table SQL:\n{table_sql}")
        
        # Get next available ID
        cursor.execute("SELECT MAX(id) FROM admins;")
        max_id = cursor.fetchone()[0]
        next_id = (max_id or 0) + 1
        print(f"\n🔢 Next ID will be: {next_id}")
        
        # Try insertion with explicit ID
        cursor.execute("""
            INSERT INTO admins (id, username, email, name, hashed_password, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """, (next_id, username, email, name, hashed_password, 1))
        
        conn.commit()
        
        print("✅ Admin created successfully!")
        print(f"   ID: {next_id}")
        print(f"   Username: {username}")
        print(f"   Email: {email}")
        print(f"   Password: {password}")
        
        # Verify creation
        cursor.execute("SELECT id, username, email, is_active FROM admins WHERE username = ?;", (username,))
        result = cursor.fetchone()
        print(f"✅ Verification: {result}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
    finally:
        conn.close()

def test_with_curl():
    """Show curl test command"""
    print("\n🧪 Test login with:")
    print("-" * 40)
    print('curl -X POST "http://localhost:8000/tenants/login" \\')
    print('  -H "Content-Type: application/x-www-form-urlencoded" \\')
    print('  -d "username=Emmanuel&password=Emmanuel12!"')

if __name__ == "__main__":
    print("🚀 Quick Admin Creator")
    print("=" * 40)
    create_admin_quick()
    test_with_curl()