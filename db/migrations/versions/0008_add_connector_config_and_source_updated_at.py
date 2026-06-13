"""add connector_config table and documents.source_updated_at

Sources de connecteurs synchronisées périodiquement (pull planifié) +
horodatage de dernière modification à la source pour le delta sync.

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "connector_config",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("connector_type", sa.String(length=50), nullable=False, server_default="sharepoint"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("config_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("parser", sa.String(length=50), nullable=False, server_default="mineru"),
        sa.Column("strategy", sa.String(length=50), nullable=False, server_default="by_sentence"),
        sa.Column("entity", sa.String(length=100), nullable=True),
        sa.Column("prune", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("interval_seconds", sa.Integer(), nullable=False, server_default="604800"),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_task_id", sa.String(length=255), nullable=True),
        sa.Column("last_status", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_connector_config_connector_type", "connector_config", ["connector_type"])
    op.create_index("ix_connector_config_enabled", "connector_config", ["enabled"])


def downgrade() -> None:
    op.drop_index("ix_connector_config_enabled", table_name="connector_config")
    op.drop_index("ix_connector_config_connector_type", table_name="connector_config")
    op.drop_table("connector_config")
    op.drop_column("documents", "source_updated_at")
