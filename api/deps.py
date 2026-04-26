"""Injection de dépendances FastAPI — store Weaviate et agent RAG (singletons)."""
from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from loguru import logger

if TYPE_CHECKING:
    from rag_agent import RAGAgent
    from weaviate_store import WeaviateStore


# ── Config ─────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_config():
    """Retourne la RAGConfig chargée depuis les variables d'environnement (mise en cache)."""
    from rag_agent.config import RAGConfig
    return RAGConfig.from_env()


# ── Weaviate Store (singleton processus) ──────────────────────────────────────

_store: "WeaviateStore | None" = None


def get_store() -> "WeaviateStore":
    """Retourne l'instance WeaviateStore connectée (crée la connexion si absente)."""
    global _store
    if _store is None or not _store.is_ready():
        cfg = get_config()
        from weaviate_store import WeaviateStore
        _store = WeaviateStore(host=cfg.weaviate_host, port=cfg.weaviate_port)
        try:
            _store.connect()
        except Exception as exc:
            logger.error("Connexion Weaviate échouée : {}", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Weaviate non disponible : {exc}",
            )
    return _store


def close_store() -> None:
    """Ferme proprement la connexion Weaviate (appelé au shutdown)."""
    global _store
    if _store is not None:
        try:
            _store.close()
        except Exception:
            pass
        _store = None


# ── RAGAgent (singleton processus) ────────────────────────────────────────────

_agent: "RAGAgent | None" = None
_agents_by_model: "dict[str, RAGAgent]" = {}


def _build_agent(llm_model: str) -> "RAGAgent":
    """Instancie un RAGAgent pour le modèle donné."""
    cfg = get_config()
    store = get_store()
    from rag_agent import RAGAgent
    agent = RAGAgent(
        weaviate_store     = store,
        openai_key         = cfg.openai_key,
        cohere_key         = cfg.cohere_key,
        embedding_model    = cfg.embedding_model,
        llm_model          = llm_model,
        top_k_retrieve     = cfg.top_k_retrieve,
        top_k_final        = cfg.top_k_final,
        hybrid_alpha       = cfg.hybrid_alpha,
        max_tokens         = cfg.max_tokens,
        max_agent_iter     = cfg.max_agent_iter,
        llm_timeout        = cfg.llm_timeout,
        enable_compression = cfg.enable_compression,
    )
    logger.info("RAGAgent initialisé (modèle={}, embedding={})", llm_model, cfg.embedding_model)
    return agent


def get_agent() -> "RAGAgent":
    """Retourne l'agent par défaut (modèle configuré dans .env)."""
    global _agent
    if _agent is None:
        _agent = _build_agent(get_config().llm_model)
    return _agent


def get_agent_for_model(model: "str | None" = None) -> "RAGAgent":
    """Retourne un agent pour le modèle demandé (mis en cache par modèle).

    Si model est None ou vide, retourne l'agent par défaut.
    """
    if not model:
        return get_agent()
    if model not in _agents_by_model:
        _agents_by_model[model] = _build_agent(model)
    return _agents_by_model[model]


def reset_agent() -> None:
    """Force la recréation de tous les agents (ex : après changement de clé API)."""
    global _agent
    _agent = None
    _agents_by_model.clear()


# ── Base de données (re-export pour les routers) ───────────────────────────────

from db.engine import get_db_session as get_db_session  # noqa: E402, F401

# ── Document Store — MinIO ou local (singleton processus) ─────────────────────

_document_store = None


def get_document_store():
    """
    Retourne le DocumentStore singleton (MinioDocumentStore ou LocalDocumentStore
    selon la variable d'environnement MINIO_ENDPOINT).
    """
    global _document_store
    if _document_store is None:
        from storage import make_document_store
        _document_store = make_document_store()
    return _document_store


# ── Celery client (singleton processus) ───────────────────────────────────────

_celery_app = None


def get_celery_app():
    """Retourne l'instance Celery singleton utilisée comme client par l'API."""
    global _celery_app
    if _celery_app is None:
        from worker.app import celery_app
        _celery_app = celery_app
        logger.info(
            "Client Celery initialisé — broker={}",
            _celery_app.conf.broker_url,
        )
    return _celery_app
