"""
Tâches périodiques (beat) — maintenance de la queue d'ingestion.

Trois tâches :

1. retry_stale_pending
   Documents en statut PENDING depuis > PENDING_STALE_MINUTES :
   le worker qui a dispatché la tâche a peut-être crashé avant même
   que Celery n'ACK le message.  On re-dispatche ingest_pdf_task.

2. retry_error_documents
   Documents en statut ERROR avec retry_count < MAX_AUTO_RETRY :
   re-dispatche automatiquement pour corriger les erreurs transitoires
   (réseau, Weaviate surchargé, etc.)

3. cleanup_stale_processing
   Documents en statut PROCESSING depuis > PROCESSING_STALE_HOURS :
   le worker est probablement mort (zombie).  On les repasse en ERROR
   pour qu'ils soient repris par retry_error_documents ou traités manuellement.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from celery.utils.log import get_task_logger

from worker.app import celery_app
from worker.queues import LIGHT_QUEUE, INGEST_QUEUE, RagCeleryPriority

_logger = get_task_logger(__name__)

# ── Paramètres ─────────────────────────────────────────────────────────────────
PENDING_STALE_MINUTES   = 10    # PENDING depuis > 10 min → re-dispatch
PROCESSING_STALE_HOURS  = 2     # PROCESSING depuis > 2h  → mark ERROR
MAX_AUTO_RETRY          = 3     # nombre max de tentatives automatiques (beat)


# ── Helpers DB ─────────────────────────────────────────────────────────────────

def _list_stale_pending() -> list[object]:
    """Retourne les documents PENDING dont updated_at < now - PENDING_STALE_MINUTES."""
    async def _inner():
        from db.engine import get_session_factory
        from db.models.document import DocumentStatus
        from db.repositories.document import DocumentRepository
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=PENDING_STALE_MINUTES)
        async with get_session_factory()() as session:
            repo = DocumentRepository(session)
            return await repo.list_by_status_before(DocumentStatus.PENDING, cutoff)
    return asyncio.run(_inner())


def _list_error_documents(max_retry: int) -> list[object]:
    """Retourne les documents ERROR avec retry_count < max_retry."""
    async def _inner():
        from db.engine import get_session_factory
        from db.models.document import DocumentStatus
        from db.repositories.document import DocumentRepository
        async with get_session_factory()() as session:
            repo = DocumentRepository(session)
            return await repo.list_by_status_retry_lt(DocumentStatus.ERROR, max_retry)
    return asyncio.run(_inner())


def _list_stale_processing() -> list[object]:
    """Retourne les documents PROCESSING dont updated_at < now - PROCESSING_STALE_HOURS."""
    async def _inner():
        from db.engine import get_session_factory
        from db.models.document import DocumentStatus
        from db.repositories.document import DocumentRepository
        cutoff = datetime.now(timezone.utc) - timedelta(hours=PROCESSING_STALE_HOURS)
        async with get_session_factory()() as session:
            repo = DocumentRepository(session)
            return await repo.list_by_status_before(DocumentStatus.PROCESSING, cutoff)
    return asyncio.run(_inner())


def _mark_error_batch(source_paths: list[str], message: str) -> None:
    async def _inner():
        from db.engine import get_session_factory
        from db.repositories.document import DocumentRepository
        async with get_session_factory()() as session:
            repo = DocumentRepository(session)
            for sp in source_paths:
                await repo.mark_error(sp, message)
            await session.commit()
    asyncio.run(_inner())


def _increment_retry_count(source_paths: list[str]) -> None:
    async def _inner():
        from db.engine import get_session_factory
        from db.repositories.document import DocumentRepository
        async with get_session_factory()() as session:
            repo = DocumentRepository(session)
            for sp in source_paths:
                await repo.increment_retry_count(sp)
            await session.commit()
    asyncio.run(_inner())


# ── Tâches ─────────────────────────────────────────────────────────────────────

@celery_app.task(
    name  = "rag.tasks.retry_stale_pending",
    queue = LIGHT_QUEUE,
)
def retry_stale_pending() -> dict:
    """Re-dispatche les documents PENDING bloqués depuis > PENDING_STALE_MINUTES."""
    from worker.tasks.ingest import ingest_pdf_task

    docs = _list_stale_pending()
    if not docs:
        return {"dispatched": 0}

    _logger.info("retry_stale_pending : %d document(s) relancé(s)", len(docs))
    for doc in docs:
        ingest_pdf_task.apply_async(
            args     = [doc.source_path, doc.parser or "docling", doc.strategy or "by_token", doc.filename or ""],
            queue    = INGEST_QUEUE,
            priority = int(RagCeleryPriority.LOW),
        )
    return {"dispatched": len(docs)}


@celery_app.task(
    name  = "rag.tasks.retry_error_documents",
    queue = LIGHT_QUEUE,
)
def retry_error_documents() -> dict:
    """Re-dispatche les documents en ERROR avec retry_count < MAX_AUTO_RETRY."""
    from worker.tasks.ingest import ingest_pdf_task

    docs = _list_error_documents(MAX_AUTO_RETRY)
    if not docs:
        return {"dispatched": 0}

    _logger.info("retry_error_documents : %d document(s) relancé(s)", len(docs))
    dispatched_paths = []
    for doc in docs:
        ingest_pdf_task.apply_async(
            args     = [doc.source_path, doc.parser or "docling", doc.strategy or "by_token", doc.filename or ""],
            queue    = INGEST_QUEUE,
            priority = int(RagCeleryPriority.LOW),
        )
        dispatched_paths.append(doc.source_path)

    _increment_retry_count(dispatched_paths)
    return {"dispatched": len(dispatched_paths)}


@celery_app.task(
    name  = "rag.tasks.cleanup_stale_processing",
    queue = LIGHT_QUEUE,
)
def cleanup_stale_processing() -> dict:
    """Marque en ERROR les documents bloqués en PROCESSING depuis > PROCESSING_STALE_HOURS."""
    docs = _list_stale_processing()
    if not docs:
        return {"cleaned": 0}

    paths = [doc.source_path for doc in docs]
    _logger.warning("cleanup_stale_processing : %d document(s) bloqués marqués ERROR", len(paths))
    _mark_error_batch(paths, f"Traitement bloqué depuis > {PROCESSING_STALE_HOURS}h — timeout worker")
    return {"cleaned": len(paths)}
