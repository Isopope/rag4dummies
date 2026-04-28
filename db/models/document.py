"""Modèle Document — suivi du statut d'ingestion des fichiers dans Weaviate."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class DocumentStatus:
    PENDING    = "pending"
    PROCESSING = "processing"
    INDEXED    = "indexed"
    ERROR      = "error"


class Document(Base):
    """Représente un document dont l'ingestion est suivie en base.

    Ce modèle reflète l'état d'indexation côté Weaviate :
    - La source de vérité pour les chunks reste Weaviate.
    - Cette table permet de suivre le statut (pending → processing → indexed)
      et de rejouer l'ingestion en cas d'erreur.
    """
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    # Chemin absolu du fichier — clé unique de réconciliation avec Weaviate
    source_path: Mapped[str] = mapped_column(
        String(1000), unique=True, index=True
    )
    filename: Mapped[str] = mapped_column(String(500))

    # Statut d'ingestion
    status: Mapped[str] = mapped_column(
        String(20), default=DocumentStatus.PENDING, index=True
    )
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)

    # Paramètres d'ingestion utilisés
    parser: Mapped[str | None] = mapped_column(String(50), nullable=True)
    strategy: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Identifiant de la tâche Celery associée (permet GET /jobs/{task_id})
    task_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # Compteur de tentatives automatiques (beat : retry_error_documents)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    # Métadonnées métier
    entity: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True,
        comment="Entité propriétaire (ex. 'dassault', 'thales')",
    )
    validity_date: Mapped[date | None] = mapped_column(
        Date, nullable=True,
        comment="Date limite de validité — exclusion automatique après cette date",
    )

    # Résultat
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return (
            f"<Document id={self.id} filename={self.filename!r} "
            f"status={self.status!r} chunks={self.chunk_count}>"
        )
