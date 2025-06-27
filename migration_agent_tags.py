# migration_agent_tags.py
"""
Migration script to add agent tags and smart routing tables
Works with both SQLite and PostgreSQL databases
"""

import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
from urllib.parse import urlparse
from datetime import datetime
import sys
import os

# Database connection strings
SQLITE_URL = "sqlite:///./chatbot.db"
POSTGRES_URL = "postgresql://chatbot_hhjv_user:dYXguSEwpwZl3Yt2R3ACsfvmM5lLIgSD@dpg-d10sp295pdvs73afujf0-a.oregon-postgres.render.com/chatbot_hhjv"

def get_postgres_connection():
    """Get PostgreSQL connection"""
    try:
        parsed = urlparse(POSTGRES_URL)
        conn = psycopg2.connect(
            host=parsed.hostname,
            port=parsed.port or 5432,
            database=parsed.path[1:],  # Remove leading slash
            user=parsed.username,
            password=parsed.password
        )
        return conn
    except Exception as e:
        print(f"❌ Error connecting to PostgreSQL: {e}")
        return None

def get_sqlite_connection():
    """Get SQLite connection"""
    try:
        db_path = "./chatbot.db"
        conn = sqlite3.connect(db_path)
        return conn
    except Exception as e:
        print(f"❌ Error connecting to SQLite: {e}")
        return None

def execute_sql(conn, sql, db_type="sqlite"):
    """Execute SQL with proper error handling"""
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        conn.commit()
        print(f"✅ Executed: {sql[:80]}...")
        return True
    except Exception as e:
        print(f"❌ Error executing SQL: {e}")
        print(f"SQL: {sql}")
        conn.rollback()
        return False

