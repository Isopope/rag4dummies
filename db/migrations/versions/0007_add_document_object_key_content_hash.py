"""add object_key, content_hash, source_scope to documents

Découple l'identité du document (source_path) du pointeur de stockage
(object_key) et ajoute un détecteur de changement (content_hash) ainsi
qu'un scope de connecteur pour le pruning (source_scope).

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("object_key", sa.String(length=1000), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("content_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("source_scope", sa.String(length=1000), nullable=True),
    )
    op.create_index("ix_documents_object_key", "documents", ["object_key"])
    op.create_index("ix_documents_source_scope", "documents", ["source_scope"])


def downgrade() -> None:
    op.drop_index("ix_documents_source_scope", table_name="documents")
    op.drop_index("ix_documents_object_key", table_name="documents")
    op.drop_column("documents", "source_scope")
    op.drop_column("documents", "content_hash")
    op.drop_column("documents", "object_key")
