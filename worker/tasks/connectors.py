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

import hashlib
import os
import sys
from pathlib import Path
from typing import Any

# Garantit que la racine du projet est dans sys.path
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from celery.utils.log import get_task_logger

from worker.asyncio_runner import run_async
from worker.app import celery_app
from worker.queues import INGEST_QUEUE, LIGHT_QUEUE, RagCeleryPriority

_logger = get_task_logger(__name__)

# Extensions document acceptées par défaut pour le crawl local
_DEFAULT_EXT = [".pdf", ".docx", ".pptx", ".txt"]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _indexed_content_hash(source_path: str) -> str | None:
    """Retourne le content_hash du doc s'il est déjà INDEXED, sinon None."""
    async def _inner() -> str | None:
        from db.engine import get_session_factory
        from db.models.document import DocumentStatus
        from db.repositories.document import DocumentRepository
        async with get_session_factory()() as session:
            repo = DocumentRepository(session)
            doc  = await repo.get_by_source(source_path)
            if doc is not None and doc.status == DocumentStatus.INDEXED:
                return doc.content_hash
            return None
    return run_async(_inner())


def _doc_sync_state(source_path: str) -> dict | None:
    """Retourne {status, source_updated_at} du doc, ou None s'il n'existe pas."""
    async def _inner() -> dict | None:
        from db.engine import get_session_factory
        from db.repositories.document import DocumentRepository
        async with get_session_factory()() as session:
            repo = DocumentRepository(session)
            doc = await repo.get_by_source(source_path)
            if doc is None:
                return None
            return {"status": doc.status, "source_updated_at": doc.source_updated_at}
    return run_async(_inner())


def _bump_source_updated_at(source_path: str, source_updated_at) -> None:
    """Met à jour source_updated_at sans rien réingérer (cas contenu inchangé)."""
    async def _inner() -> None:
        from db.engine import get_session_factory
        from db.repositories.document import DocumentRepository
        async with get_session_factory()() as session:
            repo = DocumentRepository(session)
            doc = await repo.get_by_source(source_path)
            if doc is not None and source_updated_at is not None:
                doc.source_updated_at = source_updated_at
                await session.commit()
    run_async(_inner())


def _db_upsert_pending(
    source_path: str,
    parser: str,
    strategy: str,
    *,
    object_key: str,
    content_hash: str,
    source_scope: str | None = None,
    filename: str | None = None,
    entity: str | None = None,
    validity_date: str | None = None,
    source_updated_at=None,
) -> None:
    async def _inner() -> None:
        from db.engine import get_session_factory
        from db.repositories.document import DocumentRepository
        async with get_session_factory()() as session:
            repo = DocumentRepository(session)
            await repo.upsert(
                source_path,
                parser=parser,
                strategy=strategy,
                object_key=object_key,
                content_hash=content_hash,
                source_scope=source_scope,
                filename=filename,
                entity=entity,
                validity_date=validity_date,
                source_updated_at=source_updated_at,
            )
            await session.commit()
    run_async(_inner())


def _dispatch_ingest(
    object_key: str,
    parser: str,
    strategy: str,
    filename: str,
    source: str,
    entity: str | None = None,
    validity_date: str | None = None,
) -> str:
    """Dispatche ingest_pdf_task et met à jour task_id en DB. Retourne le task_id.

    ``object_key`` = pointeur de stockage (download) ; ``source`` = identité stable
    (clé DB + champ Weaviate).
    """
    from worker.tasks.ingest import ingest_pdf_task

    job = ingest_pdf_task.apply_async(
        args     = [object_key, parser, strategy, filename, entity, validity_date],
        kwargs   = {"source": source},
        queue    = INGEST_QUEUE,
        priority = int(RagCeleryPriority.MEDIUM),
    )

    # Met à jour task_id en DB (clé = identité stable)
    async def _set_task_id() -> None:
        from db.engine import get_session_factory
        from db.repositories.document import DocumentRepository
        async with get_session_factory()() as session:
            repo = DocumentRepository(session)
            doc  = await repo.get_by_source(source)
            if doc:
                doc.task_id = job.id
            await session.commit()
    run_async(_set_task_id())

    return job.id


