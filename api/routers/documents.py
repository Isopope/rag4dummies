"""Router /documents — récupération de fichiers (fallback local si pas de MinIO).

En mode LocalDocumentStore, ce router sert les PDFs directement depuis ./uploads/.
En mode MinioDocumentStore, ce router génère une presigned URL et redirige vers MinIO
(le frontend peut aussi utiliser directement la pdf_url reçue dans /query).
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, RedirectResponse
from loguru import logger

from ..deps import get_document_store
from storage import LocalDocumentStore

router = APIRouter()


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
