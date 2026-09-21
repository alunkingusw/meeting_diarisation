"""add meeting idempotency key

Revision ID: e7f8a9b0c1d2
Revises: d9e1f2a3b4c5
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, None] = "d9e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("meetings", sa.Column("idempotency_key", sa.String(length=255), nullable=True))
    op.create_index("ix_meetings_idempotency_key", "meetings", ["idempotency_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_meetings_idempotency_key", table_name="meetings")
    op.drop_column("meetings", "idempotency_key")