"""Configuration Celery — inspirée de Onyx background/celery/configs/base.py.

Toutes les valeurs sont surchargeables via les variables d'environnement
(chargées par python-dotenv dans app.py).
"""
from __future__ import annotations

import os

from kombu import Queue

from worker.queues import INGEST_QUEUE, LIGHT_QUEUE, RagCeleryPriority

# ── Sérialisation ─────────────────────────────────────────────────────────────

task_serializer   = "json"
result_serializer = "json"
accept_content    = ["json"]
timezone          = "UTC"
enable_utc        = True

# ── Broker / backend (surchargés dans app.py depuis les vars d'env) ───────────
# broker_url et result_backend sont passés directement au constructeur Celery()

# ── Queues avec priorité ──────────────────────────────────────────────────────

task_queues = [
    Queue(INGEST_QUEUE, queue_arguments={"x-max-priority": 10}),
    Queue(LIGHT_QUEUE,  queue_arguments={"x-max-priority": 10}),
]
task_default_queue    = INGEST_QUEUE
task_queue_max_priority = 10
task_default_priority = int(RagCeleryPriority.HIGH)

# Onyx : queue_order_strategy="priority" — déqueue en ordre de priorité
worker_prefetch_multiplier = 1   # une tâche à la fois par worker (Onyx: prefetch=1 pour l'ingestion)

# ── Fiabilité (pattern clé d'Onyx) ───────────────────────────────────────────
# task_acks_late=True : la tâche n'est acquittée (ACK) qu'après complétion.
# Si le worker crashe, la tâche est automatiquement remise en queue.
task_acks_late             = True
task_reject_on_worker_lost = True   # requeue si le worker perd la connexion

# ── Résultats ─────────────────────────────────────────────────────────────────
task_track_started = True    # state STARTED visible via AsyncResult
result_expires     = 86400   # 24h — assez pour que l'API lise le résultat

# ── Timeouts ─────────────────────────────────────────────────────────────────
_soft = int(os.getenv("CELERY_INGEST_SOFT_TIMEOUT", "1800"))
task_soft_time_limit = _soft           # SoftTimeLimitExceeded levée → cleanup
task_time_limit      = _soft + 120     # SIGKILL après soft + 2 min de grâce

# ── Beat schedule ─────────────────────────────────────────────────────────────

beat_schedule = {
    # Relance les documents en statut PENDING depuis > 10 min (crash worker)
    "retry-stale-pending": {
        "task":     "rag.tasks.retry_stale_pending",
        "schedule": 600.0,   # toutes les 10 min
        "options":  {"queue": LIGHT_QUEUE, "priority": int(RagCeleryPriority.LOW)},
    },
    # Relance les documents en statut ERROR (max 3 tentatives)
    "retry-error-documents": {
        "task":     "rag.tasks.retry_error_documents",
        "schedule": 1800.0,  # toutes les 30 min
        "options":  {"queue": LIGHT_QUEUE, "priority": int(RagCeleryPriority.LOW)},
    },
    # Nettoie les documents en statut PROCESSING depuis > 2h (worker zombie)
    "cleanup-stale-processing": {
        "task":     "rag.tasks.cleanup_stale_processing",
        "schedule": 3600.0,  # toutes les heures
        "options":  {"queue": LIGHT_QUEUE, "priority": int(RagCeleryPriority.LOW)},
    },
}
