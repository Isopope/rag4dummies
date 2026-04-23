"""Modèle User — authentification via fastapi-users."""
from __future__ import annotations

from datetime import datetime

from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class User(SQLAlchemyBaseUserTableUUID, Base):
    """Table users.

    Hérite de SQLAlchemyBaseUserTableUUID qui fournit :
        id, email, hashed_password, is_active, is_superuser, is_verified
    Champs personnalisés :
        role, created_at
    """
    __tablename__ = "users"

    role: Mapped[str] = mapped_column(String(50), default="user")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} role={self.role!r}>"
