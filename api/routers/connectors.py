"""
Router /connectors — déclenchement des crawls depuis des sources externes.

Trois endpoints (POST, 202 Accepted) :
  POST /connectors/local        — scan d'un répertoire local / NFS
  POST /connectors/web          — crawl de pages web via Playwright
  POST /connectors/sharepoint   — synchronisation SharePoint / OneDrive

Chaque endpoint :
1. Valide la requête (Pydantic)
2. Dispatche la tâche de crawl sur la queue LIGHT
3. Retourne immédiatement un CrawlJobResponse avec le crawl_task_id

Le crawl_task_id peut être suivi via GET /jobs/{crawl_task_id}
(retourne l'état Celery de la tâche de crawl elle-même).
Chaque document découvert génère ensuite son propre task_id d'ingestion
(visible dans le résultat Celery SUCCESS de la tâche de crawl).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from ..deps import get_celery_app
from ..models import (
    CrawlJobResponse,
    CrawlLocalRequest,
    CrawlSharepointRequest,
    CrawlWebRequest,
)

router = APIRouter()


# ── POST /connectors/local ─────────────────────────────────────────────────────

@router.post(
    "/local",
    response_model=CrawlJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Scanner un répertoire local",
    description=(
        "Dispatche un crawl sur un répertoire local (ou monture NFS/CIFS). "
        "Les fichiers nouveaux ou modifiés sont uploadés dans le DocumentStore "
        "et une tâche d'ingestion est créée pour chacun. "
        "Les fichiers déjà indexés sont ignorés automatiquement."
    ),
)
async def crawl_local(body: CrawlLocalRequest) -> CrawlJobResponse:
    if body.parser not in ("docling", "mineru", "simple"):
        raise HTTPException(status_code=400, detail="parser doit être : docling | mineru | simple")
    if body.strategy not in ("by_token", "by_sentence", "by_block"):
        raise HTTPException(status_code=400, detail="strategy doit être : by_token | by_sentence | by_block")

    from worker.queues import LIGHT_QUEUE, RagCeleryPriority

    job = get_celery_app().send_task(
        "rag.tasks.crawl_local",
        kwargs   = {
            "directory": body.directory,
            "ext":       body.ext,
            "recursive": body.recursive,
            "parser":    body.parser,
            "strategy":  body.strategy,
        },
        queue    = LIGHT_QUEUE,
        priority = int(RagCeleryPriority.MEDIUM),
    )

    return CrawlJobResponse(
        crawl_task_id = job.id,
        connector     = "local",
        message       = f"Scan de '{body.directory}' lancé ({', '.join(body.ext)})",
    )


# ── POST /connectors/web ───────────────────────────────────────────────────────

@router.post(
    "/web",
    response_model=CrawlJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Crawler des pages web",
    description=(
        "Récupère des pages web via Playwright (rendu → PDF) et dispatche leur ingestion. "
        "Nécessite que Playwright soit installé dans l'environnement du worker "
        "(``playwright install chromium``)."
    ),
)
async def crawl_web(body: CrawlWebRequest) -> CrawlJobResponse:
    if not body.urls:
        raise HTTPException(status_code=400, detail="La liste d'URLs ne peut pas être vide.")
    if body.mode not in ("pdf", "html"):
        raise HTTPException(status_code=400, detail="mode doit être : pdf | html")
    if body.parser not in ("docling", "mineru", "simple"):
        raise HTTPException(status_code=400, detail="parser doit être : docling | mineru | simple")
    if body.strategy not in ("by_token", "by_sentence", "by_block"):
        raise HTTPException(status_code=400, detail="strategy doit être : by_token | by_sentence | by_block")

    from worker.queues import LIGHT_QUEUE, RagCeleryPriority

    job = get_celery_app().send_task(
        "rag.tasks.crawl_web",
        kwargs   = {
            "urls":       body.urls,
            "output_dir": body.output_dir,
            "mode":       body.mode,
            "parser":     body.parser,
            "strategy":   body.strategy,
        },
        queue    = LIGHT_QUEUE,
        priority = int(RagCeleryPriority.MEDIUM),
    )

    short_urls = body.urls[:3]
    suffix     = f" (+ {len(body.urls) - 3} autres)" if len(body.urls) > 3 else ""
    return CrawlJobResponse(
        crawl_task_id = job.id,
        connector     = "web",
        message       = f"Crawl de {len(body.urls)} URL(s) lancé : {short_urls}{suffix}",
    )


# ── POST /connectors/sharepoint ────────────────────────────────────────────────

@router.post(
    "/sharepoint",
    response_model=CrawlJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Synchroniser un site SharePoint / OneDrive",
    description=(
        "Télécharge les documents d'un site SharePoint via Microsoft Graph API "
        "et dispatche leur ingestion. "
        "Requiert une App Registration Entra ID avec ``Files.Read.All``. "
        "Les credentials peuvent être passés dans le corps ou définis via les variables "
        "d'environnement ``SHAREPOINT_CLIENT_ID``, ``SHAREPOINT_CLIENT_SECRET``, ``SHAREPOINT_TENANT_ID``."
    ),
)
async def crawl_sharepoint(body: CrawlSharepointRequest) -> CrawlJobResponse:
    if not body.site_url and not body.site_name:
        raise HTTPException(
            status_code=400,
            detail="site_url ou site_name est requis.",
        )
    if body.parser not in ("docling", "mineru", "simple"):
        raise HTTPException(status_code=400, detail="parser doit être : docling | mineru | simple")
    if body.strategy not in ("by_token", "by_sentence", "by_block"):
        raise HTTPException(status_code=400, detail="strategy doit être : by_token | by_sentence | by_block")

    from worker.queues import LIGHT_QUEUE, RagCeleryPriority

    job = get_celery_app().send_task(
        "rag.tasks.crawl_sharepoint",
        kwargs   = {
            "site_url":     body.site_url,
            "site_name":    body.site_name,
            "folder_path":  body.folder_path,
            "output_dir":   body.output_dir,
            "parser":       body.parser,
            "strategy":     body.strategy,
            "client_id":    body.client_id,
            "client_secret":body.client_secret,
            "tenant_id":    body.tenant_id,
        },
        queue    = LIGHT_QUEUE,
        priority = int(RagCeleryPriority.MEDIUM),
    )

    site = body.site_url or body.site_name
    folder = f" → {body.folder_path}" if body.folder_path else " (racine)"
    return CrawlJobResponse(
        crawl_task_id = job.id,
        connector     = "sharepoint",
        message       = f"Sync SharePoint '{site}'{folder} lancée",
    )
