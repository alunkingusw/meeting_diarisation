"""allow meeting comments from group-member email senders

Revision ID: 9a8b7c6d5e4f
Revises: f1a2b3c4d5e6
Create Date: 2026-10-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9a8b7c6d5e4f"
down_revision: Union[str, None] = "c6d7e8f9a0b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("meeting_comments") as batch_op:
        batch_op.alter_column(
            "user_id",
            existing_type=sa.Integer(),
            nullable=True,
        )
        batch_op.add_column(sa.Column("group_member_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_meeting_comments_group_member_id_group_members",
            "group_members",
            ["group_member_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("meeting_comments") as batch_op:
        batch_op.drop_constraint(
            "fk_meeting_comments_group_member_id_group_members", type_="foreignkey"
        )
        batch_op.drop_column("group_member_id")
        batch_op.alter_column(
            "user_id",
            existing_type=sa.Integer(),
            nullable=False,
        )