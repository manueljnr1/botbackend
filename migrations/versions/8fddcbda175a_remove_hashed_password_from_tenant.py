"""remove_hashed_password_from_tenant

Revision ID: 8fddcbda175a
Revises: beb55976f2a4
Create Date: 2025-05-20 01:39:32.080457

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8fddcbda175a'
down_revision: Union[str, None] = 'beb55976f2a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column('tenants', 'hashed_password')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('tenants', sa.Column('hashed_password', sa.String(), nullable=True))
