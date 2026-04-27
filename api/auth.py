"""Configuration fastapi-users — Bearer + JWT.

Exporte :
    - auth_backend          : backend JWT à passer aux routers
    - fastapi_users         : instance centrale FastAPIUsers
    - current_active_user   : dépendance FastAPI — tout utilisateur actif
    - current_admin_user    : dépendance FastAPI — réservé au rôle "admin"
    - UserRead / UserCreate / UserUpdate : schémas Pydantic
"""
from __future__ import annotations

import os
import uuid
from typing import Optional

from fastapi import Depends, HTTPException, status as http_status
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin, schemas
from fastapi_users.authentication import AuthenticationBackend, BearerTransport, JWTStrategy
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import get_db_session
from db.models.user import User

_JWT_SECRET   = os.getenv("JWT_SECRET_KEY", "changeme-in-production")
_JWT_LIFETIME = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60")) * 60


# ── Schémas Pydantic ───────────────────────────────────────────────────────────

class UserRead(schemas.BaseUser[uuid.UUID]):
    role: str


class UserCreate(schemas.BaseUserCreate):
    role: str = "user"


class UserUpdate(schemas.BaseUserUpdate):
    role: Optional[str] = None


# ── Adaptateur SQLAlchemy ─────────────────────────────────────────────────────

async def get_user_db(session: AsyncSession = Depends(get_db_session)):
    yield SQLAlchemyUserDatabase(session, User)


# ── UserManager ───────────────────────────────────────────────────────────────

class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = _JWT_SECRET
    verification_token_secret   = _JWT_SECRET


async def get_user_manager(user_db: SQLAlchemyUserDatabase = Depends(get_user_db)):
    yield UserManager(user_db)


# ── Transport + Strategy ──────────────────────────────────────────────────────

_bearer_transport = BearerTransport(tokenUrl="/auth/jwt/login")


def _get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=_JWT_SECRET, lifetime_seconds=_JWT_LIFETIME)


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=_bearer_transport,
    get_strategy=_get_jwt_strategy,
)


# ── Instance centrale ─────────────────────────────────────────────────────────

fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])

# Dépendance — tout utilisateur actif
#   async def my_route(user: User = Depends(current_active_user)): ...
current_active_user = fastapi_users.current_user(active=True)

# Dépendance — utilisateur optionnel (None si non authentifié)
#   async def my_route(user: User | None = Depends(current_optional_user)): ...
current_optional_user = fastapi_users.current_user(active=True, optional=True)


# Dépendance — administrateur uniquement (role == "admin")
#   async def my_route(_: User = Depends(current_admin_user)): ...
async def current_admin_user(user: User = Depends(current_active_user)) -> User:
    if user.role != "admin":
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux administrateurs.",
        )
    return user
