"""init: création des tables conversations, messages, documents, users

Revision ID: 0001
Revises:
Create Date: 2026-04-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── users ──────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id",              sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("email",           sa.String(320),        nullable=False),
        sa.Column("hashed_password", sa.String(1024),       nullable=False),
        sa.Column("role",            sa.String(50),         nullable=False, server_default="user"),
        sa.Column("created_at",      sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # ── conversations ─────────────────────────────────────────────────────────
    op.create_table(
        "conversations",
        sa.Column("id",          sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id",     sa.String(255),        nullable=False, server_default="anonymous"),
        sa.Column("title",       sa.String(500),        nullable=True),
        sa.Column("question_id", sa.String(36),         nullable=True),
        sa.Column("created_at",  sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at",  sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversations_user_id",     "conversations", ["user_id"])
    op.create_index("ix_conversations_question_id", "conversations", ["question_id"])

    # ── messages ──────────────────────────────────────────────────────────────
    op.create_table(
        "messages",
        sa.Column("id",              sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("conversation_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("role",            sa.String(20),         nullable=False),
        sa.Column("content",         sa.Text(),             nullable=False),
        sa.Column("rating",          sa.Integer(),          nullable=True),
        sa.Column("comment",         sa.Text(),             nullable=True),
        sa.Column("sources_json",    sa.Text(),             nullable=True),
        sa.Column("metadata_json",   sa.Text(),             nullable=True),
        sa.Column("created_at",      sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])

    # ── documents ─────────────────────────────────────────────────────────────
    op.create_table(
        "documents",
        sa.Column("id",            sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("source_path",   sa.String(1000),       nullable=False),
        sa.Column("filename",      sa.String(500),        nullable=False),
        sa.Column("status",        sa.String(20),         nullable=False, server_default="pending"),
        sa.Column("chunk_count",   sa.Integer(),          nullable=False, server_default="0"),
        sa.Column("parser",        sa.String(50),         nullable=True),
        sa.Column("strategy",      sa.String(50),         nullable=True),
        sa.Column("error_message", sa.Text(),             nullable=True),
        sa.Column("ingested_at",   sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at",    sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at",    sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_path"),
    )
    op.create_index("ix_documents_source_path", "documents", ["source_path"])
    op.create_index("ix_documents_status",      "documents", ["status"])


def downgrade() -> None:
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("documents")
    op.drop_table("users")
