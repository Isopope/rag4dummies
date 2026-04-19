"""
Tâches Celery d'ingestion — cœur du pipeline industriel.

Flux PDF :
    API  →  upload MinIO/local  →  DB upsert (PENDING, task_id=X)
         →  ingest_pdf_task.delay(object_key, parser, strategy)
         →  Worker : download tmpfile → ingest_pdf() → Weaviate
         →  DB mark_indexed / mark_error
         →  tmpfile supprimé

Flux JSONL :
    API  →  upload MinIO/local  →  DB upsert (PENDING, task_id=X)
         →  ingest_jsonl_task.delay(object_key, source_override)
         →  Worker : download tmpfile → ingest_jsonl() → Weaviate
         →  DB mark_indexed / mark_error

Chaque tâche :
- Met à jour le statut DB (PENDING → PROCESSING → INDEXED | ERROR)
- Retente jusqu'à MAX_RETRIES fois en cas d'échec
- Supprime le fichier temporaire même en cas d'exception (finally)
- Utilise asyncio.run() pour les appels SQLAlchemy async (pattern simple,
  compatible Celery threaded pool — chaque tâche crée son propre event loop)
"""
from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

from celery import Task
from celery.exceptions import SoftTimeLimitExceeded
from celery.utils.log import get_task_logger
from loguru import logger

from worker.app import celery_app
from worker.queues import INGEST_QUEUE, RagCeleryPriority

_task_logger = get_task_logger(__name__)

MAX_RETRIES        = 3
RETRY_BACKOFF_BASE = 60   # secondes — 60s, 120s, 240s (x2 chaque tentative)


# ── Helpers DB (sync-over-async) ───────────────────────────────────────────────

def _db_upsert(source_path: str, parser: str | None, strategy: str | None, task_id: str) -> None:
    async def _inner():
        from db.engine import get_session_factory
        async with get_session_factory()() as session:
            from db.repositories.document import DocumentRepository
            repo = DocumentRepository(session)
            await repo.upsert(source_path, parser=parser, strategy=strategy, task_id=task_id)
            await session.commit()
    asyncio.run(_inner())


def _db_mark_processing(source_path: str) -> None:
    async def _inner():
        from db.engine import get_session_factory
        async with get_session_factory()() as session:
            from db.repositories.document import DocumentRepository
            repo = DocumentRepository(session)
            await repo.mark_processing(source_path)
            await session.commit()
    asyncio.run(_inner())


def _db_mark_indexed(source_path: str, chunk_count: int) -> None:
    async def _inner():
        from db.engine import get_session_factory
        async with get_session_factory()() as session:
            from db.repositories.document import DocumentRepository
            repo = DocumentRepository(session)
            await repo.mark_indexed(source_path, chunk_count)
            await session.commit()
    asyncio.run(_inner())


def _db_mark_error(source_path: str, error_message: str) -> None:
    async def _inner():
        from db.engine import get_session_factory
        async with get_session_factory()() as session:
            from db.repositories.document import DocumentRepository
            repo = DocumentRepository(session)
            await repo.mark_error(source_path, error_message)
            await session.commit()
    asyncio.run(_inner())


# ── Utilitaires ────────────────────────────────────────────────────────────────

def _download_to_tmp(object_key: str, suffix: str) -> Path:
    """Télécharge l'objet depuis le DocumentStore vers un fichier temporaire."""
    from storage import make_document_store
    doc_store = make_document_store()
    content   = doc_store.download(object_key)
    tmp       = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.write(content)
    tmp.close()
    return Path(tmp.name)


def _build_weaviate_store():
    """Crée et connecte un WeaviateStore depuis les variables d'environnement."""
    from rag_agent.config import RAGConfig
    from weaviate_store import WeaviateStore
    cfg   = RAGConfig.from_env()
    store = WeaviateStore(host=cfg.weaviate_host, port=cfg.weaviate_port)
    store.connect()
    return store, cfg


# ── Tâche : ingestion PDF ──────────────────────────────────────────────────────

