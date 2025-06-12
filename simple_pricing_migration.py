#!/usr/bin/env python3
"""
Script to create Alembic migration for Live Chat tables (SQLite version)
Run this script from your project root directory
"""

import os
import sys
from datetime import datetime
import subprocess

def get_latest_revision():
    """Get the latest revision from alembic"""
    try:
        result = subprocess.run(['alembic', 'heads'], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            # Extract revision ID from output like "abc123 (head)"
            revision = result.stdout.strip().split()[0]
            return revision
        else:
            print("⚠️  No existing revisions found. Using None as down_revision.")
            return None
    except FileNotFoundError:
        print("❌ Alembic not found. Please install: pip install alembic")
        sys.exit(1)
    except Exception as e:
        print(f"⚠️  Could not determine latest revision: {e}")
        return None

def create_migration_file():
    """Create the migration file for SQLite"""
    
    # Check if alembic directory exists
    if not os.path.exists('alembic'):
        print("❌ Alembic directory not found. Please run 'alembic init alembic' first.")
        sys.exit(1)
    
    if not os.path.exists('alembic/versions'):
        print("❌ Alembic versions directory not found.")
        sys.exit(1)
    
    # Get the latest revision
    down_revision = get_latest_revision()
    down_revision_str = f"'{down_revision}'" if down_revision else "None"
    
    # Generate timestamp and revision ID
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    revision_id = f"create_live_chat_{timestamp}"
    
    # Create migration content for SQLite
    migration_content = f'''"""Create live chat tables

Revision ID: {revision_id}
Revises: {down_revision}
Create Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")}

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '{revision_id}'
down_revision = {down_revision_str}
branch_labels = None
depends_on = None


def upgrade():
    # Create agents table
    op.create_table('agents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('department', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),  # SQLite uses VARCHAR for enums
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('max_concurrent_chats', sa.Integer(), nullable=True),
        sa.Column('total_conversations', sa.Integer(), nullable=True),
        sa.Column('avg_response_time_seconds', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('last_seen', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_agents_id'), 'agents', ['id'], unique=False)
    op.create_index(op.f('ix_agents_tenant_id'), 'agents', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_agents_email'), 'agents', ['email'], unique=False)
    op.create_index(op.f('ix_agents_status'), 'agents', ['status'], unique=False)

    # Create conversations table
    op.create_table('conversations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.String(), nullable=False),
        sa.Column('customer_name', sa.String(), nullable=True),
        sa.Column('customer_email', sa.String(), nullable=True),
        sa.Column('platform', sa.String(), nullable=True),
        sa.Column('agent_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),  # SQLite uses VARCHAR for enums
        sa.Column('department', sa.String(), nullable=True),
        sa.Column('subject', sa.String(), nullable=True),
        sa.Column('bot_session_id', sa.String(), nullable=True),
        sa.Column('handoff_reason', sa.Text(), nullable=True),
        sa.Column('bot_context', sa.Text(), nullable=True),
        sa.Column('queue_time_seconds', sa.Integer(), nullable=True),
        sa.Column('first_response_time_seconds', sa.Integer(), nullable=True),
        sa.Column('resolution_time_seconds', sa.Integer(), nullable=True),
        sa.Column('satisfaction_rating', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('assigned_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_conversations_session_id'), 'conversations', ['session_id'], unique=True)
    op.create_index(op.f('ix_conversations_customer_id'), 'conversations', ['customer_id'], unique=False)
    op.create_index(op.f('ix_conversations_tenant_id'), 'conversations', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_conversations_status'), 'conversations', ['status'], unique=False)

    # Create messages table
    op.create_table('messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('conversation_id', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('message_type', sa.String(), nullable=True),  # SQLite uses VARCHAR for enums
        sa.Column('from_agent', sa.Boolean(), nullable=True),
        sa.Column('sender_name', sa.String(), nullable=True),
        sa.Column('agent_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_messages_conversation_id'), 'messages', ['conversation_id'], unique=False)
    op.create_index(op.f('ix_messages_created_at'), 'messages', ['created_at'], unique=False)
    op.create_index(op.f('ix_messages_from_agent'), 'messages', ['from_agent'], unique=False)

    # Set default values using UPDATE statements (SQLite doesn't support defaults in CREATE TABLE fully)
    op.execute("UPDATE agents SET department = 'general' WHERE department IS NULL")
    op.execute("UPDATE agents SET status = 'OFFLINE' WHERE status IS NULL")
    op.execute("UPDATE agents SET is_active = 1 WHERE is_active IS NULL")
    op.execute("UPDATE agents SET max_concurrent_chats = 3 WHERE max_concurrent_chats IS NULL")
    op.execute("UPDATE agents SET total_conversations = 0 WHERE total_conversations IS NULL")
    op.execute("UPDATE agents SET avg_response_time_seconds = 0 WHERE avg_response_time_seconds IS NULL")
    
    op.execute("UPDATE conversations SET platform = 'web' WHERE platform IS NULL")
    op.execute("UPDATE conversations SET status = 'QUEUED' WHERE status IS NULL")
    op.execute("UPDATE conversations SET department = 'general' WHERE department IS NULL")
    op.execute("UPDATE conversations SET queue_time_seconds = 0 WHERE queue_time_seconds IS NULL")
    
    op.execute("UPDATE messages SET message_type = 'TEXT' WHERE message_type IS NULL")
    op.execute("UPDATE messages SET from_agent = 0 WHERE from_agent IS NULL")


def downgrade():
    # Drop tables in reverse order
    op.drop_index(op.f('ix_messages_from_agent'), table_name='messages')
    op.drop_index(op.f('ix_messages_created_at'), table_name='messages')
    op.drop_index(op.f('ix_messages_conversation_id'), table_name='messages')
    op.drop_table('messages')
    
    op.drop_index(op.f('ix_conversations_status'), table_name='conversations')
    op.drop_index(op.f('ix_conversations_tenant_id'), table_name='conversations')
    op.drop_index(op.f('ix_conversations_customer_id'), table_name='conversations')
    op.drop_index(op.f('ix_conversations_session_id'), table_name='conversations')
    op.drop_table('conversations')
    
    op.drop_index(op.f('ix_agents_status'), table_name='agents')
    op.drop_index(op.f('ix_agents_email'), table_name='agents')
    op.drop_index(op.f('ix_agents_tenant_id'), table_name='agents')
    op.drop_index(op.f('ix_agents_id'), table_name='agents')
    op.drop_table('agents')
'''

    # Write migration file
    filename = f'{timestamp}_{revision_id}.py'
    filepath = os.path.join('alembic', 'versions', filename)
    
    with open(filepath, 'w') as f:
        f.write(migration_content)
    
    print(f"✅ Migration file created: {filepath}")
    return filepath

def run_migration():
    """Run the migration"""
    try:
        print("\n🚀 Running migration...")
        result = subprocess.run(['alembic', 'upgrade', 'head'], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Migration completed successfully!")
            if result.stdout.strip():
                print(result.stdout)
        else:
            print("❌ Migration failed:")
            print(result.stderr)
            return False
    except Exception as e:
        print(f"❌ Error running migration: {e}")
        return False
    
    return True

def create_sample_agent():
    """Create a sample Python script to add a test agent"""
    
    sample_agent_script = '''#!/usr/bin/env python3
"""
Sample script to create a test agent
Run this after the migration is complete
"""

import sys
import os

# Add your project root to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from app.database import get_db
from app.live_chat.models import Agent, AgentStatus

def create_test_agent():
    """Create a test agent for testing"""
    db = next(get_db())
    
    try:
        # Check if agent already exists
        existing_agent = db.query(Agent).filter(Agent.email == "test@example.com").first()
        if existing_agent:
            print(f"✅ Test agent already exists: {existing_agent.name} (ID: {existing_agent.id})")
            return existing_agent.id
        
        # Create new agent
        agent = Agent(
            tenant_id=1,  # Update this to match your tenant ID
            name="Test Agent",
            email="test@example.com",
            department="general",
            status=AgentStatus.OFFLINE,
            is_active=True,
            max_concurrent_chats=3
        )
        
        db.add(agent)
        db.commit()
        db.refresh(agent)
        
        print(f"✅ Test agent created: {agent.name} (ID: {agent.id})")
        print(f"   Email: {agent.email}")
        print(f"   Department: {agent.department}")
        print(f"   Status: {agent.status}")
        
        return agent.id
        
    except Exception as e:
        print(f"❌ Error creating test agent: {e}")
        db.rollback()
        return None
    finally:
        db.close()

if __name__ == "__main__":
    create_test_agent()
'''
    
    with open('create_test_agent.py', 'w') as f:
        f.write(sample_agent_script)
    
    print("✅ Sample agent creation script created: create_test_agent.py")

def create_sqlite_test_script():
    """Create a test script to verify the SQLite database"""
    
    test_script = '''#!/usr/bin/env python3
"""
Test script to verify SQLite database and live chat tables
"""

import sys
import os
import sqlite3
from pathlib import Path

# Add your project root to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_database():
    """Test the SQLite database and tables"""
    
    # Check if database file exists
    db_path = "./chatbot.db"
    if not os.path.exists(db_path):
        print(f"❌ Database file not found: {db_path}")
        return False
    
    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if live chat tables exist
        tables_to_check = ['agents', 'conversations', 'messages']
        
        print("🔍 Checking live chat tables...")
        for table in tables_to_check:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
            result = cursor.fetchone()
            
            if result:
                print(f"✅ Table '{table}' exists")
                
                # Get table info
                cursor.execute(f"PRAGMA table_info({table})")
                columns = cursor.fetchall()
                print(f"   Columns: {len(columns)}")
                
                # Count rows
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print(f"   Rows: {count}")
                
            else:
                print(f"❌ Table '{table}' does not exist")
        
        # Check if tenants table exists (dependency)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tenants'")
        if cursor.fetchone():
            print("✅ Tenants table exists (dependency satisfied)")
        else:
            print("⚠️  Tenants table not found - you may need to create it first")
        
        conn.close()
        
        print("\n🎉 Database check completed!")
        return True
        
    except Exception as e:
        print(f"❌ Error checking database: {e}")
        return False

def show_database_schema():
    """Show the database schema"""
    db_path = "./chatbot.db"
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("\n📋 Database Schema:")
        print("=" * 50)
        
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        
        for table in tables:
            table_name = table[0]
            print(f"\n🔹 Table: {table_name}")
            
            # Get table info
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            
            for col in columns:
                col_id, name, col_type, not_null, default, pk = col
                pk_str = " (PRIMARY KEY)" if pk else ""
                null_str = " NOT NULL" if not_null else ""
                default_str = f" DEFAULT {default}" if default else ""
                
                print(f"   - {name}: {col_type}{null_str}{default_str}{pk_str}")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error showing schema: {e}")

if __name__ == "__main__":
    print("🔧 Testing SQLite Live Chat Database")
    print("=" * 40)
    
    if test_database():
        show_database_schema()
    else:
        print("\\n❌ Database test failed. Please run the migration first.")
'''
    
    with open('test_sqlite_db.py', 'w') as f:
        f.write(test_script)
    
    print("✅ SQLite test script created: test_sqlite_db.py")

def main():
    """Main function"""
    print("🏗️  Creating Live Chat Migration for SQLite...")
    print("=" * 50)
    
    # Check if we're in the right directory
    if not os.path.exists('app'):
        print("❌ Please run this script from your project root directory (where 'app' folder is located)")
        sys.exit(1)
    
    # Check if SQLite database exists
    if os.path.exists('./chatbot.db'):
        print("✅ SQLite database found: ./chatbot.db")
    else:
        print("⚠️  SQLite database not found. It will be created when you run the migration.")
    
    # Create migration file
    migration_file = create_migration_file()
    
    # Ask if user wants to run migration immediately
    response = input("\n🤔 Do you want to run the migration now? (y/n): ").lower().strip()
    
    if response in ['y', 'yes']:
        if run_migration():
            print("\n🎉 Live chat tables created successfully in SQLite!")
            
            # Create sample scripts
            create_sample_agent()
            create_sqlite_test_script()
            
            print("\n📝 Next steps:")
            print("1. Run 'python test_sqlite_db.py' to verify the database")
            print("2. Run 'python create_test_agent.py' to create a test agent")
            print("3. Install Redis: pip install redis")
            print("4. Start Redis server: redis-server")
            print("5. Test the live chat API endpoints")
            print("6. Apply the code fixes from the previous artifact")
            
            print("\n💡 SQLite Notes:")
            print("- Enum values are stored as strings")
            print("- Boolean values are stored as integers (0/1)")
            print("- Timezone info may not be preserved")
        else:
            print("\n❌ Migration failed. Please check the error above.")
    else:
        print(f"\n📁 Migration file created but not run: {migration_file}")
        print("To run it later: alembic upgrade head")

if __name__ == "__main__":
    main()