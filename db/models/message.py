"""Modèle Message — une paire (question utilisateur / réponse LLM) notée."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .conversation import Conversation

# Rôles valides (alignés sur l'API OpenAI)
ROLE_USER      = "user"
ROLE_ASSISTANT = "assistant"


class Message(Base):
    """Représente un message dans une conversation notée.

    Chaque conversation sauvegardée contient exactement deux messages :
    - role='user'      → la question posée au pipeline RAG
    - role='assistant' → la réponse LLM, enrichie du feedback utilisateur

    Le feedback (rating + comment) n'est pertinent que sur les messages
    de type 'assistant'. Les champs sources_json et metadata_json sérialisent
    les données structurées du pipeline (chunks rerankés, decision_log, etc.).
    """
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text)

    # ── Feedback (uniquement sur role='assistant') ─────────────────────────────
    rating: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="Note de 1 à 5 attribuée par l'utilisateur (None = non noté)",
    )
    comment: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Commentaire libre de l'utilisateur sur la réponse LLM",
    )

    # ── Métadonnées pipeline RAG (JSON sérialisé) ─────────────────────────────
    sources_json: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="JSON : liste des chunks rerankés ayant servi à la réponse",
    )
    metadata_json: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="JSON : decision_log, follow_up_suggestions, n_retrieved, etc.",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # ── Relations ──────────────────────────────────────────────────────────────
    conversation: Mapped["Conversation"] = relationship(
        "Conversation", back_populates="messages"
    )

    def __repr__(self) -> str:
        rating_str = f" rating={self.rating}" if self.rating is not None else ""
        return (
            f"<Message id={self.id} role={self.role!r}"
            f"{rating_str} conv={self.conversation_id}>"
        )
