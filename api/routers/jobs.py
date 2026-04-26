"""Router /jobs — suivi de l'état des tâches d'ingestion Celery."""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, status

from ..auth import current_admin_user
from ..deps import get_db_session, get_document_store
from ..models import JobStatusResponse
from db.models.user import User

router = APIRouter()


@router.get(
    "/{task_id}",
    response_model=JobStatusResponse,
    summary="État d'une tâche d'ingestion",
    description=(
        "Retourne l'état courant d'une tâche d'ingestion identifiée par son ``task_id`` "
        "(retourné par ``POST /ingest/pdf`` ou ``POST /ingest/jsonl``). "
        "Consulte à la fois Celery (état temps-réel) et la base de données (statut persistant)."
    ),
)
async def get_job_status(
    task_id: str,
    db=Depends(get_db_session),
    doc_store=Depends(get_document_store),
    _: User = Depends(current_admin_user),
) -> JobStatusResponse:
    # ── 1. État Celery (temps réel) ────────────────────────────────────────────
    from worker.app import celery_app
    celery_result = celery_app.AsyncResult(task_id)
    celery_state  = celery_result.state  # PENDING | STARTED | SUCCESS | FAILURE | RETRY

    # ── 2. Statut DB (persistant) ──────────────────────────────────────────────
    from db.repositories.document import DocumentRepository
    repo = DocumentRepository(db)
    doc  = await repo.get_by_task_id(task_id)

    if doc is None:
        # La tâche Celery existe (au moins dans le broker) mais pas encore en DB
        # (peut arriver dans les premières millisecondes après le dispatch)
        if celery_state == "PENDING":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tâche '{task_id}' introuvable.",
            )
        return JobStatusResponse(
            task_id      = task_id,
            celery_state = celery_state,
            status       = "unknown",
        )

    # ── 3. URL présignée (uniquement si indexé) ────────────────────────────────
    from db.models.document import DocumentStatus
    pdf_url: str | None = None
    if doc.status == DocumentStatus.INDEXED:
        expires = int(os.getenv("MINIO_PRESIGN_EXPIRES", "3600"))
        try:
            pdf_url = doc_store.presigned_url(doc.source_path, expires_seconds=expires)
        except Exception:
            pdf_url = None

    return JobStatusResponse(
        task_id      = task_id,
        celery_state = celery_state,
        status       = doc.status,
        source       = doc.source_path,
        filename     = doc.filename,
        chunk_count  = doc.chunk_count,
        pdf_url      = pdf_url,
        error        = doc.error_message,
    )
