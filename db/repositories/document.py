"""Repository Document — suivi du statut d'ingestion."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.document import Document, DocumentStatus


class DocumentRepository:
    """CRUD pour les documents et leur statut d'ingestion."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Création / upsert ──────────────────────────────────────────────────────

    async def upsert(
        self,
        source_path: str,
        *,
        parser: str | None = None,
        strategy: str | None = None,
        task_id: str | None = None,
        entity: str | None = None,
        validity_date: str | None = None,
    ) -> Document:
        """Crée ou récupère un Document pour ce source_path, statut PENDING.

        Appelé au début de l'ingestion pour enregistrer le document.
        """
        doc = await self.get_by_source(source_path)
        if doc is None:
            from datetime import date as _date
            doc = Document(
                source_path   = source_path,
                filename      = Path(source_path).name,
                status        = DocumentStatus.PENDING,
                parser        = parser,
                strategy      = strategy,
                task_id       = task_id,
                entity        = entity,
                validity_date = _date.fromisoformat(validity_date) if validity_date else None,
            )
            self._session.add(doc)
            await self._session.flush()
        else:
            # Réinitialise le statut si on rejoue l'ingestion
            doc.status        = DocumentStatus.PENDING
            doc.error_message = None
            doc.chunk_count   = 0
            doc.parser        = parser or doc.parser
            doc.strategy      = strategy or doc.strategy
            if task_id:
                doc.task_id = task_id
            if entity is not None:
                doc.entity = entity
            if validity_date is not None:
                from datetime import date as _date
                doc.validity_date = _date.fromisoformat(validity_date)
        return doc

    async def mark_processing(self, source_path: str) -> Document | None:
        doc = await self.get_by_source(source_path)
        if doc:
            doc.status = DocumentStatus.PROCESSING
        return doc

    async def mark_indexed(self, source_path: str, chunk_count: int) -> Document | None:
        doc = await self.get_by_source(source_path)
        if doc:
            doc.status      = DocumentStatus.INDEXED
            doc.chunk_count = chunk_count
            doc.ingested_at = datetime.now(timezone.utc)
        return doc

    async def mark_error(self, source_path: str, error_message: str) -> Document | None:
        doc = await self.get_by_source(source_path)
        if doc:
            doc.status        = DocumentStatus.ERROR
            doc.error_message = error_message
        return doc

    # ── Lecture ────────────────────────────────────────────────────────────────

    async def get(self, document_id: uuid.UUID) -> Document | None:
        result = await self._session.execute(
            select(Document).where(Document.id == document_id)
        )
        return result.scalar_one_or_none()

    async def get_by_source(self, source_path: str) -> Document | None:
        result = await self._session.execute(
            select(Document).where(Document.source_path == source_path)
        )
        return result.scalar_one_or_none()

    async def get_by_task_id(self, task_id: str) -> Document | None:
        result = await self._session.execute(
            select(Document).where(Document.task_id == task_id)
        )
        return result.scalar_one_or_none()

    async def list_all(
        self,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Document]:
        """Liste les documents, avec filtre optionnel par statut."""
        stmt = (
            select(Document)
            .order_by(Document.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if status is not None:
            stmt = stmt.where(Document.status == status)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    # ── Suppression ────────────────────────────────────────────────────────────

    async def delete_by_source(self, source_path: str) -> bool:
        doc = await self.get_by_source(source_path)
        if doc is None:
            return False
        await self._session.delete(doc)
        return True

    # ── Méthodes pour les tâches beat ─────────────────────────────────────────

    async def list_by_status_before(
        self, status: str, cutoff: datetime
    ) -> list[Document]:
        """Retourne les documents d'un statut donné dont updated_at < cutoff."""
        result = await self._session.execute(
            select(Document)
            .where(Document.status == status)
            .where(Document.updated_at < cutoff)
        )
        return list(result.scalars().all())

    async def list_by_status_retry_lt(
        self, status: str, max_retry: int
    ) -> list[Document]:
        """Retourne les documents d'un statut donné avec retry_count < max_retry."""
        result = await self._session.execute(
            select(Document)
            .where(Document.status == status)
            .where(Document.retry_count < max_retry)
        )
        return list(result.scalars().all())

    async def increment_retry_count(self, source_path: str) -> None:
        """Incrémente le compteur de tentatives automatiques d'un document."""
        doc = await self.get_by_source(source_path)
        if doc is not None:
            doc.retry_count = (doc.retry_count or 0) + 1
