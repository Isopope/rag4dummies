"""Modèle ConnectorConfig — sources de connecteurs synchronisées périodiquement.

Persiste les sources (ex. sites SharePoint) à re-synchroniser automatiquement :
cadence, paramètres de crawl, état de la dernière synchronisation. Équivalent
léger du cc_pair d'Onyx. Les credentials NE SONT PAS stockés ici — ils sont lus
depuis l'environnement du worker.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

# Cadence de synchronisation par défaut : 7 jours.
DEFAULT_SYNC_INTERVAL_SECONDS = 7 * 24 * 3600


class ConnectorConfig(Base):
    """Une source de connecteur synchronisée périodiquement (pull planifié)."""

    __tablename__ = "connector_config"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    name: Mapped[str] = mapped_column(String(255))
    connector_type: Mapped[str] = mapped_column(
        String(50), default="sharepoint", index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    # Paramètres spécifiques au connecteur (JSON) : site_url, site_name, folder_path…
    config_json: Mapped[str] = mapped_column(Text, default="{}")

    # Paramètres d'ingestion appliqués
    parser: Mapped[str] = mapped_column(String(50), default="mineru")
    strategy: Mapped[str] = mapped_column(String(50), default="by_sentence")
    entity: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prune: Mapped[bool] = mapped_column(Boolean, default=True)

    # Cadence (secondes) — défaut 7 jours
    interval_seconds: Mapped[int] = mapped_column(
        Integer, default=DEFAULT_SYNC_INTERVAL_SECONDS
    )

    # État de la dernière synchronisation
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(50), nullable=True)

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
            f"<ConnectorConfig id={self.id} name={self.name!r} "
            f"type={self.connector_type!r} enabled={self.enabled}>"
        )
