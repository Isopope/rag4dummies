"""Index-time content enrichment.

Onyx separates the content shown to users from the content optimized for
retrieval. BRH keeps ``page_content`` clean and stores/generates enriched text
only for embedding and keyword indexing.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EMBEDDING_VERSION = "brh-embedding-v2-onyx-aligned"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _join_non_empty(parts: list[str], separator: str = "\n\n") -> str:
    return separator.join(part.strip() for part in parts if part and part.strip())


def _source_name(source: str) -> str:
    if not source:
        return "document"
    try:
        return Path(source).name or source
    except Exception:
        return source


def generate_title_text(chunk: dict[str, Any]) -> str:
    """Return the stable title string used for title embeddings."""
    source_name = _source_name(_clean(chunk.get("source")))
    title_path = _clean(chunk.get("title_path"))
    if title_path:
        return f"{source_name} - {title_path}"
    return source_name


def generate_metadata_suffix_semantic(chunk: dict[str, Any]) -> str:
    """Natural-language metadata suffix used in passage embeddings."""
    parts = []
    entity = _clean(chunk.get("entity"))
    validity_date = _clean(chunk.get("validity_date"))
    kind = _clean(chunk.get("kind"))
    page_idx = chunk.get("page_idx")

    if entity:
        parts.append(f"Entity: {entity}")
    if validity_date:
        parts.append(f"Validity date: {validity_date}")
    if kind:
        parts.append(f"Document element type: {kind}")
    if page_idx is not None:
        parts.append(f"Page: {page_idx}")

    return _join_non_empty(parts, separator="\n")


def generate_metadata_suffix_keyword(chunk: dict[str, Any]) -> str:
    """Keyword-oriented metadata suffix for BM25-style search."""
    parts = [
        _clean(chunk.get("entity")),
        _clean(chunk.get("kind")),
        _clean(chunk.get("validity_date")),
        _clean(chunk.get("title_path")),
    ]
    return " ".join(part for part in parts if part)


def generate_enriched_content_for_chunk_embedding(chunk: dict[str, Any]) -> str:
    """Mirror Onyx's semantic enrichment order for dense embeddings."""
    title_prefix = _clean(chunk.get("title_prefix"))
    if not title_prefix:
        title_text = _clean(chunk.get("title_text")) or generate_title_text(chunk)
        title_prefix = f"Title: {title_text}" if title_text else ""

    doc_summary = _clean(chunk.get("doc_summary"))
    content = _clean(chunk.get("page_content"))
    chunk_context = _clean(chunk.get("chunk_context"))
    metadata_suffix = _clean(chunk.get("metadata_suffix_semantic"))
    if not metadata_suffix:
        metadata_suffix = generate_metadata_suffix_semantic(chunk)

    return _join_non_empty(
        [title_prefix, doc_summary, content, chunk_context, metadata_suffix]
    )


def generate_enriched_content_for_chunk_text(chunk: dict[str, Any]) -> str:
    """Build the keyword/BM25 text variant, matching Onyx's split suffixes."""
    title_prefix = _clean(chunk.get("title_prefix"))
    if not title_prefix:
        title_text = _clean(chunk.get("title_text")) or generate_title_text(chunk)
        title_prefix = f"Title: {title_text}" if title_text else ""

    metadata_suffix = _clean(chunk.get("metadata_suffix_keyword"))
    if not metadata_suffix:
        metadata_suffix = generate_metadata_suffix_keyword(chunk)

    return _join_non_empty(
        [
            title_prefix,
            _clean(chunk.get("doc_summary")),
            _clean(chunk.get("page_content")),
            _clean(chunk.get("chunk_context")),
            metadata_suffix,
        ]
    )


def enrich_chunk_for_embedding(
    chunk: dict[str, Any],
    *,
    embedding_model: str,
    embedding_provider: str,
    embedding_dim: int | None = None,
    embedding_created_at: str | None = None,
) -> dict[str, Any]:
    """Mutate and return a chunk with Onyx-style indexing fields."""
    title_text = generate_title_text(chunk)
    chunk["title_text"] = title_text
    chunk["title_prefix"] = f"Title: {title_text}" if title_text else ""
    chunk.setdefault("doc_summary", "")
    chunk.setdefault("chunk_context", "")
    chunk["metadata_suffix_semantic"] = generate_metadata_suffix_semantic(chunk)
    chunk["metadata_suffix_keyword"] = generate_metadata_suffix_keyword(chunk)
    chunk["embedding_content"] = generate_enriched_content_for_chunk_embedding(chunk)
    chunk["embedding_model"] = embedding_model
    chunk["embedding_provider"] = embedding_provider
    if embedding_dim is not None:
        chunk["embedding_dim"] = embedding_dim
    chunk["embedding_version"] = EMBEDDING_VERSION
    chunk["embedding_created_at"] = embedding_created_at or datetime.now(
        timezone.utc
    ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return chunk