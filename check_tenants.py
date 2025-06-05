#!/usr/bin/env python3
"""
Quick script to check what's in your tenants database
Run this from your project root directory
"""

import sqlite3
import os
from datetime import datetime

def find_database():
    """Find the database file"""
    if os.path.exists('chatbot.db'):
        return 'chatbot.db'
    
    # Look for other common names
    for name in ['app.db', 'database.db', 'main.db']:
        if os.path.exists(name):
            return name
    
    return None

def check_tenants():
    """Check all tenants in the database"""
    db_path = find_database()
    if not db_path:
        print("❌ Could not find database file!")
        return
    
    print(f"📁 Using database: {db_path}")
    print("=" * 60)
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get all tenants
        cursor.execute("SELECT * FROM tenants ORDER BY id DESC")
        tenants = cursor.fetchall()
        
        if not tenants:
            print("📋 No tenants found in database")
            return
        
        # Get column names
        cursor.execute("PRAGMA table_info(tenants)")
        columns = [col[1] for col in cursor.fetchall()]
        
        print(f"📊 Found {len(tenants)} tenant(s):")
        print("-" * 60)
        
        for tenant in tenants:
            print(f"🆔 Tenant ID: {tenant[0]}")
            for i, value in enumerate(tenant):
                if i < len(columns):
                    if columns[i] in ['created_at', 'updated_at'] and value:
                        print(f"   {columns[i]}: {value}")
                    elif columns[i] == 'api_key' and value:
                        print(f"   {columns[i]}: {value[:20]}...")
                    elif value is not None:
                        print(f"   {columns[i]}: {value}")
            print("-" * 40)
        
        conn.close()
        
    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
    except Exception as e:
        print(f"❌ Error: {e}")

def check_specific_email(email):
    """Check if a specific email exists"""
    db_path = find_database()
    if not db_path:
        print("❌ Could not find database file!")
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, name, email, is_active, supabase_user_id FROM tenants WHERE email = ?", (email,))
        result = cursor.fetchone()
        
        if result:
            print(f"✅ Found tenant with email '{email}':")
            print(f"   ID: {result[0]}")
            print(f"   Name: {result[1]}")
            print(f"   Email: {result[2]}")
            print(f"   Active: {result[3]}")
            print(f"   Supabase ID: {result[4] or 'None'}")
        else:
            print(f"❌ No tenant found with email '{email}'")
        
        conn.close()
        
    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")

def check_recent_tenants():
    """Check the most recent tenants"""
    db_path = find_database()
    if not db_path:
        print("❌ Could not find database file!")
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get the 5 most recent tenants
        cursor.execute("""
            SELECT id, name, email, is_active, supabase_user_id, created_at 
            FROM tenants 
            ORDER BY id DESC 
            LIMIT 5
        """)
        tenants = cursor.fetchall()
        
        if tenants:
            print("🕒 Most recent tenants:")
            print("-" * 60)
            for tenant in tenants:
                print(f"ID: {tenant[0]} | Name: {tenant[1]} | Email: {tenant[2]}")
                print(f"Active: {tenant[3]} | Supabase: {tenant[4] or 'None'}")
                print(f"Created: {tenant[5] or 'Unknown'}")
                print("-" * 40)
        else:
            print("📋 No tenants found")
        
        conn.close()
        
    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")

def main():
    print("🔍 TENANT DATABASE CHECKER")
    print("=" * 60)
    
    while True:
        print("\nChoose an option:")
        print("1. Show all tenants")
        print("2. Check specific email")
        print("3. Show recent tenants")
        print("4. Exit")
        
        choice = input("\nEnter choice (1-4): ").strip()
        
        if choice == '1':
            print("\n" + "=" * 60)
            check_tenants()
        elif choice == '2':
            email = input("Enter email to check: ").strip()
            if email:
                print("\n" + "=" * 60)
                check_specific_email(email)
        elif choice == '3':
            print("\n" + "=" * 60)
            check_recent_tenants()
        elif choice == '4':
            print("👋 Goodbye!")
            break
        else:
            print("❌ Invalid choice, please try again")

if __name__ == "__main__":
    main()