def _upload_and_dispatch(
    doc_path: Path,
    source_label: str,
    parser: str,
    strategy: str,
    *,
    source_scope: str | None = None,
    entity: str | None = None,
    validity_date: str | None = None,
    source_updated_at=None,
) -> dict[str, Any]:
    """
    Upload un FetchedDocument.path dans le DocumentStore et dispatche l'ingestion.

    Identité = ``source_label`` (chemin/URL stable) ; stockage = object_key adressé
    par contenu ; détection de changement via content_hash.

    Retourne un dict ``{"status": ...}`` :
      - status="dispatched" + object_key/task_id
      - status="skipped"   (déjà indexé, contenu inchangé)
      - status="missing"   (fichier introuvable)
    Le champ ``source`` est toujours présent (pour le discovered-set du pruning).
    """
    from storage import make_document_store

    if not doc_path.exists():
        _logger.warning("Fichier introuvable, ignoré : %s", doc_path)
        return {"status": "missing", "source": source_label}

    content      = doc_path.read_bytes()
    content_hash = hashlib.sha256(content).hexdigest()

    # Skip si déjà INDEXED avec le même contenu (dédoublonnage par identité + hash)
    if _indexed_content_hash(source_label) == content_hash:
        _logger.debug("Inchangé, ignoré : %s", source_label)
        return {"status": "skipped", "source": source_label}

    doc_store  = make_document_store()
    object_key = doc_store.make_object_key(doc_path.name, content)

    suffix = doc_path.suffix.lower()
    mime   = "application/pdf" if suffix == ".pdf" else "application/octet-stream"
    doc_store.upload(content, object_key, content_type=mime)

    _db_upsert_pending(
        source_label,
        parser,
        strategy,
        object_key=object_key,
        content_hash=content_hash,
        source_scope=source_scope,
        filename=doc_path.name,
        entity=entity,
        validity_date=validity_date,
        source_updated_at=source_updated_at,
    )
    task_id = _dispatch_ingest(
        object_key,
        parser,
        strategy,
        doc_path.name,
        source=source_label,
        entity=entity,
        validity_date=validity_date,
    )

    _logger.info("Dispatché : %s (object_key=%s) → task_id=%s", source_label, object_key, task_id)
    return {
        "status": "dispatched",
        "object_key": object_key,
        "task_id": task_id,
        "source": source_label,
    }


def _process_fetched_docs(
    docs,
    parser: str,
    strategy: str,
    *,
    source_scope: str | None = None,
    entity: str | None = None,
    validity_date: str | None = None,
) -> dict[str, Any]:
    """Boucle commune : upload+dispatch chaque doc, collecte résultats/skip/erreurs.

    Construit aussi le ``discovered`` set (toutes les identités vues, pour le
    pruning). Une erreur sur un document ne fait pas échouer le crawl entier ;
    elle est collectée dans ``errors``.
    """
    results: list[dict] = []
    skipped = 0
    errors: list[dict] = []
    discovered: set[str] = set()
    for doc in docs:
        if doc.path is None:
            continue
        src = str(doc.source)
        discovered.add(src)
        try:
            r = _upload_and_dispatch(
                Path(doc.path),
                src,
                parser,
                strategy,
                source_scope=source_scope,
                entity=entity,
                validity_date=validity_date,
            )
        except Exception as exc:  # échec par document → on continue
            _logger.error("Échec dispatch %s : %s", src, exc)
            errors.append({"source": src, "error": str(exc)})
            continue
        if r.get("status") == "dispatched":
            results.append(r)
        else:
            skipped += 1
    return {"results": results, "skipped": skipped, "errors": errors, "discovered": discovered}


