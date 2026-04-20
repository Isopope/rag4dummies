"""Router /ingest — ingestion de PDF et JSONL dans Weaviate via Celery."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from loguru import logger

from ..deps import get_celery_app, get_db_session, get_document_store
from ..models import IngestJobResponse
from storage import DocumentStore

router = APIRouter()

_MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB


def _check_file_size(content: bytes, filename: str) -> None:
    if len(content) > _MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Fichier trop volumineux (maximum 100 MB).",
        )


def _check_extension(filename: str, allowed: set[str]) -> None:
    ext = Path(filename).suffix.lower()
    if ext not in allowed:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Extension non supportée '{ext}'. Accepté : {sorted(allowed)}",
        )


# ── POST /ingest/pdf ───────────────────────────────────────────────────────────

@router.post(
    "/pdf",
    response_model=IngestJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingérer un PDF (asynchrone)",
    description=(
        "Upload un fichier PDF, le conserve dans l'object store (MinIO ou local) "
        "et dispatche l'ingestion vers un worker Celery. "
        "La réponse (202 Accepted) contient le ``task_id`` permettant de suivre "
        "la progression via ``GET /jobs/{task_id}``."
    ),
)
async def ingest_pdf(
    file:     UploadFile = File(..., description="Fichier PDF à indexer"),
    parser:   str        = Form("mineru",      description="Parser : docling | mineru | simple"),
    strategy: str        = Form("by_sentence", description="Stratégie de découpage : by_token | by_sentence | by_block"),
    doc_store: DocumentStore = Depends(get_document_store),
    db=Depends(get_db_session),
) -> IngestJobResponse:
    if parser not in ("docling", "mineru", "simple"):
        raise HTTPException(status_code=400, detail="parser doit être : docling | mineru | simple")
    if strategy not in ("by_token", "by_sentence", "by_block"):
        raise HTTPException(status_code=400, detail="strategy doit être : by_token | by_sentence | by_block")

    filename = file.filename or "upload.pdf"
    _check_extension(filename, {".pdf"})
    content = await file.read()
    _check_file_size(content, filename)

    object_key = DocumentStore.make_object_key(filename, content)

    # 1. Upload dans l'object store
    doc_store.upload(content, object_key, content_type="application/pdf")

    # 2. Dispatcher la tâche Celery
    from worker.queues import INGEST_QUEUE, RagCeleryPriority
    celery = get_celery_app()
    job = celery.send_task(
        "rag.tasks.ingest_pdf",
        args     = [object_key, parser, strategy, filename],
        queue    = INGEST_QUEUE,
        priority = int(RagCeleryPriority.HIGH),
    )

    # 3. Enregistrer en DB (PENDING, task_id)
    from db.repositories.document import DocumentRepository
    repo = DocumentRepository(db)
    await repo.upsert(object_key, parser=parser, strategy=strategy, task_id=job.id)
    await db.commit()

    # 4. URL présignée immédiate (disponible dès l'upload)
    expires  = int(os.getenv("MINIO_PRESIGN_EXPIRES", "3600"))
    pdf_url  = doc_store.presigned_url(object_key, expires_seconds=expires)

    logger.info("PDF '{}' dispatché — task_id={}", filename, job.id)
    return IngestJobResponse(
        task_id  = job.id,
        status   = "pending",
        source   = object_key,
        filename = filename,
        pdf_url  = pdf_url,
    )


# ── POST /ingest/jsonl ─────────────────────────────────────────────────────────

@router.post(
    "/jsonl",
    response_model=IngestJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingérer un JSONL pré-chunké (asynchrone)",
    description="Upload un fichier JSONL de chunks pré-découpés et dispatche l'ingestion vers un worker Celery.",
)
async def ingest_jsonl(
    file:            UploadFile = File(..., description="Fichier JSONL à indexer"),
    source_override: str        = Form("", description="Remplace le champ source présent dans le JSONL"),
    doc_store: DocumentStore = Depends(get_document_store),
    db=Depends(get_db_session),
) -> IngestJobResponse:
    filename = file.filename or "upload.jsonl"
    _check_extension(filename, {".jsonl"})
    content = await file.read()
    _check_file_size(content, filename)

    object_key       = DocumentStore.make_object_key(filename, content)
    effective_source = source_override.strip() or None

    doc_store.upload(content, object_key, content_type="application/x-ndjson")

    from worker.queues import INGEST_QUEUE, RagCeleryPriority
    celery = get_celery_app()
    job = celery.send_task(
        "rag.tasks.ingest_jsonl",
        args     = [object_key, effective_source, filename],
        queue    = INGEST_QUEUE,
        priority = int(RagCeleryPriority.HIGH),
    )

    from db.repositories.document import DocumentRepository
    repo = DocumentRepository(db)
    await repo.upsert(object_key, task_id=job.id)
    await db.commit()

    logger.info("JSONL '{}' dispatché — task_id={}", filename, job.id)
    return IngestJobResponse(
        task_id  = job.id,
        status   = "pending",
        source   = object_key,
        filename = filename,
    )


