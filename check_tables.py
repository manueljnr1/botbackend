# check_tables.py
import sqlite3
import sys

def check_tables(db_path):
    """Check what tables exist in the SQLite database."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        if tables:
            print(f"\nTables in {db_path}:")
            for table in tables:
                print(f"- {table[0]}")
                
                # Show columns for each table
                cursor.execute(f"PRAGMA table_info({table[0]});")
                columns = cursor.fetchall()
                print("  Columns:")
                for col in columns:
                    print(f"  - {col[1]} ({col[2]})")
                print()
        else:
            print(f"\nNo tables found in {db_path}")
        
    except sqlite3.Error as e:
        print(f"Error: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_tables.py <database_path>")
        sys.exit(1)
    
    db_path = sys.argv[1]
    print(f"Checking tables in: {db_path}")
    check_tables(db_path)