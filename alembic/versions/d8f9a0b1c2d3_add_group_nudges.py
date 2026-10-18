"""add group nudge delivery records

Revision ID: d8f9a0b1c2d3
Revises: c7e8f9a0b1c2
Create Date: 2026-10-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d8f9a0b1c2d3"
down_revision: Union[str, None] = "c7e8f9a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "group_nudges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("groups.id"), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("recipient_email", sa.String(320), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "group_id", "period_start", "period_end", "recipient_email",
            name="uq_group_nudge_recipient_period",
        ),
    )
    op.create_index("ix_group_nudges_group_id", "group_nudges", ["group_id"])


def downgrade() -> None:
    op.drop_index("ix_group_nudges_group_id", table_name="group_nudges")
    op.drop_table("group_nudges")