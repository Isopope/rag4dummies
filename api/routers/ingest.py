"""Router /ingest — ingestion de PDF et JSONL dans Weaviate."""
from __future__ import annotations

import asyncio
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from loguru import logger

from ..deps import get_config, get_document_store, get_store
from ..models import IngestResponse
from storage import DocumentStore

router = APIRouter()

_THREAD_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="rag-ingest")

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
    response_model=IngestResponse,
    summary="Ingérer un PDF",
    description=(
        "Upload un fichier PDF, l'analyse, embed les chunks via OpenAI et les stocke dans Weaviate. "
        "Le PDF est conservé dans l'object store (MinIO ou local) ; la réponse inclut une ``pdf_url`` "
        "utilisable par le frontend pour le visual grounding."
    ),
)
async def ingest_pdf(
    file:     UploadFile = File(..., description="Fichier PDF à indexer"),
    parser:   str        = Form("docling",  description="Parser : docling | mineru | simple"),
    strategy: str        = Form("by_token", description="Stratégie de découpage : by_token | by_sentence | by_block"),
    store=Depends(get_store),
    cfg=Depends(get_config),
    doc_store: DocumentStore = Depends(get_document_store),
) -> IngestResponse:
    if parser not in ("docling", "mineru", "simple"):
        raise HTTPException(status_code=400, detail="parser doit être : docling | mineru | simple")
    if strategy not in ("by_token", "by_sentence", "by_block"):
        raise HTTPException(status_code=400, detail="strategy doit être : by_token | by_sentence | by_block")

    filename = file.filename or "upload.pdf"
    _check_extension(filename, {".pdf"})
    content = await file.read()
    _check_file_size(content, filename)

    # Clé déterministe : {sha256_8chars}-{nom_safe}.pdf
    object_key = DocumentStore.make_object_key(filename, content)

    # Upload dans l'object store (MinIO ou local)
    doc_store.upload(content, object_key, content_type="application/pdf")

    # L'ingestor a besoin du fichier sur disque pour le parser — tmpfile éphémère
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    loop = asyncio.get_event_loop()
    try:
        n = await loop.run_in_executor(
            _THREAD_POOL,
            lambda: _run_ingest_pdf(tmp_path, store, cfg, parser, strategy, source_override=object_key),
        )
    except Exception as exc:
        logger.exception("Erreur ingestion PDF '{}' : {}", filename, exc)
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    expires = int(os.getenv("MINIO_PRESIGN_EXPIRES", "3600"))
    pdf_url = doc_store.presigned_url(object_key, expires_seconds=expires)

    return IngestResponse(n_chunks=n, source=object_key, filename=filename, pdf_url=pdf_url)


def _run_ingest_pdf(dest: Path, store, cfg, parser: str, strategy: str, source_override: str | None = None) -> int:
    from ingestor import ingest_pdf as _ingest_pdf
    return _ingest_pdf(
        pdf_path          = dest,
        weaviate_store    = store,
        openai_key        = cfg.openai_key,
        embedding_model   = cfg.embedding_model,
        chunking_strategy = strategy,
        parser            = parser if parser != "simple" else "docling",
        force_simple      = (parser == "simple"),
        source_override   = source_override,
    )


# ── POST /ingest/jsonl ─────────────────────────────────────────────────────────

@router.post(
    "/jsonl",
    response_model=IngestResponse,
    summary="Ingérer un JSONL pré-chunké",
    description="Upload un fichier JSONL de chunks pré-découpés et les indexe dans Weaviate.",
)
async def ingest_jsonl(
    file:            UploadFile = File(..., description="Fichier JSONL à indexer"),
    source_override: str        = Form("", description="Remplace le champ source présent dans le JSONL"),
    store=Depends(get_store),
    cfg=Depends(get_config),
) -> IngestResponse:
    filename = file.filename or "upload.jsonl"
    _check_extension(filename, {".jsonl"})
    content = await file.read()
    _check_file_size(content, filename)

    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    loop = asyncio.get_event_loop()
    try:
        n = await loop.run_in_executor(
            _THREAD_POOL,
            lambda: _run_ingest_jsonl(tmp_path, store, cfg, source_override.strip() or None),
        )
    except Exception as exc:
        logger.exception("Erreur ingestion JSONL '{}' : {}", filename, exc)
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    effective_source = source_override.strip() or filename
    return IngestResponse(n_chunks=n, source=effective_source, filename=filename)


def _run_ingest_jsonl(dest: Path, store, cfg, source_override: str | None) -> int:
    from ingestor import ingest_jsonl as _ingest_jsonl
    return _ingest_jsonl(
        jsonl_path      = dest,
        weaviate_store  = store,
        openai_key      = cfg.openai_key,
        embedding_model = cfg.embedding_model,
        source_override = source_override,
    )

