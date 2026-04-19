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


def get_agent() -> "RAGAgent":
    """Retourne l'instance RAGAgent (crée l'agent si absent)."""
    global _agent
    if _agent is None:
        cfg = get_config()
        store = get_store()
        from rag_agent import RAGAgent
        _agent = RAGAgent(
            weaviate_store  = store,
            openai_key      = cfg.openai_key,
            cohere_key      = cfg.cohere_key,
            embedding_model = cfg.embedding_model,
            llm_model       = cfg.llm_model,
            top_k_retrieve  = cfg.top_k_retrieve,
            top_k_final     = cfg.top_k_final,
            hybrid_alpha    = cfg.hybrid_alpha,
            max_tokens      = cfg.max_tokens,
            max_agent_iter  = cfg.max_agent_iter,
            llm_timeout     = cfg.llm_timeout,
            enable_compression = cfg.enable_compression,
        )
        logger.info("RAGAgent initialisé (modèle={}, embedding={})", cfg.llm_model, cfg.embedding_model)
    return _agent


def reset_agent() -> None:
    """Force la recréation de l'agent (ex : après changement de clé API)."""
    global _agent
    _agent = None