def _prune_scope(source_scope: str, discovered: set[str]) -> list[str]:
    """Supprime les documents INDEXED du scope absents du discovered-set.

    Réutilise ``delete_tracked_document`` (Weaviate + object store + DB).
    Retourne la liste des identités supprimées.
    """
    from worker.tasks.ingest import _build_weaviate_store

    async def _inner() -> list[str]:
        from api.document_cleanup import delete_tracked_document
        from db.engine import get_session_factory
        from db.repositories.document import DocumentRepository
        from storage import make_document_store

        factory = get_session_factory()
        async with factory() as session:
            repo = DocumentRepository(session)
            indexed = await repo.list_indexed_by_scope(source_scope)
            targets = [
                (d.source_path, d.object_key)
                for d in indexed
                if d.source_path not in discovered
            ]
        if not targets:
            return []

        doc_store = make_document_store()
        store, _cfg = _build_weaviate_store()
        deleted: list[str] = []
        try:
            for source_path, object_key in targets:
                handle = object_key or source_path
                try:
                    async with factory() as session:
                        repo = DocumentRepository(session)
                        await delete_tracked_document(
                            handle,
                            repo=repo,
                            db_session=session,
                            doc_store=doc_store,
                            weaviate_store=store,
                            require_db_record=False,
                        )
                    deleted.append(source_path)
                except Exception as exc:
                    _logger.error("Pruning échec pour %s : %s", source_path, exc)
        finally:
            try:
                store.close()
            except Exception:
                pass
        return deleted

    return run_async(_inner())


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
    parser: str      = "mineru",
    strategy: str    = "by_sentence",
    entity: str | None   = None,
    validity_date: str | None = None,
    prune: bool      = False,
) -> dict[str, Any]:
    """
    Scanne un répertoire local et dispatche l'ingestion des fichiers nouveaux/modifiés.

    Paramètres
    ----------
    directory : chemin absolu du répertoire à scanner
    ext       : extensions acceptées (ex. [".pdf", ".docx"])
    recursive : descendre dans les sous-répertoires
    parser    : docling | mineru | simple
    strategy  : by_token | by_sentence | by_block
    prune     : si True, supprime les documents de ce répertoire qui ne sont
                plus présents à la source (détection de suppression).
    """
    from openingestion.fetcher.local import LocalFileFetcher

    _logger.info("crawl_local_task | dir=%s ext=%s prune=%s", directory, ext, prune)

    # Erreur de fetch (répertoire introuvable, etc.) → la tâche échoue (FAILURE).
    fetcher = LocalFileFetcher(ext=ext, recursive=recursive)
    docs = fetcher(dir=directory)

    source_scope = f"local:{os.path.abspath(directory)}"
    summary = _process_fetched_docs(
        docs, parser, strategy,
        source_scope=source_scope, entity=entity, validity_date=validity_date,
    )

    pruned: list[str] = []
    if prune:
        pruned = _prune_scope(source_scope, summary["discovered"])

    _logger.info(
        "crawl_local_task terminé | dispatched=%d skipped=%d errors=%d pruned=%d",
        len(summary["results"]), summary["skipped"], len(summary["errors"]), len(pruned),
    )

    # Échec honnête : si rien n'a été dispatché et que tout a échoué → FAILURE.
    if not summary["results"] and summary["errors"]:
        raise RuntimeError(
            f"crawl_local : {len(summary['errors'])} document(s) en erreur, aucun dispatché."
        )

    return {
        "dispatched": len(summary["results"]),
        "skipped": summary["skipped"],
        "errors": summary["errors"],
        "pruned": pruned,
        "tasks": summary["results"],
    }


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
    parser: str      = "mineru",
    strategy: str    = "by_sentence",
    entity: str | None    = None,
    validity_date: str | None = None,
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

    # Erreur de fetch → la tâche échoue (FAILURE), au lieu de SUCCESS+{error}.
    docs = fetcher(urls=urls)

    # Pas de pruning côté web (pas de sémantique de corpus complet) → scope None.
    summary = _process_fetched_docs(
        docs, parser, strategy,
        source_scope=None, entity=entity, validity_date=validity_date,
    )

    _logger.info(
        "crawl_web_task terminé | dispatched=%d skipped=%d errors=%d",
        len(summary["results"]), summary["skipped"], len(summary["errors"]),
    )

    if not summary["results"] and summary["errors"]:
        raise RuntimeError(
            f"crawl_web : {len(summary['errors'])} URL(s) en erreur, aucune dispatchée."
        )

    return {
        "dispatched": len(summary["results"]),
        "skipped": summary["skipped"],
        "errors": summary["errors"],
        "tasks": summary["results"],
    }


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
    parser: str             = "mineru",
    strategy: str           = "by_sentence",
    entity: str | None      = None,
    validity_date: str | None = None,
    # Credentials — priorité : paramètre > variable d'environnement
    client_id: str     | None = None,
    client_secret: str | None = None,
    tenant_id: str     | None = None,
    prune: bool        = False,
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

    # Erreurs de configuration → la tâche échoue (FAILURE) au lieu de SUCCESS+{error}.
    if not all([_cid, _csec, _tid]):
        raise RuntimeError(
            "Credentials SharePoint manquants. "
            "Définissez SHAREPOINT_CLIENT_ID, SHAREPOINT_CLIENT_SECRET, SHAREPOINT_TENANT_ID."
        )
    if not site_url and not site_name:
        raise RuntimeError("site_url ou site_name requis")

    _logger.info(
        "crawl_sharepoint_task | site=%s folder=%s prune=%s",
        site_url or site_name, folder_path, prune,
    )

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    fetcher = SharepointFetcher(
        client_id     = _cid,
        client_secret = _csec,
        tenant_id     = _tid,
        output_dir    = output_dir,
    )

    # Erreur de fetch → FAILURE.
    docs = fetcher(site_url=site_url, site_name=site_name, folder_path=folder_path)

    source_scope = f"sharepoint:{site_url or site_name}:{folder_path or '/'}"
    summary = _process_fetched_docs(
        docs, parser, strategy,
        source_scope=source_scope, entity=entity, validity_date=validity_date,
    )

    pruned: list[str] = []
    if prune:
        pruned = _prune_scope(source_scope, summary["discovered"])

    _logger.info(
        "crawl_sharepoint_task terminé | dispatched=%d skipped=%d errors=%d pruned=%d",
        len(summary["results"]), summary["skipped"], len(summary["errors"]), len(pruned),
    )

    if not summary["results"] and summary["errors"]:
        raise RuntimeError(
            f"crawl_sharepoint : {len(summary['errors'])} document(s) en erreur, aucun dispatché."
        )

    return {
        "dispatched": len(summary["results"]),
        "skipped": summary["skipped"],
        "errors": summary["errors"],
        "pruned": pruned,
        "tasks": summary["results"],
    }


