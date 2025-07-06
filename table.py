import os
import subprocess
from urllib.parse import urlparse
import re
import sys

# --- Configuration ---
# The full connection URL for your Render PostgreSQL database.
DB_URL = "postgresql://chatbot_hhjv_user:dYXguSEwpwZl3Yt2R3ACsfvmM5lLIgSD@dpg-d10sp295pdvs73afujf0-a.oregon-postgres.render.com/chatbot_hhjv"
# The name of the output file where the schema will be saved.
OUTPUT_FILE = "render_schema.sql"
# Path to pg_dump if it's not in your system's PATH.
# We are providing the full path to the Homebrew installation of postgresql@16
# to resolve the version mismatch error.
PG_DUMP_PATH = '/usr/local/opt/postgresql@16/bin/pg_dump'

def extract_postgres_schema():
    """
    Uses the pg_dump utility to connect to a PostgreSQL database,
    extract the CREATE TABLE statements for all tables, modify them to be
    idempotent, and save them to a .sql file.
    """
    print("--- PostgreSQL Schema Extractor ---")
    
    try:
        # Set environment variables for pg_dump from the URL.
        # This is a secure way to pass credentials without them being visible
        # in the command history.
        parsed_url = urlparse(DB_URL)
        env = os.environ.copy()
        env['PGHOST'] = parsed_url.hostname
        env['PGPORT'] = str(parsed_url.port or 5432)
        env['PGUSER'] = parsed_url.username
        env['PGPASSWORD'] = parsed_url.password
        env['PGDATABASE'] = parsed_url.path.lstrip('/')
        
        print(f"Host: {env['PGHOST']}")
        print(f"Database: {env['PGDATABASE']}")
        print(f"User: {env['PGUSER']}")
        
        # Command to run pg_dump.
        # --schema-only: Dumps only the object definitions (schema), not data.
        # --no-owner: Prevents setting object ownership, which is important
        #             when migrating between different systems.
        # --no-privileges: Prevents dumping access privileges (ACLs).
        command = [
            PG_DUMP_PATH,
            '--schema-only',
            '--no-owner',
            '--no-privileges',
            '--dbname', env['PGDATABASE']
        ]

        print("\nRunning pg_dump to extract schema...")
        
        # Execute the pg_dump command.
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            env=env,
            check=True # This will raise an error if pg_dump fails
        )
        
        schema_sql = process.stdout
        
        print("Schema extracted successfully. Modifying for Supabase compatibility...")

        # Use regex to replace "CREATE TABLE" with "CREATE TABLE IF NOT EXISTS".
        # This makes the script safe to re-run.
        modified_sql = re.sub(
            r'CREATE TABLE',
            'CREATE TABLE IF NOT EXISTS',
            schema_sql,
            flags=re.IGNORECASE
        )

        # Write the final, modified schema to the output file.
        with open(OUTPUT_FILE, 'w') as f:
            f.write("-- Schema extracted from Render PostgreSQL database\n")
            f.write("-- Modified to be compatible with Supabase (using IF NOT EXISTS)\n\n")
            f.write(modified_sql)
            
        print(f"✅ Successfully exported and modified schema to '{OUTPUT_FILE}'")

    except FileNotFoundError:
        print("\n--- ERROR ---")
        print(f"Error: The command '{PG_DUMP_PATH}' was not found.")
        print("Please ensure that PostgreSQL client tools (specifically pg_dump) are installed and in your system's PATH.")
        print("If it's installed elsewhere, specify the full path in the PG_DUMP_PATH variable in this script.")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print("\n--- ERROR ---")
        print("An error occurred while running pg_dump.")
        print("This could be due to incorrect connection details, network issues, or the database not being accessible.")
        print("\nError details from pg_dump:")
        print(e.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    extract_postgres_schema()
