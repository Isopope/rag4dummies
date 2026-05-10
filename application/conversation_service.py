"""Service applicatif de persistance conversationnelle."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from db.repositories import ConversationRepository


class ConversationService:
    """Facade metier pour les operations de session/conversation."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = ConversationRepository(session)

    async def save_stream_turn(
        self,
        *,
        requested_session_id: str | None,
        user_id: str,
        question: str,
        answer: str,
        sources: list[dict[str, Any]],
        follow_up_suggestions: list[str],
        question_id: str | None,
        title: str | None,
        usage: dict[str, Any] | None,
    ) -> str:
        """Persiste un tour stream et retourne l'identifiant de session retenu."""

        saved_session_id = requested_session_id
        if saved_session_id:
            try:
                existing = await self._repo.get(uuid.UUID(saved_session_id))
            except ValueError:
                existing = None
            if existing is None or existing.user_id != user_id:
                saved_session_id = None

        if not saved_session_id:
            conv = await self._repo.create_session(user_id=user_id, title=title)
            saved_session_id = str(conv.id)

        await self._repo.append_turn(
            session_id=saved_session_id,
            question=question,
            answer=answer,
            sources=sources,
            follow_up_suggestions=follow_up_suggestions,
            n_retrieved=len(sources),
            question_id=question_id,
            title=title,
            usage=usage,
        )
        await self._session.commit()
        return saved_session_id
