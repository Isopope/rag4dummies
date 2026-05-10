"""Nœuds rerank — API externe + fallback LLM + fusion wRRF agentique.

Architecture du reranking :
  Liste A : retrieved_docs triés par _accumulated_rrf + _neighbor_bonus
            (signal agentique : chunks retrouvés souvent par la boucle ReAct)
  Liste B : sortie de _api_rerank ou _llm_rerank
            (signal de pertinence froide)
  Fusion  : weighted_rrf([A, B], [1.0, 1.2])
            Le reranker est légèrement favorisé pour les cas simples,
            mais la Liste A compense pour les chunks multi-retrouvés.

Port de rag_pipeline.py:855-972.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Optional

from loguru import logger

from ..config import RAGConfig
from ..llm import parse_json_llm
from ..state import UnifiedRAGState, log_entry
from ..tools.query import weighted_rrf


def _api_rerank(
    docs: list[dict],
    question: str,
    reranker_url: str,
) -> list[dict]:
    """Reranking générique via API (ex: serveur Infinity hébergeant BAAI/bge-reranker-v2-m3).

    Compatible avec l'API Cohere / Infinity.
    """
    import requests

    docs_texts = [(doc.get("page_content") or "")[:2048] for doc in docs]
    payload = {
        "query": question,
        "documents": docs_texts,
        # Optionnel pour Infinity si c'est le seul modèle chargé
        "model": "BAAI/bge-reranker-v2-m3",
        "top_n": len(docs),
        "return_documents": False
    }

    response = requests.post(reranker_url, json=payload, timeout=10.0)
    response.raise_for_status()
    results = response.json().get("results", [])

    scored = [{**doc} for doc in docs]
    for result in results:
        idx = result.get("index")
        if idx is not None and idx < len(scored):
            scored[idx]["_rerank_score"] = result.get("relevance_score", 0.0)

    return sorted(scored, key=lambda d: float(d.get("_rerank_score", 0.0)), reverse=True)


def _llm_rerank(
    docs: list[dict],
    question: str,
    llm_call: Callable,
    llm_timeout: float,
) -> list[dict]:
    """Reranking LLM fallback — note chaque chunk de 0 à 10.

    Améliorations vs. version originale :
    - Troncature 400 → 800 caractères (moins de perte d'information clé)
    - Ajout de _hit_count comme signal contextuel pour le LLM
    - Retourne tous les docs triés (sans troncature : gérée par la fusion wRRF)
    """
    summaries = []
    for i, doc in enumerate(docs):
        kind      = doc.get("kind", "text")
        title     = (doc.get("title_path") or "").strip()
        text_     = (doc.get("page_content") or "")[:800].replace("\n", " ")  # 400 → 800
        hit_count = doc.get("_hit_count", 1)
        hit_info  = f" [retrouvé {hit_count}x]" if hit_count > 1 else ""
        extra     = " *(contexte étendu)*" if doc.get("_expanded") else ""
        summaries.append(f"[{i}] {kind}{extra}{hit_info} | {title} | {text_}…")

    prompt = (
        f"Question : {question}\n\n"
        "Note la pertinence de chaque extrait de 0 à 10 "
        "(10 = répond parfaitement à la question, 0 = hors sujet).\n"
        "L'indication [retrouvé Nx] signifie que l'agent a trouvé cet extrait N fois — "
        "tiens-en compte comme signal de pertinence.\n"
        "Réponds UNIQUEMENT avec un tableau JSON compact d'entiers sur UNE SEULE LIGNE, "
        "dans l'ordre exact des extraits (sans balise markdown, sans indentation, sans saut de ligne).\n"
        f"Exemple pour {len(docs)} extraits : [{', '.join(['8'] * min(len(docs), 4))}"
        f"{'...' if len(docs) > 4 else ''}]\n\n"
        + "\n".join(summaries)
    )

    scores: list[int] = []
    try:
        resp = llm_call(
            messages=[
                {"role": "system", "content": "Tu es un expert en pertinence documentaire."},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.0,
            max_tokens=max(600, len(docs) * 15),
        )
        text_resp = resp.choices[0].message.content or "[]"
        try:
            parsed = parse_json_llm(text_resp)
            if not isinstance(parsed, list):
                raise ValueError(f"Pas une liste JSON : {text_resp[:50]}")
            scores = [int(s) for s in parsed]
        except Exception:
            nums   = re.findall(r"\b(?:10|[0-9])\b", text_resp)
            scores = [int(n) for n in nums] if nums else []
    except TimeoutError:
        logger.warning("rerank LLM — timeout")
    except Exception as exc:
        logger.warning("rerank LLM — erreur : {}", exc)

    if not scores:
        scores = [5] * len(docs)
    if len(scores) < len(docs):
        scores += [0] * (len(docs) - len(scores))
    elif len(scores) > len(docs):
        scores = scores[: len(docs)]

    scored = [{**doc} for doc in docs]
    for i, doc in enumerate(scored):
        doc["_rerank_score"] = scores[i]
    # Retourne tous les docs triés, sans [:20] — la troncature est gérée par la fusion wRRF
    return sorted(scored, key=lambda d: float(d.get("_rerank_score", 0.0)), reverse=True)


def rerank(
    state: UnifiedRAGState,
    *,
    llm_call: Callable,
    reranker_url: Optional[str] = None,
    cohere_client: Any | None = None,
    rag_config: RAGConfig | None = None,
    config: RAGConfig | None = None,
) -> dict:
    """Nœud 4 : reranking API (Infinity/BGE) ou fallback LLM avec fusion wRRF.

    Deux listes indépendantes sont construites puis fusionnées :
      Liste A : triée par _accumulated_rrf + _neighbor_bonus  (signal récurrence agent)
      Liste B : sortie API ou LLM                             (signal pertinence froide)
    weighted_rrf([A, B], [1.0, 1.2]) — le reranker est légèrement favorisé,
    mais la Liste A compense pour les chunks retrouvés plusieurs fois.
    """
    rag_config = rag_config or config
    if rag_config is None:
        raise TypeError("rerank requires 'rag_config' or backward-compatible 'config'")
    _ = cohere_client  # Ancien paramètre conservé pour compatibilité des tests/appels legacy.
    qid      = state["question_id"]
    docs     = state.get("retrieved_docs", [])
    question = state["question"]
    log      = list(state.get("decision_log", []))
    top_k    = getattr(rag_config, "top_k_rerank", rag_config.top_k_final)

    if not docs:
        log.append(log_entry("rerank", "Aucun document à reranker"))
        return {"reranked_docs": [], "decision_log": log}

    # ── Liste A : signal agentique (récurrence des récupérations) ─────────────
    list_a = sorted(
        docs,
        key=lambda d: d.get("_accumulated_rrf", 0.0) + d.get("_neighbor_bonus", 0.0),
        reverse=True,
    )

    # ── Liste B : signal de pertinence froide (Cohere ou LLM) ─────────────────
    list_b: list[dict] = []

    if reranker_url:
        try:
            list_b = _api_rerank(docs, question, reranker_url)
            log.append(log_entry(
                "rerank.api",
                f"API Rerank : {len(docs)} docs scorés (Liste B)",
                {"n_input": len(docs)},
            ))
        except Exception as exc:
            logger.warning("[{}] API Rerank échoué, fallback LLM : {}", qid, exc)
            log.append(log_entry(
                "rerank.api",
                f"API Rerank échoué : {exc} — fallback LLM",
                {"error": str(exc)},
            ))

    if not list_b:
        # Fallback LLM
        list_b = _llm_rerank(docs, question, llm_call, rag_config.llm_timeout)
        log.append(log_entry(
            "rerank.llm",
            f"LLM Rerank : {len(docs)} docs scorés (Liste B)",
            {"n_input": len(docs)},
        ))

    # ── Fusion wRRF (Liste A + Liste B) ───────────────────────────────────────
    # Poids : reranker légèrement favorisé (1.2) pour les cas simples,
    # mais la Liste A compense pour les chunks retrouvés plusieurs fois.
    reranked = weighted_rrf([list_a, list_b], [1.0, 1.2])[:top_k]

    top_chunk_info = None
    if reranked:
        top = reranked[0]
        top_chunk_info = (
            f"{Path(top.get('source', '')).name}"
            f"[{top.get('chunk_index')}] hits={top.get('_hit_count', 1)}"
        )
    log.append(log_entry(
        "rerank.fusion",
        f"wRRF(A agentique, B reranker) : {len(docs)} → {len(reranked)} chunks (top {top_k})",
        {
            "n_input":   len(docs),
            "n_output":  len(reranked),
            "top_chunk": top_chunk_info,
        },
    ))
    return {"reranked_docs": reranked, "decision_log": log}
