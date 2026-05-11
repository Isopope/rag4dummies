"""Ingesteur PDF → chunks → embeddings OpenAI → Weaviate.

Deux modes selon ce qui est installé :
  • openingestion  (défaut) — pipeline complet DoclingChef / MinerUChef + chunker
  • simple         (fallback) — extraction page par page avec PyMuPDF + découpage naïf

Embeddings : OpenAI Embeddings (text-embedding-3-small, text-embedding-3-large, etc.)
Pipeline Onyx-aligned : content_vector séparé de title_vector, enrichissement invisible.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Callable

from loguru import logger

from rag_agent.retrieval.content_enrichment import enrich_chunk_for_embedding


# ── embedding helper ──────────────────────────────────────────────────────────

def _embed_texts(
    texts: list[str],
    api_key: str,
    model: str,
    batch_size: int = 2048,
    progress_cb: Callable[[str], None] | None = None,
) -> list[list[float]]:
    """Encode une liste de passages en vecteurs."""
    from llm.embedder import EmbeddingModel

    embedder = EmbeddingModel(
        model=model,
        api_key=api_key,
    )

    if progress_cb:
        progress_cb(f"  Embedding de {len(texts)} chunks…")

    return embedder.embed_passages(texts)


def _embedding_provider(model: str) -> str:
    from llm.embedder import EmbeddingModel

    return EmbeddingModel(model=model).provider.value


def _embed_chunk_field_with_failure_handling(
    chunks: list[dict],
    field: str,
    api_key: str,
    model: str,
    progress_cb: Callable[[str], None] | None = None,
) -> list[list[float]]:
    """Embed a chunk field with Onyx-style fallback from batch to source/chunk."""
    texts = [chunk.get(field) or " " for chunk in chunks]
    try:
        vectors = _embed_texts(texts, api_key, model, progress_cb=progress_cb)
        if len(vectors) != len(texts):
            raise RuntimeError(
                f"Embedding count mismatch for field {field}: {len(vectors)} != {len(texts)}"
            )
        return vectors
    except Exception as batch_exc:
        logger.warning(
            "Embedding batch failed for field {}: {}. Retrying by source.",
            field,
            batch_exc,
        )

    vectors_by_pos: list[list[float] | None] = [None] * len(chunks)
    positions_by_source: dict[str, list[int]] = {}
    for pos, chunk in enumerate(chunks):
        positions_by_source.setdefault(chunk.get("source") or "", []).append(pos)

    for source, positions in positions_by_source.items():
        source_texts = [texts[pos] for pos in positions]
        try:
            source_vectors = _embed_texts(
                source_texts, api_key, model, progress_cb=progress_cb
            )
            if len(source_vectors) != len(source_texts):
                raise RuntimeError(
                    "Embedding count mismatch for "
                    f"source {source} field {field}: "
                    f"{len(source_vectors)} != {len(source_texts)}"
                )
            for pos, vector in zip(positions, source_vectors):
                vectors_by_pos[pos] = vector
            continue
        except Exception as source_exc:
            logger.warning(
                "Embedding retry failed for source {} field {}: {}. Retrying by chunk.",
                source,
                field,
                source_exc,
            )

        for pos in positions:
            chunk = chunks[pos]
            try:
                vectors_by_pos[pos] = _embed_texts(
                    [texts[pos]], api_key, model, progress_cb=progress_cb
                )[0]
            except Exception as chunk_exc:
                logger.error(
                    "Embedding failed for source={} chunk_index={} field={}: {}",
                    chunk.get("source"),
                    chunk.get("chunk_index"),
                    field,
                    chunk_exc,
                )
                raise RuntimeError(
                    "Embedding failed for "
                    f"source={chunk.get('source')} "
                    f"chunk_index={chunk.get('chunk_index')} field={field}"
                ) from chunk_exc

    if any(vector is None for vector in vectors_by_pos):
        raise RuntimeError(f"Embedding failed to produce all vectors for field {field}")
    return [vector for vector in vectors_by_pos if vector is not None]


def _prepare_chunks_for_embedding(
    chunks: list[dict],
    embedding_model: str,
) -> None:
    provider = _embedding_provider(embedding_model)
    for chunk in chunks:
        enrich_chunk_for_embedding(
            chunk,
            embedding_model=embedding_model,
            embedding_provider=provider,
        )


def _embed_content_and_titles(
    chunks: list[dict],
    api_key: str,
    embedding_model: str,
    progress_cb: Callable[[str], None] | None = None,
) -> tuple[list[list[float]], list[list[float]]]:
    """Génère content_vectors et title_vectors avec cache de titres (Onyx pattern)."""
    _prepare_chunks_for_embedding(chunks, embedding_model)

    if progress_cb:
        progress_cb("Embedding du contenu enrichi des chunks...")
    content_vectors = _embed_chunk_field_with_failure_handling(
        chunks, "embedding_content", api_key, embedding_model, progress_cb
    )

    # Cache titres — un seul embedding par titre unique (Onyx embedder.py:180)
    unique_title_chunks: list[dict] = []
    seen_titles: set[str] = set()
    for chunk in chunks:
        title_text = chunk.get("title_text") or "document"
        if title_text not in seen_titles:
            seen_titles.add(title_text)
            unique_title_chunks.append(
                {
                    "source": chunk.get("source", ""),
                    "chunk_index": chunk.get("chunk_index", -1),
                    "title_text": title_text,
                }
            )

    if progress_cb:
        progress_cb(f"Embedding de {len(unique_title_chunks)} titre(s) unique(s)...")
    unique_title_vectors = _embed_chunk_field_with_failure_handling(
        unique_title_chunks, "title_text", api_key, embedding_model, progress_cb
    )
    title_vector_by_text = {
        chunk["title_text"]: vector
        for chunk, vector in zip(unique_title_chunks, unique_title_vectors)
    }
    title_vectors = [
        title_vector_by_text[chunk.get("title_text") or "document"] for chunk in chunks
    ]

    if content_vectors:
        embedding_dim = len(content_vectors[0])
        for chunk in chunks:
            chunk["embedding_dim"] = embedding_dim

    return content_vectors, title_vectors


# ── mode openingestion ────────────────────────────────────────────────────────

def _ingest_with_openingestion(
    pdf_path: Path,
    source: str,
    parser: str,
    strategy: str,
    api_key: str,
    embedding_model: str,
    progress_cb: Callable[[str], None],
    entity: str | None = None,
    validity_date: str | None = None,
) -> tuple[list[dict], list[list[float]], list[list[float]]]:
    from openingestion import ingest

    progress_cb(f"Parsing '{pdf_path.name}' avec {parser} / {strategy}…")

    mineru_tmp = Path(tempfile.mkdtemp(prefix="mineru_out_"))
    try:
        chunks = ingest(
            pdf_path,
            parser=parser,
            strategy=strategy,
            image_mode="path",
            mineru_output_dir=mineru_tmp,
        )
    finally:
        shutil.rmtree(mineru_tmp, ignore_errors=True)

    progress_cb(f"{len(chunks)} chunks extraits.")

    import json as _json

    chunk_dicts = []
    for c in chunks:
        page_idx = c.position_int[0][0] if c.position_int else 0
        extras   = c.extras or {}

        captions  = extras.get("captions",  getattr(c, "captions",  [])) or []
        footnotes = extras.get("footnotes", getattr(c, "footnotes", [])) or []
        html = extras.get("html", getattr(c, "html", "")) or ""

        chunk_dicts.append({
            "page_content":  c.page_content,
            "source":        source,
            "kind":          c.kind.value if hasattr(c.kind, "value") else str(c.kind),
            "title_path":    c.title_path or "",
            "title_level":   c.title_level,
            "chunk_index":   c.chunk_index,
            "reading_order": c.reading_order,
            "prev_chunk":    c.prev_chunk_index if c.prev_chunk_index is not None else -1,
            "next_chunk":    c.next_chunk_index if c.next_chunk_index is not None else -1,
            "page_idx":      page_idx,
            "token_count":   c.token_count,
            "html":          html,
            "captions_json": _json.dumps(captions,  ensure_ascii=False),
            "footnotes_json":_json.dumps(footnotes, ensure_ascii=False),
            "bboxes_json":   _json.dumps(c.position_int or [], ensure_ascii=False),
        })

    # Injecter les métadonnées métier avant enrichissement
    for chunk in chunk_dicts:
        chunk["entity"] = entity or ""
        if validity_date:
            chunk["validity_date"] = validity_date

    progress_cb("Embedding des chunks (Modèle d'embedding)…")
    content_vectors, title_vectors = _embed_content_and_titles(
        chunk_dicts, api_key, embedding_model, progress_cb
    )

    return chunk_dicts, content_vectors, title_vectors


# ── mode fallback (PyMuPDF) ───────────────────────────────────────────────────

def _ingest_simple(
    pdf_path: Path,
    source: str,
    api_key: str,
    embedding_model: str,
    chunk_size: int = 800,
    progress_cb: Callable[[str], None] | None = None,
    entity: str | None = None,
    validity_date: str | None = None,
) -> tuple[list[dict], list[list[float]], list[list[float]]]:
    try:
        import fitz
    except ImportError:
        raise ImportError("pymupdf est requis en mode fallback : pip install pymupdf")

    _cb = progress_cb or (lambda m: None)
    _cb(f"Extraction texte de '{pdf_path.name}' (mode simple)…")

    doc = fitz.open(str(pdf_path))
    raw_pages: list[tuple[int, str]] = []
    for page in doc:
        text = page.get_text("text").strip()
        if text:
            raw_pages.append((page.number, text))
    doc.close()

    _cb(f"{len(raw_pages)} pages avec du texte.")

    chunk_dicts: list[dict] = []
    idx = 0
    for page_idx, text in raw_pages:
        for start in range(0, len(text), chunk_size):
            block = text[start : start + chunk_size].strip()
            if not block:
                continue
            chunk_dicts.append({
                "page_content":   block,
                "source":        source,
                "kind":          "text",
                "title_path":    "",
                "title_level":   0,
                "chunk_index":   idx,
                "reading_order": idx,
                "prev_chunk":    idx - 1,
                "next_chunk":    -1,
                "page_idx":      page_idx,
                "token_count":   len(block) // 4,
                "html":          "",
                "captions_json": "[]",
                "footnotes_json":"[]",
                "bboxes_json":   "[]",
            })
            idx += 1

    _cb(f"{len(chunk_dicts)} chunks créés (mode simple).")

    # Injecter les métadonnées métier avant enrichissement
    for chunk in chunk_dicts:
        chunk["entity"] = entity or ""
        if validity_date:
            chunk["validity_date"] = validity_date

    _cb("Embedding des chunks (Modèle d'embedding)…")
    content_vectors, title_vectors = _embed_content_and_titles(
        chunk_dicts, api_key, embedding_model, _cb
    )

    return chunk_dicts, content_vectors, title_vectors


# ── point d'entrée public ─────────────────────────────────────────────────────

def ingest_pdf(
    pdf_path: Path,
    weaviate_store,
    api_key: str,
    embedding_model: str = "text-embedding-3-small",
    chunking_strategy: str = "by_token",
    parser: str = "docling",
    progress_cb: Callable[[str], None] | None = None,
    force_simple: bool = False,
    source_override: str | None = None,
    entity: str | None = None,
    validity_date: str | None = None,
) -> int:
    """Parse un PDF, embed ses chunks via OpenAI Embeddings et les stocke dans Weaviate.

    Parameters
    ----------
    pdf_path:
        Chemin vers le fichier PDF.
    weaviate_store:
        Instance connectée de ``WeaviateStore``.
    api_key:
        Clé API OpenAI.
    embedding_model:
        Modèle d'embedding OpenAI (défaut : text-embedding-3-small).
    chunking_strategy:
        Stratégie openingestion : by_token, by_sentence, by_block…
    parser:
        Parser openingestion : docling ou mineru.
    progress_cb:
        Callback appelé avec des messages de progression (pour l'UI).
    force_simple:
        Si True, utilise le mode PyMuPDF même si openingestion est dispo.
    source_override:
        Si renseigné, remplace la valeur par défaut (chemin absolu du PDF)
        pour le champ ``source`` stocké dans Weaviate.  Utilisé par l'API
        pour stocker la clé MinIO (ex. ``abc12345-mon-doc.pdf``) plutôt que
        le chemin local éphémère.

    Returns
    -------
    int
        Nombre de chunks stockés.
    """
    _cb = progress_cb or (lambda msg: logger.info(msg))
    source = source_override or str(pdf_path.resolve())
    rfc3339_date: str | None = f"{validity_date}T00:00:00Z" if validity_date else None

    # Supprimer les éventuels chunks existants pour ce fichier
    weaviate_store.delete_source(source)

    if force_simple:
        chunk_dicts, content_vectors, title_vectors = _ingest_simple(
            pdf_path,
            source,
            api_key,
            embedding_model,
            progress_cb=_cb,
            entity=entity,
            validity_date=rfc3339_date,
        )
    else:
        try:
            chunk_dicts, content_vectors, title_vectors = _ingest_with_openingestion(
                pdf_path, source, parser, chunking_strategy,
                api_key, embedding_model, _cb,
                entity=entity,
                validity_date=rfc3339_date,
            )
        except ImportError:
            logger.warning(
                "openingestion introuvable — passage en mode simple (PyMuPDF)."
            )
            _cb(" openingestion non installé, mode simple activé.")
            chunk_dicts, content_vectors, title_vectors = _ingest_simple(
                pdf_path,
                source,
                api_key,
                embedding_model,
                progress_cb=_cb,
                entity=entity,
                validity_date=rfc3339_date,
            )

    _cb("Stockage dans Weaviate…")
    # Finaliser le versioning avec embedding_dim connu
    provider = _embedding_provider(embedding_model)
    dim = len(content_vectors[0]) if content_vectors else None
    for chunk in chunk_dicts:
        enrich_chunk_for_embedding(
            chunk,
            embedding_model=embedding_model,
            embedding_provider=provider,
            embedding_dim=dim,
        )

    n = weaviate_store.insert_chunks(chunk_dicts, content_vectors, title_vectors)
    _cb(f" {n} chunks indexés pour '{pdf_path.name}'.")
    return n


# ── ingestion depuis un fichier JSONL pré-découpé ────────────────────────────

def ingest_jsonl(
    jsonl_path: Path,
    weaviate_store,
    api_key: str,
    embedding_model: str = "text-embedding-3-small",
    progress_cb: Callable[[str], None] | None = None,
    source_override: str | None = None,
) -> int:
    """Ingère un fichier JSONL de chunks pré-découpés (format openingestion) dans Weaviate.

    Chaque ligne JSON doit contenir au minimum ``page_content`` et ``source``.
    Les champs supplémentaires du format openingestion sont mappés vers le
    schéma Weaviate (prev_chunk_index → prev_chunk, position_int → page_idx, etc.).

    Parameters
    ----------
    jsonl_path:
        Chemin vers le fichier ``.jsonl``.
    weaviate_store:
        Instance connectée de ``WeaviateStore``.
    api_key:
        Clé API OpenAI (pour les embeddings).
    embedding_model:
        Modèle OpenAI Embeddings.
    progress_cb:
        Callback de progression (UI).
    source_override:
        Remplace le champ ``source`` présent dans le JSONL.
        Utile quand le chemin stocké dans le fichier ne correspond plus
        à l'emplacement réel du PDF.
    """
    import json as _json

    _cb = progress_cb or (lambda msg: logger.info(msg))

    _cb(f"Lecture de '{jsonl_path.name}'…")
    raw_lines: list[dict] = []
    with jsonl_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                raw_lines.append(_json.loads(line))

    if not raw_lines:
        raise ValueError(f"Fichier vide : {jsonl_path}")

    _cb(f"{len(raw_lines)} lignes lues.")

    first_source = raw_lines[0].get("source", str(jsonl_path))
    source = source_override or first_source

    weaviate_store.delete_source(source)

    chunk_dicts: list[dict] = []
    for raw in raw_lines:
        extras = raw.get("extras") or {}

        pos = raw.get("position_int") or []
        page_idx = int(pos[0][0]) if pos and pos[0] else 0

        inferred = extras.get("inferred_caption", "")
        captions: list[str] = [inferred] if inferred else []

        html: str = extras.get("html", "") or ""

        chunk_dicts.append({
            "page_content":  raw.get("page_content") or "",
            "source":        source,
            "kind":          raw.get("kind") or "text",
            "title_path":    raw.get("title_path") or "",
            "title_level":   int(raw.get("title_level") or 0),
            "chunk_index":   int(raw.get("chunk_index") or 0),
            "reading_order": int(raw.get("reading_order") or 0),
            "prev_chunk":    int(raw["prev_chunk_index"]) if raw.get("prev_chunk_index") is not None else -1,
            "next_chunk":    int(raw["next_chunk_index"]) if raw.get("next_chunk_index") is not None else -1,
            "page_idx":      page_idx,
            "token_count":   int(raw.get("token_count") or 0),
            "html":          html,
            "captions_json": _json.dumps(captions, ensure_ascii=False),
            "footnotes_json": "[]",
            "bboxes_json":   _json.dumps(pos, ensure_ascii=False),
        })

    _cb("Embedding des chunks (Modèle d'embedding)…")
    content_vectors, title_vectors = _embed_content_and_titles(
        chunk_dicts, api_key, embedding_model, _cb
    )

    _cb("Stockage dans Weaviate…")
    n = weaviate_store.insert_chunks(chunk_dicts, content_vectors, title_vectors)
    _cb(f" {n} chunks indexés pour '{jsonl_path.name}'.")
    return n