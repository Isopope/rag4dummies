"""Router /ingest — ingestion de PDF et JSONL dans Weaviate via Celery."""
from __future__ import annotations

import mimetypes
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from ..auth import current_admin_user
from db.models.user import User

from loguru import logger

from ..deps import get_celery_app, get_db_session, get_document_store
from ..models import IngestJobResponse
from storage import DocumentStore

router = APIRouter()

_MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB
_SUPPORTED_DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".pptx", ".txt"}


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


def _guess_content_type(filename: str) -> str:
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


def _check_parser_support_for_file(parser: str, filename: str) -> None:
    if parser == "simple" and Path(filename).suffix.lower() != ".pdf":
        raise HTTPException(
            status_code=400,
            detail="Le parser simple n'est supporté que pour les fichiers PDF.",
        )


async def _submit_document_ingest(
    *,
    file: UploadFile,
    parser: str,
    strategy: str,
    entity: str | None,
    validity_date: str | None,
    doc_store: DocumentStore,
    db,
    allowed_extensions: set[str],
    default_filename: str,
) -> IngestJobResponse:
    if parser not in ("docling", "mineru", "simple"):
        raise HTTPException(status_code=400, detail="parser doit être : docling | mineru | simple")
    if strategy not in ("by_token", "by_sentence", "by_block"):
        raise HTTPException(status_code=400, detail="strategy doit être : by_token | by_sentence | by_block")
    if validity_date:
        import re
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", validity_date):
            raise HTTPException(status_code=400, detail="validity_date doit être au format YYYY-MM-DD")

    filename = file.filename or default_filename
    _check_extension(filename, allowed_extensions)
    _check_parser_support_for_file(parser, filename)
    content = await file.read()
    _check_file_size(content, filename)

    object_key = DocumentStore.make_object_key(filename, content)

    # 1. Upload dans l'object store
    doc_store.upload(content, object_key, content_type=_guess_content_type(filename))

    task_id = str(uuid.uuid4())

    # 2. Enregistrer en DB avant dispatch pour éviter une course avec le worker
    from db.repositories.document import DocumentRepository
    repo = DocumentRepository(db)
    await repo.upsert(
        object_key,
        parser=parser,
        strategy=strategy,
        task_id=task_id,
        entity=entity,
        validity_date=validity_date,
    )
    await db.commit()

    # 3. Dispatcher la tâche Celery avec l'id déjà persisté en DB
    from worker.queues import INGEST_QUEUE, RagCeleryPriority
    celery = get_celery_app()
    try:
        celery.send_task(
            "rag.tasks.ingest_pdf",
            args=[object_key, parser, strategy, filename],
            kwargs={"entity": entity, "validity_date": validity_date},
            task_id=task_id,
            queue=INGEST_QUEUE,
            priority=int(RagCeleryPriority.HIGH),
        )
    except Exception as exc:
        await repo.mark_error(object_key, f"Dispatch Celery échoué : {exc}")
        await db.commit()
        logger.exception("Dispatch Celery échoué pour '{}'", filename)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Impossible de planifier l'ingestion.",
        )

    expires = int(os.getenv("MINIO_PRESIGN_EXPIRES", "3600"))
    file_url = doc_store.presigned_url(object_key, expires_seconds=expires)

    logger.info("Document '{}' dispatché — task_id={}", filename, task_id)
    return IngestJobResponse(
        task_id=task_id,
        status="pending",
        source=object_key,
        filename=filename,
        pdf_url=file_url,
    )


@router.post(
    "/file",
    response_model=IngestJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingérer un document (asynchrone)",
    description=(
        "Upload un document (PDF, DOCX, PPTX, TXT), le conserve dans l'object store "
        "et dispatche l'ingestion vers un worker Celery. "
        "La réponse (202 Accepted) contient le ``task_id`` permettant de suivre "
        "la progression via ``GET /jobs/{task_id}``."
    ),
)
async def ingest_file(
    file: UploadFile = File(..., description="Fichier à indexer (.pdf, .docx, .pptx, .txt)"),
    parser: str = Form("docling", description="Parser : docling | mineru | simple"),
    strategy: str = Form("by_sentence", description="Stratégie de découpage : by_token | by_sentence | by_block"),
    entity: str | None = Form(None, description="Entité propriétaire (ex. 'dassault', 'thales')"),
    validity_date: str | None = Form(None, description="Date de validité ISO YYYY-MM-DD"),
    doc_store: DocumentStore = Depends(get_document_store),
    db=Depends(get_db_session),
    _: User = Depends(current_admin_user),
) -> IngestJobResponse:
    return await _submit_document_ingest(
        file=file,
        parser=parser,
        strategy=strategy,
        entity=entity,
        validity_date=validity_date,
        doc_store=doc_store,
        db=db,
        allowed_extensions=_SUPPORTED_DOCUMENT_EXTENSIONS,
        default_filename="upload.pdf",
    )


# ── POST /ingest/pdf ───────────────────────────────────────────────────────────

@router.post(
    "/pdf",
    response_model=IngestJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingérer un PDF (asynchrone)",
    description=(
        "Alias rétrocompatible pour l'ingestion de PDFs. "
        "Pour les autres formats, utiliser ``POST /ingest/file``."
    ),
)
async def ingest_pdf(
    file:     UploadFile = File(..., description="Fichier PDF à indexer"),
    parser:   str        = Form("mineru",      description="Parser : docling | mineru | simple"),
    strategy: str        = Form("by_sentence", description="Stratégie de découpage : by_token | by_sentence | by_block"),
    entity:   str | None = Form(None,          description="Entité propriétaire (ex. 'dassault', 'thales')"),
    validity_date: str | None = Form(None,     description="Date de validité ISO YYYY-MM-DD"),
    doc_store: DocumentStore = Depends(get_document_store),
    db=Depends(get_db_session),
    _: User = Depends(current_admin_user),  # admin uniquement
) -> IngestJobResponse:
    return await _submit_document_ingest(
        file=file,
        parser=parser,
        strategy=strategy,
        entity=entity,
        validity_date=validity_date,
        doc_store=doc_store,
        db=db,
        allowed_extensions={".pdf"},
        default_filename="upload.pdf",
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
    _: User = Depends(current_admin_user),  # admin uniquement
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
