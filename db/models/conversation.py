"""Modèle Conversation — créé uniquement quand l'utilisateur note une réponse."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .message import Message


class Conversation(Base):
    """Représente un échange question/réponse noté par l'utilisateur.

    Une conversation n'est créée que lorsque l'utilisateur soumet un feedback
    (rating + commentaire optionnel) depuis l'UI. Elle contient deux messages :
    le message user (question) et le message assistant (réponse LLM).
    """
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    # Identité appelant — chaîne libre, pas de FK sur users pour rester souple
    user_id: Mapped[str] = mapped_column(
        String(255), default="anonymous", index=True
    )
    # Titre court généré par le pipeline RAG (generate_title)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # UUID de la requête RAG d'origine (question_id dans UnifiedRAGState)
    question_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ── Relations ──────────────────────────────────────────────────────────────
    messages: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<Conversation id={self.id} user={self.user_id!r} "
            f"title={self.title!r}>"
        )
