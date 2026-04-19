"""
Package worker — ingestion asynchrone avec Celery.

Architecture inspirée d'Onyx (background/celery/) :
- Deux queues : rag.ingest (lourd) + rag.light (léger / beat)
- Priorités : CRITICAL > HIGH > MEDIUM > LOW
- task_acks_late=True : requeue si le worker crashe
- Beat schedule : retry des docs en erreur + cleanup des stales

Démarrage des workers :
    # Worker ingestion (lourd, concurrence 2) :
    celery -A worker.app worker -Q rag.ingest -c 2 -l info

    # Worker léger (cleanup, beat, concurrence 4) :
    celery -A worker.app worker -Q rag.light -c 4 -l info

    # Beat scheduler (tâches périodiques) :
    celery -A worker.app beat -l info
"""
from worker.app import celery_app

__all__ = ["celery_app"]
