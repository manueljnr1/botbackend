"""Create live chat tables

Revision ID: create_live_chat_20250612_030614
Revises: 8fddcbda175a
Create Date: 2025-06-12 03:06:14.049815

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'create_live_chat_20250612_030614'
down_revision = '8fddcbda175a'
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
