"""add task_id to documents table

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("task_id", sa.String(255), nullable=True))
    op.create_index("ix_documents_task_id", "documents", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_documents_task_id", table_name="documents")
    op.drop_column("documents", "task_id")
