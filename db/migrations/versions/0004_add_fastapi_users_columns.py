"""add fastapi-users columns to users table

Ajoute is_active, is_superuser, is_verified requis par fastapi-users.

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_active",    sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("users", sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("is_verified",  sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("users", "is_verified")
    op.drop_column("users", "is_superuser")
    op.drop_column("users", "is_active")