# ── Tâche : synchronisation delta SharePoint (planifiée) ────────────────────────

@celery_app.task(
    name      = "rag.tasks.sync_sharepoint",
    queue     = LIGHT_QUEUE,
    bind      = True,
    acks_late = True,
)
def sync_sharepoint_task(
    self,
    site_url: str    | None = None,
    site_name: str   | None = None,
    folder_path: str | None = None,
    parser: str      = "mineru",
    strategy: str    = "by_sentence",
    entity: str | None        = None,
    validity_date: str | None = None,
    prune: bool      = True,
) -> dict[str, Any]:
    """Synchronisation **delta** d'une source SharePoint (pour le pull planifié).

    Liste les métadonnées (avec ``lastModifiedDateTime``) et ne télécharge / ré-ingère
    que les items nouveaux ou modifiés ; les inchangés sont ignorés sans download.
    Si ``prune``, supprime les documents du scope absents de la source.
    Credentials lus depuis l'environnement.
    """
    import shutil
    import tempfile

    from db.models.document import DocumentStatus
    from worker.connectors.sharepoint_sync import SharepointGraphClient

    client   = SharepointGraphClient()
    site_id  = client.resolve_site_id(site_url, site_name)
    drive_id = client.default_drive_id(site_id)
    items    = client.list_items(drive_id, folder_path)
    scope    = f"sharepoint:{site_url or site_name}:{folder_path or '/'}"

    _logger.info(
        "sync_sharepoint | site=%s folder=%s items=%d prune=%s",
        site_url or site_name, folder_path, len(items), prune,
    )

    results: list[dict] = []
    skipped = 0
    errors: list[dict] = []
    discovered: set[str] = set()

    for item in items:
        discovered.add(item.web_url)
        try:
            state = _doc_sync_state(item.web_url)
            stored_dt = state["source_updated_at"] if state else None
            need_fetch = (
                state is None
                or state["status"] != DocumentStatus.INDEXED
                or item.last_modified is None
                or stored_dt is None
                or item.last_modified > stored_dt
            )
            if not need_fetch:
                skipped += 1
                continue

            content = client.download_item(drive_id, item.id)
            tmpdir = tempfile.mkdtemp(prefix="sp_sync_")
            try:
                tmp_path = Path(tmpdir) / item.name
                tmp_path.write_bytes(content)
                r = _upload_and_dispatch(
                    tmp_path,
                    item.web_url,
                    parser,
                    strategy,
                    source_scope=scope,
                    entity=entity,
                    validity_date=validity_date,
                    source_updated_at=item.last_modified,
                )
            finally:
                shutil.rmtree(tmpdir, ignore_errors=True)

            if r.get("status") == "dispatched":
                results.append(r)
            else:
                # Contenu identique malgré un timestamp plus récent : on fait
                # converger source_updated_at pour ne pas re-télécharger en boucle.
                skipped += 1
                _bump_source_updated_at(item.web_url, item.last_modified)
        except Exception as exc:
            _logger.error("sync_sharepoint item %s : %s", item.web_url, exc)
            errors.append({"source": item.web_url, "error": str(exc)})

    pruned: list[str] = []
    if prune:
        pruned = _prune_scope(scope, discovered)

    _logger.info(
        "sync_sharepoint terminé | dispatched=%d skipped=%d errors=%d pruned=%d",
        len(results), skipped, len(errors), len(pruned),
    )

    if not results and errors:
        raise RuntimeError(
            f"sync_sharepoint : {len(errors)} item(s) en erreur, aucun dispatché."
        )

    return {
        "dispatched": len(results),
        "skipped": skipped,
        "errors": errors,
        "pruned": pruned,
        "tasks": results,
    }
