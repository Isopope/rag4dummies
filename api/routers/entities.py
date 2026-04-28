"""Router /entities — CRUD des entités propriétaires (admin uniquement)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import current_admin_user
from db.engine import get_db_session
from db.models.user import User
from db.repositories.entity import EntityRepository

router = APIRouter()


class EntityOut(BaseModel):
    id: str
    name: str
    created_at: str


class EntityCreate(BaseModel):
    name: str


# ── GET /entities ──────────────────────────────────────────────────────────────

@router.get("", response_model=list[EntityOut], summary="Lister les entités")
async def list_entities(
    session: AsyncSession = Depends(get_db_session),
) -> list[EntityOut]:
    repo = EntityRepository(session)
    entities = await repo.list_all()
    return [EntityOut(id=str(e.id), name=e.name, created_at=str(e.created_at)) for e in entities]


# ── POST /entities ─────────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=EntityOut,
    status_code=status.HTTP_201_CREATED,
    summary="Créer une entité",
)
async def create_entity(
    body: EntityCreate,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(current_admin_user),
) -> EntityOut:
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Le nom de l'entité ne peut pas être vide.")
    repo = EntityRepository(session)
    if await repo.get_by_name(name):
        raise HTTPException(status_code=409, detail=f"L'entité '{name}' existe déjà.")
    entity = await repo.create(name)
    return EntityOut(id=str(entity.id), name=entity.name, created_at=str(entity.created_at))


# ── DELETE /entities/{entity_id} ───────────────────────────────────────────────

@router.delete(
    "/{entity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Supprimer une entité",
)
async def delete_entity(
    entity_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(current_admin_user),
) -> None:
    repo = EntityRepository(session)
    deleted = await repo.delete(entity_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Entité introuvable.")
