#!/usr/bin/env python3
"""
Simple SQLite to JSON export without model dependencies
"""

import sqlite3
import json
from datetime import datetime

def export_sqlite_to_json():
    """Export SQLite database directly to JSON"""
    
    # Connect to SQLite database
    try:
        conn = sqlite3.connect('chatbot.db')
        conn.row_factory = sqlite3.Row  # This enables column access by name
        cursor = conn.cursor()
    except Exception as e:
        print(f"❌ Could not connect to database: {e}")
        return
    
    export_data = {}
    
    try:
        # Get all table names
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        print("📋 Found tables:")
        for table in tables:
            table_name = table[0]
            print(f"  - {table_name}")
            
            # Get all data from each table
            cursor.execute(f"SELECT * FROM {table_name}")
            rows = cursor.fetchall()
            
            # Convert rows to list of dictionaries
            table_data = []
            for row in rows:
                table_data.append(dict(row))
            
            export_data[table_name] = table_data
            print(f"    → {len(table_data)} records")
        
        # Save to JSON file
        with open('database_export_simple.json', 'w') as f:
            json.dump(export_data, f, indent=2, default=str)
        
        print(f"\n✅ Export completed!")
        print(f"📁 Saved to: database_export_simple.json")
        print(f"📊 Total tables exported: {len(export_data)}")
        
        # Show summary
        total_records = sum(len(table_data) for table_data in export_data.values())
        print(f"📊 Total records: {total_records}")
        
    except Exception as e:
        print(f"❌ Export failed: {e}")
        
    finally:
        conn.close()

if __name__ == "__main__":
    export_sqlite_to_json()
    