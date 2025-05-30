import sqlite3
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def upgrade_chatbot_database(db_path: str = "./chatbot.db"):
    """Add Slack fields to the existing chatbot.db SQLite database"""
    
    if not os.path.exists(db_path):
        logger.error(f"Database file {db_path} does not exist!")
        return False
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        logger.info(f"Starting Slack migration for {db_path}")
        
        # Add Slack fields to tenants table
        slack_tenant_fields = [
            ("slack_bot_token", "TEXT"),
            ("slack_signing_secret", "TEXT"),
            ("slack_app_id", "TEXT"),
            ("slack_client_id", "TEXT"),
            ("slack_client_secret", "TEXT"),
            ("slack_enabled", "BOOLEAN DEFAULT 0"),
            ("slack_team_id", "TEXT"),
            ("slack_bot_user_id", "TEXT")
        ]
        
        logger.info("Adding Slack fields to tenants table...")
        for field_name, field_type in slack_tenant_fields:
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
        
        # Commit all changes
        conn.commit()
        logger.info("✅ All Slack fields added successfully!")
        
        # Verify the changes
        logger.info("Verifying changes...")
        
        # Check tenants table structure
        cursor.execute("PRAGMA table_info(tenants);")
        tenant_columns = [col[1] for col in cursor.fetchall()]
        slack_tenant_columns = [field[0] for field in slack_tenant_fields]
        
        for col in slack_tenant_columns:
            if col in tenant_columns:
                logger.info(f"✅ Verified: {col} exists in tenants table")
            else:
                logger.error(f"❌ Missing: {col} not found in tenants table")
        
        logger.info("🎉 Slack migration completed successfully!")
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
            
            # Highlight Slack fields
            prefix = "🆕" if name.startswith("slack") else "   "
            print(f"{prefix} {name}: {data_type} {null_str} {default_str} {pk_str}".strip())
            
    except Exception as e:
        print(f"Error showing schema: {e}")
    finally:
        conn.close()

def check_existing_integrations():
    """Check what integrations are already available"""
    conn = sqlite3.connect("./chatbot.db")
    cursor = conn.cursor()
    
    try:
        print("\n🔍 CHECKING EXISTING INTEGRATIONS:")
        print("=" * 50)
        
        cursor.execute("PRAGMA table_info(tenants);")
        columns = [col[1] for col in cursor.fetchall()]
        
        # Check Discord
        discord_fields = ["discord_bot_token", "discord_enabled"]
        has_discord = any(field in columns for field in discord_fields)
        print(f"Discord Integration: {'✅ Available' if has_discord else '❌ Not Available'}")
        
        # Check Slack
        slack_fields = ["slack_bot_token", "slack_enabled"]
        has_slack = any(field in columns for field in slack_fields)
        print(f"Slack Integration: {'✅ Available' if has_slack else '❌ Not Available'}")
        
        # Check platform field in chat_sessions
        cursor.execute("PRAGMA table_info(chat_sessions);")
        session_columns = [col[1] for col in cursor.fetchall()]
        has_platform = "platform" in session_columns
        print(f"Multi-Platform Support: {'✅ Available' if has_platform else '❌ Not Available'}")
        
        return has_slack
        
    except Exception as e:
        print(f"Error checking integrations: {e}")
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    print("🚀 SLACK INTEGRATION MIGRATION")
    print("=" * 50)
    print("This will add Slack fields to your chatbot.db database")
    print("New fields to be added to tenants table:")
    print("  • slack_bot_token (Bot OAuth Token)")
    print("  • slack_signing_secret (App Signing Secret)")
    print("  • slack_app_id (Slack App ID)")
    print("  • slack_client_id (OAuth Client ID)")
    print("  • slack_client_secret (OAuth Client Secret)")
    print("  • slack_enabled (Enable/Disable flag)")
    print("  • slack_team_id (Workspace ID)")
    print("  • slack_bot_user_id (Bot User ID)")
    
    # Check current status
    already_has_slack = check_existing_integrations()
    
    if already_has_slack:
        print("\n⚠️  WARNING: Slack fields may already exist in your database!")
        print("The migration will skip existing fields automatically.")
    
    response = input("\nProceed with Slack migration? (y/n): ")
    
    if response.lower() in ['y', 'yes']:
        success = upgrade_chatbot_database()
        
        if success:
            show_updated_schema()
            print("\n🎉 SUCCESS!")
            print("Slack fields have been added to your database.")
            print("\n🚀 Next Steps:")
            print("1. Update your Tenant model in app/tenants/models.py")
            print("2. Add the Slack integration files to app/slack/")
            print("3. Update main.py to include Slack router")
            print("4. Create a Slack app and configure it")
            print("5. Test with your first tenant!")
            
            print("\n📖 Integration Guide:")
            print("Follow the SLACK_SETUP.md guide for complete setup instructions")
        else:
            print("\n❌ FAILED!")
            print("Migration failed. Please check the error messages above.")
    else:
        print("Migration cancelled.")