@celery_app.task(
    name        = "rag.tasks.ingest_pdf",
    queue       = INGEST_QUEUE,
    bind        = True,
    acks_late   = True,
    max_retries = MAX_RETRIES,
    priority    = int(RagCeleryPriority.HIGH),
)
def ingest_pdf_task(
    self: Task,
    object_key: str,
    parser: str    = "docling",
    strategy: str  = "by_token",
    filename: str  = "",
) -> dict:
    """
    Télécharge le PDF depuis le DocumentStore, l'ingère dans Weaviate et met
    à jour le statut DB.

    Paramètres
    ----------
    object_key : clé MinIO/locale du fichier (= valeur stockée dans Weaviate.source)
    parser     : docling | mineru | simple
    strategy   : by_token | by_sentence | by_block
    filename   : nom d'affichage (pour les logs)

    Retourne
    --------
    dict avec {object_key, chunk_count, status}
    """
    _task_logger.info("Début ingestion PDF | task=%s object_key=%s", self.request.id, object_key)

    tmp_path: Path | None = None
    store = None
    try:
        # 1. Marquer PROCESSING en DB
        _db_mark_processing(object_key)

        # 2. Télécharger vers un tmpfile
        tmp_path = _download_to_tmp(object_key, suffix=".pdf")

        # 3. Connexion Weaviate
        store, cfg = _build_weaviate_store()

        # 4. Ingestion
        from ingestor import ingest_pdf as _ingest_pdf
        n = _ingest_pdf(
            pdf_path          = tmp_path,
            weaviate_store    = store,
            openai_key        = cfg.openai_key,
            embedding_model   = cfg.embedding_model,
            chunking_strategy = strategy,
            parser            = parser if parser != "simple" else "docling",
            force_simple      = (parser == "simple"),
            source_override   = object_key,
        )

        # 5. Marquer INDEXED en DB
        _db_mark_indexed(object_key, n)
        _task_logger.info("Ingestion OK | task=%s object_key=%s chunks=%d", self.request.id, object_key, n)

        return {"object_key": object_key, "chunk_count": n, "status": "indexed"}

    except SoftTimeLimitExceeded:
        msg = f"Timeout dépassé pour '{object_key}'"
        _task_logger.error(msg)
        _db_mark_error(object_key, msg)
        raise   # ne pas retenter un timeout

    except Exception as exc:
        retry_in = RETRY_BACKOFF_BASE * (2 ** self.request.retries)
        _task_logger.warning(
            "Erreur ingestion PDF | task=%s attempt=%d/%d : %s — retry dans %ds",
            self.request.id, self.request.retries + 1, MAX_RETRIES, exc, retry_in,
        )
        if self.request.retries >= MAX_RETRIES:
            _db_mark_error(object_key, str(exc))
            raise
        raise self.retry(exc=exc, countdown=retry_in)

    finally:
        if store is not None:
            try:
                store.close()
            except Exception:
                pass
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


# ── Tâche : ingestion JSONL ────────────────────────────────────────────────────

@celery_app.task(
    name        = "rag.tasks.ingest_jsonl",
    queue       = INGEST_QUEUE,
    bind        = True,
    acks_late   = True,
    max_retries = MAX_RETRIES,
    priority    = int(RagCeleryPriority.HIGH),
)
def ingest_jsonl_task(
    self: Task,
    object_key: str,
    source_override: str | None = None,
    filename: str               = "",
) -> dict:
    """
    Télécharge le JSONL depuis le DocumentStore et l'ingère dans Weaviate.

    Paramètres
    ----------
    object_key      : clé MinIO/locale du fichier .jsonl
    source_override : remplace le champ source présent dans le JSONL
    filename        : nom d'affichage
    """
    _task_logger.info("Début ingestion JSONL | task=%s object_key=%s", self.request.id, object_key)

    tmp_path: Path | None = None
    store = None
    try:
        _db_mark_processing(object_key)
        tmp_path = _download_to_tmp(object_key, suffix=".jsonl")
        store, cfg = _build_weaviate_store()

        from ingestor import ingest_jsonl as _ingest_jsonl
        n = _ingest_jsonl(
            jsonl_path      = tmp_path,
            weaviate_store  = store,
            openai_key      = cfg.openai_key,
            embedding_model = cfg.embedding_model,
            source_override = source_override,
        )

        _db_mark_indexed(object_key, n)
        _task_logger.info("Ingestion JSONL OK | task=%s chunks=%d", self.request.id, n)
        return {"object_key": object_key, "chunk_count": n, "status": "indexed"}

    except SoftTimeLimitExceeded:
        msg = f"Timeout dépassé pour '{object_key}'"
        _db_mark_error(object_key, msg)
        raise

    except Exception as exc:
        retry_in = RETRY_BACKOFF_BASE * (2 ** self.request.retries)
        if self.request.retries >= MAX_RETRIES:
            _db_mark_error(object_key, str(exc))
            raise
        raise self.retry(exc=exc, countdown=retry_in)

    finally:
        if store is not None:
            try:
                store.close()
            except Exception:
                pass
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
