import os
import psycopg2
import pandas as pd
from sqlalchemy import create_engine, text, inspect
from tqdm import tqdm
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseMigrator:
    def __init__(self, source_url, target_url):
        self.source_engine = create_engine(source_url)
        self.target_engine = create_engine(target_url)
        
    def test_connections(self):
        """Test both database connections"""
        logger.info("Testing database connections...")
        
        try:
            # Test source connection
            with self.source_engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                logger.info("✅ Source database connection successful")
        except Exception as e:
            logger.error(f"❌ Source database connection failed: {e}")
            raise
            
        try:
            # Test target connection
            with self.target_engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                logger.info("✅ Target database connection successful")
        except Exception as e:
            logger.error(f"❌ Target database connection failed: {e}")
            raise
        
    def get_tables(self):
        """Get list of all tables in source database"""
        inspector = inspect(self.source_engine)
        return inspector.get_table_names()
    
    def migrate_schema(self):
        """Export and import schema structure"""
        logger.info("Migrating schema...")
        
        # Get schema from source
        with self.source_engine.connect() as conn:
            # Export schema (you might need to adjust this query)
            schema_query = """
            SELECT table_name, column_name, data_type, is_nullable, column_default
            FROM information_schema.columns 
            WHERE table_schema = 'public'
            ORDER BY table_name, ordinal_position;
            """
            schema_df = pd.read_sql(schema_query, conn)
        
        logger.info(f"Found {len(schema_df)} columns across tables")
        return schema_df
    
    def migrate_table_data(self, table_name, batch_size=1000):
        """Migrate data for a specific table"""
        logger.info(f"Migrating table: {table_name}")
        
        try:
            # Count total rows
            with self.source_engine.connect() as conn:
                count_result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                total_rows = count_result.scalar()
            
            if total_rows == 0:
                logger.info(f"Table {table_name} is empty, skipping...")
                return
                
            logger.info(f"Total rows in {table_name}: {total_rows}")
            
            # Check if table exists in target
            inspector = inspect(self.target_engine)
            if table_name not in inspector.get_table_names():
                logger.warning(f"Table {table_name} doesn't exist in target database, skipping...")
                return
            
            # Migrate in batches
            for offset in tqdm(range(0, total_rows, batch_size), desc=f"Migrating {table_name}"):
                query = f"SELECT * FROM {table_name} LIMIT {batch_size} OFFSET {offset}"
                
                # Read batch from source
                df_batch = pd.read_sql(query, self.source_engine)
                
                # Write batch to target
                df_batch.to_sql(
                    table_name, 
                    self.target_engine, 
                    if_exists='append', 
                    index=False,
                    method='multi'
                )
            
            logger.info(f"✅ Successfully migrated {table_name}")
            
        except Exception as e:
            logger.error(f"❌ Error migrating {table_name}: {str(e)}")
            raise
    
    def migrate_all_data(self, exclude_tables=None):
        """Migrate all tables"""
        exclude_tables = exclude_tables or []
        tables = [t for t in self.get_tables() if t not in exclude_tables]
        
        logger.info(f"Starting migration of {len(tables)} tables...")
        
        for table in tables:
            try:
                self.migrate_table_data(table)
            except Exception as e:
                logger.error(f"Failed to migrate {table}: {e}")
                # Continue with other tables
                continue
    
    def validate_migration(self):
        """Validate that migration was successful"""
        logger.info("Validating migration...")
        
        tables = self.get_tables()
        validation_results = {}
        
        for table in tables:
            try:
                # Count rows in both databases
                with self.source_engine.connect() as conn:
                    source_count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
                
                with self.target_engine.connect() as conn:
                    target_count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
                
                validation_results[table] = {
                    'source_count': source_count,
                    'target_count': target_count,
                    'match': source_count == target_count
                }
                
                if source_count == target_count:
                    logger.info(f"✅ {table}: {source_count} rows migrated successfully")
                else:
                    logger.error(f"❌ {table}: Source({source_count}) != Target({target_count})")
                    
            except Exception as e:
                logger.error(f"❌ Error validating {table}: {e}")
                validation_results[table] = {'error': str(e)}
        
        return validation_results

def main():
    # Database connection strings
    RENDER_DB_URL = "postgresql://chatbot_hhjv_user:dYXguSEwpwZl3Yt2R3ACsfvmM5lLIgSD@dpg-d10sp295pdvs73afujf0-a.oregon-postgres.render.com/chatbot_hhjv"
    
    # Replace YOUR_ACTUAL_PASSWORD with your real Supabase database password
    SUPABASE_DB_URL = "postgresql://postgres.hkamqejkluurrnrfgskg:fN4NoRUVAVV9hnsY@aws-0-us-east-2.pooler.supabase.com:6543/postgres"
   
    # Validate URL format
    if not RENDER_DB_URL.startswith(('postgresql://', 'postgres://')):
        raise ValueError("RENDER_DB_URL must start with 'postgresql://' or 'postgres://'")
    
    if not SUPABASE_DB_URL.startswith(('postgresql://', 'postgres://')):
        raise ValueError("SUPABASE_DB_URL must start with 'postgresql://' or 'postgres://'")
    
    print(f"Source: {RENDER_DB_URL.split('@')[0]}@***")
    print(f"Target: {SUPABASE_DB_URL.split('@')[0]}@***")
    
    # Initialize migrator
    migrator = DatabaseMigrator(RENDER_DB_URL, SUPABASE_DB_URL)
    
    try:
        # Step 0: Test connections first
        migrator.test_connections()
        
        # Step 1: Get schema info
        schema_info = migrator.migrate_schema()
        print("Schema information retrieved")
        
        # Step 2: Migrate all data
        # Exclude system tables if any
        exclude_tables = ['alembic_version']  # Add any tables to skip
        migrator.migrate_all_data(exclude_tables=exclude_tables)
        
        # Step 3: Validate migration
        validation_results = migrator.validate_migration()
        
        # Print summary
        print("\n" + "="*50)
        print("MIGRATION SUMMARY")
        print("="*50)
        
        for table, result in validation_results.items():
            if 'error' in result:
                print(f"❌ {table}: ERROR - {result['error']}")
            elif result['match']:
                print(f"✅ {table}: {result['source_count']} rows")
            else:
                print(f"❌ {table}: MISMATCH - Source: {result['source_count']}, Target: {result['target_count']}")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise

if __name__ == "__main__":
    main()