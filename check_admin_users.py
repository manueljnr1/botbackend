#!/usr/bin/env python3
"""
Check admin users in the database
"""
import os
import sys
import sqlite3

def check_admin_users():
    """Check admin users directly using SQLite"""
    db_path = "chatbot.db"
    
    if not os.path.exists(db_path):
        print(f"Error: Database file not found: {db_path}")
        return False
    
    try:
        # Connect to the database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if users table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if not cursor.fetchone():
            print("Error: 'users' table does not exist")
            return False
        
        # Query admin users
        cursor.execute("SELECT id, username, email, is_admin, is_active, tenant_id FROM users WHERE is_admin = 1")
        admin_users = cursor.fetchall()
        
        if not admin_users:
            print("No admin users found in the database")
        else:
            print(f"Found {len(admin_users)} admin users:")
            print("-" * 80)
            print(f"{'ID':<5} {'Username':<20} {'Email':<30} {'Active':<10} {'Tenant ID':<10}")
            print("-" * 80)
            
            for user in admin_users:
                user_id, username, email, _, is_active, tenant_id = user
                active_str = "Yes" if is_active else "No"
                tenant_str = str(tenant_id) if tenant_id else "None"
                print(f"{user_id:<5} {username:<20} {email:<30} {active_str:<10} {tenant_str:<10}")
        
        # Check if there are any users at all
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        
        if total_users == 0:
            print("\nNo users found in the database.")
            print("You may need to create an admin user.")
        else:
            print(f"\nTotal users in database: {total_users}")
        
        conn.close()
        return True
        
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    check_admin_users()
