#!/usr/bin/env python3
"""
Simple Email Normalization Script
Normalizes emails in both SQLite and PostgreSQL databases without circular imports
"""

import sqlite3
import psycopg2
import os
import argparse
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def normalize_sqlite_emails(db_path="chatbot.db"):
    """Normalize emails in SQLite database"""
    logger.info(f"🔄 Connecting to SQLite database: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get all tenants with their emails
        cursor.execute("SELECT id, email FROM tenants WHERE email IS NOT NULL")
        tenants = cursor.fetchall()
        
        logger.info(f"📊 Found {len(tenants)} tenants")
        
        updated_count = 0
        conflicts = 0
        
        for tenant_id, email in tenants:
            normalized_email = email.lower().strip()
            
            if email != normalized_email:
                # Check for conflicts
                cursor.execute(
                    "SELECT id FROM tenants WHERE LOWER(email) = ? AND id != ?", 
                    (normalized_email, tenant_id)
                )
                conflict = cursor.fetchone()
                
                if conflict:
                    logger.warning(f"⚠️ Conflict: {email} -> {normalized_email} already exists")
                    conflicts += 1
                    continue
                
                # Update the email
                cursor.execute(
                    "UPDATE tenants SET email = ? WHERE id = ?", 
                    (normalized_email, tenant_id)
                )
                logger.info(f"✅ Updated tenant {tenant_id}: {email} -> {normalized_email}")
                updated_count += 1
        
        conn.commit()
        logger.info(f"🎉 SQLite: Updated {updated_count} emails, {conflicts} conflicts found")
        
    except Exception as e:
        logger.error(f"❌ SQLite error: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()
    
    return True

def normalize_postgresql_emails(database_url):
    """Normalize emails in PostgreSQL database"""
    logger.info(f"🔄 Connecting to PostgreSQL database")
    
    try:
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()
        
        # Get all tenants with their emails
        cursor.execute("SELECT id, email FROM tenants WHERE email IS NOT NULL")
        tenants = cursor.fetchall()
        
        logger.info(f"📊 Found {len(tenants)} tenants")
        
        updated_count = 0
        conflicts = 0
        
        for tenant_id, email in tenants:
            normalized_email = email.lower().strip()
            
            if email != normalized_email:
                # Check for conflicts
                cursor.execute(
                    "SELECT id FROM tenants WHERE LOWER(email) = %s AND id != %s", 
                    (normalized_email, tenant_id)
                )
                conflict = cursor.fetchone()
                
                if conflict:
                    logger.warning(f"⚠️ Conflict: {email} -> {normalized_email} already exists")
                    conflicts += 1
                    continue
                
                # Update the email
                cursor.execute(
                    "UPDATE tenants SET email = %s WHERE id = %s", 
                    (normalized_email, tenant_id)
                )
                logger.info(f"✅ Updated tenant {tenant_id}: {email} -> {normalized_email}")
                updated_count += 1
        
        conn.commit()
        logger.info(f"🎉 PostgreSQL: Updated {updated_count} emails, {conflicts} conflicts found")
        
    except Exception as e:
        logger.error(f"❌ PostgreSQL error: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()
    
    return True

def main():
    parser = argparse.ArgumentParser(description="Normalize email addresses in tenant database")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--local", action="store_true", help="Use local SQLite database")
    group.add_argument("--production", action="store_true", help="Use production PostgreSQL")
    group.add_argument("--custom", action="store_true", help="Use DATABASE_URL from environment")
    
    args = parser.parse_args()
    
    try:
        if args.local:
            logger.info("🎯 Target: LOCAL SQLite database")
            success = normalize_sqlite_emails()
        
        elif args.production or args.custom:
            logger.info("🎯 Target: PostgreSQL database")
            
            # Get PostgreSQL URL from environment
            database_url = (
                os.getenv("RENDER_DATABASE_URL") or 
                os.getenv("PRODUCTION_DATABASE_URL") or 
                os.getenv("DATABASE_URL")
            )
            
            if not database_url:
                logger.error("❌ No PostgreSQL URL found. Set RENDER_DATABASE_URL or DATABASE_URL")
                return
            
            # Check if it's actually a PostgreSQL URL
            if not database_url.startswith('postgresql://'):
                logger.error(f"❌ Expected PostgreSQL URL but got: {database_url}")
                logger.error("❌ Make sure your environment variable contains a PostgreSQL URL")
                return
            
            # Confirm production operation (only if not custom)
            if args.production:
                response = input("\n⚠️  You are about to modify PRODUCTION database. Continue? (yes/no): ")
                if response.lower() not in ["yes", "y"]:
                    logger.info("❌ Operation cancelled")
                    return
            
            success = normalize_postgresql_emails(database_url)
        
        if success:
            logger.info("🎉 Email normalization completed successfully!")
        else:
            logger.error("❌ Email normalization failed!")
            
    except KeyboardInterrupt:
        logger.info("\n⚠️ Operation cancelled by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")

if __name__ == "__main__":
    main()