def migrate_sqlite():
    """Run migration for SQLite"""
    print("\n🔄 Starting SQLite migration...")
    
    conn = get_sqlite_connection()
    if not conn:
        return False
    
    try:
        # 1. Create agent_tags table
        sql_agent_tags = """
        CREATE TABLE IF NOT EXISTS agent_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            name VARCHAR(50) NOT NULL,
            display_name VARCHAR(100) NOT NULL,
            category VARCHAR(50) NOT NULL,
            description TEXT,
            color VARCHAR(7) DEFAULT '#6366f1',
            icon VARCHAR(50),
            priority_weight REAL DEFAULT 1.0,
            is_active BOOLEAN DEFAULT 1,
            keywords TEXT,
            routing_rules TEXT,
            total_conversations INTEGER DEFAULT 0,
            success_rate REAL DEFAULT 0.0,
            average_satisfaction REAL DEFAULT 0.0,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id),
            FOREIGN KEY (created_by) REFERENCES agents(id)
        );
        """
        
        # 2. Create agent_tags_association table
        sql_association = """
        CREATE TABLE IF NOT EXISTS agent_tags_association (
            agent_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            proficiency_level INTEGER DEFAULT 3,
            assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            assigned_by INTEGER,
            PRIMARY KEY (agent_id, tag_id),
            FOREIGN KEY (agent_id) REFERENCES agents(id),
            FOREIGN KEY (tag_id) REFERENCES agent_tags(id),
            FOREIGN KEY (assigned_by) REFERENCES agents(id)
        );
        """
        
        # 3. Create conversation_tagging table
        sql_conversation_tagging = """
        CREATE TABLE IF NOT EXISTS conversation_tagging (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            confidence_score REAL DEFAULT 0.0,
            detection_method VARCHAR(50) NOT NULL,
            detected_keywords TEXT,
            message_text TEXT,
            message_id INTEGER,
            influenced_routing BOOLEAN DEFAULT 0,
            routing_weight REAL DEFAULT 0.0,
            human_verified BOOLEAN DEFAULT 0,
            verified_by INTEGER,
            verified_at TIMESTAMP,
            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES live_chat_conversations(id),
            FOREIGN KEY (tag_id) REFERENCES agent_tags(id),
            FOREIGN KEY (message_id) REFERENCES live_chat_messages(id),
            FOREIGN KEY (verified_by) REFERENCES agents(id)
        );
        """
        
        # 4. Create agent_tag_performance table
        sql_performance = """
        CREATE TABLE IF NOT EXISTS agent_tag_performance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            total_conversations INTEGER DEFAULT 0,
            successful_resolutions INTEGER DEFAULT 0,
            average_resolution_time REAL DEFAULT 0.0,
            customer_satisfaction_avg REAL DEFAULT 0.0,
            conversations_last_30_days INTEGER DEFAULT 0,
            satisfaction_last_30_days REAL DEFAULT 0.0,
            proficiency_level INTEGER DEFAULT 3,
            improvement_trend REAL DEFAULT 0.0,
            certified BOOLEAN DEFAULT 0,
            certification_date TIMESTAMP,
            last_training_date TIMESTAMP,
            is_available_for_tag BOOLEAN DEFAULT 1,
            max_concurrent_for_tag INTEGER DEFAULT 2,
            current_active_conversations INTEGER DEFAULT 0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_conversation_date TIMESTAMP,
            FOREIGN KEY (agent_id) REFERENCES agents(id),
            FOREIGN KEY (tag_id) REFERENCES agent_tags(id)
        );
        """
        
        # 5. Create smart_routing_log table
        sql_routing_log = """
        CREATE TABLE IF NOT EXISTS smart_routing_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            tenant_id INTEGER NOT NULL,
            assigned_agent_id INTEGER,
            routing_method VARCHAR(50) NOT NULL,
            confidence_score REAL DEFAULT 0.0,
            detected_tags TEXT,
            customer_context TEXT,
            available_agents TEXT,
            scoring_breakdown TEXT,
            fallback_reason VARCHAR(200),
            alternative_agents TEXT,
            customer_satisfaction INTEGER,
            resolution_time_minutes INTEGER,
            was_transferred BOOLEAN DEFAULT 0,
            transfer_reason VARCHAR(200),
            routing_accuracy REAL,
            success_factors TEXT,
            improvement_suggestions TEXT,
            routed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            conversation_ended_at TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES live_chat_conversations(id),
            FOREIGN KEY (tenant_id) REFERENCES tenants(id),
            FOREIGN KEY (assigned_agent_id) REFERENCES agents(id)
        );
        """
        
        # 6. Add new columns to agents table
        agent_columns = [
            "ALTER TABLE agents ADD COLUMN primary_specialization VARCHAR(50);",
            "ALTER TABLE agents ADD COLUMN secondary_specializations TEXT;",
            "ALTER TABLE agents ADD COLUMN skill_level INTEGER DEFAULT 3;",
            "ALTER TABLE agents ADD COLUMN accepts_overflow BOOLEAN DEFAULT 1;"
        ]
        
        # Execute all SQL statements
        tables = [
            ("agent_tags", sql_agent_tags),
            ("agent_tags_association", sql_association),
            ("conversation_tagging", sql_conversation_tagging),
            ("agent_tag_performance", sql_performance),
            ("smart_routing_log", sql_routing_log)
        ]
        
        for table_name, sql in tables:
            print(f"Creating table: {table_name}")
            if not execute_sql(conn, sql, "sqlite"):
                return False
        
        # Add new columns to agents table
        for sql in agent_columns:
            try:
                execute_sql(conn, sql, "sqlite")
            except Exception as e:
                if "duplicate column name" in str(e).lower():
                    print(f"⚠️  Column already exists, skipping: {sql}")
                else:
                    print(f"❌ Error adding column: {e}")
        
        # Create indexes for better performance
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_agent_tags_tenant ON agent_tags(tenant_id);",
            "CREATE INDEX IF NOT EXISTS idx_agent_tags_category ON agent_tags(category);",
            "CREATE INDEX IF NOT EXISTS idx_conversation_tagging_conversation ON conversation_tagging(conversation_id);",
            "CREATE INDEX IF NOT EXISTS idx_conversation_tagging_tag ON conversation_tagging(tag_id);",
            "CREATE INDEX IF NOT EXISTS idx_performance_agent ON agent_tag_performance(agent_id);",
            "CREATE INDEX IF NOT EXISTS idx_performance_tag ON agent_tag_performance(tag_id);",
            "CREATE INDEX IF NOT EXISTS idx_routing_log_tenant ON smart_routing_log(tenant_id);",
            "CREATE INDEX IF NOT EXISTS idx_routing_log_conversation ON smart_routing_log(conversation_id);"
        ]
        
        for index_sql in indexes:
            execute_sql(conn, index_sql, "sqlite")
        
        conn.close()
        print("✅ SQLite migration completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ SQLite migration failed: {e}")
        if conn:
            conn.close()
        return False

