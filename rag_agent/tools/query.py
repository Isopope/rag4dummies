"""Outils de recherche et agrégation.

Port de langgraph_implementation/tools.py adapté pour UnifiedRAGState.
QueryTool intègre la logique de production de rag_pipeline.py :
- Double recherche hybride (alpha + alpha-0.3)
- Weighted Reciprocal Rank Fusion (wRRF)
- Retry avec backoff exponentiel sur Weaviate
- Mode mock sans infrastructure réelle
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime
from typing import Any, Callable, Optional

from loguru import logger

from ..state import (
    RetrievedObject,
    TaskStatus,
    ToolResult,
    UnifiedRAGState,
    add_to_environment,
)


# ── Helpers de production (portés de rag_pipeline.py) ─────────────────────────

def weaviate_with_retry(fn: Callable, *args, max_retries: int = 3, base_delay: float = 0.5, **kwargs) -> Any:
    """Appelle fn(*args, **kwargs) avec retry exponentiel.

    Port exact de rag_pipeline.py:240-251.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            delay = base_delay * (2 ** attempt)
            logger.warning("Weaviate retry {}/{} dans {:.1f}s : {}", attempt + 1, max_retries, delay, exc)
            time.sleep(delay)
    raise RuntimeError(f"Weaviate indisponible après {max_retries} tentatives") from last_exc


