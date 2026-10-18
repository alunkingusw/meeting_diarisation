"""add project expiry to groups

Revision ID: e9a0b1c2d3e4
Revises: d8f9a0b1c2d3
Create Date: 2026-10-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e9a0b1c2d3e4"
down_revision: Union[str, None] = "d8f9a0b1c2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("groups", sa.Column("project_expiry", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("groups", "project_expiry")