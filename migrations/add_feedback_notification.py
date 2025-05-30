import sqlite3
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def upgrade_chatbot_database(db_path: str = "./chatbot.db"):
    """Add missing feedback_notification_enabled field to tenants table"""
    
    if not os.path.exists(db_path):
        logger.error(f"Database file {db_path} does not exist!")
        return False
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        logger.info(f"Starting feedback notification field migration for {db_path}")
        
        # Add the missing field
        try:
            cursor.execute("""
                ALTER TABLE tenants 
                ADD COLUMN feedback_notification_enabled BOOLEAN DEFAULT 1;
            """)
            logger.info("✅ Added feedback_notification_enabled to tenants table")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                logger.info("ℹ️  feedback_notification_enabled already exists in tenants table")
            else:
                logger.error(f"❌ Error adding feedback_notification_enabled: {e}")
                raise e
        
        # Commit changes
        conn.commit()
        logger.info("✅ Migration completed successfully!")
        
        # Verify the change
        cursor.execute("PRAGMA table_info(tenants);")
        columns = [col[1] for col in cursor.fetchall()]
        
        if "feedback_notification_enabled" in columns:
            logger.info("✅ Verified: feedback_notification_enabled exists in tenants table")
        else:
            logger.error("❌ Missing: feedback_notification_enabled not found in tenants table")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def show_tenant_schema():
    """Show the current tenants table schema"""
    conn = sqlite3.connect("./chatbot.db")
    cursor = conn.cursor()
    
    try:
        print("\n📋 TENANTS TABLE SCHEMA:")
        print("=" * 50)
        
        cursor.execute("PRAGMA table_info(tenants);")
        columns = cursor.fetchall()
        
        for col in columns:
            col_id, name, data_type, not_null, default_val, pk = col
            null_str = "NOT NULL" if not_null else "NULL"
            pk_str = "PRIMARY KEY" if pk else ""
            default_str = f"DEFAULT {default_val}" if default_val else ""
            
            # Highlight the feedback field
            prefix = "🆕" if name == "feedback_notification_enabled" else "   "
            print(f"{prefix} {name}: {data_type} {null_str} {default_str} {pk_str}".strip())
            
    except Exception as e:
        print(f"Error showing schema: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    print("🔧 FEEDBACK NOTIFICATION FIELD FIX")
    print("=" * 50)
    print("This will add the missing 'feedback_notification_enabled' field")
    print("to your tenants table.")
    
    response = input("\nProceed with migration? (y/n): ")
    
    if response.lower() in ['y', 'yes']:
        success = upgrade_chatbot_database()
        
        if success:
            show_tenant_schema()
            print("\n🎉 SUCCESS!")
            print("Missing field has been added to your database.")
            print("You can now restart your application!")
        else:
            print("\n❌ FAILED!")
            print("Migration failed. Please check the error messages above.")
    else:
        print("Migration cancelled.")