def migrate_postgres():
    """Run migration for PostgreSQL"""
    print("\n🔄 Starting PostgreSQL migration...")
    
    conn = get_postgres_connection()
    if not conn:
        return False
    
    try:
        # 1. Create agent_tags table
        sql_agent_tags = """
        CREATE TABLE IF NOT EXISTS agent_tags (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NOT NULL,
            name VARCHAR(50) NOT NULL,
            display_name VARCHAR(100) NOT NULL,
            category VARCHAR(50) NOT NULL,
            description TEXT,
            color VARCHAR(7) DEFAULT '#6366f1',
            icon VARCHAR(50),
            priority_weight REAL DEFAULT 1.0,
            is_active BOOLEAN DEFAULT TRUE,
            keywords JSONB,
            routing_rules JSONB,
            total_conversations INTEGER DEFAULT 0,
            success_rate REAL DEFAULT 0.0,
            average_satisfaction REAL DEFAULT 0.0,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id),
            FOREIGN KEY (created_by) REFERENCES agents(id)
        );
        """
        
        # 2. Create agent_tags_association table
        sql_association = """
        CREATE TABLE IF NOT EXISTS agent_tags_association (
            agent_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            proficiency_level INTEGER DEFAULT 3,
            assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            assigned_by INTEGER,
            PRIMARY KEY (agent_id, tag_id),
            FOREIGN KEY (agent_id) REFERENCES agents(id),
            FOREIGN KEY (tag_id) REFERENCES agent_tags(id),
            FOREIGN KEY (assigned_by) REFERENCES agents(id)
        );
        """
        
        # 3. Create conversation_tagging table
        sql_conversation_tagging = """
        CREATE TABLE IF NOT EXISTS conversation_tagging (
            id SERIAL PRIMARY KEY,
            conversation_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            confidence_score REAL DEFAULT 0.0,
            detection_method VARCHAR(50) NOT NULL,
            detected_keywords JSONB,
            message_text TEXT,
            message_id INTEGER,
            influenced_routing BOOLEAN DEFAULT FALSE,
            routing_weight REAL DEFAULT 0.0,
            human_verified BOOLEAN DEFAULT FALSE,
            verified_by INTEGER,
            verified_at TIMESTAMP,
            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES live_chat_conversations(id),
            FOREIGN KEY (tag_id) REFERENCES agent_tags(id),
            FOREIGN KEY (message_id) REFERENCES live_chat_messages(id),
            FOREIGN KEY (verified_by) REFERENCES agents(id)
        );
        """
        
        # 4. Create agent_tag_performance table
        sql_performance = """
        CREATE TABLE IF NOT EXISTS agent_tag_performance (
            id SERIAL PRIMARY KEY,
            agent_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            total_conversations INTEGER DEFAULT 0,
            successful_resolutions INTEGER DEFAULT 0,
            average_resolution_time REAL DEFAULT 0.0,
            customer_satisfaction_avg REAL DEFAULT 0.0,
            conversations_last_30_days INTEGER DEFAULT 0,
            satisfaction_last_30_days REAL DEFAULT 0.0,
            proficiency_level INTEGER DEFAULT 3,
            improvement_trend REAL DEFAULT 0.0,
            certified BOOLEAN DEFAULT FALSE,
            certification_date TIMESTAMP,
            last_training_date TIMESTAMP,
            is_available_for_tag BOOLEAN DEFAULT TRUE,
            max_concurrent_for_tag INTEGER DEFAULT 2,
            current_active_conversations INTEGER DEFAULT 0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_conversation_date TIMESTAMP,
            FOREIGN KEY (agent_id) REFERENCES agents(id),
            FOREIGN KEY (tag_id) REFERENCES agent_tags(id)
        );
        """
        
        # 5. Create smart_routing_log table
        sql_routing_log = """
        CREATE TABLE IF NOT EXISTS smart_routing_log (
            id SERIAL PRIMARY KEY,
            conversation_id INTEGER NOT NULL,
            tenant_id INTEGER NOT NULL,
            assigned_agent_id INTEGER,
            routing_method VARCHAR(50) NOT NULL,
            confidence_score REAL DEFAULT 0.0,
            detected_tags JSONB,
            customer_context JSONB,
            available_agents JSONB,
            scoring_breakdown JSONB,
            fallback_reason VARCHAR(200),
            alternative_agents JSONB,
            customer_satisfaction INTEGER,
            resolution_time_minutes INTEGER,
            was_transferred BOOLEAN DEFAULT FALSE,
            transfer_reason VARCHAR(200),
            routing_accuracy REAL,
            success_factors JSONB,
            improvement_suggestions JSONB,
            routed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            conversation_ended_at TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES live_chat_conversations(id),
            FOREIGN KEY (tenant_id) REFERENCES tenants(id),
            FOREIGN KEY (assigned_agent_id) REFERENCES agents(id)
        );
        """
        
        # 6. Add new columns to agents table (PostgreSQL style)
        agent_columns = [
            "ALTER TABLE agents ADD COLUMN IF NOT EXISTS primary_specialization VARCHAR(50);",
            "ALTER TABLE agents ADD COLUMN IF NOT EXISTS secondary_specializations JSONB;",
            "ALTER TABLE agents ADD COLUMN IF NOT EXISTS skill_level INTEGER DEFAULT 3;",
            "ALTER TABLE agents ADD COLUMN IF NOT EXISTS accepts_overflow BOOLEAN DEFAULT TRUE;"
        ]
        
        # Execute all SQL statements
        tables = [
            ("agent_tags", sql_agent_tags),
            ("agent_tags_association", sql_association),
            ("conversation_tagging", sql_conversation_tagging),
            ("agent_tag_performance", sql_performance),
            ("smart_routing_log", sql_routing_log)
        ]
        
        for table_name, sql in tables:
            print(f"Creating table: {table_name}")
            if not execute_sql(conn, sql, "postgres"):
                return False
        
        # Add new columns to agents table
        for sql in agent_columns:
            execute_sql(conn, sql, "postgres")
        
        # Create indexes for better performance
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_agent_tags_tenant ON agent_tags(tenant_id);",
            "CREATE INDEX IF NOT EXISTS idx_agent_tags_category ON agent_tags(category);",
            "CREATE INDEX IF NOT EXISTS idx_conversation_tagging_conversation ON conversation_tagging(conversation_id);",
            "CREATE INDEX IF NOT EXISTS idx_conversation_tagging_tag ON conversation_tagging(tag_id);",
            "CREATE INDEX IF NOT EXISTS idx_performance_agent ON agent_tag_performance(agent_id);",
            "CREATE INDEX IF NOT EXISTS idx_performance_tag ON agent_tag_performance(tag_id);",
            "CREATE INDEX IF NOT EXISTS idx_routing_log_tenant ON smart_routing_log(tenant_id);",
            "CREATE INDEX IF NOT EXISTS idx_routing_log_conversation ON smart_routing_log(conversation_id);"
        ]
        
        for index_sql in indexes:
            execute_sql(conn, index_sql, "postgres")
        
        conn.close()
        print("✅ PostgreSQL migration completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ PostgreSQL migration failed: {e}")
        if conn:
            conn.close()
        return False

