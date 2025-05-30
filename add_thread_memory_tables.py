# alembic/versions/add_thread_memory_tables.py
"""
Add thread memory tables for Slack integration

Revision ID: add_thread_memory
Revises: previous_revision_id
Create Date: 2024-12-XX XX:XX:XX.XXXXXX
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'add_thread_memory'
down_revision = 'previous_revision_id'  # Replace with your latest revision
branch_labels = None
depends_on = None

def upgrade():
    # Create slack_thread_memory table
    op.create_table(
        'slack_thread_memory',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('channel_id', sa.String(length=50), nullable=False),
        sa.Column('thread_ts', sa.String(length=50), nullable=True),
        sa.Column('user_id', sa.String(length=50), nullable=False),
        sa.Column('conversation_context', sa.Text(), nullable=True),
        sa.Column('user_preferences', sa.Text(), nullable=True),
        sa.Column('topic_summary', sa.Text(), nullable=True),
        sa.Column('message_count', sa.Integer(), nullable=True, default=0),
        sa.Column('last_activity', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, default=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for slack_thread_memory
    op.create_index('idx_slack_thread_tenant_channel', 'slack_thread_memory', ['tenant_id', 'channel_id'])
    op.create_index('idx_slack_thread_user_activity', 'slack_thread_memory', ['user_id', 'last_activity'])
    op.create_index('idx_slack_thread_ts', 'slack_thread_memory', ['thread_ts'])
    op.create_index(op.f('ix_slack_thread_memory_id'), 'slack_thread_memory', ['id'])
    op.create_index(op.f('ix_slack_thread_memory_tenant_id'), 'slack_thread_memory', ['tenant_id'])
    op.create_index(op.f('ix_slack_thread_memory_channel_id'), 'slack_thread_memory', ['channel_id'])
    op.create_index(op.f('ix_slack_thread_memory_user_id'), 'slack_thread_memory', ['user_id'])
    
    # Create slack_channel_context table
    op.create_table(
        'slack_channel_context',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('channel_id', sa.String(length=50), nullable=False),
        sa.Column('channel_name', sa.String(length=100), nullable=True),
        sa.Column('channel_type', sa.String(length=20), nullable=True),
        sa.Column('bot_enabled', sa.Boolean(), nullable=True, default=True),
        sa.Column('thread_mode', sa.String(length=20), nullable=True, default='auto'),
        sa.Column('channel_topic', sa.Text(), nullable=True),
        sa.Column('common_questions', sa.Text(), nullable=True),
        sa.Column('channel_personality', sa.Text(), nullable=True),
        sa.Column('total_messages', sa.Integer(), nullable=True, default=0),
        sa.Column('active_threads', sa.Integer(), nullable=True, default=0),
        sa.Column('last_activity', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for slack_channel_context
    op.create_index('idx_slack_channel_tenant', 'slack_channel_context', ['tenant_id', 'channel_id'])
    op.create_index(op.f('ix_slack_channel_context_id'), 'slack_channel_context', ['id'])
    op.create_index(op.f('ix_slack_channel_context_tenant_id'), 'slack_channel_context', ['tenant_id'])
    op.create_index(op.f('ix_slack_channel_context_channel_id'), 'slack_channel_context', ['channel_id'])

def downgrade():
    # Drop slack_channel_context table and indexes
    op.drop_index(op.f('ix_slack_channel_context_channel_id'), table_name='slack_channel_context')
    op.drop_index(op.f('ix_slack_channel_context_tenant_id'), table_name='slack_channel_context')
    op.drop_index(op.f('ix_slack_channel_context_id'), table_name='slack_channel_context')
    op.drop_index('idx_slack_channel_tenant', table_name='slack_channel_context')
    op.drop_table('slack_channel_context')
    
    # Drop slack_thread_memory table and indexes
    op.drop_index(op.f('ix_slack_thread_memory_user_id'), table_name='slack_thread_memory')
    op.drop_index(op.f('ix_slack_thread_memory_channel_id'), table_name='slack_thread_memory')
    op.drop_index(op.f('ix_slack_thread_memory_tenant_id'), table_name='slack_thread_memory')
    op.drop_index(op.f('ix_slack_thread_memory_id'), table_name='slack_thread_memory')
    op.drop_index('idx_slack_thread_ts', table_name='slack_thread_memory')
    op.drop_index('idx_slack_thread_user_activity', table_name='slack_thread_memory')
    op.drop_index('idx_slack_thread_tenant_channel', table_name='slack_thread_memory')
    op.drop_table('slack_thread_memory')