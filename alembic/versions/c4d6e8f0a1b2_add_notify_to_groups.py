"""add notify flag to groups

Revision ID: c4d6e8f0a1b2
Revises: a71cbeb0ac72
Create Date: 2026-09-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4d6e8f0a1b2'
down_revision: Union[str, None] = 'a71cbeb0ac72'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'groups',
        sa.Column('notify', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('groups', 'notify')