#!/usr/bin/env python3
"""
Script to add supabase_user_id column to tenants table
Run this from your project root directory
"""

import sqlite3
import os
import sys
from pathlib import Path

def find_database_file():
    """Find the SQLite database file"""
    possible_names = [
        'app.db',
        'database.db', 
        'chatbot.db',
        'main.db',
        'tenant.db',
        'data.db'
    ]
    
    for name in possible_names:
        if os.path.exists(name):
            return name
    
    # Look in common directories
    for directory in ['.', 'data', 'db', 'database']:
        if os.path.exists(directory):
            for name in possible_names:
                path = os.path.join(directory, name)
                if os.path.exists(path):
                    return path
    
    return None

def check_table_structure(db_path):
    """Check current table structure"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if tenants table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tenants'")
        table_exists = cursor.fetchone() is not None
        
        if not table_exists:
            print("❌ tenants table not found!")
            conn.close()
            return False, []
        
        # Get table info
        cursor.execute("PRAGMA table_info(tenants)")
        columns = cursor.fetchall()
        
        print("Current tenants table structure:")
        for col in columns:
            print(f"  - {col[1]} ({col[2]})")
        
        # Check if supabase_user_id already exists
        column_names = [col[1] for col in columns]
        
        conn.close()
        return 'supabase_user_id' in column_names, column_names
        
    except sqlite3.Error as e:
        print(f"Error checking table structure: {e}")
        return False, []

def add_supabase_column(db_path):
    """Add the supabase_user_id column"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Add the column
        cursor.execute("ALTER TABLE tenants ADD COLUMN supabase_user_id VARCHAR")
        
        # Commit the changes
        conn.commit()
        
        print("✅ Successfully added supabase_user_id column!")
        
        # Verify it was added
        cursor.execute("PRAGMA table_info(tenants)")
        columns = cursor.fetchall()
        
        print("\nUpdated table structure:")
        for col in columns:
            print(f"  - {col[1]} ({col[2]})")
        
        conn.close()
        return True
        
    except sqlite3.Error as e:
        print(f"❌ Error adding column: {e}")
        return False

def main():
    print("🔍 Looking for SQLite database file...")
    
    # Find database file
    db_path = find_database_file()
    
    if not db_path:
        print("❌ Could not find database file!")
        print("Please specify the path manually:")
        print("Available files:")
        for file in os.listdir('.'):
            if file.endswith('.db'):
                print(f"  - {file}")
        
        # Ask user for manual input
        manual_path = input("\nEnter database file path: ").strip()
        if manual_path and os.path.exists(manual_path):
            db_path = manual_path
        else:
            print("❌ Invalid path. Exiting.")
            sys.exit(1)
    
    print(f"📁 Found database: {db_path}")
    
    # Check if backup is needed
    backup_path = f"{db_path}.backup"
    if not os.path.exists(backup_path):
        print(f"💾 Creating backup: {backup_path}")
        import shutil
        shutil.copy2(db_path, backup_path)
        print("✅ Backup created!")
    
    # Check current structure
    print("\n🔍 Checking current table structure...")
    already_exists, columns = check_table_structure(db_path)
    
    if already_exists is False and not columns:
        print("❌ tenants table not found!")
        return
    
    if already_exists:
        print("✅ supabase_user_id column already exists!")
        return
    
    # Add the column
    print("\n🔧 Adding supabase_user_id column...")
    success = add_supabase_column(db_path)
    
    if success:
        print("\n🎉 All done! You can now test registration.")
        print("The column has been added successfully.")
    else:
        print("\n❌ Failed to add column. Check the error above.")
        print(f"Your backup is available at: {backup_path}")

if __name__ == "__main__":
    main()