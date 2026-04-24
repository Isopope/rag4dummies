"""
Tâches Celery de crawl / découverte de documents depuis des sources externes.

Trois connecteurs, tous appuyés sur openingestion.fetcher :
- crawl_local_task   → LocalFileFetcher  (répertoire local / NFS / monture)
- crawl_web_task     → WebFetcher        (Playwright → PDF)
- crawl_sharepoint_task → SharepointFetcher (Graph API)

Flux commun pour chaque FetchedDocument découvert :
  1. Vérifie si le document est déjà INDEXED en DB → skip si oui
  2. Lit le contenu du fichier téléchargé par le fetcher
  3. Upload dans le DocumentStore (MinIO ou local)
  4. Upsert en DB (PENDING, task_id=None pour l'instant)
  5. Dispatche ingest_pdf_task → worker lourd fait le reste

Les tâches connecteurs s'exécutent sur la queue LIGHT (légère) car leur
travail propre est I/O bound ; l'ingestion lourde reste sur INGEST.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

# Garantit que la racine du projet est dans sys.path
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from celery.utils.log import get_task_logger

from worker.app import celery_app
from worker.queues import INGEST_QUEUE, LIGHT_QUEUE, RagCeleryPriority

_logger = get_task_logger(__name__)

# Extensions PDF/document acceptées par défaut pour le crawl local
_DEFAULT_EXT = [".pdf"]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _is_already_indexed(source_path: str) -> bool:
    """Retourne True si le document est déjà INDEXED en base."""
    async def _inner() -> bool:
        from db.engine import get_session_factory
        from db.models.document import DocumentStatus
        from db.repositories.document import DocumentRepository
        async with get_session_factory()() as session:
            repo = DocumentRepository(session)
            doc  = await repo.get_by_source(source_path)
            return doc is not None and doc.status == DocumentStatus.INDEXED
    return asyncio.run(_inner())


def _db_upsert_pending(source_path: str, parser: str, strategy: str) -> None:
    async def _inner() -> None:
        from db.engine import get_session_factory
        from db.repositories.document import DocumentRepository
        async with get_session_factory()() as session:
            repo = DocumentRepository(session)
            await repo.upsert(source_path, parser=parser, strategy=strategy)
            await session.commit()
    asyncio.run(_inner())


def _dispatch_ingest(object_key: str, parser: str, strategy: str, filename: str) -> str:
    """Dispatche ingest_pdf_task et met à jour task_id en DB. Retourne le task_id."""
    from worker.tasks.ingest import ingest_pdf_task

    job = ingest_pdf_task.apply_async(
        args     = [object_key, parser, strategy, filename],
        queue    = INGEST_QUEUE,
        priority = int(RagCeleryPriority.MEDIUM),
    )

    # Met à jour task_id en DB
    async def _set_task_id() -> None:
        from db.engine import get_session_factory
        from db.repositories.document import DocumentRepository
        async with get_session_factory()() as session:
            repo = DocumentRepository(session)
            doc  = await repo.get_by_source(object_key)
            if doc:
                doc.task_id = job.id
            await session.commit()
    asyncio.run(_set_task_id())

    return job.id


def _upload_and_dispatch(
    doc_path: Path,
    source_label: str,
    parser: str,
    strategy: str,
) -> dict[str, str] | None:
    """
    Upload un FetchedDocument.path dans le DocumentStore et dispatche l'ingestion.

    Retourne {"object_key": ..., "task_id": ...} ou None si déjà indexé / erreur.
    """
    from storage import make_document_store

    if not doc_path.exists():
        _logger.warning("Fichier introuvable, ignoré : %s", doc_path)
        return None

    content    = doc_path.read_bytes()
    doc_store  = make_document_store()
    object_key = doc_store.make_object_key(doc_path.name, content)

    # Skip si déjà INDEXED
    if _is_already_indexed(object_key):
        _logger.debug("Déjà indexé, ignoré : %s", object_key)
        return None

    # Upload
    suffix     = doc_path.suffix.lower()
    mime       = "application/pdf" if suffix == ".pdf" else "application/octet-stream"
    doc_store.upload(content, object_key, content_type=mime)

    # DB + dispatch
    _db_upsert_pending(object_key, parser, strategy)
    task_id = _dispatch_ingest(object_key, parser, strategy, doc_path.name)

    _logger.info("Dispatché : %s → task_id=%s", object_key, task_id)
    return {"object_key": object_key, "task_id": task_id, "source_label": source_label}


# ── Tâche : crawl dossier local ────────────────────────────────────────────────

@celery_app.task(
    name      = "rag.tasks.crawl_local",
    queue     = LIGHT_QUEUE,
    bind      = True,
    acks_late = True,
)
def crawl_local_task(
    self,
    directory: str,
    ext: list[str]   = _DEFAULT_EXT,
    recursive: bool  = True,
    parser: str      = "docling",
    strategy: str    = "by_token",
) -> dict[str, Any]:
    """
    Scanne un répertoire local et dispatche l'ingestion des fichiers nouveaux.

    Paramètres
    ----------
    directory : chemin absolu du répertoire à scanner
    ext       : extensions acceptées (ex. [".pdf", ".docx"])
    recursive : descendre dans les sous-répertoires
    parser    : docling | mineru | simple
    strategy  : by_token | by_sentence | by_block
    """
    from openingestion.fetcher.local import LocalFileFetcher

    _logger.info("crawl_local_task | dir=%s ext=%s", directory, ext)

    fetcher = LocalFileFetcher(ext=ext, recursive=recursive)
    try:
        docs = fetcher(dir=directory)
    except (ValueError, FileNotFoundError) as exc:
        _logger.error("crawl_local_task : %s", exc)
        return {"error": str(exc), "dispatched": 0}

    results   = []
    skipped   = 0
    for doc in docs:
        if doc.path is None:
            continue
        r = _upload_and_dispatch(Path(doc.path), str(doc.source), parser, strategy)
        if r:
            results.append(r)
        else:
            skipped += 1

    _logger.info(
        "crawl_local_task terminé | dispatched=%d skipped=%d", len(results), skipped
    )
    return {"dispatched": len(results), "skipped": skipped, "tasks": results}


# ── Tâche : crawl web ──────────────────────────────────────────────────────────

@celery_app.task(
    name      = "rag.tasks.crawl_web",
    queue     = LIGHT_QUEUE,
    bind      = True,
    acks_late = True,
    time_limit = 300,   # 5 min max pour Playwright
)
def crawl_web_task(
    self,
    urls: list[str],
    output_dir: str  = "./tmp/web_fetch",
    mode: str        = "pdf",
    parser: str      = "docling",
    strategy: str    = "by_token",
) -> dict[str, Any]:
    """
    Récupère des pages web via Playwright (rendu → PDF) et dispatche l'ingestion.

    Paramètres
    ----------
    urls       : liste d'URLs à crawler
    output_dir : répertoire de sortie temporaire pour les PDFs générés
    mode       : pdf | html
    parser     : docling | mineru | simple
    strategy   : by_token | by_sentence | by_block
    """
    from openingestion.fetcher.web import WebFetcher

    _logger.info("crawl_web_task | %d URL(s)", len(urls))

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    fetcher = WebFetcher(output_dir=output_dir, mode=mode, headless=True)

    try:
        docs = fetcher(urls=urls)
    except Exception as exc:
        _logger.error("crawl_web_task : %s", exc)
        return {"error": str(exc), "dispatched": 0}

    results = []
    skipped = 0
    for doc in docs:
        if doc.path is None:
            continue
        r = _upload_and_dispatch(Path(doc.path), str(doc.source), parser, strategy)
        if r:
            results.append(r)
        else:
            skipped += 1

    _logger.info(
        "crawl_web_task terminé | dispatched=%d skipped=%d", len(results), skipped
    )
    return {"dispatched": len(results), "skipped": skipped, "tasks": results}


# ── Tâche : crawl SharePoint ───────────────────────────────────────────────────

@celery_app.task(
    name      = "rag.tasks.crawl_sharepoint",
    queue     = LIGHT_QUEUE,
    bind      = True,
    acks_late = True,
)
def crawl_sharepoint_task(
    self,
    site_url: str    | None = None,
    site_name: str   | None = None,
    folder_path: str | None = None,
    output_dir: str         = "./tmp/sharepoint_fetch",
    parser: str             = "docling",
    strategy: str           = "by_token",
    # Credentials — priorité : paramètre > variable d'environnement
    client_id: str     | None = None,
    client_secret: str | None = None,
    tenant_id: str     | None = None,
) -> dict[str, Any]:
    """
    Synchronise les documents d'un site SharePoint / OneDrive et dispatche l'ingestion.

    Authentification : App Registration Entra ID avec Files.Read.All.
    Les credentials peuvent être passés en paramètre ou via les variables
    d'environnement SHAREPOINT_CLIENT_ID / SHAREPOINT_CLIENT_SECRET / SHAREPOINT_TENANT_ID.

    Paramètres
    ----------
    site_url    : URL complète du site (ex. https://tenant.sharepoint.com/sites/MonSite)
    site_name   : Nom court du site (alternatif à site_url)
    folder_path : Sous-dossier à indexer (None = racine)
    output_dir  : Répertoire de téléchargement temporaire
    parser / strategy : transmis à ingest_pdf_task
    """
    from openingestion.fetcher.sharepoint import SharepointFetcher

    _cid    = client_id     or os.getenv("SHAREPOINT_CLIENT_ID")
    _csec   = client_secret or os.getenv("SHAREPOINT_CLIENT_SECRET")
    _tid    = tenant_id     or os.getenv("SHAREPOINT_TENANT_ID")

    if not all([_cid, _csec, _tid]):
        msg = (
            "Credentials SharePoint manquants. "
            "Définissez SHAREPOINT_CLIENT_ID, SHAREPOINT_CLIENT_SECRET, SHAREPOINT_TENANT_ID."
        )
        _logger.error(msg)
        return {"error": msg, "dispatched": 0}

    if not site_url and not site_name:
        return {"error": "site_url ou site_name requis", "dispatched": 0}

    _logger.info("crawl_sharepoint_task | site=%s folder=%s", site_url or site_name, folder_path)

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    fetcher = SharepointFetcher(
        client_id     = _cid,
        client_secret = _csec,
        tenant_id     = _tid,
        output_dir    = output_dir,
    )

    try:
        docs = fetcher(site_url=site_url, site_name=site_name, folder_path=folder_path)
    except Exception as exc:
        _logger.error("crawl_sharepoint_task : %s", exc)
        return {"error": str(exc), "dispatched": 0}

    results = []
    skipped = 0
    for doc in docs:
        if doc.path is None:
            continue
        r = _upload_and_dispatch(Path(doc.path), str(doc.source), parser, strategy)
        if r:
            results.append(r)
        else:
            skipped += 1

    _logger.info(
        "crawl_sharepoint_task terminé | dispatched=%d skipped=%d", len(results), skipped
    )
    return {"dispatched": len(results), "skipped": skipped, "tasks": results}
