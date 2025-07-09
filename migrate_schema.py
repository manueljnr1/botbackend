import sqlite3
import re
import os

class SQLiteToPostgreSQLMigrator:
    def __init__(self, sqlite_db_path):
        self.sqlite_db_path = sqlite_db_path
        self.connection = None
        
    def connect(self):
        """Connect to SQLite database"""
        try:
            self.connection = sqlite3.connect(self.sqlite_db_path)
            self.connection.row_factory = sqlite3.Row
            print(f"✓ Connected to SQLite database: {self.sqlite_db_path}")
        except sqlite3.Error as e:
            print(f"✗ Error connecting to database: {e}")
            raise
    
    def get_tables(self):
        """Get all table names from SQLite database"""
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """)
        return [row[0] for row in cursor.fetchall()]
    
    def get_table_schema(self, table_name):
        """Get CREATE TABLE statement for a specific table"""
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT sql FROM sqlite_master 
            WHERE type='table' AND name=?
        """, (table_name,))
        result = cursor.fetchone()
        return result[0] if result else None
    
    def get_indexes(self, table_name=None):
        """Get all indexes, optionally filtered by table"""
        cursor = self.connection.cursor()
        if table_name:
            cursor.execute("""
                SELECT name, sql FROM sqlite_master 
                WHERE type='index' AND tbl_name=? AND sql IS NOT NULL
                ORDER BY name
            """, (table_name,))
        else:
            cursor.execute("""
                SELECT name, sql FROM sqlite_master 
                WHERE type='index' AND sql IS NOT NULL
                ORDER BY name
            """)
        return cursor.fetchall()
    
    def get_triggers(self, table_name=None):
        """Get all triggers, optionally filtered by table"""
        cursor = self.connection.cursor()
        if table_name:
            cursor.execute("""
                SELECT name, sql FROM sqlite_master 
                WHERE type='trigger' AND tbl_name=?
                ORDER BY name
            """, (table_name,))
        else:
            cursor.execute("""
                SELECT name, sql FROM sqlite_master 
                WHERE type='trigger'
                ORDER BY name
            """)
        return cursor.fetchall()
    
    def convert_sqlite_to_postgres_type(self, sqlite_type):
        """Convert SQLite data types to PostgreSQL equivalents"""
        sqlite_type = sqlite_type.upper().strip()
        
        # Handle common SQLite to PostgreSQL type mappings
        type_mappings = {
            'INTEGER': 'INTEGER',
            'INT': 'INTEGER',
            'BIGINT': 'BIGINT',
            'REAL': 'REAL',
            'FLOAT': 'REAL',
            'DOUBLE': 'DOUBLE PRECISION',
            'NUMERIC': 'NUMERIC',
            'DECIMAL': 'DECIMAL',
            'BOOLEAN': 'BOOLEAN',
            'BOOL': 'BOOLEAN',
            'DATE': 'DATE',
            'TIME': 'TIME',
            'DATETIME': 'TIMESTAMP',
            'TIMESTAMP': 'TIMESTAMP',
            'BLOB': 'BYTEA',
            'CLOB': 'TEXT',
        }
        
        # Handle TEXT/VARCHAR variations
        if sqlite_type in ['TEXT', 'VARCHAR'] or sqlite_type.startswith('VARCHAR(') or sqlite_type.startswith('CHAR('):
            return sqlite_type.replace('TEXT', 'TEXT')
        
        # Handle parameterized types
        for sqlite_key, postgres_val in type_mappings.items():
            if sqlite_type.startswith(sqlite_key):
                return sqlite_type.replace(sqlite_key, postgres_val)
        
        # Default to TEXT for unknown types
        return 'TEXT'
    
    def convert_create_table_statement(self, sqlite_sql):
        """Convert SQLite CREATE TABLE to PostgreSQL format"""
        if not sqlite_sql:
            return None
            
        # Remove SQLite-specific syntax
        postgres_sql = sqlite_sql
        
        # Convert AUTOINCREMENT to SERIAL
        postgres_sql = re.sub(r'INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT', 'SERIAL PRIMARY KEY', postgres_sql, flags=re.IGNORECASE)
        postgres_sql = re.sub(r'INTEGER\s+AUTOINCREMENT', 'SERIAL', postgres_sql, flags=re.IGNORECASE)
        
        # Convert data types
        type_patterns = [
            (r'\bINTEGER\b', 'INTEGER'),
            (r'\bREAL\b', 'REAL'),
            (r'\bBLOB\b', 'BYTEA'),
            (r'\bDATETIME\b', 'TIMESTAMP'),
        ]
        
        for pattern, replacement in type_patterns:
            postgres_sql = re.sub(pattern, replacement, postgres_sql, flags=re.IGNORECASE)
        
        # Handle WITHOUT ROWID tables (not supported in PostgreSQL)
        postgres_sql = re.sub(r'\s+WITHOUT\s+ROWID', '', postgres_sql, flags=re.IGNORECASE)
        
        return postgres_sql
    
    def convert_index_statement(self, sqlite_sql):
        """Convert SQLite index to PostgreSQL format"""
        if not sqlite_sql:
            return None
        
        # PostgreSQL indexes are very similar to SQLite, minimal conversion needed
        postgres_sql = sqlite_sql
        
        # Remove IF NOT EXISTS if present (PostgreSQL supports it, but some prefer without)
        # postgres_sql = re.sub(r'IF\s+NOT\s+EXISTS\s+', '', postgres_sql, flags=re.IGNORECASE)
        
        return postgres_sql
    
    def generate_migration_script(self, output_file='migration_to_postgres.sql'):
        """Generate complete migration script"""
        if not self.connection:
            self.connect()
        
        migration_script = []
        migration_script.append("-- SQLite to PostgreSQL Migration Script")
        migration_script.append("-- Generated automatically")
        migration_script.append("-- Review and test before running on production!")
        migration_script.append("")
        migration_script.append("-- Enable UUID extension (common in Supabase)")
        migration_script.append("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";")
        migration_script.append("")
        
        # Get all tables
        tables = self.get_tables()
        
        if not tables:
            print("No tables found in the database.")
            return
        
        print(f"Found {len(tables)} tables: {', '.join(tables)}")
        
        # Process each table
        for table_name in tables:
            print(f"Processing table: {table_name}")
            
            migration_script.append(f"-- Table: {table_name}")
            migration_script.append(f"DROP TABLE IF EXISTS {table_name} CASCADE;")
            
            # Get table schema
            sqlite_schema = self.get_table_schema(table_name)
            postgres_schema = self.convert_create_table_statement(sqlite_schema)
            
            if postgres_schema:
                migration_script.append(postgres_schema + ";")
            else:
                migration_script.append(f"-- ERROR: Could not convert schema for table {table_name}")
            
            migration_script.append("")
            
            # Get indexes for this table
            indexes = self.get_indexes(table_name)
            if indexes:
                migration_script.append(f"-- Indexes for {table_name}")
                for index_name, index_sql in indexes:
                    if index_sql:
                        postgres_index = self.convert_index_statement(index_sql)
                        migration_script.append(postgres_index + ";")
                migration_script.append("")
        
        # Get all triggers
        triggers = self.get_triggers()
        if triggers:
            migration_script.append("-- Triggers")
            migration_script.append("-- WARNING: Triggers may need manual conversion")
            for trigger_name, trigger_sql in triggers:
                migration_script.append(f"-- Original SQLite trigger: {trigger_name}")
                migration_script.append(f"-- {trigger_sql}")
                migration_script.append("")
        
        # Write to file
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(migration_script))
        
        print(f"✓ Migration script written to: {output_file}")
        
        # Display summary
        self.display_summary(tables, indexes, triggers)
    
    def display_summary(self, tables, indexes, triggers):
        """Display migration summary"""
        print("\n" + "="*50)
        print("MIGRATION SUMMARY")
        print("="*50)
        print(f"Tables processed: {len(tables)}")
        print(f"Indexes found: {len(indexes)}")
        print(f"Triggers found: {len(triggers)}")
        
        if tables:
            print("\nTables:")
            for table in tables:
                print(f"  - {table}")
        
        print("\nNext steps:")
        print("1. Review the generated migration_to_postgres.sql file")
        print("2. Test the schema creation on a development Supabase instance")
        print("3. Adjust any data types or constraints as needed")
        print("4. Run the migration script on your Supabase database")
        print("5. Use a separate script to migrate the actual data")
        
        print("\nNotes:")
        print("- AUTOINCREMENT has been converted to SERIAL")
        print("- Review any custom constraints or triggers manually")
        print("- Test thoroughly before running on production")
    
    def close(self):
        """Close database connection"""
        if self.connection:
            self.connection.close()
            print("✓ Database connection closed")

def main():
    # Configuration
    sqlite_db_path = "./chatbot.db"
    output_file = "migration_to_postgres.sql"
    
    # Check if database exists
    if not os.path.exists(sqlite_db_path):
        print(f"✗ Database file not found: {sqlite_db_path}")
        print("Please check the path and try again.")
        return
    
    # Create migrator instance
    migrator = SQLiteToPostgreSQLMigrator(sqlite_db_path)
    
    try:
        # Generate migration script
        migrator.generate_migration_script(output_file)
        
    except Exception as e:
        print(f"✗ Error during migration: {e}")
        
    finally:
        # Clean up
        migrator.close()

if __name__ == "__main__":
    main()