"""create base schema

Revision ID: 74252ed682e8
Revises:
Create Date: 2026-08-14 13:05:26.487861

Inserted as the new root of the migration chain (ahead of what was
previously the first migration, 68e27f62dd30). That migration - despite
being named "baseline schema" - only ever contained ALTER TABLE statements
against tables it assumed already existed, because historically those
tables were created by `Base.metadata.create_all()` in `backend/startup.py`
rather than by Alembic. Now that `startup.py` no longer does that (the
project switched to Alembic owning the schema), `alembic upgrade head`
against a genuinely empty database - e.g. a fresh volume on first deploy -
needs a migration that actually creates the tables. This one creates them
in the pre-68e27f62dd30 shape; the existing chain then alters them forward
to the current schema exactly as it did before.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '74252ed682e8'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('username', sa.String(length=45), nullable=True),
        sa.Column('created', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        'groups',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=45), nullable=True),
        sa.Column('created', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        'group_members',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=45), nullable=True),
        sa.Column('created', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        'meetings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('group_id', sa.Integer(), sa.ForeignKey('groups.id'), nullable=True),
        sa.Column('date', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('created', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        'raw_files',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('file_name', sa.String(length=255), nullable=True),
        sa.Column('human_name', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('meeting_id', sa.Integer(), sa.ForeignKey('meetings.id'), nullable=False),
        sa.Column('raw_file_type', sa.VARCHAR(), nullable=True),
    )
    op.create_table(
        'users_groups',
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('group_id', sa.Integer(), sa.ForeignKey('groups.id'), primary_key=True),
    )
    op.create_table(
        'groups_group_members',
        sa.Column('group_id', sa.Integer(), sa.ForeignKey('groups.id'), primary_key=True),
        sa.Column('group_member_id', sa.Integer(), sa.ForeignKey('group_members.id'), primary_key=True),
    )
    op.create_table(
        'meetings_group_members',
        sa.Column('meeting_id', sa.Integer(), sa.ForeignKey('meetings.id'), primary_key=True),
        sa.Column('group_member_id', sa.Integer(), sa.ForeignKey('group_members.id'), primary_key=True),
        sa.Column('confirmed', sa.Boolean(), nullable=True, server_default=sa.false()),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('meetings_group_members')
    op.drop_table('groups_group_members')
    op.drop_table('users_groups')
    op.drop_table('raw_files')
    op.drop_table('meetings')
    op.drop_table('group_members')
    op.drop_table('groups')
    op.drop_table('users')
