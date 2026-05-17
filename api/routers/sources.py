"""Router /sources — gestion des documents indexés dans Weaviate."""
from __future__ import annotations

import urllib.parse
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_admin_user
from ..deps import get_document_store, get_db_session, get_store, reset_agent
from ..document_cleanup import delete_tracked_document, find_tracked_source_for_indexed_source
from ..models import SourceItem, SourcesResponse
from db.models.user import User

router = APIRouter()


# ── GET /sources ───────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=SourcesResponse,
    summary="Lister les sources indexées",
)
async def list_sources(store=Depends(get_store), _: User = Depends(current_admin_user)) -> SourcesResponse:
    """Retourne la liste des documents indexés et le nombre de chunks par document."""
    try:
        raw = store.list_sources()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    items: list[SourceItem] = []
    for s in raw:
        try:
            n = store.count(s)
        except Exception:
            n = 0
        items.append(SourceItem(source=s, name=Path(s).name, n_chunks=n))

    try:
        total = store.count()
    except Exception:
        total = sum(i.n_chunks for i in items)

    return SourcesResponse(sources=items, total_chunks=total)


# ── DELETE /sources ────────────────────────────────────────────────────────────

@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Vider toute la base (reset)",
    description="⚠️ Supprime les chunks Weaviate ainsi que les documents suivis et leurs fichiers stockés. Irréversible.",
)
async def reset_sources(
    store=Depends(get_store),
    doc_store=Depends(get_document_store),
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(current_admin_user),
) -> None:
    try:
        repo = DocumentRepository(db)
        tracked_sources = await repo.list_source_paths()
        for source_path in tracked_sources:
            await delete_tracked_document(
                source_path,
                repo=repo,
                db_session=db,
                doc_store=doc_store,
                weaviate_store=store,
                require_db_record=False,
            )

        if store.count() > 0:
            store.reset_collection()

        reset_agent()  # force la recréation de l'agent qui tient un ref au store
        logger.warning("Base documents/chunks vidée via DELETE /sources.")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── DELETE /sources/{encoded_source} ──────────────────────────────────────────

@router.delete(
    "/{encoded_source:path}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Supprimer un document",
    description="Supprime les chunks d'une source et, si elle est suivie en base, le document et son fichier stocké. L'identifiant est le chemin source encodé en URL.",
)
async def delete_source(
    encoded_source: str,
    store=Depends(get_store),
    doc_store=Depends(get_document_store),
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(current_admin_user),
) -> None:
    source = urllib.parse.unquote(encoded_source)
    if not source:
        raise HTTPException(status_code=400, detail="Identifiant source vide.")

    from db.repositories.document import DocumentRepository

    try:
        repo = DocumentRepository(db)
        tracked_source = await find_tracked_source_for_indexed_source(
            source,
            repo=repo,
            doc_store=doc_store,
        )

        if tracked_source is None:
            deleted_chunks = int(store.delete_source(source) or 0)
            logger.info("Source '{}' supprimée via API (chunks={}, non suivie en DB).", source, deleted_chunks)
            return

        result = await delete_tracked_document(
            tracked_source,
            repo=repo,
            db_session=db,
            doc_store=doc_store,
            weaviate_store=store,
            require_db_record=False,
        )
        logger.info(
            "Source '{}' supprimée via API (tracked_source='{}', chunks={}).",
            source,
            tracked_source,
            result.deleted_chunks,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
