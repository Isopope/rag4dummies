"""Router /documents — récupération de fichiers (fallback local si pas de MinIO).

En mode LocalDocumentStore, ce router sert les PDFs directement depuis ./uploads/.
En mode MinioDocumentStore, ce router génère une presigned URL et redirige vers MinIO
(le frontend peut aussi utiliser directement la pdf_url reçue dans /query).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, RedirectResponse
from loguru import logger
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_admin_user
from ..deps import get_document_store, get_db_session
from db.models.user import User
from storage import LocalDocumentStore

router = APIRouter()


# ── Schémas réponse ────────────────────────────────────────────────────────────

class DocumentItemResponse(BaseModel):
    id: str
    filename: str
    source_path: str
    status: str
    chunk_count: int
    parser: Optional[str]
    strategy: Optional[str]
    task_id: Optional[str]
    entity: Optional[str]
    validity_date: Optional[str]
    created_at: str
    ingested_at: Optional[str]
    error_message: Optional[str]


class DocumentListStatsResponse(BaseModel):
    total_documents: int
    indexed_documents: int
    total_chunks: int


class PaginatedDocumentsResponse(BaseModel):
    items: list[DocumentItemResponse]
    total: int
    limit: int
    offset: int
    stats: DocumentListStatsResponse


# ── GET /documents — liste ─────────────────────────────────────────────────────

@router.get(
    "",
    response_model=PaginatedDocumentsResponse,
    summary="Lister les documents ingérés",
    description="Retourne la liste des documents suivis en base, avec leur statut d'ingestion.",
)
async def list_documents(
    status_filter: Optional[str] = Query(None, alias="status", description="Filtrer par statut : pending | processing | indexed | error"),
    limit:  int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(current_admin_user),
) -> PaginatedDocumentsResponse:
    from db.repositories.document import DocumentRepository
    repo = DocumentRepository(db)
    docs = await repo.list_all(status=status_filter, limit=limit, offset=offset)
    total = await repo.count_all(status=status_filter)
    stats = await repo.get_global_stats()

    items = [
        DocumentItemResponse(
            id           = str(doc.id),
            filename     = doc.filename,
            source_path  = doc.source_path,
            status       = doc.status,
            chunk_count  = doc.chunk_count,
            parser       = doc.parser,
            strategy     = doc.strategy,
            task_id      = doc.task_id,
            entity       = doc.entity,
            validity_date = doc.validity_date.isoformat() if doc.validity_date else None,
            created_at   = doc.created_at.isoformat(),
            ingested_at  = doc.ingested_at.isoformat() if doc.ingested_at else None,
            error_message = doc.error_message,
        )
        for doc in docs
    ]
    return PaginatedDocumentsResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        stats=DocumentListStatsResponse(**stats),
    )


# ── DELETE /documents/{object_key} ────────────────────────────────────────────

@router.delete(
    "/{object_key:path}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Supprimer un document",
    description="Supprime le document de l'object store et de la base de données.",
)
async def delete_document(
    object_key: str,
    doc_store=Depends(get_document_store),
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(current_admin_user),
) -> None:
    if not object_key or ".." in object_key or object_key.startswith("/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Clé invalide.")

    from db.repositories.document import DocumentRepository
    repo = DocumentRepository(db)
    deleted_db = await repo.delete_by_source(object_key)
    await db.commit()

    # Suppression dans l'object store (silencieux si absent)
    try:
        doc_store.delete(object_key)
    except Exception as exc:
        logger.warning("Suppression object store échouée pour '{}' : {}", object_key, exc)

    if not deleted_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document '{object_key}' introuvable.")


# ── GET /documents/{object_key} — téléchargement ──────────────────────────────

@router.get(
    "/{object_key:path}",
    summary="Télécharger un document",
    description=(
        "Retourne le fichier PDF identifié par sa clé.\n\n"
        "- **Mode local** : réponse directe (FileResponse).\n"
        "- **Mode MinIO** : redirection HTTP 302 vers la presigned URL MinIO."
    ),
)
async def get_document(
    object_key: str,
    doc_store=Depends(get_document_store),
    _: User = Depends(current_admin_user),
):
    if not object_key or ".." in object_key or object_key.startswith("/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Clé invalide.")

    if isinstance(doc_store, LocalDocumentStore):
        # Mode local — sert le fichier directement
        file_path = doc_store.uploads_dir / object_key
        if not file_path.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Fichier '{object_key}' introuvable.",
            )
        return FileResponse(
            path        = str(file_path),
            media_type  = "application/pdf",
            filename    = Path(object_key).name,
        )

    # Mode MinIO — redirection vers presigned URL
    if not doc_store.exists(object_key):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Objet '{object_key}' introuvable dans le bucket.",
        )
    expires = int(os.getenv("MINIO_PRESIGN_EXPIRES", "3600"))
    url = doc_store.presigned_url(object_key, expires_seconds=expires)
    return RedirectResponse(url=url, status_code=302)
