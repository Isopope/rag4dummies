"""Repository Conversation + Message.

Principe : une conversation n'est créée que lorsqu'un utilisateur
soumet un feedback (rating ± commentaire) sur une réponse LLM.
La méthode centrale est ``save_feedback``.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.conversation import Conversation
from ..models.message import ROLE_ASSISTANT, ROLE_USER, Message


class ConversationRepository:
    """CRUD pour les conversations notées et leurs messages."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Création ───────────────────────────────────────────────────────────────

    async def save_feedback(
        self,
        *,
        question: str,
        answer: str,
        rating: int,
        comment: str | None = None,
        user_id: str = "anonymous",
        question_id: str | None = None,
        title: str | None = None,
        sources: list[dict[str, Any]] | None = None,
        decision_log: list[dict[str, Any]] | None = None,
        follow_up_suggestions: list[str] | None = None,
        n_retrieved: int = 0,
        usage: dict[str, Any] | None = None,
    ) -> tuple[Conversation, Message]:
        """Crée atomiquement une conversation + 2 messages avec feedback.

        Returns
        -------
        tuple[Conversation, Message]
            La conversation créée et le message assistant portant le feedback.
        """
        conv = Conversation(
            user_id     = user_id,
            title       = title,
            question_id = question_id,
        )
        self._session.add(conv)
        await self._session.flush()  # obtient conv.id avant d'insérer les messages

        # Message utilisateur (question)
        user_msg = Message(
            conversation_id = conv.id,
            role            = ROLE_USER,
            content         = question,
        )

        # Métadonnées pipeline sérialisées
        metadata = {
            "decision_log":          decision_log or [],
            "follow_up_suggestions": follow_up_suggestions or [],
            "n_retrieved":           n_retrieved,
        }
        if usage is not None:
            metadata["usage"] = usage

        # Message assistant (réponse LLM + feedback)
        asst_msg = Message(
            conversation_id = conv.id,
            role            = ROLE_ASSISTANT,
            content         = answer,
            rating          = rating,
            comment         = comment,
            sources_json    = json.dumps(sources or [], ensure_ascii=False),
            metadata_json   = json.dumps(metadata, ensure_ascii=False),
        )

        self._session.add_all([user_msg, asst_msg])
        await self._session.flush()
        await self._session.refresh(conv)
        return conv, asst_msg

    # ── Lecture ────────────────────────────────────────────────────────────────

    async def get(self, conversation_id: uuid.UUID) -> Conversation | None:
        """Retourne une conversation par son id (avec messages eager-loaded)."""
        result = await self._session.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        return result.scalar_one_or_none()

    async def list_by_user(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Conversation]:
        """Liste les conversations notées d'un utilisateur (tri antichronologique)."""
        result = await self._session.execute(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def list_all(
        self,
        limit: int = 50,
        offset: int = 0,
        min_rating: int | None = None,
    ) -> list[Conversation]:
        """Liste toutes les conversations (admin), avec filtre optionnel par note minimale."""
        stmt = (
            select(Conversation)
            .order_by(Conversation.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if min_rating is not None:
            # Filtre via une sous-requête sur les messages assistant notés
            from sqlalchemy import exists
            stmt = stmt.where(
                exists(
                    select(Message.id)
                    .where(Message.conversation_id == Conversation.id)
                    .where(Message.role == ROLE_ASSISTANT)
                    .where(Message.rating >= min_rating)
                )
            )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    # ── Sessions (création + turns) ────────────────────────────────────────────

    async def create_session(
        self,
        user_id: str = "anonymous",
        title: str | None = None,
    ) -> Conversation:
        """Crée une nouvelle session de chat vide."""
        conv = Conversation(user_id=user_id, title=title)
        self._session.add(conv)
        await self._session.flush()
        await self._session.refresh(conv)
        return conv

    async def append_turn(
        self,
        *,
        session_id: str,
        question: str,
        answer: str,
        sources: list[dict[str, Any]] | None = None,
        follow_up_suggestions: list[str] | None = None,
        n_retrieved: int = 0,
        question_id: str | None = None,
        title: str | None = None,
        usage: dict[str, Any] | None = None,
    ) -> tuple[Message, Message] | None:
        """Ajoute un tour (question + réponse) à une session existante.

        Met à jour le titre si la session n'en a pas encore.
        Retourne None si session_id invalide ou introuvable.
        """
        try:
            conv_uuid = uuid.UUID(session_id)
        except ValueError:
            return None

        result = await self._session.execute(
            select(Conversation).where(Conversation.id == conv_uuid)
        )
        conv = result.scalar_one_or_none()
        if conv is None:
            return None

        # Ne remplace le titre que si la session n'en a pas encore
        if title and not conv.title:
            conv.title = title

        user_msg = Message(
            conversation_id=conv.id,
            role=ROLE_USER,
            content=question,
        )

        metadata = {
            "follow_up_suggestions": follow_up_suggestions or [],
            "n_retrieved":           n_retrieved,
        }
        if usage is not None:
            metadata["usage"] = usage

        asst_msg = Message(
            conversation_id=conv.id,
            role=ROLE_ASSISTANT,
            content=answer,
            sources_json=json.dumps(sources or [], ensure_ascii=False),
            metadata_json=json.dumps(metadata, ensure_ascii=False),
        )

        self._session.add_all([user_msg, asst_msg])
        await self._session.flush()
        return user_msg, asst_msg

    async def update_title(self, session_id: str, title: str) -> bool:
        """Met à jour le titre d'une session (force, même si déjà défini)."""
        try:
            conv_uuid = uuid.UUID(session_id)
        except ValueError:
            return False
        result = await self._session.execute(
            select(Conversation).where(Conversation.id == conv_uuid)
        )
        conv = result.scalar_one_or_none()
        if conv is None:
            return False
        conv.title = title
        return True

    # ── Suppression ────────────────────────────────────────────────────────────

    async def delete(self, conversation_id: uuid.UUID) -> bool:
        """Supprime une conversation et ses messages (cascade)."""
        conv = await self.get(conversation_id)
        if conv is None:
            return False
        await self._session.delete(conv)
        return True
