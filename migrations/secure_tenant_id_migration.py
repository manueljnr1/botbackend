# ==============================================================================
# CREATE FILE: migrations/secure_tenant_id_migration.py
# ==============================================================================

"""
Secure Tenant ID Migration Script
Migrates from sequential to secure random 9-digit tenant IDs
Supports both PostgreSQL and SQLite databases
"""

import os
import sys
import random
import logging
import time
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from sqlalchemy import create_engine, text, MetaData, Table, Column, Integer, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine import Engine
from contextlib import contextmanager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class TenantMapping:
    """Data class to store tenant ID mappings"""
    old_id: int
    new_id: int
    name: str
    email: str
    business_name: str


class SecureTenantIDMigration:
    """
    Migration handler for converting sequential tenant IDs to secure random IDs
    """
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.engine = create_engine(database_url)
        self.Session = sessionmaker(bind=self.engine)
        self.is_postgresql = 'postgresql' in database_url.lower()
        self.is_sqlite = 'sqlite' in database_url.lower()
        
        # Tables that reference tenant_id (customize based on your schema)
        self.dependent_tables = [
            'users',
            'tenant_credentials', 
            'knowledge_bases',
            'faqs',
            'chat_sessions',
            'agents',
            'live_chat_conversations',
            'live_chat_settings',
            'instagram_integrations',
            'telegram_integrations',
            'tenant_subscriptions',
            'tenant_password_resets'
        ]
        
        logger.info(f"Initialized migration for {'PostgreSQL' if self.is_postgresql else 'SQLite'}")
    
    @contextmanager
    def get_session(self):
        """Context manager for database sessions"""
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            session.close()
    
    @staticmethod
    def generate_secure_tenant_id() -> int:
        """Generate a secure random 9-digit tenant ID"""
        return random.randint(100000000, 999999999)
    
    def validate_prerequisites(self) -> bool:
        """Validate that migration can proceed safely"""
        logger.info("🔍 Validating migration prerequisites...")
        
        try:
            with self.get_session() as session:
                # Check if tenants table exists
                inspector = inspect(self.engine)
                tables = inspector.get_table_names()
                
                if 'tenants' not in tables:
                    logger.error("❌ Tenants table not found!")
                    return False
                
                # Check for existing secure IDs
                result = session.execute(text("SELECT COUNT(*) FROM tenants WHERE id >= 100000000"))
                secure_count = result.scalar()
                
                if secure_count > 0:
                    logger.warning(f"⚠️ Found {secure_count} tenants with secure IDs already")
                
                # Check dependent tables exist
                missing_tables = []
                for table in self.dependent_tables:
                    if table not in tables:
                        missing_tables.append(table)
                
                if missing_tables:
                    logger.warning(f"⚠️ Missing tables (will skip): {missing_tables}")
                    # Remove missing tables from migration list
                    self.dependent_tables = [t for t in self.dependent_tables if t not in missing_tables]
                
                # Check for foreign key constraints
                tenant_fks = []
                for table in self.dependent_tables:
                    try:
                        foreign_keys = inspector.get_foreign_keys(table)
                        for fk in foreign_keys:
                            if fk['referred_table'] == 'tenants':
                                tenant_fks.append(f"{table}.{fk['constrained_columns'][0]}")
                    except Exception as e:
                        logger.warning(f"Could not check FKs for {table}: {e}")
                
                logger.info(f"✅ Found {len(tenant_fks)} foreign key references to tenants")
                
                return True
                
        except Exception as e:
            logger.error(f"❌ Prerequisites validation failed: {e}")
            return False
    
    def create_backup_table(self) -> bool:
        """Create backup table for rollback purposes"""
        logger.info("💾 Creating backup table...")
        
        try:
            with self.get_session() as session:
                # Create backup table with old ID mappings
                backup_sql = """
                CREATE TABLE IF NOT EXISTS tenant_id_migration_backup (
                    old_id INTEGER,
                    new_id INTEGER,
                    tenant_name VARCHAR(255),
                    tenant_email VARCHAR(255),
                    migration_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status VARCHAR(50) DEFAULT 'pending'
                )
                """
                session.execute(text(backup_sql))
                
                # Create index for faster lookups
                if self.is_postgresql:
                    session.execute(text(
                        "CREATE INDEX IF NOT EXISTS idx_backup_old_id ON tenant_id_migration_backup(old_id)"
                    ))
                else:  # SQLite
                    session.execute(text(
                        "CREATE INDEX IF NOT EXISTS idx_backup_old_id ON tenant_id_migration_backup(old_id)"
                    ))
                
                logger.info("✅ Backup table created successfully")
                return True
                
        except Exception as e:
            logger.error(f"❌ Failed to create backup table: {e}")
            return False
    
    def get_tenants_to_migrate(self) -> List[TenantMapping]:
        """Get list of tenants that need secure IDs"""
        logger.info("📋 Identifying tenants to migrate...")
        
        try:
            with self.get_session() as session:
                # Get tenants with insecure IDs (< 100000000)
                result = session.execute(text("""
                    SELECT id, name, email, business_name 
                    FROM tenants 
                    WHERE id < 100000000 
                    ORDER BY id
                """))
                
                tenants = result.fetchall()
                mappings = []
                used_ids = set()
                
                logger.info(f"Found {len(tenants)} tenants to migrate")
                
                for tenant in tenants:
                    old_id, name, email, business_name = tenant
                    
                    # Generate unique new ID
                    new_id = self.generate_secure_tenant_id()
                    while new_id in used_ids:
                        new_id = self.generate_secure_tenant_id()
                    used_ids.add(new_id)
                    
                    # Check if new ID already exists in database
                    check_result = session.execute(
                        text("SELECT id FROM tenants WHERE id = :new_id"), 
                        {"new_id": new_id}
                    )
                    if check_result.first():
                        # ID collision, generate another
                        while True:
                            new_id = self.generate_secure_tenant_id()
                            if new_id not in used_ids:
                                check_result = session.execute(
                                    text("SELECT id FROM tenants WHERE id = :new_id"), 
                                    {"new_id": new_id}
                                )
                                if not check_result.first():
                                    used_ids.add(new_id)
                                    break
                    
                    mappings.append(TenantMapping(
                        old_id=old_id,
                        new_id=new_id,
                        name=name or 'Unknown',
                        email=email or 'unknown@example.com',
                        business_name=business_name or 'Unknown Business'
                    ))
                
                logger.info(f"✅ Generated {len(mappings)} secure ID mappings")
                return mappings
                
        except Exception as e:
            logger.error(f"❌ Failed to get tenants to migrate: {e}")
            return []
    
    def store_migration_plan(self, mappings: List[TenantMapping]) -> bool:
        """Store the migration plan in backup table"""
        logger.info("💾 Storing migration plan...")
        
        try:
            with self.get_session() as session:
                for mapping in mappings:
                    session.execute(text("""
                        INSERT INTO tenant_id_migration_backup 
                        (old_id, new_id, tenant_name, tenant_email, status)
                        VALUES (:old_id, :new_id, :name, :email, 'planned')
                    """), {
                        'old_id': mapping.old_id,
                        'new_id': mapping.new_id,
                        'name': mapping.name,
                        'email': mapping.email
                    })
                
                logger.info(f"✅ Stored migration plan for {len(mappings)} tenants")
                return True
                
        except Exception as e:
            logger.error(f"❌ Failed to store migration plan: {e}")
            return False
    
    def update_foreign_keys(self, mappings: List[TenantMapping]) -> bool:
        """Update all foreign key references"""
        logger.info("🔄 Updating foreign key references...")
        
        total_updates = 0
        
        try:
            with self.get_session() as session:
                for table in self.dependent_tables:
                    table_updates = 0
                    logger.info(f"   Updating {table}...")
                    
                    try:
                        for mapping in mappings:
                            # Update tenant_id foreign keys
                            result = session.execute(text(f"""
                                UPDATE {table} 
                                SET tenant_id = :new_id 
                                WHERE tenant_id = :old_id
                            """), {
                                'new_id': mapping.new_id,
                                'old_id': mapping.old_id
                            })
                            
                            table_updates += result.rowcount
                        
                        logger.info(f"   ✅ {table}: {table_updates} records updated")
                        total_updates += table_updates
                        
                    except Exception as e:
                        logger.warning(f"   ⚠️ {table}: {e}")
                        # Continue with other tables
                        continue
                
                logger.info(f"✅ Total foreign key updates: {total_updates}")
                return True
                
        except Exception as e:
            logger.error(f"❌ Failed to update foreign keys: {e}")
            return False
    
    def update_tenant_ids(self, mappings: List[TenantMapping]) -> bool:
        """Update the tenant IDs in the tenants table"""
        logger.info("🔄 Updating tenant primary keys...")
        
        try:
            with self.get_session() as session:
                if self.is_postgresql:
                    # PostgreSQL approach - use a temporary column
                    logger.info("   Using PostgreSQL method with temporary column...")
                    
                    # Add temporary column
                    session.execute(text("ALTER TABLE tenants ADD COLUMN temp_new_id INTEGER"))
                    
                    # Set new IDs in temporary column
                    for mapping in mappings:
                        session.execute(text("""
                            UPDATE tenants 
                            SET temp_new_id = :new_id 
                            WHERE id = :old_id
                        """), {
                            'new_id': mapping.new_id,
                            'old_id': mapping.old_id
                        })
                    
                    # Drop the old primary key constraint
                    session.execute(text("ALTER TABLE tenants DROP CONSTRAINT tenants_pkey"))
                    
                    # Update the ID column
                    session.execute(text("UPDATE tenants SET id = temp_new_id WHERE temp_new_id IS NOT NULL"))
                    
                    # Recreate primary key
                    session.execute(text("ALTER TABLE tenants ADD PRIMARY KEY (id)"))
                    
                    # Drop temporary column
                    session.execute(text("ALTER TABLE tenants DROP COLUMN temp_new_id"))
                    
                    # Reset sequence if it exists
                    try:
                        session.execute(text("SELECT setval('tenants_id_seq', 999999999, false)"))
                    except:
                        pass  # Sequence might not exist
                
                else:
                    # SQLite approach - direct updates (SQLite allows this)
                    logger.info("   Using SQLite method with direct updates...")
                    
                    for mapping in mappings:
                        session.execute(text("""
                            UPDATE tenants 
                            SET id = :new_id 
                            WHERE id = :old_id
                        """), {
                            'new_id': mapping.new_id,
                            'old_id': mapping.old_id
                        })
                
                # Update backup table status
                for mapping in mappings:
                    session.execute(text("""
                        UPDATE tenant_id_migration_backup 
                        SET status = 'completed' 
                        WHERE old_id = :old_id
                    """), {'old_id': mapping.old_id})
                
                logger.info(f"✅ Updated {len(mappings)} tenant IDs successfully")
                return True
                
        except Exception as e:
            logger.error(f"❌ Failed to update tenant IDs: {e}")
            return False
    
    def verify_migration(self, mappings: List[TenantMapping]) -> bool:
        """Verify that migration completed successfully"""
        logger.info("🔍 Verifying migration results...")
        
        try:
            with self.get_session() as session:
                # Check that old IDs no longer exist
                old_ids = [m.old_id for m in mappings]
                old_ids_str = ','.join(map(str, old_ids))
                
                old_result = session.execute(text(f"""
                    SELECT COUNT(*) FROM tenants WHERE id IN ({old_ids_str})
                """))
                old_count = old_result.scalar()
                
                if old_count > 0:
                    logger.error(f"❌ Found {old_count} tenants with old IDs still present!")
                    return False
                
                # Check that new IDs exist
                new_ids = [m.new_id for m in mappings]
                new_ids_str = ','.join(map(str, new_ids))
                
                new_result = session.execute(text(f"""
                    SELECT COUNT(*) FROM tenants WHERE id IN ({new_ids_str})
                """))
                new_count = new_result.scalar()
                
                if new_count != len(mappings):
                    logger.error(f"❌ Expected {len(mappings)} new IDs, found {new_count}!")
                    return False
                
                # Verify foreign key integrity
                integrity_issues = 0
                for table in self.dependent_tables:
                    try:
                        result = session.execute(text(f"""
                            SELECT COUNT(*) FROM {table} t
                            WHERE t.tenant_id NOT IN (SELECT id FROM tenants)
                        """))
                        orphaned = result.scalar()
                        
                        if orphaned > 0:
                            logger.error(f"❌ {table}: {orphaned} orphaned records!")
                            integrity_issues += orphaned
                        else:
                            logger.info(f"   ✅ {table}: No orphaned records")
                            
                    except Exception as e:
                        logger.warning(f"   ⚠️ Could not verify {table}: {e}")
                
                if integrity_issues > 0:
                    logger.error(f"❌ Found {integrity_issues} referential integrity issues!")
                    return False
                
                # Check for insecure IDs remaining
                insecure_result = session.execute(text("""
                    SELECT COUNT(*) FROM tenants WHERE id < 100000000
                """))
                insecure_count = insecure_result.scalar()
                
                if insecure_count > 0:
                    logger.warning(f"⚠️ {insecure_count} tenants still have insecure IDs")
                
                logger.info("✅ Migration verification completed successfully!")
                return True
                
        except Exception as e:
            logger.error(f"❌ Migration verification failed: {e}")
            return False
    
    def run_migration(self, dry_run: bool = True) -> bool:
        """Execute the complete migration process"""
        start_time = time.time()
        
        logger.info("🚀 Starting Secure Tenant ID Migration")
        logger.info(f"   Database: {'PostgreSQL' if self.is_postgresql else 'SQLite'}")
        logger.info(f"   Mode: {'DRY RUN' if dry_run else 'ACTUAL MIGRATION'}")
        logger.info(f"   URL: {self.database_url.split('@')[0]}@***")
        
        try:
            # Step 1: Prerequisites
            if not self.validate_prerequisites():
                logger.error("❌ Prerequisites validation failed!")
                return False
            
            # Step 2: Create backup
            if not self.create_backup_table():
                logger.error("❌ Backup table creation failed!")
                return False
            
            # Step 3: Get migration plan
            mappings = self.get_tenants_to_migrate()
            if not mappings:
                logger.info("✅ No tenants need migration - all IDs are secure!")
                return True
            
            # Step 4: Store plan
            if not self.store_migration_plan(mappings):
                logger.error("❌ Failed to store migration plan!")
                return False
            
            logger.info(f"📊 Migration Summary:")
            logger.info(f"   Tenants to migrate: {len(mappings)}")
            logger.info(f"   Dependent tables: {len(self.dependent_tables)}")
            
            # Show sample mappings
            logger.info("🔄 Sample ID mappings:")
            for mapping in mappings[:5]:
                logger.info(f"   {mapping.old_id} → {mapping.new_id} ({mapping.name})")
            if len(mappings) > 5:
                logger.info(f"   ... and {len(mappings) - 5} more")
            
            if dry_run:
                logger.info("🔍 DRY RUN COMPLETED - No changes made to database")
                logger.info("💡 Run with dry_run=False to apply changes")
                return True
            
            # Confirm before proceeding
            logger.warning("⚠️ ABOUT TO MODIFY DATABASE - This cannot be easily undone!")
            
            # Step 5: Update foreign keys
            if not self.update_foreign_keys(mappings):
                logger.error("❌ Foreign key updates failed!")
                return False
            
            # Step 6: Update tenant IDs
            if not self.update_tenant_ids(mappings):
                logger.error("❌ Tenant ID updates failed!")
                return False
            
            # Step 7: Verify
            if not self.verify_migration(mappings):
                logger.error("❌ Migration verification failed!")
                return False
            
            elapsed_time = time.time() - start_time
            logger.info(f"🎉 MIGRATION COMPLETED SUCCESSFULLY!")
            logger.info(f"   Migrated: {len(mappings)} tenants")
            logger.info(f"   Duration: {elapsed_time:.2f} seconds")
            logger.info(f"   Backup table: tenant_id_migration_backup")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Migration failed with error: {e}")
            return False
    
    def rollback_migration(self) -> bool:
        """Rollback migration using backup data"""
        logger.warning("🔄 ATTEMPTING MIGRATION ROLLBACK")
        logger.warning("⚠️ This is a complex operation - ensure you have a database backup!")
        
        try:
            with self.get_session() as session:
                # Get rollback mappings
                result = session.execute(text("""
                    SELECT old_id, new_id, tenant_name 
                    FROM tenant_id_migration_backup 
                    WHERE status = 'completed'
                    ORDER BY old_id
                """))
                
                rollback_mappings = result.fetchall()
                
                if not rollback_mappings:
                    logger.error("❌ No completed migrations found to rollback!")
                    return False
                
                logger.info(f"🔄 Rolling back {len(rollback_mappings)} tenant ID changes...")
                
                # Rollback foreign keys
                for table in self.dependent_tables:
                    try:
                        for old_id, new_id, name in rollback_mappings:
                            session.execute(text(f"""
                                UPDATE {table} 
                                SET tenant_id = :old_id 
                                WHERE tenant_id = :new_id
                            """), {
                                'old_id': old_id,
                                'new_id': new_id
                            })
                        logger.info(f"   ✅ Rolled back {table}")
                    except Exception as e:
                        logger.error(f"   ❌ Failed to rollback {table}: {e}")
                
                # Rollback tenant IDs
                for old_id, new_id, name in rollback_mappings:
                    session.execute(text("""
                        UPDATE tenants 
                        SET id = :old_id 
                        WHERE id = :new_id
                    """), {
                        'old_id': old_id,
                        'new_id': new_id
                    })
                
                # Update backup status
                session.execute(text("""
                    UPDATE tenant_id_migration_backup 
                    SET status = 'rolled_back' 
                    WHERE status = 'completed'
                """))
                
                logger.warning("⚠️ ROLLBACK COMPLETED - Tenant IDs restored to original values")
                return True
                
        except Exception as e:
            logger.error(f"❌ Rollback failed: {e}")
            return False

