"""Router /sources — gestion des documents indexés dans Weaviate."""
from __future__ import annotations

import urllib.parse
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger

from ..auth import current_admin_user
from ..deps import get_store, reset_agent
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
    description="⚠️ Supprime **tous** les chunks Weaviate. Irréversible.",
)
async def reset_sources(store=Depends(get_store), _: User = Depends(current_admin_user)) -> None:
    try:
        store.reset_collection()
        reset_agent()  # force la recréation de l'agent qui tient un ref au store
        logger.warning("Collection Weaviate vidée via DELETE /sources.")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── DELETE /sources/{encoded_source} ──────────────────────────────────────────

@router.delete(
    "/{encoded_source:path}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Supprimer un document",
    description="Supprime tous les chunks d'un document. L'identifiant est le chemin source encodé en URL.",
)
async def delete_source(encoded_source: str, store=Depends(get_store), _: User = Depends(current_admin_user)) -> None:
    source = urllib.parse.unquote(encoded_source)
    if not source:
        raise HTTPException(status_code=400, detail="Identifiant source vide.")
    try:
        store.delete_source(source)
        logger.info("Source '{}' supprimée via API.", source)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
