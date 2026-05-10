"""Router /ingest — ingestion de PDF et JSONL dans Weaviate via Celery."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from application import IngestionService
from ..auth import current_admin_user
from db.models.user import User

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
    entity:   str | None = Form(None,          description="Entité propriétaire (ex. 'dassault', 'thales')"),
    validity_date: str | None = Form(None,     description="Date de validité ISO YYYY-MM-DD"),
    doc_store: DocumentStore = Depends(get_document_store),
    db=Depends(get_db_session),
    _: User = Depends(current_admin_user),  # admin uniquement
) -> IngestJobResponse:
    if parser not in ("docling", "mineru", "simple"):
        raise HTTPException(status_code=400, detail="parser doit être : docling | mineru | simple")
    if strategy not in ("by_token", "by_sentence", "by_block"):
        raise HTTPException(status_code=400, detail="strategy doit être : by_token | by_sentence | by_block")
    if validity_date:
        import re
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", validity_date):
            raise HTTPException(status_code=400, detail="validity_date doit être au format YYYY-MM-DD")

    filename = file.filename or "upload.pdf"
    _check_extension(filename, {".pdf"})
    content = await file.read()
    _check_file_size(content, filename)
    service = IngestionService(db, doc_store, get_celery_app())
    payload = await service.submit_pdf(
        filename=filename,
        content=content,
        parser=parser,
        strategy=strategy,
        entity=entity,
        validity_date=validity_date,
    )
    return IngestJobResponse(**payload)


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
    effective_source = source_override.strip() or None
    service = IngestionService(db, doc_store, get_celery_app())
    payload = await service.submit_jsonl(
        filename=filename,
        content=content,
        source_override=effective_source,
    )
    return IngestJobResponse(**payload)


