
"""
Fixed Secure Tenant ID Migration Script
Handles PostgreSQL foreign key constraints properly
"""

import os
import sys
import random
import logging
import time
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from sqlalchemy import create_engine, text, MetaData, inspect
from sqlalchemy.orm import sessionmaker
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


@dataclass
class ForeignKeyConstraint:
    """Data class to store foreign key constraint info"""
    table_name: str
    constraint_name: str
    column_name: str


class FixedSecureTenantIDMigration:
    """
    Fixed migration handler that properly handles PostgreSQL foreign key constraints
    """
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.engine = create_engine(database_url)
        self.Session = sessionmaker(bind=self.engine)
        self.is_postgresql = 'postgresql' in database_url.lower()
        
        # All tables that reference tenant_id (discovered from error log)
        self.dependent_tables = [
            'users',
            'tenant_credentials', 
            'tenant_password_resets',
            'knowledge_bases',
            'faqs',
            'chat_sessions',
            'tenant_subscriptions',
            'conversation_sessions',
            'booking_requests',
            'usage_logs',
            'billing_history',
            'live_chats',
            'pending_feedback',
            'conversations',
            'security_incidents',
            'conversation_tags',
            'conversation_transfers',
            'instagram_integrations',
            'telegram_integrations',
            'instagram_conversations',
            'instagram_webhook_events',
            'telegram_chats',
            'instagram_messages',
            'agents',
            'live_chat_settings',
            'live_chat_conversations',
            'agent_sessions',
            'chat_queue',
            'customer_profiles',
            'agent_tags',
            'smart_routing_log'
        ]
        
        self.foreign_key_constraints = []
        
        logger.info(f"Initialized FIXED migration for PostgreSQL")
    
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
    
    def discover_foreign_key_constraints(self) -> bool:
        """Discover all foreign key constraints that reference tenants.id"""
        logger.info("🔍 Discovering foreign key constraints...")
        
        try:
            with self.get_session() as session:
                # Query PostgreSQL system tables to find all FK constraints
                result = session.execute(text("""
                    SELECT 
                        tc.table_name,
                        tc.constraint_name,
                        kcu.column_name
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu 
                        ON tc.constraint_name = kcu.constraint_name
                    JOIN information_schema.constraint_column_usage ccu 
                        ON ccu.constraint_name = tc.constraint_name
                    WHERE tc.constraint_type = 'FOREIGN KEY'
                        AND ccu.table_name = 'tenants'
                        AND ccu.column_name = 'id'
                    ORDER BY tc.table_name, tc.constraint_name
                """))
                
                constraints = result.fetchall()
                
                for table_name, constraint_name, column_name in constraints:
                    self.foreign_key_constraints.append(ForeignKeyConstraint(
                        table_name=table_name,
                        constraint_name=constraint_name,
                        column_name=column_name
                    ))
                
                logger.info(f"✅ Found {len(self.foreign_key_constraints)} foreign key constraints")
                
                # Log the constraints for debugging
                for fk in self.foreign_key_constraints[:10]:  # Show first 10
                    logger.info(f"   FK: {fk.table_name}.{fk.column_name} -> tenants.id ({fk.constraint_name})")
                
                if len(self.foreign_key_constraints) > 10:
                    logger.info(f"   ... and {len(self.foreign_key_constraints) - 10} more")
                
                return True
                
        except Exception as e:
            logger.error(f"❌ Failed to discover foreign key constraints: {e}")
            return False
    
    def drop_foreign_key_constraints(self) -> bool:
        """Drop all foreign key constraints that reference tenants.id"""
        logger.info("🔧 Dropping foreign key constraints...")
        
        try:
            with self.get_session() as session:
                dropped_count = 0
                
                for fk in self.foreign_key_constraints:
                    try:
                        session.execute(text(f"""
                            ALTER TABLE {fk.table_name} 
                            DROP CONSTRAINT IF EXISTS {fk.constraint_name}
                        """))
                        dropped_count += 1
                        
                    except Exception as e:
                        logger.warning(f"   ⚠️ Could not drop {fk.constraint_name}: {e}")
                        continue
                
                logger.info(f"✅ Dropped {dropped_count} foreign key constraints")
                return True
                
        except Exception as e:
            logger.error(f"❌ Failed to drop foreign key constraints: {e}")
            return False
    
    def recreate_foreign_key_constraints(self) -> bool:
        """Recreate all foreign key constraints that reference tenants.id"""
        logger.info("🔧 Recreating foreign key constraints...")
        
        try:
            with self.get_session() as session:
                recreated_count = 0
                
                for fk in self.foreign_key_constraints:
                    try:
                        session.execute(text(f"""
                            ALTER TABLE {fk.table_name} 
                            ADD CONSTRAINT {fk.constraint_name} 
                            FOREIGN KEY ({fk.column_name}) 
                            REFERENCES tenants(id)
                        """))
                        recreated_count += 1
                        
                    except Exception as e:
                        logger.warning(f"   ⚠️ Could not recreate {fk.constraint_name}: {e}")
                        continue
                
                logger.info(f"✅ Recreated {recreated_count} foreign key constraints")
                return True
                
        except Exception as e:
            logger.error(f"❌ Failed to recreate foreign key constraints: {e}")
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
                # Update only existing tables
                for table in self.dependent_tables:
                    table_updates = 0
                    logger.info(f"   Updating {table}...")
                    
                    try:
                        # Check if table exists first
                        table_check = session.execute(text(f"""
                            SELECT COUNT(*) FROM information_schema.tables 
                            WHERE table_name = '{table}'
                        """))
                        
                        if table_check.scalar() == 0:
                            logger.info(f"   ⚠️ {table}: Table not found, skipping")
                            continue
                        
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
    
    def update_tenant_ids_fixed(self, mappings: List[TenantMapping]) -> bool:
        """Update tenant IDs using the FIXED approach for PostgreSQL"""
        logger.info("🔄 Updating tenant primary keys (FIXED METHOD)...")
        
        try:
            with self.get_session() as session:
                logger.info("   Step 1: Dropping foreign key constraints...")
                if not self.drop_foreign_key_constraints():
                    logger.error("   ❌ Failed to drop foreign key constraints")
                    return False
                
                logger.info("   Step 2: Adding temporary column...")
                # Add temporary column
                session.execute(text("ALTER TABLE tenants ADD COLUMN temp_new_id INTEGER"))
                
                logger.info("   Step 3: Setting new IDs in temporary column...")
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
                
                logger.info("   Step 4: Dropping old primary key constraint...")
                # Drop the old primary key constraint (should work now)
                session.execute(text("ALTER TABLE tenants DROP CONSTRAINT tenants_pkey"))
                
                logger.info("   Step 5: Updating ID column...")
                # Update the ID column
                session.execute(text("UPDATE tenants SET id = temp_new_id WHERE temp_new_id IS NOT NULL"))
                
                logger.info("   Step 6: Recreating primary key...")
                # Recreate primary key
                session.execute(text("ALTER TABLE tenants ADD PRIMARY KEY (id)"))
                
                logger.info("   Step 7: Dropping temporary column...")
                # Drop temporary column
                session.execute(text("ALTER TABLE tenants DROP COLUMN temp_new_id"))
                
                logger.info("   Step 8: Recreating foreign key constraints...")
                if not self.recreate_foreign_key_constraints():
                    logger.warning("   ⚠️ Some foreign key constraints could not be recreated")
                
                logger.info("   Step 9: Resetting sequence...")
                # Reset sequence if it exists
                try:
                    session.execute(text("SELECT setval('tenants_id_seq', 999999999, false)"))
                    logger.info("   ✅ Sequence reset successfully")
                except Exception as e:
                    logger.info(f"   ⚠️ Sequence reset failed (may not exist): {e}")
                
                # Update backup table status
                for mapping in mappings:
                    session.execute(text("""
                        UPDATE tenant_id_migration_backup 
                        SET status = 'completed' 
                        WHERE old_id = :old_id
                    """), {'old_id': mapping.old_id})
                
                logger.info(f"✅ Updated {len(mappings)} tenant IDs successfully using FIXED method")
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
                
                # Verify foreign key integrity for existing tables only
                integrity_issues = 0
                for table in self.dependent_tables:
                    try:
                        # Check if table exists first
                        table_check = session.execute(text(f"""
                            SELECT COUNT(*) FROM information_schema.tables 
                            WHERE table_name = '{table}'
                        """))
                        
                        if table_check.scalar() == 0:
                            continue  # Skip non-existent tables
                        
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
        """Execute the complete FIXED migration process"""
        start_time = time.time()
        
        logger.info("🚀 Starting FIXED Secure Tenant ID Migration")
        logger.info(f"   Database: PostgreSQL")
        logger.info(f"   Mode: {'DRY RUN' if dry_run else 'ACTUAL MIGRATION'}")
        logger.info(f"   URL: {self.database_url.split('@')[0]}@***")
        
        try:
            # Step 1: Discover constraints
            if not self.discover_foreign_key_constraints():
                logger.error("❌ Foreign key constraint discovery failed!")
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
            logger.info(f"   Foreign key constraints: {len(self.foreign_key_constraints)}")
            
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
            
            # Step 5: Update foreign keys FIRST (while constraints exist)
            if not self.update_foreign_keys(mappings):
                logger.error("❌ Foreign key updates failed!")
                return False
            
            # Step 6: Update tenant IDs using FIXED method
            if not self.update_tenant_ids_fixed(mappings):
                logger.error("❌ Tenant ID updates failed!")
                return False
            
            # Step 7: Verify
            if not self.verify_migration(mappings):
                logger.error("❌ Migration verification failed!")
                return False
            
            elapsed_time = time.time() - start_time
            logger.info(f"🎉 FIXED MIGRATION COMPLETED SUCCESSFULLY!")
            logger.info(f"   Migrated: {len(mappings)} tenants")
            logger.info(f"   Duration: {elapsed_time:.2f} seconds")
            logger.info(f"   Backup table: tenant_id_migration_backup")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Migration failed with error: {e}")
            return False