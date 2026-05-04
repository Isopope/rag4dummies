"""Router /feedback — sauvegarde des réponses LLM notées par l'utilisateur.

Une conversation n'est persistée en base que lorsque l'utilisateur
soumet explicitement un rating (et optionnellement un commentaire) depuis l'UI.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import FeedbackRequest, FeedbackResponse, ConversationItem
from db import get_db_session
from db.repositories import ConversationRepository

router = APIRouter()


# ── POST /feedback ─────────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Soumettre un feedback",
    description=(
        "Enregistre une réponse LLM notée par l'utilisateur. "
        "Crée une conversation + 2 messages (question / réponse) en base."
    ),
)
async def submit_feedback(
    body: FeedbackRequest,
    session: AsyncSession = Depends(get_db_session),
) -> FeedbackResponse:
    repo = ConversationRepository(session)
    try:
        conv, asst_msg = await repo.save_feedback(
            question              = body.question,
            answer                = body.answer,
            rating                = body.rating,
            comment               = body.comment,
            user_id               = body.user_id,
            question_id           = body.question_id,
            title                 = body.conversation_title,
            sources               = [s.model_dump() for s in body.sources],
            decision_log          = body.decision_log,
            follow_up_suggestions = body.follow_up_suggestions,
            n_retrieved           = body.n_retrieved,
            usage                 = body.usage.model_dump() if body.usage is not None else None,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return FeedbackResponse(
        conversation_id = str(conv.id),
        message_id      = str(asst_msg.id),
        rating          = asst_msg.rating,
        comment         = asst_msg.comment,
    )


# ── GET /feedback ──────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=list[ConversationItem],
    summary="Lister les conversations notées",
    description="Retourne les conversations ayant reçu un feedback, triées antichronologiquement.",
)
async def list_feedback(
    user_id:    str        = Query("anonymous", description="Filtrer par utilisateur"),
    min_rating: int | None = Query(None, ge=1, le=5, description="Note minimale"),
    limit:      int        = Query(20, ge=1, le=100),
    offset:     int        = Query(0, ge=0),
    session: AsyncSession  = Depends(get_db_session),
) -> list[ConversationItem]:
    repo = ConversationRepository(session)
    convs = await repo.list_all(limit=limit, offset=offset, min_rating=min_rating)
    # Filtrage user_id si différent de "all"
    if user_id != "all":
        convs = [c for c in convs if c.user_id == user_id]

    return [
        ConversationItem(
            conversation_id = str(c.id),
            user_id         = c.user_id,
            title           = c.title,
            question_id     = c.question_id,
            created_at      = c.created_at.isoformat(),
            message_count   = len(c.messages),
        )
        for c in convs
    ]


# ── GET /feedback/{conversation_id} ───────────────────────────────────────────

@router.get(
    "/{conversation_id}",
    response_model=ConversationItem,
    summary="Détail d'une conversation notée",
)
async def get_feedback(
    conversation_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> ConversationItem:
    try:
        cid = uuid.UUID(conversation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="conversation_id invalide (UUID attendu).")

    repo = ConversationRepository(session)
    conv = await repo.get(cid)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation introuvable.")

    return ConversationItem(
        conversation_id = str(conv.id),
        user_id         = conv.user_id,
        title           = conv.title,
        question_id     = conv.question_id,
        created_at      = conv.created_at.isoformat(),
        message_count   = len(conv.messages),
    )
