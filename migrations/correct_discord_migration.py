import sqlite3
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def upgrade_chatbot_database(db_path: str = "./chatbot.db"):
    """Add Discord fields to the existing chatbot.db SQLite database"""
    
    if not os.path.exists(db_path):
        logger.error(f"Database file {db_path} does not exist!")
        return False
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        logger.info(f"Starting Discord migration for {db_path}")
        
        # Add Discord fields to tenants table
        discord_tenant_fields = [
            ("discord_bot_token", "TEXT"),
            ("discord_application_id", "TEXT"), 
            ("discord_enabled", "BOOLEAN DEFAULT 0"),
            ("discord_status_message", "TEXT DEFAULT 'Chatting with customers'")
        ]
        
        logger.info("Adding Discord fields to tenants table...")
        for field_name, field_type in discord_tenant_fields:
            try:
                cursor.execute(f"""
                    ALTER TABLE tenants 
                    ADD COLUMN {field_name} {field_type};
                """)
                logger.info(f"✅ Added {field_name} to tenants table")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e):
                    logger.info(f"ℹ️  {field_name} already exists in tenants table")
                else:
                    logger.error(f"❌ Error adding {field_name}: {e}")
                    raise e
        
        # Add Discord fields to chat_sessions table
        discord_session_fields = [
            ("discord_channel_id", "TEXT"),
            ("discord_user_id", "TEXT"),
            ("discord_guild_id", "TEXT"),
            ("platform", "TEXT DEFAULT 'web'")
        ]
        
        logger.info("Adding Discord fields to chat_sessions table...")
        for field_name, field_type in discord_session_fields:
            try:
                cursor.execute(f"""
                    ALTER TABLE chat_sessions 
                    ADD COLUMN {field_name} {field_type};
                """)
                logger.info(f"✅ Added {field_name} to chat_sessions table")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e):
                    logger.info(f"ℹ️  {field_name} already exists in chat_sessions table")
                else:
                    logger.error(f"❌ Error adding {field_name}: {e}")
                    raise e
        
        # Commit all changes
        conn.commit()
        logger.info("✅ All Discord fields added successfully!")
        
        # Verify the changes
        logger.info("Verifying changes...")
        
        # Check tenants table structure
        cursor.execute("PRAGMA table_info(tenants);")
        tenant_columns = [col[1] for col in cursor.fetchall()]
        discord_tenant_columns = [field[0] for field in discord_tenant_fields]
        
        for col in discord_tenant_columns:
            if col in tenant_columns:
                logger.info(f"✅ Verified: {col} exists in tenants table")
            else:
                logger.error(f"❌ Missing: {col} not found in tenants table")
        
        # Check chat_sessions table structure
        cursor.execute("PRAGMA table_info(chat_sessions);")
        session_columns = [col[1] for col in cursor.fetchall()]
        discord_session_columns = [field[0] for field in discord_session_fields]
        
        for col in discord_session_columns:
            if col in session_columns:
                logger.info(f"✅ Verified: {col} exists in chat_sessions table")
            else:
                logger.error(f"❌ Missing: {col} not found in chat_sessions table")
        
        logger.info("🎉 Discord migration completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def show_updated_schema():
    """Show the updated database schema"""
    conn = sqlite3.connect("./chatbot.db")
    cursor = conn.cursor()
    
    try:
        print("\n📋 UPDATED DATABASE SCHEMA:")
        print("=" * 50)
        
        # Show tenants table schema
        print("\n🏢 TENANTS TABLE:")
        cursor.execute("PRAGMA table_info(tenants);")
        columns = cursor.fetchall()
        
        for col in columns:
            col_id, name, data_type, not_null, default_val, pk = col
            null_str = "NOT NULL" if not_null else "NULL"
            pk_str = "PRIMARY KEY" if pk else ""
            default_str = f"DEFAULT {default_val}" if default_val else ""
            
            # Highlight Discord fields
            prefix = "🆕" if name.startswith("discord") else "   "
            print(f"{prefix} {name}: {data_type} {null_str} {default_str} {pk_str}".strip())
        
        # Show chat_sessions table schema
        print("\n💬 CHAT_SESSIONS TABLE:")
        cursor.execute("PRAGMA table_info(chat_sessions);")
        columns = cursor.fetchall()
        
        for col in columns:
            col_id, name, data_type, not_null, default_val, pk = col
            null_str = "NOT NULL" if not_null else "NULL"
            pk_str = "PRIMARY KEY" if pk else ""
            default_str = f"DEFAULT {default_val}" if default_val else ""
            
            # Highlight Discord fields
            prefix = "🆕" if name.startswith("discord") or name == "platform" else "   "
            print(f"{prefix} {name}: {data_type} {null_str} {default_str} {pk_str}".strip())
            
    except Exception as e:
        print(f"Error showing schema: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    print("🚀 DISCORD INTEGRATION MIGRATION")
    print("=" * 50)
    print("This will add Discord fields to your chatbot.db database")
    print("Tables to be modified:")
    print("  • tenants (4 new Discord fields)")
    print("  • chat_sessions (4 new Discord fields)")
    
    response = input("\nProceed with migration? (y/n): ")
    
    if response.lower() in ['y', 'yes']:
        success = upgrade_chatbot_database()
        
        if success:
            show_updated_schema()
            print("\n🎉 SUCCESS!")
            print("Discord fields have been added to your database.")
            print("You can now proceed with the Discord bot integration!")
        else:
            print("\n❌ FAILED!")
            print("Migration failed. Please check the error messages above.")
    else:
        print("Migration cancelled.")