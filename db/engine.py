"""Moteur SQLAlchemy async + factory de session.

Drivers supportés :
- SQLite (dev/tests) : sqlite+aiosqlite:///./rag.db
- PostgreSQL (prod)  : postgresql+asyncpg://user:pass@host:5432/ragdb
"""
from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from functools import lru_cache

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

load_dotenv()

DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./rag.db")


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Retourne l'AsyncEngine SQLAlchemy (singleton par processus)."""
    is_sqlite = DATABASE_URL.startswith("sqlite")
    return create_async_engine(
        DATABASE_URL,
        echo=os.getenv("DB_ECHO", "false").lower() == "true",
        # SQLite ne supporte pas le pool pre-ping
        pool_pre_ping=not is_sqlite,
        # SQLite : un seul thread suffit
        connect_args={"check_same_thread": False} if is_sqlite else {},
    )


@lru_cache(maxsize=1)
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Retourne la factory de sessions (singleton)."""
    return async_sessionmaker(
        bind=get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency FastAPI : yield une AsyncSession avec commit/rollback automatique."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_all_tables() -> None:
    """Crée toutes les tables si elles n'existent pas (utile pour SQLite / tests).

    En production avec PostgreSQL, préférer les migrations Alembic.
    """
    from .models import Base
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
