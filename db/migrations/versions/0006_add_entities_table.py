"""add entities table

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "entities",
        sa.Column("id",         sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name",       sa.String(100),        nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_entities_name", "entities", ["name"])


def downgrade() -> None:
    op.drop_index("ix_entities_name", table_name="entities")
    op.drop_table("entities")
