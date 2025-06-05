#!/usr/bin/env python3
"""
Ultimate import script that checks PostgreSQL schema and converts data types accordingly
"""

import json
import psycopg2
from urllib.parse import urlparse
from datetime import datetime

def get_table_schema(cursor, table_name):
    """Get column data types for a table"""
    cursor.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = %s
    """, (table_name,))
    
    schema = {}
    for row in cursor.fetchall():
        column_name, data_type = row
        schema[column_name] = data_type
    
    return schema

def convert_value_by_schema(value, data_type):
    """Convert value based on PostgreSQL data type"""
    
    if value is None:
        return None
    
    # Handle boolean type
    if data_type == 'boolean':
        if value in [0, '0', False, 'false', 'False']:
            return False
        elif value in [1, '1', True, 'true', 'True']:
            return True
        else:
            return bool(value)
    
    # Handle timestamp types
    if 'timestamp' in data_type and value:
        try:
            if isinstance(value, str):
                return datetime.fromisoformat(value.replace('Z', '+00:00'))
            return value
        except:
            return value
    
    # Handle date types
    if data_type == 'date' and value:
        try:
            if isinstance(value, str):
                return datetime.fromisoformat(value.split('T')[0]).date()
            return value
        except:
            return value
    
    # Handle numeric types
    if data_type in ['integer', 'bigint', 'smallint']:
        try:
            return int(value) if value is not None else None
        except:
            return value
    
    if data_type in ['numeric', 'decimal', 'real', 'double precision']:
        try:
            return float(value) if value is not None else None
        except:
            return value
    
    # Return as-is for other types (text, varchar, etc.)
    return value

def import_to_postgresql():
    """Schema-aware import from JSON to PostgreSQL"""
    
    # Load the exported data
    try:
        with open('database_export_simple.json', 'r') as f:
            data = json.load(f)
        print(f"✅ Loaded export file with {len(data)} tables")
    except FileNotFoundError:
        print("❌ database_export_simple.json not found!")
        return
    except Exception as e:
        print(f"❌ Error loading export file: {e}")
        return
    
    # Get PostgreSQL connection
    database_url = input("Enter your PostgreSQL DATABASE_URL: ").strip()
    
    if not database_url.startswith('postgresql://'):
        print("❌ Invalid PostgreSQL URL")
        return
    
    try:
        url = urlparse(database_url)
        conn = psycopg2.connect(
            host=url.hostname,
            port=url.port or 5432,
            database=url.path[1:],
            user=url.username,
            password=url.password
        )
        
        conn.autocommit = False
        cursor = conn.cursor()
        print("✅ Connected to PostgreSQL")
        
        # Define import order for foreign key dependencies
        import_order = [
            'admins',
            'pricing_plans', 
            'tenants',
            'users',
            'tenant_credentials',
            'tenant_subscriptions',
            'tenant_password_resets',
            'knowledge_bases',
            'faqs',
            'chat_sessions',
            'chat_messages',
            'agents',
            'usage_logs',
            'live_chats',
            'live_chat_messages',
            'conversation_sessions'
        ]
        
        skip_tables = [
            'sqlite_sequence', 'alembic_version', 'admins_backup', 
            'pending_feedback', 'password_resets', 'booking_requests',
            'billing_history', 'agent_sessions', 'chat_queue',
            'slack_thread_memory', 'slack_channel_context'
        ]
        
        imported_tables = 0
        total_records = 0
        failed_tables = []
        
        # Import tables in order
        for table_name in import_order:
            if table_name not in data:
                continue
                
            records = data[table_name]
            if not records:
                print(f"⏭️ Skipping {table_name} (empty)")
                continue
            
            try:
                print(f"🔄 Importing {table_name} ({len(records)} records)...")
                
                # Get PostgreSQL schema for this table
                try:
                    schema = get_table_schema(cursor, table_name)
                    if not schema:
                        print(f"⚠️ Table {table_name} doesn't exist in PostgreSQL, skipping")
                        continue
                except Exception as e:
                    print(f"⚠️ Could not get schema for {table_name}: {e}")
                    continue
                
                # Get columns from first record
                columns = list(records[0].keys())
                
                # Filter out columns that don't exist in PostgreSQL
                valid_columns = [col for col in columns if col in schema]
                if len(valid_columns) != len(columns):
                    missing = set(columns) - set(valid_columns)
                    print(f"   Note: Skipping columns not in PostgreSQL: {missing}")
                
                if not valid_columns:
                    print(f"⚠️ No valid columns for {table_name}")
                    continue
                
                # Create INSERT statement
                placeholders = ', '.join(['%s'] * len(valid_columns))
                columns_str = ', '.join([f'"{col}"' for col in valid_columns])
                insert_sql = f'INSERT INTO "{table_name}" ({columns_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'
                
                # Prepare data with schema-aware conversion
                values_list = []
                for record in records:
                    converted_values = []
                    for col in valid_columns:
                        original_value = record.get(col)
                        pg_data_type = schema[col]
                        converted_value = convert_value_by_schema(original_value, pg_data_type)
                        converted_values.append(converted_value)
                    values_list.append(converted_values)
                
                # Execute batch insert
                cursor.executemany(insert_sql, values_list)
                imported_count = cursor.rowcount
                print(f"✅ {table_name}: {imported_count} records imported")
                
                conn.commit()
                imported_tables += 1
                total_records += imported_count
                
            except Exception as e:
                print(f"⚠️ Error importing {table_name}: {e}")
                failed_tables.append(table_name)
                conn.rollback()
                continue
        
        print(f"\n🎉 Import completed!")
        print(f"📊 Tables imported: {imported_tables}")
        print(f"📊 Total records imported: {total_records}")
        
        if failed_tables:
            print(f"⚠️ Failed tables: {', '.join(failed_tables)}")
        
        # Final verification
        print(f"\n🔍 Final verification:")
        key_tables = ['tenants', 'admins', 'chat_messages', 'users', 'pricing_plans']
        for table in key_tables:
            try:
                cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
                count = cursor.fetchone()[0]
                print(f"  - {table}: {count} records")
            except Exception as e:
                print(f"  - {table}: {e}")
        
    except Exception as e:
        print(f"❌ Database error: {e}")
        
    finally:
        if 'conn' in locals():
            conn.close()
            print("✅ Database connection closed")

if __name__ == "__main__":
    print("🚀 Ultimate PostgreSQL Import - Schema Aware")
    print("This script checks PostgreSQL schema and converts data types automatically")
    print()
    import_to_postgresql()