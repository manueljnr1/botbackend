"""add_tenant_branding_customization

Revision ID: c972fb4e4f2f
Revises: 8fddcbda175a
Create Date: 2025-06-20 00:46:51.473093

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c972fb4e4f2f'
down_revision: Union[str, None] = '8fddcbda175a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - SAFE VERSION: Only adds branding fields."""
    # ### SAFE: Only adding branding columns to tenants table ###
    
    # Add branding color columns
    op.add_column('tenants', sa.Column('primary_color', sa.String(length=7), nullable=True))
    op.add_column('tenants', sa.Column('secondary_color', sa.String(length=7), nullable=True))
    op.add_column('tenants', sa.Column('text_color', sa.String(length=7), nullable=True))
    op.add_column('tenants', sa.Column('background_color', sa.String(length=7), nullable=True))
    op.add_column('tenants', sa.Column('user_bubble_color', sa.String(length=7), nullable=True))
    op.add_column('tenants', sa.Column('bot_bubble_color', sa.String(length=7), nullable=True))
    op.add_column('tenants', sa.Column('border_color', sa.String(length=7), nullable=True))
    
    # Add logo columns
    op.add_column('tenants', sa.Column('logo_image_url', sa.String(), nullable=True))
    op.add_column('tenants', sa.Column('logo_text', sa.String(length=10), nullable=True))
    
    # Add layout and styling columns
    op.add_column('tenants', sa.Column('border_radius', sa.String(length=10), nullable=True))
    op.add_column('tenants', sa.Column('widget_position', sa.String(length=20), nullable=True))
    op.add_column('tenants', sa.Column('font_family', sa.String(length=100), nullable=True))
    
    # Add advanced customization
    op.add_column('tenants', sa.Column('custom_css', sa.Text(), nullable=True))
    
    # Add branding metadata
    op.add_column('tenants', sa.Column('branding_updated_at', sa.DateTime(), nullable=True))
    op.add_column('tenants', sa.Column('branding_version', sa.Integer(), nullable=True))
    
    # Set default values for existing tenants
    op.execute("""
        UPDATE tenants SET 
            primary_color = '#007bff',
            secondary_color = '#f0f4ff',
            text_color = '#222222',
            background_color = '#ffffff',
            user_bubble_color = '#007bff',
            bot_bubble_color = '#f0f4ff',
            border_color = '#e0e0e0',
            border_radius = '12px',
            widget_position = 'bottom-right',
            font_family = 'Inter, sans-serif',
            branding_version = 1
        WHERE primary_color IS NULL
    """)
    
    # Set logo_text for existing tenants
    op.execute("""
        UPDATE tenants SET 
            logo_text = UPPER(SUBSTR(COALESCE(business_name, name, 'AI'), 1, 2))
        WHERE logo_text IS NULL
    """)


def downgrade() -> None:
    """Downgrade schema - Remove branding fields."""
    # Remove all branding columns in reverse order
    op.drop_column('tenants', 'branding_version')
    op.drop_column('tenants', 'branding_updated_at')
    op.drop_column('tenants', 'custom_css')
    op.drop_column('tenants', 'font_family')
    op.drop_column('tenants', 'widget_position')
    op.drop_column('tenants', 'border_radius')
    op.drop_column('tenants', 'logo_text')
    op.drop_column('tenants', 'logo_image_url')
    op.drop_column('tenants', 'border_color')
    op.drop_column('tenants', 'bot_bubble_color')
    op.drop_column('tenants', 'user_bubble_color')
    op.drop_column('tenants', 'background_color')
    op.drop_column('tenants', 'text_color')
    op.drop_column('tenants', 'secondary_color')
    op.drop_column('tenants', 'primary_color')