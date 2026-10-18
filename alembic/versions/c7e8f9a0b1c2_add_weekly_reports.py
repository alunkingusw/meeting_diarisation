"""add backend-owned weekly reports

Revision ID: c7e8f9a0b1c2
Revises: b2c3d4e5f6a7
Create Date: 2026-10-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c7e8f9a0b1c2"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "weekly_reports",
        sa.Column("report_id", sa.String(64), primary_key=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("groups.id"), nullable=False),
        sa.Column("group_name", sa.String(255), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("report_text", sa.Text(), nullable=True),
        sa.Column("model", sa.String(255), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("unavailable", sa.JSON(), nullable=False),
        sa.Column("recipients", sa.JSON(), nullable=False),
        sa.Column("queued_recipients", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("group_id", "period_start", "period_end", name="uq_weekly_report_period"),
    )
    op.create_index("ix_weekly_reports_group_id", "weekly_reports", ["group_id"])


def downgrade() -> None:
    op.drop_index("ix_weekly_reports_group_id", table_name="weekly_reports")
    op.drop_table("weekly_reports")