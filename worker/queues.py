"""Définitions des queues et priorités Celery.

Inspiré de OnyxCeleryPriority — simplifié pour notre projet.
"""
from enum import IntEnum

# ── Noms des queues ────────────────────────────────────────────────────────────

INGEST_QUEUE = "rag.ingest"   # tâches lourdes : parsing PDF, embedding, Weaviate
LIGHT_QUEUE  = "rag.light"    # tâches légères : beat, cleanup, retry


# ── Priorités (0 = plus haute, 9 = plus basse) ─────────────────────────────────
# Redis utilise une convention « plus grand = plus prioritaire » mais Celery
# avec queue_order_strategy="priority" utilise le contraire (0 = highest).

class RagCeleryPriority(IntEnum):
    CRITICAL = 0   # re-ingestion manuelle urgente
    HIGH     = 3   # ingestion normale (soumise par l'utilisateur)
    MEDIUM   = 5   # default — beat tasks
    LOW      = 7   # cleanup, retry automatique
