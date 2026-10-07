"""add GitHub/Trello index tables (backend/project_rag)

Revision ID: a1b2c3d4e5f6
Revises: 9a8b7c6d5e4f
Create Date: 2026-10-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "9a8b7c6d5e4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rag_repos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("groups.id"), nullable=False, unique=True),
        sa.Column("github_url", sa.String(512), nullable=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("local_path", sa.String(1024), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trello_board_id", sa.String(24), nullable=True),
        sa.Column("trello_last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ingest_status", sa.String(16), nullable=False, server_default="idle"),
        sa.Column("ingest_error", sa.Text(), nullable=True),
    )
    op.create_table(
        "rag_commits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("repo_id", sa.Integer(), sa.ForeignKey("rag_repos.id"), nullable=False, index=True),
        sa.Column("sha", sa.String(40), nullable=False),
        sa.Column("author_name", sa.String(256), nullable=False, index=True),
        sa.Column("author_email", sa.String(256), nullable=False),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("files_changed", sa.Integer(), nullable=True),
        sa.Column("additions", sa.Integer(), nullable=True),
        sa.Column("deletions", sa.Integer(), nullable=True),
        sa.Column("diff_text", sa.Text(), nullable=False),
        sa.Column("chroma_id", sa.String(256), nullable=True),
        sa.UniqueConstraint("repo_id", "sha", name="uq_commits_repo_sha"),
    )
    op.create_table(
        "rag_issues",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("repo_id", sa.Integer(), sa.ForeignKey("rag_repos.id"), nullable=False, index=True),
        sa.Column("github_issue_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("author", sa.String(256), nullable=False, index=True),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("chroma_id", sa.String(256), nullable=True),
        sa.UniqueConstraint("repo_id", "github_issue_number", name="uq_issues_repo_number"),
    )
    op.create_table(
        "rag_issue_comments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("issue_id", sa.Integer(), sa.ForeignKey("rag_issues.id"), nullable=False, index=True),
        sa.Column("github_comment_id", sa.BigInteger(), nullable=False),
        sa.Column("author", sa.String(256), nullable=False, index=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("chroma_id", sa.String(256), nullable=True),
        sa.UniqueConstraint("issue_id", "github_comment_id", name="uq_issue_comments_issue_github_id"),
    )
    op.create_table(
        "rag_review_comments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("repo_id", sa.Integer(), sa.ForeignKey("rag_repos.id"), nullable=False, index=True),
        sa.Column("github_comment_id", sa.BigInteger(), nullable=False),
        sa.Column("pr_number", sa.Integer(), nullable=False),
        sa.Column("author", sa.String(256), nullable=False, index=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("file_path", sa.String(1024), nullable=True),
        sa.Column("line", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("chroma_id", sa.String(256), nullable=True),
        sa.UniqueConstraint("repo_id", "github_comment_id", name="uq_review_comments_repo_github_id"),
    )
    op.create_table(
        "rag_trello_actions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("repo_id", sa.Integer(), sa.ForeignKey("rag_repos.id"), nullable=False, index=True),
        sa.Column("trello_action_id", sa.String(24), nullable=False),
        sa.Column("action_type", sa.String(50), nullable=False, index=True),
        sa.Column("card_id", sa.String(24), nullable=False, index=True),
        sa.Column("card_name", sa.Text(), nullable=False),
        sa.Column("member_creator", sa.String(256), nullable=False, index=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("chroma_id", sa.String(256), nullable=True),
        sa.UniqueConstraint("repo_id", "trello_action_id", name="uq_trello_actions_repo_trello_id"),
    )


def downgrade() -> None:
    for table in (
        "rag_trello_actions",
        "rag_review_comments",
        "rag_issue_comments",
        "rag_issues",
        "rag_commits",
        "rag_repos",
    ):
        op.drop_table(table)
