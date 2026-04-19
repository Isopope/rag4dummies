"""Alembic env.py — configuration des migrations.

Supporte les migrations offline (SQL script) et online (connexion directe).
Avec SQLAlchemy async, les migrations online utilisent run_sync pour rester
compatibles avec Alembic qui est synchrone.

URL sync déduite automatiquement depuis DATABASE_URL :
  postgresql+asyncpg://... → postgresql+psycopg2://...
  sqlite+aiosqlite://...   → sqlite://...
"""
from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

load_dotenv()

# ── Config Alembic ─────────────────────────────────────────────────────────────
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── Import des modèles pour l'autogenerate ─────────────────────────────────────
# IMPORTANT : importer tous les modèles ici pour qu'Alembic les détecte
from db.models import Base  # noqa: E402  (après load_dotenv)
from db.models import Conversation, Document, Message, User  # noqa: F401

target_metadata = Base.metadata


# ── Résolution de l'URL sync ───────────────────────────────────────────────────

def _sync_url() -> str:
    """Convertit DATABASE_URL (async) en URL synchrone pour Alembic."""
    url = os.getenv("DATABASE_URL", "sqlite:///./rag.db")
    url = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    url = url.replace("sqlite+aiosqlite://",   "sqlite://")
    return url


# ── Mode offline (génère un script SQL sans connexion) ────────────────────────

def run_migrations_offline() -> None:
    url = _sync_url()
    context.configure(
        url                     = url,
        target_metadata         = target_metadata,
        literal_binds           = True,
        dialect_opts            = {"paramstyle": "named"},
        compare_type            = True,
        compare_server_default  = True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Mode online (connexion directe) ──────────────────────────────────────────

def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = _sync_url()

    connectable = engine_from_config(
        cfg,
        prefix        = "sqlalchemy.",
        poolclass     = pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection              = connection,
            target_metadata         = target_metadata,
            compare_type            = True,
            compare_server_default  = True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
