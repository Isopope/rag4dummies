"""Application FastAPI — RAG API.

Démarrage :
    uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gère le cycle de vie de l'application : connexion et déconnexion Weaviate."""
    # ── Startup ───────────────────────────────────────────────────────────────
    try:
        from .deps import get_store
        get_store()
        logger.info("Weaviate connecté au démarrage de l'API.")
    except Exception as exc:
        logger.warning("Weaviate non disponible au démarrage : {}", exc)

    # Crée les tables SQLite si elles n'existent pas (mode dev)
    # En prod PostgreSQL, utiliser : alembic upgrade head
    db_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./rag.db")
    if db_url.startswith("sqlite"):
        from db import create_all_tables
        try:
            await create_all_tables()
            logger.info("Tables SQLite créées / vérifiées.")
        except Exception as exc:
            logger.warning("Impossible de créer les tables SQLite : {}", exc)

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    from .deps import close_store
    close_store()
    logger.info("API arrêtée — connexion Weaviate fermée.")


def create_app() -> FastAPI:
    """Factory de l'application FastAPI."""
    app = FastAPI(
        title="RAG API",
        description=(
            "API REST pour le pipeline RAG — Weaviate hybrid + OpenAI + LangGraph.\n\n"
            "**Endpoints principaux :**\n"
            "- `POST /query` — Requête synchrone\n"
            "- `POST /query/stream` — Streaming SSE nœud par nœud\n"
            "- `POST /ingest/pdf` — Ingestion asynchrone d'un PDF (retourne task_id)\n"
            "- `POST /ingest/jsonl` — Ingestion asynchrone d'un JSONL pré-chunké\n"
            "- `GET /jobs/{task_id}` — Suivi de l'état d'une tâche d'ingestion\n"
            "- `POST /connectors/local` — Scan d'un répertoire local / NFS\n"
            "- `POST /connectors/web` — Crawl de pages web via Playwright\n"
            "- `POST /connectors/sharepoint` — Sync SharePoint / OneDrive\n"
            "- `GET /sources` — Liste des documents indexés\n"
            "- `POST /feedback` — Enregistrer un feedback utilisateur\n"
            "- `GET /feedback` — Lister les conversations notées\n\n"
            f"Base de données : `{os.getenv('DATABASE_URL', 'sqlite+aiosqlite:///./rag.db')}`"
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",")]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ───────────────────────────────────────────────────────────────
    from .routers import ingest, query, sources, feedback, documents, jobs, connectors
    app.include_router(query.router,      prefix="/query",      tags=["query"])
    app.include_router(ingest.router,     prefix="/ingest",     tags=["ingest"])
    app.include_router(sources.router,    prefix="/sources",    tags=["sources"])
    app.include_router(feedback.router,   prefix="/feedback",   tags=["feedback"])
    app.include_router(documents.router,  prefix="/documents",  tags=["documents"])
    app.include_router(jobs.router,       prefix="/jobs",       tags=["jobs"])
    app.include_router(connectors.router, prefix="/connectors", tags=["connectors"])

    # ── Health check ──────────────────────────────────────────────────────────
    @app.get("/health", tags=["health"], summary="Statut de l'API")
    async def health():
        from .deps import _store
        weaviate_ready = _store is not None and _store.is_ready()
        return {
            "status": "ok",
            "weaviate": "connected" if weaviate_ready else "disconnected",
        }

    return app


app = create_app()
