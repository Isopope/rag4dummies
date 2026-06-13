"""Repository ConnectorConfig — sources de connecteurs synchronisées périodiquement."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.connector_config import ConnectorConfig


class ConnectorConfigRepository:
    """CRUD + sélection des sources dues pour la synchronisation planifiée."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, **fields) -> ConnectorConfig:
        cfg = ConnectorConfig(**fields)
        self._session.add(cfg)
        await self._session.flush()
        return cfg

    async def get(self, config_id: uuid.UUID) -> ConnectorConfig | None:
        result = await self._session.execute(
            select(ConnectorConfig).where(ConnectorConfig.id == config_id)
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[ConnectorConfig]:
        result = await self._session.execute(
            select(ConnectorConfig).order_by(ConnectorConfig.created_at.desc())
        )
        return list(result.scalars().all())

    async def update(self, config_id: uuid.UUID, **fields) -> ConnectorConfig | None:
        cfg = await self.get(config_id)
        if cfg is None:
            return None
        for key, value in fields.items():
            if value is not None and hasattr(cfg, key):
                setattr(cfg, key, value)
        return cfg

    async def delete(self, config_id: uuid.UUID) -> bool:
        cfg = await self.get(config_id)
        if cfg is None:
            return False
        await self._session.delete(cfg)
        return True

    async def mark_dispatched(
        self, config_id: uuid.UUID, task_id: str, now: datetime, status: str = "queued"
    ) -> ConnectorConfig | None:
        cfg = await self.get(config_id)
        if cfg is not None:
            cfg.last_sync_at = now
            cfg.last_task_id = task_id
            cfg.last_status = status
        return cfg

    async def list_due(self, now: datetime) -> list[ConnectorConfig]:
        """Sources actives jamais synchronisées ou dont l'intervalle est écoulé."""
        result = await self._session.execute(
            select(ConnectorConfig).where(ConnectorConfig.enabled.is_(True))
        )
        due: list[ConnectorConfig] = []
        for cfg in result.scalars().all():
            if cfg.last_sync_at is None:
                due.append(cfg)
                continue
            last = cfg.last_sync_at
            # Normalise les datetimes naïfs (SQLite) vers la tz de `now`.
            if last.tzinfo is None and now.tzinfo is not None:
                last = last.replace(tzinfo=now.tzinfo)
            if now - last >= timedelta(seconds=cfg.interval_seconds):
                due.append(cfg)
        return due
