# find_db.py
import os

def find_sqlite_files(start_path):
    """Find all SQLite database files in the given directory and subdirectories."""
    sqlite_files = []
    
    for root, dirs, files in os.walk(start_path):
        for file in files:
            if file.endswith('.db') or file.endswith('.sqlite') or file.endswith('.sqlite3'):
                sqlite_files.append(os.path.join(root, file))
    
    return sqlite_files

if __name__ == "__main__":
    # Start search from the current directory
    current_dir = os.getcwd()
    print(f"Searching for SQLite database files in: {current_dir}")
    
    db_files = find_sqlite_files(current_dir)
    
    if db_files:
        print("\nFound SQLite database files:")
        for file in db_files:
            print(f"- {file}")
    else:
        print("\nNo SQLite database files found.")
        