"""Service applicatif pour la soumission des jobs d'ingestion."""
from __future__ import annotations

import os
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from db.repositories.document import DocumentRepository
from storage import DocumentStore


class IngestionService:
    """Facade metier pour upload, dispatch Celery et suivi DB."""

    def __init__(self, session: AsyncSession, document_store: DocumentStore, celery_app: Any) -> None:
        self._session = session
        self._document_store = document_store
        self._celery_app = celery_app

    async def submit_pdf(
        self,
        *,
        filename: str,
        content: bytes,
        parser: str,
        strategy: str,
        entity: str | None = None,
        validity_date: str | None = None,
    ) -> dict[str, Any]:
        object_key = DocumentStore.make_object_key(filename, content)
        self._document_store.upload(content, object_key, content_type="application/pdf")

        from worker.queues import INGEST_QUEUE, RagCeleryPriority

        job = self._celery_app.send_task(
            "rag.tasks.ingest_pdf",
            args=[object_key, parser, strategy, filename],
            kwargs={"entity": entity, "validity_date": validity_date},
            queue=INGEST_QUEUE,
            priority=int(RagCeleryPriority.HIGH),
        )

        repo = DocumentRepository(self._session)
        await repo.upsert(
            object_key,
            parser=parser,
            strategy=strategy,
            task_id=job.id,
            entity=entity,
            validity_date=validity_date,
        )
        await self._session.commit()

        expires = int(os.getenv("MINIO_PRESIGN_EXPIRES", "3600"))
        pdf_url = self._document_store.presigned_url(object_key, expires_seconds=expires)

        logger.info("PDF '{}' dispatché — task_id={}", filename, job.id)
        return {
            "task_id": job.id,
            "status": "pending",
            "source": object_key,
            "filename": filename,
            "pdf_url": pdf_url,
        }

    async def submit_jsonl(
        self,
        *,
        filename: str,
        content: bytes,
        source_override: str | None = None,
    ) -> dict[str, Any]:
        object_key = DocumentStore.make_object_key(filename, content)
        self._document_store.upload(content, object_key, content_type="application/x-ndjson")

        from worker.queues import INGEST_QUEUE, RagCeleryPriority

        job = self._celery_app.send_task(
            "rag.tasks.ingest_jsonl",
            args=[object_key, source_override, filename],
            queue=INGEST_QUEUE,
            priority=int(RagCeleryPriority.HIGH),
        )

        repo = DocumentRepository(self._session)
        await repo.upsert(object_key, task_id=job.id)
        await self._session.commit()

        logger.info("JSONL '{}' dispatché — task_id={}", filename, job.id)
        return {
            "task_id": job.id,
            "status": "pending",
            "source": object_key,
            "filename": filename,
        }
