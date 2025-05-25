from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    """Add live chat tables"""
    
    # Create agents table
    op.create_table('agents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('avatar_url', sa.String(), nullable=True),
        sa.Column('department', sa.String(), nullable=True),
        sa.Column('skills', sa.Text(), nullable=True),
        sa.Column('status', sa.Enum('online', 'busy', 'away', 'offline', name='agentstatus'), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('max_concurrent_chats', sa.Integer(), nullable=True),
        sa.Column('current_chat_count', sa.Integer(), nullable=True),
        sa.Column('total_chats_handled', sa.Integer(), nullable=True),
        sa.Column('average_response_time', sa.Integer(), nullable=True),
        sa.Column('customer_satisfaction_rating', sa.Float(), nullable=True),
        sa.Column('last_seen', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_agents_id'), 'agents', ['id'], unique=False)
    
    # Create live_chats table
    op.create_table('live_chats',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.String(), nullable=True),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('user_identifier', sa.String(), nullable=False),
        sa.Column('user_name', sa.String(), nullable=True),
        sa.Column('user_email', sa.String(), nullable=True),
        sa.Column('platform', sa.String(), nullable=True),
        sa.Column('agent_id', sa.Integer(), nullable=True),
        sa.Column('assigned_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.Enum('waiting', 'active', 'resolved', 'abandoned', 'transferred', 'escalated', name='chatstatus'), nullable=True),
        sa.Column('subject', sa.String(), nullable=True),
        sa.Column('priority', sa.String(), nullable=True),
        sa.Column('department', sa.String(), nullable=True),
        sa.Column('chatbot_session_id', sa.String(), nullable=True),
        sa.Column('handoff_reason', sa.Text(), nullable=True),
        sa.Column('bot_context', sa.Text(), nullable=True),
        sa.Column('queue_time', sa.Integer(), nullable=True),
        sa.Column('first_response_time', sa.Integer(), nullable=True),
        sa.Column('resolution_time', sa.Integer(), nullable=True),
        sa.Column('customer_satisfaction', sa.Integer(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_live_chats_id'), 'live_chats', ['id'], unique=False)
    op.create_index(op.f('ix_live_chats_session_id'), 'live_chats', ['session_id'], unique=True)
    op.create_index(op.f('ix_live_chats_user_identifier'), 'live_chats', ['user_identifier'], unique=False)
    
    # Create live_chat_messages table
    op.create_table('live_chat_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('chat_id', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('message_type', sa.Enum('text', 'image', 'file', 'system', 'handoff', name='messagetype'), nullable=True),
        sa.Column('file_url', sa.String(), nullable=True),
        sa.Column('is_from_user', sa.Boolean(), nullable=True),
        sa.Column('agent_id', sa.Integer(), nullable=True),
        sa.Column('sender_name', sa.String(), nullable=True),
        sa.Column('is_internal', sa.Boolean(), nullable=True),
        sa.Column('read_by_user', sa.Boolean(), nullable=True),
        sa.Column('read_by_agent', sa.Boolean(), nullable=True),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('platform_message_id', sa.String(), nullable=True),
        sa.Column('metadata', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ),
        sa.ForeignKeyConstraint(['chat_id'], ['live_chats.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_live_chat_messages_id'), 'live_chat_messages', ['id'], unique=False)
    
    # Create agent_sessions table
    op.create_table('agent_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('agent_id', sa.Integer(), nullable=False),
        sa.Column('session_token', sa.String(), nullable=True),
        sa.Column('ip_address', sa.String(), nullable=True),
        sa.Column('user_agent', sa.String(), nullable=True),
        sa.Column('status', sa.Enum('online', 'busy', 'away', 'offline', name='agentstatus'), nullable=True),
        sa.Column('last_activity', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('logged_in_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('logged_out_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_agent_sessions_id'), 'agent_sessions', ['id'], unique=False)
    op.create_index(op.f('ix_agent_sessions_session_token'), 'agent_sessions', ['session_token'], unique=True)
    
    # Create chat_queue table
    op.create_table('chat_queue',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('chat_id', sa.Integer(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('estimated_wait_time', sa.Integer(), nullable=True),
        sa.Column('department', sa.String(), nullable=True),
        sa.Column('priority', sa.String(), nullable=True),
        sa.Column('preferred_agent_id', sa.Integer(), nullable=True),
        sa.Column('required_skills', sa.Text(), nullable=True),
        sa.Column('queued_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['chat_id'], ['live_chats.id'], ),
        sa.ForeignKeyConstraint(['preferred_agent_id'], ['agents.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_chat_queue_id'), 'chat_queue', ['id'], unique=False)

def downgrade():
    """Remove live chat tables"""
    op.drop_table('chat_queue')
    op.drop_table('agent_sessions')
    op.drop_table('live_chat_messages')
    op.drop_table('live_chats')
    op.drop_table('agents')
    
    # Drop enums
    op.execute('DROP TYPE IF EXISTS chatstatus CASCADE')
    op.execute('DROP TYPE IF EXISTS agentstatus CASCADE')
    op.execute('DROP TYPE IF EXISTS messagetype CASCADE')