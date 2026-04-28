"""Repository Entity — CRUD pour les entités propriétaires."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.entity import Entity


class EntityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[Entity]:
        result = await self._session.execute(select(Entity).order_by(Entity.name))
        return list(result.scalars().all())

    async def get_by_name(self, name: str) -> Entity | None:
        result = await self._session.execute(
            select(Entity).where(Entity.name == name.lower())
        )
        return result.scalar_one_or_none()

    async def create(self, name: str) -> Entity:
        entity = Entity(name=name.lower().strip())
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity_id: uuid.UUID) -> bool:
        entity = await self._session.get(Entity, entity_id)
        if entity is None:
            return False
        await self._session.delete(entity)
        return True
