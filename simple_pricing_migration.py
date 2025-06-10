#!/usr/bin/env python3
"""
Quick and Simple LiveChat Cleanup
Just deletes the livechat_addon plans directly
"""

import sqlite3
import psycopg2
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def cleanup_sqlite():
    """Clean up SQLite database"""
    try:
        conn = sqlite3.connect('./chatbot.db')
        cursor = conn.cursor()
        
        # Delete livechat addon plans
        cursor.execute("DELETE FROM pricing_plans WHERE plan_type = 'livechat_addon'")
        deleted_count = cursor.rowcount
        
        logger.info(f"SQLite: Deleted {deleted_count} livechat addon plans")
        
        # Update any orphaned subscriptions to use a valid plan
        cursor.execute("SELECT id FROM pricing_plans WHERE plan_type = 'free' AND is_active = 1 LIMIT 1")
        free_plan = cursor.fetchone()
        
        if free_plan:
            cursor.execute("""
                UPDATE tenant_subscriptions 
                SET plan_id = ? 
                WHERE plan_id NOT IN (SELECT id FROM pricing_plans) 
                AND is_active = 1
            """, (free_plan[0],))
            updated_count = cursor.rowcount
            logger.info(f"SQLite: Updated {updated_count} orphaned subscriptions")
        
        conn.commit()
        conn.close()
        
        logger.info("✅ SQLite cleanup completed")
        return True
        
    except Exception as e:
        logger.error(f"❌ SQLite cleanup failed: {e}")
        return False

def cleanup_postgres():
    """Clean up PostgreSQL database"""
    try:
        conn = psycopg2.connect(
            "postgresql://chatbot_hhjv_user:dYXguSEwpwZl3Yt2R3ACsfvmM5lLIgSD@dpg-d10sp295pdvs73afujf0-a.oregon-postgres.render.com/chatbot_hhjv"
        )
        cursor = conn.cursor()
        
        # Delete livechat addon plans
        cursor.execute("DELETE FROM pricing_plans WHERE plan_type = 'livechat_addon'")
        deleted_count = cursor.rowcount
        
        logger.info(f"PostgreSQL: Deleted {deleted_count} livechat addon plans")
        
        # Update any orphaned subscriptions to use a valid plan
        cursor.execute("SELECT id FROM pricing_plans WHERE plan_type = 'free' AND is_active = true LIMIT 1")
        free_plan = cursor.fetchone()
        
        if free_plan:
            cursor.execute("""
                UPDATE tenant_subscriptions 
                SET plan_id = %s 
                WHERE plan_id NOT IN (SELECT id FROM pricing_plans) 
                AND is_active = true
            """, (free_plan[0],))
            updated_count = cursor.rowcount
            logger.info(f"PostgreSQL: Updated {updated_count} orphaned subscriptions")
        
        conn.commit()
        conn.close()
        
        logger.info("✅ PostgreSQL cleanup completed")
        return True
        
    except Exception as e:
        logger.error(f"❌ PostgreSQL cleanup failed: {e}")
        return False

def main():
    logger.info("🚀 Starting Quick LiveChat Cleanup...")
    
    sqlite_success = cleanup_sqlite()
    postgres_success = cleanup_postgres()
    
    if sqlite_success and postgres_success:
        logger.info("🎉 All databases cleaned successfully!")
        return 0
    else:
        logger.error("💥 Some cleanups failed")
        return 1

if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)