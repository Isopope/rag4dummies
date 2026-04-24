"""Instance Celery — point d'entrée unique pour les workers et les clients."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Garantit que la racine du projet est dans sys.path quelle que soit
# la façon dont le worker est lancé (PYTHONPATH non défini, etc.)
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from celery import Celery
from celery.signals import worker_ready, worker_shutdown
from dotenv import load_dotenv
from loguru import logger

load_dotenv()


def make_celery_app() -> Celery:
    broker_url      = os.getenv("CELERY_BROKER_URL",      "redis://localhost:6379/0")
    result_backend  = os.getenv("CELERY_RESULT_BACKEND",  "redis://localhost:6379/1")

    app = Celery(
        "rag_worker",
        broker=broker_url,
        backend=result_backend,
    )

    # Charge la config depuis worker/config.py
    app.config_from_object("worker.config")

    # Autodiscouverte des tâches
    app.autodiscover_tasks(["worker.tasks"])

    return app


celery_app = make_celery_app()


# ── Signaux worker ────────────────────────────────────────────────────────────

@worker_ready.connect
def on_worker_ready(sender, **kwargs):
    logger.info("Worker Celery prêt — queue(s) : {}", sender.app.conf.task_default_queue)


@worker_shutdown.connect
def on_worker_shutdown(sender, **kwargs):
    logger.info("Worker Celery arrêté.")
