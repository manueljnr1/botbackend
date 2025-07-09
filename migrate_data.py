import psycopg2
import psycopg2.extras
import json
import sys
from datetime import datetime
import logging
from typing import Dict, List, Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('migration.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

class PostgreSQLMigrator:
    def __init__(self):
        # Source database (Render PostgreSQL)
        self.source_config = {
            'host': 'dpg-d10sp295pdvs73afujf0-a.oregon-postgres.render.com',
            'port': 5432,
            'database': 'chatbot_hhjv',
            'user': 'chatbot_hhjv_user',
            'password': 'dYXguSEwpwZl3Yt2R3ACsfvmM5lLIgSD'
        }
        
        # Destination database (Supabase PostgreSQL)
        self.dest_config = {
            'host': 'aws-0-us-east-2.pooler.supabase.com',
            'port': 6543,
            'database': 'postgres',
            'user': 'postgres.hkamqejkluurrnrfgskg',
            'password': 'IqcUKwYmnUskG4RV',
            'sslmode': 'require'
        }
        
        self.source_conn = None
        self.dest_conn = None
        
        # Define migration order (respecting foreign key dependencies)
        self.migration_order = [
            'admins',
            'tenants',
            'pricing_plans',
            'tenant_subscriptions',
            'tenant_credentials',
            'tenant_password_resets',
            'billing_history',
            'usage_logs',
            'agents',
            'agent_tags',
            'agent_tags_association',
            'agent_permission_overrides',
            'agent_role_history',
            'agent_sessions',
            'agent_tag_performance',
            'chat_sessions',
            'chat_messages',
            'conversation_sessions',
            'live_chat_conversations',
            'live_chat_messages',
            'chat_queue',
            'conversation_transfers',
            'conversation_tags',
            'conversation_tagging',
            'customer_profiles',
            'customer_devices',
            'customer_preferences',
            'customer_sessions',
            'live_chat_settings',
            'faqs',
            'booking_requests',
            'pending_feedback',
            'scraped_emails',
            'security_incidents',
            'slack_channel_context',
            'slack_thread_memory',
            'smart_routing_log',
            'instagram_integrations',
            'instagram_conversations',
            'instagram_messages',
            'instagram_webhook_events',
            'telegram_integrations',
            'telegram_chats',
            'knowledge_bases',
            'users',
            'password_resets'
        ]
        
        # Tables to skip (if they don't exist in source or are system tables)
        self.skip_tables = set()
        
        # Statistics
        self.stats = {
            'tables_migrated': 0,
            'total_rows_migrated': 0,
            'failed_tables': [],
            'start_time': None,
            'end_time': None
        }

    def connect_databases(self):
        """Establish connections to both source and destination databases"""
        try:
            logging.info("Connecting to source database (Render PostgreSQL)...")
            self.source_conn = psycopg2.connect(**self.source_config)
            self.source_conn.set_session(autocommit=False)
            logging.info("✓ Connected to source database")
            
            logging.info("Connecting to destination database (Supabase PostgreSQL)...")
            self.dest_conn = psycopg2.connect(**self.dest_config)
            self.dest_conn.set_session(autocommit=False)
            logging.info("✓ Connected to destination database")
            
        except Exception as e:
            logging.error(f"Failed to connect to databases: {e}")
            raise

    def get_table_columns(self, table_name: str, connection) -> List[str]:
        """Get column names for a table"""
        cursor = connection.cursor()
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = %s 
            ORDER BY ordinal_position
        """, (table_name,))
        return [row[0] for row in cursor.fetchall()]

    def check_table_exists(self, table_name: str, connection) -> bool:
        """Check if table exists in database"""
        cursor = connection.cursor()
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = %s
            );
        """, (table_name,))
        return cursor.fetchone()[0]

    def get_table_row_count(self, table_name: str, connection) -> int:
        """Get row count for a table"""
        cursor = connection.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        return cursor.fetchone()[0]

    def disable_foreign_key_checks(self):
        """Disable foreign key checks for faster insertion"""
        cursor = self.dest_conn.cursor()
        cursor.execute("SET session_replication_role = replica;")
        self.dest_conn.commit()
        logging.info("Disabled foreign key checks")

    def enable_foreign_key_checks(self):
        """Re-enable foreign key checks"""
        cursor = self.dest_conn.cursor()
        cursor.execute("SET session_replication_role = default;")
        self.dest_conn.commit()
        logging.info("Enabled foreign key checks")

    def truncate_table(self, table_name: str):
        """Truncate table in destination database"""
        cursor = self.dest_conn.cursor()
        cursor.execute(f"TRUNCATE TABLE {table_name} RESTART IDENTITY CASCADE;")
        self.dest_conn.commit()
        logging.info(f"Truncated table: {table_name}")

    def convert_data_types(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert data types for PostgreSQL compatibility"""
        converted = {}
        for key, value in data.items():
            if value is None:
                converted[key] = None
            elif isinstance(value, dict) or isinstance(value, list):
                # Convert dict/list to JSON string for JSONB columns
                converted[key] = json.dumps(value) if value else None
            else:
                converted[key] = value
        return converted

    def migrate_table(self, table_name: str) -> bool:
        """Migrate a single table from source to destination"""
        try:
            # Check if table exists in source
            if not self.check_table_exists(table_name, self.source_conn):
                logging.warning(f"Table {table_name} does not exist in source database, skipping")
                self.skip_tables.add(table_name)
                return True

            # Check if table exists in destination
            if not self.check_table_exists(table_name, self.dest_conn):
                logging.warning(f"Table {table_name} does not exist in destination database, skipping")
                self.skip_tables.add(table_name)
                return True

            # Get row count
            source_count = self.get_table_row_count(table_name, self.source_conn)
            logging.info(f"Migrating table {table_name} ({source_count} rows)")

            if source_count == 0:
                logging.info(f"Table {table_name} is empty, skipping")
                return True

            # Get column names from both databases
            source_columns = self.get_table_columns(table_name, self.source_conn)
            dest_columns = self.get_table_columns(table_name, self.dest_conn)

            # Find common columns
            common_columns = list(set(source_columns) & set(dest_columns))
            if not common_columns:
                logging.error(f"No common columns found for table {table_name}")
                return False

            # Log column differences
            source_only = set(source_columns) - set(dest_columns)
            dest_only = set(dest_columns) - set(source_columns)
            
            if source_only:
                logging.warning(f"Columns in source but not destination: {source_only}")
            if dest_only:
                logging.info(f"Columns in destination but not source: {dest_only}")

            # Truncate destination table
            self.truncate_table(table_name)

            # Fetch data from source in batches
            source_cursor = self.source_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            dest_cursor = self.dest_conn.cursor()

            columns_str = ', '.join([f'"{col}"' for col in common_columns])
            placeholders = ', '.join(['%s'] * len(common_columns))

            # Query source data
            source_cursor.execute(f"SELECT {columns_str} FROM {table_name}")

            batch_size = 1000
            rows_processed = 0
            
            while True:
                rows = source_cursor.fetchmany(batch_size)
                if not rows:
                    break

                # Prepare batch for insertion
                batch_data = []
                for row in rows:
                    row_dict = dict(row)
                    converted_row = self.convert_data_types(row_dict)
                    batch_data.append(tuple(converted_row[col] for col in common_columns))

                # Insert batch
                insert_query = f"""
                    INSERT INTO {table_name} ({columns_str}) 
                    VALUES ({placeholders})
                """
                
                dest_cursor.executemany(insert_query, batch_data)
                rows_processed += len(batch_data)
                
                if rows_processed % 5000 == 0:
                    logging.info(f"Processed {rows_processed}/{source_count} rows for {table_name}")

            self.dest_conn.commit()
            
            # Verify migration
            dest_count = self.get_table_row_count(table_name, self.dest_conn)
            
            if dest_count == source_count:
                logging.info(f"✓ Successfully migrated {table_name}: {dest_count} rows")
                self.stats['total_rows_migrated'] += dest_count
                return True
            else:
                logging.error(f"✗ Row count mismatch for {table_name}: source={source_count}, dest={dest_count}")
                return False

        except Exception as e:
            logging.error(f"Failed to migrate table {table_name}: {e}")
            self.dest_conn.rollback()
            return False

    def reset_sequences(self):
        """Reset sequences for SERIAL columns to continue from max ID"""
        logging.info("Resetting sequences...")
        cursor = self.dest_conn.cursor()
        
        # Get all sequences
        cursor.execute("""
            SELECT schemaname, tablename, columnname, pg_get_serial_sequence(schemaname||'.'||tablename, columnname) as sequence_name
            FROM (
                SELECT schemaname, tablename, columnname
                FROM pg_stats
                WHERE schemaname = 'public'
            ) t
            WHERE pg_get_serial_sequence(schemaname||'.'||tablename, columnname) IS NOT NULL;
        """)
        
        sequences = cursor.fetchall()
        
        for schema, table, column, sequence in sequences:
            try:
                # Get max value from table
                cursor.execute(f"SELECT COALESCE(MAX({column}), 0) FROM {table}")
                max_val = cursor.fetchone()[0]
                
                # Reset sequence
                cursor.execute(f"SELECT setval('{sequence}', {max_val + 1})")
                logging.info(f"Reset sequence {sequence} to {max_val + 1}")
                
            except Exception as e:
                logging.warning(f"Could not reset sequence {sequence}: {e}")
        
        self.dest_conn.commit()

    def verify_migration(self):
        """Verify the migration by comparing row counts"""
        logging.info("Verifying migration...")
        verification_failed = []
        
        for table_name in self.migration_order:
            if table_name in self.skip_tables:
                continue
                
            try:
                if (self.check_table_exists(table_name, self.source_conn) and 
                    self.check_table_exists(table_name, self.dest_conn)):
                    
                    source_count = self.get_table_row_count(table_name, self.source_conn)
                    dest_count = self.get_table_row_count(table_name, self.dest_conn)
                    
                    if source_count != dest_count:
                        verification_failed.append(f"{table_name}: source={source_count}, dest={dest_count}")
                        
            except Exception as e:
                logging.error(f"Verification failed for {table_name}: {e}")
                verification_failed.append(f"{table_name}: verification error")
        
        if verification_failed:
            logging.error("Verification failed for tables:")
            for failure in verification_failed:
                logging.error(f"  - {failure}")
        else:
            logging.info("✓ All tables verified successfully")

    def run_migration(self):
        """Run the complete migration process"""
        self.stats['start_time'] = datetime.now()
        logging.info("Starting PostgreSQL to Supabase migration")
        
        try:
            # Connect to databases
            self.connect_databases()
            
            # Disable foreign key checks for faster insertion
            self.disable_foreign_key_checks()
            
            # Migrate tables in dependency order
            for table_name in self.migration_order:
                if table_name not in self.skip_tables:
                    success = self.migrate_table(table_name)
                    if success:
                        self.stats['tables_migrated'] += 1
                    else:
                        self.stats['failed_tables'].append(table_name)
            
            # Reset sequences
            self.reset_sequences()
            
            # Re-enable foreign key checks
            self.enable_foreign_key_checks()
            
            # Verify migration
            self.verify_migration()
            
        except Exception as e:
            logging.error(f"Migration failed: {e}")
            raise
        finally:
            self.stats['end_time'] = datetime.now()
            self.print_summary()
            self.close_connections()

    def print_summary(self):
        """Print migration summary"""
        duration = self.stats['end_time'] - self.stats['start_time']
        
        logging.info("\n" + "="*50)
        logging.info("MIGRATION SUMMARY")
        logging.info("="*50)
        logging.info(f"Duration: {duration}")
        logging.info(f"Tables migrated: {self.stats['tables_migrated']}")
        logging.info(f"Total rows migrated: {self.stats['total_rows_migrated']:,}")
        logging.info(f"Tables skipped: {len(self.skip_tables)}")
        logging.info(f"Failed tables: {len(self.stats['failed_tables'])}")
        
        if self.skip_tables:
            logging.info(f"\nSkipped tables: {', '.join(self.skip_tables)}")
        
        if self.stats['failed_tables']:
            logging.error(f"\nFailed tables: {', '.join(self.stats['failed_tables'])}")
        
        logging.info("\n✓ Migration completed!")

    def close_connections(self):
        """Close database connections"""
        if self.source_conn:
            self.source_conn.close()
            logging.info("Closed source database connection")
        
        if self.dest_conn:
            self.dest_conn.close()
            logging.info("Closed destination database connection")

def main():
    """Main function to run the migration"""
    migrator = PostgreSQLMigrator()
    
    try:
        # Confirm before starting
        print("This will migrate data from Render PostgreSQL to Supabase PostgreSQL")
        print("This will TRUNCATE existing data in destination tables!")
        confirm = input("Are you sure you want to continue? (yes/no): ")
        
        if confirm.lower() != 'yes':
            print("Migration cancelled")
            return
        
        migrator.run_migration()
        
    except KeyboardInterrupt:
        logging.info("Migration interrupted by user")
    except Exception as e:
        logging.error(f"Migration failed with error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()