def _safe_score(value: Any) -> float:
    """Convertit un score arbitraire en float comparable."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _normalize_chunk_index(value: Any) -> Optional[int]:
    """Normalise chunk_index en entier si possible."""
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _fingerprint_doc(doc: dict[str, Any]) -> str:
    """Construit une empreinte stable pour les documents incomplets."""
    fingerprint_parts = [
        str(doc.get("source", "")),
        str(doc.get("title_path", "")),
        str(doc.get("page_idx", "")),
        str(doc.get("kind", "")),
        str(doc.get("page_content", "")),
    ]
    payload = "\x1f".join(part.strip() for part in fingerprint_parts)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _doc_key(doc: dict[str, Any]) -> tuple[str, str]:
    """Retourne une clé de déduplication robuste, stable même si source/index manquent."""
    for identifier_field in ("uuid", "id", "_id"):
        identifier = str(doc.get(identifier_field, "") or "").strip()
        if identifier:
            return (identifier_field, identifier)

    source = str(doc.get("source", "") or "").strip()
    chunk_index = _normalize_chunk_index(doc.get("chunk_index"))
    if source and chunk_index is not None:
        return ("source_chunk", f"{source}:{chunk_index}")

    title_path = str(doc.get("title_path", "") or "").strip()
    page_idx = str(doc.get("page_idx", "") or "").strip()
    return ("fallback", f"{source}|{title_path}|{page_idx}|{_fingerprint_doc(doc)}")


def _doc_rank_score(doc: dict[str, Any]) -> float:
    """Retourne le score de classement le plus pertinent disponible."""
    if "_rrf_score" in doc:
        return _safe_score(doc.get("_rrf_score"))
    return _safe_score(doc.get("_score"))


def weighted_rrf(
    ranked_results: list[list[dict]],
    weights: list[float],
    k: int = 60,
) -> list[dict]:
    """Weighted Reciprocal Rank Fusion sur plusieurs listes ordonnées.

    Formule : score(doc) = Σ weight_i / (k + rank_i)
    Port exact de rag_pipeline.py:195-219.
    """
    if len(ranked_results) != len(weights):
        raise ValueError(
            "weighted_rrf attend autant de listes de résultats que de poids "
            f"({len(ranked_results)} != {len(weights)})"
        )

    rrf_scores: dict[tuple[str, str], float] = {}
    best_doc: dict[tuple[str, str], dict] = {}
    best_source_scores: dict[tuple[str, str], float] = {}

    for result_list, weight in zip(ranked_results, weights):
        for rank, doc in enumerate(result_list, start=1):
            key = _doc_key(doc)
            rrf_scores[key] = rrf_scores.get(key, 0.0) + weight / (k + rank)
            source_score = _safe_score(doc.get("_source_score", doc.get("_score")))
            if key not in best_doc or source_score > best_source_scores[key]:
                best_doc[key] = doc
                best_source_scores[key] = source_score

    return [
        {
            **best_doc[key],
            "_source_score": best_source_scores[key],
            "_rrf_score": rrf_scores[key],
            "_score": rrf_scores[key],
        }
        for key in sorted(rrf_scores, key=lambda x: rrf_scores[x], reverse=True)
    ]


def combine_chunks(chunk_sets: list[list[dict]]) -> list[dict]:
    """Fusionne plusieurs listes de chunks en dédupliquant par (source, chunk_index).

    Port exact de rag_pipeline.py:158-177.
    """
    unique: dict[tuple[str, str], dict] = {}
    for chunk in (c for cs in chunk_sets for c in cs):
        key = _doc_key(chunk)
        if key not in unique:
            unique[key] = chunk
        else:
            if _doc_rank_score(chunk) > _doc_rank_score(unique[key]):
                merged = {**chunk}
                for meta_key, value in unique[key].items():
                    if meta_key.startswith("_") and meta_key not in merged:
                        merged[meta_key] = value
                unique[key] = merged
    return sorted(unique.values(), key=_doc_rank_score, reverse=True)


def deduplicate_queries(queries: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """Déduplique les requêtes par comparaison insensible à la casse, somme les poids.

    Port exact de rag_pipeline.py:180-192.
    """
    query_map: dict[str, tuple[str, float]] = {}
    for query, weight in queries:
        key = query.lower().strip()
        if key in query_map:
            orig, w = query_map[key]
            query_map[key] = (orig, w + weight)
        else:
            query_map[key] = (query, weight)
    return list(query_map.values())


# ── QueryTool ─────────────────────────────────────────────────────────────────

class QueryTool:
    """Recherche hybride sur Weaviate avec wRRF, retry et mode mock.

    Encapsule la logique search_documents de rag_pipeline.py:627-683.
    """

    _CHUNK_INDEX_MIN = 0
    _CHUNK_INDEX_MAX = 100_000
    _CONTENT_VECTOR="content_vector"
    _TITLE_VECTOR="title_vector"

    def __init__(
        self,
        weaviate_store=None,
        embedder: Optional[Callable] = None,
    ) -> None:
        self.weaviate_store = weaviate_store  # None → mode mock
        self.embedder       = embedder
        self.name           = "query"

    def _embed_query(self, text: str) -> list[float]:
        if self.embedder is None:
            raise RuntimeError("Un embedder est requis pour l'encodage des requêtes")
        normalized = text.strip() or " "

        embed_query = getattr(self.embedder, "embed_query", None)
        if callable(embed_query):
            return embed_query(normalized)

        encode_query = getattr(self.embedder, "encode_query", None)
        if callable(encode_query):
            return encode_query(normalized)

        if callable(self.embedder):
            return self.embedder(normalized)

        raise TypeError(
            "Embedder incompatible : méthode embed_query/encode_query absente "
            "et objet non callable"
        )

    def embed_query(self, text: str) -> list[float]:
        return self._embed_query(text)

    def execute(
        self,
        query: str,
        source_filter: Optional[str] = None,
        top_k: int = 20,
        alpha: float = 0.5,
    ) -> list[dict]:
        """Effectue une triple recherche hybride + wRRF.

        Retourne une liste de chunks triés par score décroissant.
        """
        if self.weaviate_store is None:
            return self._mock_results(query, top_k)

        if self.embedder is None:
            raise RuntimeError("Un embedder est requis pour la recherche réelle")

        vector   = self._embed_query(query)
        sem_docs = weaviate_with_retry(
            self.weaviate_store.hybrid_search,
            query=query, query_vector=vector,
            top_k=top_k, alpha=alpha, 
            source=source_filter,
            target_vector=self._CONTENT_VECTOR
        )
        kw_docs  = weaviate_with_retry(
            self.weaviate_store.hybrid_search,
            query=query, query_vector=vector,
            top_k=top_k, alpha=max(0.0, round(alpha - 0.3, 1)), 
            source=source_filter,
            target_vector=self._CONTENT_VECTOR
        )
        title_docs = weaviate_with_retry(
            self.weaviate_store.hybrid_search,
            query=query, query_vector=vector,
            top_k=top_k, alpha=1.0, 
            source=source_filter, 
            target_vector=self._TITLE_VECTOR
        )
        return weighted_rrf([sem_docs, kw_docs, title_docs], [1.0, 0.5, 0.8])

    def get_chunk_by_index(self, source: str, idx: int) -> Optional[dict]:
        """Récupère un chunk voisin par son index."""
        if self.weaviate_store is None:
            return None
        if not (self._CHUNK_INDEX_MIN <= idx <= self._CHUNK_INDEX_MAX):
            return None
        return weaviate_with_retry(self.weaviate_store.get_chunk_by_index, source, idx)

    def _mock_results(self, query: str, top_k: int) -> list[dict]:
        """Retourne des chunks synthétiques (mode mock sans Weaviate)."""
        return [
            {
                "source":       "/mock/document.pdf",
                "chunk_index":  i,
                "page_content": f"Mock content about '{query}' — chunk {i + 1}",
                "kind":         "text",
                "title_path":   f"Section {i + 1}",
                "page_idx":     i,
                "token_count":  50,
                "prev_chunk":   i - 1,
                "next_chunk":   i + 1 if i < 2 else -1,
                "_score":       0.9 - i * 0.05,
            }
            for i in range(min(top_k, 3))
        ]

    # ── Interface ToolResult (compatibilité ElysiaState) ──────────────────────

    def execute_as_tool_result(
        self,
        state: UnifiedRAGState,
        search_query: str,
        collection_names: Optional[list[str]] = None,
        filters: Optional[dict] = None,
        limit: int = 5,
    ) -> UnifiedRAGState:
        """Execute la recherche et écrit le résultat dans state['environment']."""
        colls = collection_names or state.get("collection_names") or ["RagChunk"]
        source_filter = (filters or {}).get("source") or state.get("source_filter")

        try:
            raw_docs = self.execute(
                query=search_query,
                source_filter=source_filter,
                top_k=limit,
            )
            objects = [
                RetrievedObject(
                    uuid=str(doc.get("chunk_index", i)),
                    properties=doc,
                    collection_name=colls[0],
                    query_used=search_query,
                )
                for i, doc in enumerate(raw_docs)
            ]
            result = ToolResult(
                tool_name="query",
                collection_names=colls,
                objects=objects,
                metadata={
                    "search_query":  search_query,
                    "results_count": len(objects),
                    "executed_at":   datetime.now().isoformat(),
                },
                status=TaskStatus.COMPLETED,
            )
            add_to_environment(state, result)
        except Exception as exc:
            (state.setdefault("errors", [])).append({  # type: ignore[attr-defined]
                "tool_name": "query",
                "message":   str(exc),
                "timestamp": datetime.now().isoformat(),
            })
        return state