def create_default_tags(db_type="sqlite"):
    """Create default agent tags after migration"""
    print(f"\n🏷️  Creating default tags for {db_type}...")
    
    if db_type == "sqlite":
        conn = get_sqlite_connection()
    else:
        conn = get_postgres_connection()
    
    if not conn:
        return False
    
    default_tags = [
        {
            "name": "billing",
            "display_name": "Billing & Payments",
            "category": "financial",
            "description": "Handle payment issues, billing inquiries, and subscription management",
            "color": "#10b981",
            "priority_weight": 1.5,
            "keywords": '["bill", "billing", "payment", "charge", "invoice", "refund", "subscription"]'
        },
        {
            "name": "refunds",
            "display_name": "Refunds & Returns",
            "category": "financial", 
            "description": "Process refunds, returns, and dispute resolution",
            "color": "#f59e0b",
            "priority_weight": 1.3,
            "keywords": '["refund", "return", "money back", "cancel", "dispute"]'
        },
        {
            "name": "authentication",
            "display_name": "Login & Authentication",
            "category": "technical",
            "description": "Help with login issues, password resets, and account access",
            "color": "#8b5cf6",
            "priority_weight": 1.2,
            "keywords": '["login", "password", "access", "account", "locked", "reset", "2fa"]'
        },
        {
            "name": "technical",
            "display_name": "Technical Support",
            "category": "technical",
            "description": "Resolve technical issues, bugs, and system problems",
            "color": "#3b82f6",
            "priority_weight": 1.1,
            "keywords": '["bug", "error", "broken", "not working", "technical", "crash"]'
        },
        {
            "name": "account",
            "display_name": "Account Management",
            "category": "general",
            "description": "Account settings, profile updates, and information management",
            "color": "#6366f1",
            "priority_weight": 1.0,
            "keywords": '["account", "profile", "settings", "update", "information"]'
        },
        {
            "name": "sales",
            "display_name": "Sales & Upgrades",
            "category": "sales",
            "description": "Product sales, plan upgrades, and pricing inquiries",
            "color": "#ec4899",
            "priority_weight": 1.4,
            "keywords": '["buy", "purchase", "upgrade", "pricing", "plan", "demo"]'
        },
        {
            "name": "general",
            "display_name": "General Support",
            "category": "general",
            "description": "General inquiries and basic support",
            "color": "#6b7280",
            "priority_weight": 0.8,
            "keywords": '["help", "question", "support", "information"]'
        }
    ]
    
    try:
        cursor = conn.cursor()
        
        # Insert default tags for all tenants
        if db_type == "sqlite":
            # Get all tenant IDs
            cursor.execute("SELECT id FROM tenants")
            tenants = cursor.fetchall()
            
            for tenant_row in tenants:
                tenant_id = tenant_row[0]
                
                for tag in default_tags:
                    # Check if tag already exists
                    cursor.execute(
                        "SELECT id FROM agent_tags WHERE tenant_id = ? AND name = ?",
                        (tenant_id, tag["name"])
                    )
                    
                    if not cursor.fetchone():
                        cursor.execute("""
                            INSERT INTO agent_tags 
                            (tenant_id, name, display_name, category, description, color, priority_weight, keywords)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            tenant_id, tag["name"], tag["display_name"], tag["category"],
                            tag["description"], tag["color"], tag["priority_weight"], tag["keywords"]
                        ))
                        print(f"Created tag: {tag['display_name']} for tenant {tenant_id}")
        
        else:  # PostgreSQL
            cursor.execute("SELECT id FROM tenants")
            tenants = cursor.fetchall()
            
            for tenant_row in tenants:
                tenant_id = tenant_row[0]
                
                for tag in default_tags:
                    # Check if tag already exists
                    cursor.execute(
                        "SELECT id FROM agent_tags WHERE tenant_id = %s AND name = %s",
                        (tenant_id, tag["name"])
                    )
                    
                    if not cursor.fetchone():
                        cursor.execute("""
                            INSERT INTO agent_tags 
                            (tenant_id, name, display_name, category, description, color, priority_weight, keywords)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            tenant_id, tag["name"], tag["display_name"], tag["category"],
                            tag["description"], tag["color"], tag["priority_weight"], tag["keywords"]
                        ))
                        print(f"Created tag: {tag['display_name']} for tenant {tenant_id}")
        
        conn.commit()
        conn.close()
        print(f"✅ Default tags created successfully for {db_type}!")
        return True
        
    except Exception as e:
        print(f"❌ Error creating default tags: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False

def main():
    """Main migration function"""
    print("🚀 Starting Agent Tags Migration")
    print("=" * 50)
    
    # Check command line arguments
    if len(sys.argv) > 1:
        db_type = sys.argv[1].lower()
        if db_type not in ["sqlite", "postgres", "both"]:
            print("Usage: python migration_agent_tags.py [sqlite|postgres|both]")
            sys.exit(1)
    else:
        db_type = "both"
    
    success = True
    
    if db_type in ["sqlite", "both"]:
        sqlite_success = migrate_sqlite()
        if sqlite_success:
            create_default_tags("sqlite")
        success = success and sqlite_success
    
    if db_type in ["postgres", "both"]:
        postgres_success = migrate_postgres()
        if postgres_success:
            create_default_tags("postgres")
        success = success and postgres_success
    
    print("\n" + "=" * 50)
    if success:
        print("🎉 Migration completed successfully!")
        print("\n📋 What was created:")
        print("   • agent_tags - Store skill tags")
        print("   • agent_tags_association - Agent-tag relationships")
        print("   • conversation_tagging - Tag detection for conversations")
        print("   • agent_tag_performance - Performance tracking per tag")
        print("   • smart_routing_log - Routing decision logs")
        print("   • 4 new columns added to agents table")
        print("   • 7 default tags created for each tenant")
        print("\n✅ Your smart routing system is ready to use!")
    else:
        print("❌ Migration failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()