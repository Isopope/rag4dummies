"""Router /sessions — CRUD des sessions de chat.

Une session est créée automatiquement par le pipeline de streaming
(POST /query/stream) à chaque nouveau thread de conversation.
Ce router expose la liste, la consultation, le renommage et la suppression.
"""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    RenameSessionRequest,
    SessionDetail,
    SessionItem,
    SessionMessageItem,
    ChunkModel,
    TokenUsageSummary,
)
from ..auth import current_active_user
from db import get_db_session
from db.models.user import User
from db.repositories import ConversationRepository

router = APIRouter()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_sources(sources_json: str | None) -> list[ChunkModel]:
    """Désérialise sources_json → list[ChunkModel], silencieux en cas d'erreur."""
    if not sources_json:
        return []
    try:
        raw = json.loads(sources_json)
        result = []
        for s in raw:
            if isinstance(s, dict):
                try:
                    result.append(ChunkModel(**s))
                except Exception:
                    pass
        return result
    except Exception:
        return []


def _conv_to_item(conv) -> SessionItem:
    """Mappe une Conversation SQLAlchemy vers SessionItem (vue liste)."""
    # Dernier message utilisateur comme aperçu
    last_msg: str | None = None
    for msg in reversed(conv.messages):
        if msg.role == "user":
            last_msg = msg.content[:100]
            break

    return SessionItem(
        id=str(conv.id),
        title=conv.title,
        created_at=conv.created_at.isoformat(),
        updated_at=conv.updated_at.isoformat(),
        message_count=len(conv.messages),
        last_message=last_msg,
    )


def _conv_to_detail(conv) -> SessionDetail:
    """Mappe une Conversation SQLAlchemy vers SessionDetail (vue complète)."""
    messages = []
    for m in conv.messages:
        meta = {}
        usage = None
        try:
            meta = json.loads(m.metadata_json or "{}")
            raw_usage = meta.get("usage")
            if isinstance(raw_usage, dict):
                usage = TokenUsageSummary(**raw_usage)
        except Exception:
            pass
        messages.append(
            SessionMessageItem(
                id=str(m.id),
                role=m.role,
                content=m.content,
                sources=_load_sources(m.sources_json),
                follow_up_suggestions=meta.get("follow_up_suggestions", []),
                usage=usage,
                created_at=m.created_at.isoformat(),
            )
        )
    return SessionDetail(
        id=str(conv.id),
        title=conv.title,
        created_at=conv.created_at.isoformat(),
        updated_at=conv.updated_at.isoformat(),
        messages=messages,
    )


# ── GET /sessions ──────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=list[SessionItem],
    summary="Lister les sessions",
    description="Retourne les sessions de chat de l'utilisateur connecté, triées antichronologiquement.",
)
async def list_sessions(
    limit:   int = Query(50, ge=1, le=200),
    offset:  int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    user:    User = Depends(current_active_user),
) -> list[SessionItem]:
    repo  = ConversationRepository(session)
    convs = await repo.list_by_user(user_id=str(user.id), limit=limit, offset=offset)
    return [_conv_to_item(c) for c in convs]


# ── GET /sessions/{session_id} ─────────────────────────────────────────────────

@router.get(
    "/{session_id}",
    response_model=SessionDetail,
    summary="Charger une session",
    description="Retourne une session complète avec tous ses messages.",
)
async def get_session(
    session_id: str,
    session: AsyncSession = Depends(get_db_session),
    user:    User = Depends(current_active_user),
) -> SessionDetail:
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="session_id invalide")

    repo = ConversationRepository(session)
    conv = await repo.get(sid)
    if conv is None:
        raise HTTPException(status_code=404, detail="Session introuvable")
    if conv.user_id != str(user.id):
        raise HTTPException(status_code=403, detail="Accès refusé")

    return _conv_to_detail(conv)


# ── DELETE /sessions/{session_id} ─────────────────────────────────────────────

@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Supprimer une session",
)
async def delete_session(
    session_id: str,
    session: AsyncSession = Depends(get_db_session),
    user:    User = Depends(current_active_user),
) -> None:
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="session_id invalide")

    repo = ConversationRepository(session)
    conv = await repo.get(sid)
    if conv is None:
        raise HTTPException(status_code=404, detail="Session introuvable")
    if conv.user_id != str(user.id):
        raise HTTPException(status_code=403, detail="Accès refusé")

    deleted = await repo.delete(sid)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session introuvable")


# ── PATCH /sessions/{session_id} ──────────────────────────────────────────────

@router.patch(
    "/{session_id}",
    response_model=SessionItem,
    summary="Renommer une session",
)
async def rename_session(
    session_id: str,
    body: RenameSessionRequest,
    session: AsyncSession = Depends(get_db_session),
    user:    User = Depends(current_active_user),
) -> SessionItem:
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="session_id invalide")

    repo = ConversationRepository(session)
    conv = await repo.get(sid)
    if conv is None:
        raise HTTPException(status_code=404, detail="Session introuvable")
    if conv.user_id != str(user.id):
        raise HTTPException(status_code=403, detail="Accès refusé")

    ok = await repo.update_title(session_id, body.title)
    if not ok:
        raise HTTPException(status_code=404, detail="Session introuvable")

    conv = await repo.get(sid)
    return _conv_to_item(conv)
