"""add entity and validity_date to documents table

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "entity",
            sa.String(100),
            nullable=True,
            comment="Entité propriétaire (ex. 'dassault', 'thales')",
        ),
    )
    op.create_index("ix_documents_entity", "documents", ["entity"])
    op.add_column(
        "documents",
        sa.Column(
            "validity_date",
            sa.Date(),
            nullable=True,
            comment="Date limite de validité — exclusion automatique après cette date",
        ),
    )


def downgrade() -> None:
    op.drop_column("documents", "validity_date")
    op.drop_index("ix_documents_entity", table_name="documents")
    op.drop_column("documents", "entity")
