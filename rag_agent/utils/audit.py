"""Audit RAG — écrit un fichier JSON par requête avec tous les chunks par section.

Usage :
    from rag_agent.utils.audit import write_query_audit
    write_query_audit(state, audit_dir="audits")
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def write_query_audit(
    state: dict[str, Any],
    audit_dir: str | os.PathLike = "audits",
) -> Path:
    """Écrit le fichier d'audit de la requête et retourne son chemin.

    Structure du fichier :
    {
      "question_id": "...",
      "question":    "...",
      "timestamp":   "ISO-8601",
      "stats": {
        "all_docs_total":       25,
        "retrieved_docs_final": 10,
        "sources_seen":         ["doc_a.pdf", ...]
      },
      "pipeline_phases": {
        "all_docs":       [...],   // tout ce que le ReAct a accumulé
        "retrieved_docs": [...]    // ce qui arrive à la génération
      },
      "by_section": {
        "Section A > Sous-section": [
          {
            "chunk_index": 7,
            "source":      "doc.pdf",
            "page":        2,
            "score":       0.85,
            "expanded":    false,
            "in_final":    true,
            "content":     "..."
          }, ...
        ],
        "__no_section__": [...]   // chunks sans title_path
      }
    }
    """
    audit_path = Path(audit_dir)
    audit_path.mkdir(parents=True, exist_ok=True)

    question_id = state.get("question_id", "unknown")
    timestamp   = datetime.now(timezone.utc).isoformat()
    date_prefix = timestamp[:10].replace("-", "")

    all_docs       = state.get("all_docs", [])
    retrieved_docs = state.get("retrieved_docs", [])

    # Ensemble des (source, chunk_index) qui ont survécu à la consolidation
    final_keys = {
        (d.get("source", ""), d.get("chunk_index", -1))
        for d in retrieved_docs
    }

    def _chunk_entry(doc: dict, phase_set: set) -> dict:
        source    = doc.get("source", "")
        chunk_idx = doc.get("chunk_index", -1)
        raw_page  = doc.get("page_idx", 0)
        try:
            page = int(raw_page) + 1 if int(raw_page) > 0 else 0
        except (TypeError, ValueError):
            page = 0
        return {
            "chunk_index": chunk_idx,
            "source":      Path(source).name,
            "page":        page,
            "score":       round(float(doc.get("_score", 0.0)), 4),
            "expanded":    bool(doc.get("_expanded")),
            "in_final":    (source, chunk_idx) in phase_set,
            "title_path":  (doc.get("title_path") or "").strip(),
            "content":     (doc.get("page_content") or "").strip(),
        }

    # ── Sections (groupement par title_path) ──────────────────────────────────
    by_section: dict[str, list[dict]] = defaultdict(list)
    seen_keys: set[tuple] = set()

    for doc in all_docs:
        key     = (doc.get("source", ""), doc.get("chunk_index", -1))
        section = (doc.get("title_path") or "").strip() or "__no_section__"
        entry   = _chunk_entry(doc, final_keys)

        # déduplique par (source, chunk_index) — garde le score le plus haut
        existing = next(
            (e for e in by_section[section] if e["source"] == entry["source"] and e["chunk_index"] == entry["chunk_index"]),
            None,
        )
        if existing is None:
            by_section[section].append(entry)
            seen_keys.add(key)
        elif entry["score"] > existing["score"]:
            existing["score"] = entry["score"]

    # Tri par score desc dans chaque section
    for section in by_section:
        by_section[section].sort(key=lambda e: e["score"], reverse=True)

    # ── Stats ─────────────────────────────────────────────────────────────────
    sources_seen = sorted({Path(d.get("source", "")).name for d in all_docs if d.get("source")})

    payload = {
        "question_id": question_id,
        "question":    state.get("question", ""),
        "timestamp":   timestamp,
        "stats": {
            "all_docs_total":       len(all_docs),
            "retrieved_docs_final": len(retrieved_docs),
            "sources_seen":         sources_seen,
            "sections_count":       len(by_section),
        },
        "pipeline_phases": {
            "all_docs": [
                _chunk_entry(d, final_keys) for d in all_docs
            ],
            "retrieved_docs": [
                _chunk_entry(d, final_keys) for d in retrieved_docs
            ],
        },
        "by_section": dict(by_section),
    }

    filename = audit_path / f"{date_prefix}_{question_id[:8]}.json"
    filename.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return filename
