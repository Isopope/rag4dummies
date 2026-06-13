"""Router /connectors/configs — sources de connecteurs synchronisées périodiquement.

CRUD admin des sources planifiées (SharePoint) + déclenchement manuel « Sync now ».
La tâche beat ``dispatch_due_connector_syncs`` re-synchronise automatiquement
chaque source selon sa cadence (``interval_seconds``).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_admin_user
from ..deps import get_celery_app
from ..models import (
    ConnectorConfigRequest,
    ConnectorConfigResponse,
    ConnectorConfigUpdate,
    CrawlJobResponse,
)
from db import get_db_session
from db.models.user import User
from db.repositories import ConnectorConfigRepository

router = APIRouter()

_VALID_PARSERS = ("docling", "mineru", "simple")
_VALID_STRATEGIES = ("by_token", "by_sentence", "by_block")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _to_response(cfg) -> ConnectorConfigResponse:
    try:
        params = json.loads(cfg.config_json or "{}")
    except json.JSONDecodeError:
        params = {}
    return ConnectorConfigResponse(
        id=str(cfg.id),
        name=cfg.name,
        connector_type=cfg.connector_type,
        enabled=cfg.enabled,
        site_url=params.get("site_url"),
        site_name=params.get("site_name"),
        folder_path=params.get("folder_path"),
        parser=cfg.parser,
        strategy=cfg.strategy,
        entity=cfg.entity,
        prune=cfg.prune,
        interval_seconds=cfg.interval_seconds,
        last_sync_at=cfg.last_sync_at.isoformat() if cfg.last_sync_at else None,
        last_task_id=cfg.last_task_id,
        last_status=cfg.last_status,
        created_at=cfg.created_at.isoformat(),
    )


def _validate(parser: str | None, strategy: str | None) -> None:
    if parser is not None and parser not in _VALID_PARSERS:
        raise HTTPException(status_code=400, detail="parser doit être : docling | mineru | simple")
    if strategy is not None and strategy not in _VALID_STRATEGIES:
        raise HTTPException(status_code=400, detail="strategy doit être : by_token | by_sentence | by_block")


def _parse_uuid(config_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(config_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="id invalide")


def _dispatch_sharepoint_sync(cfg) -> str:
    """Dispatche la sync delta SharePoint pour une config. Retourne le task_id."""
    from worker.queues import LIGHT_QUEUE, RagCeleryPriority
    try:
        params = json.loads(cfg.config_json or "{}")
    except json.JSONDecodeError:
        params = {}
    job = get_celery_app().send_task(
        "rag.tasks.sync_sharepoint",
        kwargs={
            "site_url":    params.get("site_url"),
            "site_name":   params.get("site_name"),
            "folder_path": params.get("folder_path"),
            "parser":      cfg.parser,
            "strategy":    cfg.strategy,
            "entity":      cfg.entity,
            "prune":       cfg.prune,
        },
        queue=LIGHT_QUEUE,
        priority=int(RagCeleryPriority.MEDIUM),
    )
    return job.id


# ── POST /connectors/configs ─────────────────────────────────────────────────

@router.post("", response_model=ConnectorConfigResponse, status_code=status.HTTP_201_CREATED,
             summary="Créer une source planifiée")
async def create_config(
    body: ConnectorConfigRequest,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(current_admin_user),
) -> ConnectorConfigResponse:
    if body.connector_type != "sharepoint":
        raise HTTPException(status_code=400, detail="Seul connector_type='sharepoint' est planifiable pour l'instant.")
    if not body.site_url and not body.site_name:
        raise HTTPException(status_code=400, detail="site_url ou site_name est requis.")
    _validate(body.parser, body.strategy)

    config_json = json.dumps({
        "site_url": body.site_url,
        "site_name": body.site_name,
        "folder_path": body.folder_path,
    })
    repo = ConnectorConfigRepository(session)
    cfg = await repo.create(
        name=body.name,
        connector_type=body.connector_type,
        enabled=body.enabled,
        config_json=config_json,
        parser=body.parser,
        strategy=body.strategy,
        entity=body.entity,
        prune=body.prune,
        interval_seconds=body.interval_seconds,
    )
    await session.commit()
    return _to_response(cfg)


# ── GET /connectors/configs ──────────────────────────────────────────────────

@router.get("", response_model=list[ConnectorConfigResponse], summary="Lister les sources planifiées")
async def list_configs(
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(current_admin_user),
) -> list[ConnectorConfigResponse]:
    repo = ConnectorConfigRepository(session)
    return [_to_response(c) for c in await repo.list_all()]


# ── PATCH /connectors/configs/{id} ────────────────────────────────────────────

@router.patch("/{config_id}", response_model=ConnectorConfigResponse, summary="Modifier une source planifiée")
async def update_config(
    config_id: str,
    body: ConnectorConfigUpdate,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(current_admin_user),
) -> ConnectorConfigResponse:
    _validate(body.parser, body.strategy)
    repo = ConnectorConfigRepository(session)
    cfg = await repo.get(_parse_uuid(config_id))
    if cfg is None:
        raise HTTPException(status_code=404, detail="Source introuvable")

    # Recompose config_json si un paramètre source change
    if any(v is not None for v in (body.site_url, body.site_name, body.folder_path)):
        try:
            current = json.loads(cfg.config_json or "{}")
        except json.JSONDecodeError:
            current = {}
        for key in ("site_url", "site_name", "folder_path"):
            val = getattr(body, key)
            if val is not None:
                current[key] = val
        cfg.config_json = json.dumps(current)

    await repo.update(
        cfg.id,
        name=body.name,
        parser=body.parser,
        strategy=body.strategy,
        entity=body.entity,
        prune=body.prune,
        interval_seconds=body.interval_seconds,
        enabled=body.enabled,
    )
    await session.commit()
    cfg = await repo.get(_parse_uuid(config_id))
    return _to_response(cfg)


# ── DELETE /connectors/configs/{id} ───────────────────────────────────────────

@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Supprimer une source planifiée")
async def delete_config(
    config_id: str,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(current_admin_user),
) -> None:
    repo = ConnectorConfigRepository(session)
    ok = await repo.delete(_parse_uuid(config_id))
    if not ok:
        raise HTTPException(status_code=404, detail="Source introuvable")


# ── POST /connectors/configs/{id}/run ─────────────────────────────────────────

@router.post("/{config_id}/run", response_model=CrawlJobResponse, status_code=status.HTTP_202_ACCEPTED,
             summary="Synchroniser maintenant (Sync now)")
async def run_config(
    config_id: str,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(current_admin_user),
) -> CrawlJobResponse:
    repo = ConnectorConfigRepository(session)
    cfg = await repo.get(_parse_uuid(config_id))
    if cfg is None:
        raise HTTPException(status_code=404, detail="Source introuvable")

    task_id = _dispatch_sharepoint_sync(cfg)
    await repo.mark_dispatched(cfg.id, task_id, datetime.now(timezone.utc), status="queued")
    await session.commit()

    return CrawlJobResponse(
        crawl_task_id=task_id,
        connector="sharepoint",
        message=f"Sync immédiate de '{cfg.name}' lancée",
    )
