"""Router /ingest — ingestion de PDF et JSONL dans Weaviate."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from loguru import logger

from ..deps import get_config, get_store
from ..models import IngestResponse

router = APIRouter()

_THREAD_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="rag-ingest")

UPLOADS_DIR   = Path(__file__).parent.parent.parent / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)

_MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB
_ALLOWED_EXTENSIONS = {".pdf", ".jsonl"}


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
    description="Upload un fichier PDF, l'analyse, embed les chunks via OpenAI et les stocke dans Weaviate.",
)
async def ingest_pdf(
    file:     UploadFile = File(..., description="Fichier PDF à indexer"),
    parser:   str        = Form("docling",  description="Parser : docling | mineru | simple"),
    strategy: str        = Form("by_token", description="Stratégie de découpage : by_token | by_sentence | by_block"),
    store=Depends(get_store),
    cfg=Depends(get_config),
) -> IngestResponse:
    if parser not in ("docling", "mineru", "simple"):
        raise HTTPException(status_code=400, detail="parser doit être : docling | mineru | simple")
    if strategy not in ("by_token", "by_sentence", "by_block"):
        raise HTTPException(status_code=400, detail="strategy doit être : by_token | by_sentence | by_block")

    filename = file.filename or "upload.pdf"
    _check_extension(filename, {".pdf"})
    content = await file.read()
    _check_file_size(content, filename)

    dest = UPLOADS_DIR / filename
    dest.write_bytes(content)

    loop = asyncio.get_event_loop()
    try:
        n = await loop.run_in_executor(
            _THREAD_POOL,
            lambda: _run_ingest_pdf(dest, store, cfg, parser, strategy),
        )
    except Exception as exc:
        logger.exception("Erreur ingestion PDF '{}' : {}", filename, exc)
        raise HTTPException(status_code=500, detail=str(exc))

    return IngestResponse(n_chunks=n, source=str(dest), filename=filename)


def _run_ingest_pdf(dest: Path, store, cfg, parser: str, strategy: str) -> int:
    from ingestor import ingest_pdf as _ingest_pdf
    return _ingest_pdf(
        pdf_path         = dest,
        weaviate_store   = store,
        openai_key       = cfg.openai_key,
        embedding_model  = cfg.embedding_model,
        chunking_strategy= strategy,
        parser           = parser if parser != "simple" else "docling",
        force_simple     = (parser == "simple"),
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

    dest = UPLOADS_DIR / filename
    dest.write_bytes(content)

    loop = asyncio.get_event_loop()
    try:
        n = await loop.run_in_executor(
            _THREAD_POOL,
            lambda: _run_ingest_jsonl(dest, store, cfg, source_override.strip() or None),
        )
    except Exception as exc:
        logger.exception("Erreur ingestion JSONL '{}' : {}", filename, exc)
        raise HTTPException(status_code=500, detail=str(exc))

    return IngestResponse(n_chunks=n, source=str(dest), filename=filename)


def _run_ingest_jsonl(dest: Path, store, cfg, source_override: str | None) -> int:
    from ingestor import ingest_jsonl as _ingest_jsonl
    return _ingest_jsonl(
        jsonl_path      = dest,
        weaviate_store  = store,
        openai_key      = cfg.openai_key,
        embedding_model = cfg.embedding_model,
        source_override = source_override,
    )
