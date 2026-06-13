"""Ingesteur documents → chunks → embeddings OpenAI → Weaviate.

Deux modes selon ce qui est installé :
  • openingestion  (défaut) — pipeline complet DoclingChef / MinerUChef + chunker
  • simple         (fallback) — extraction page par page avec PyMuPDF + découpage naïf

Embeddings : OpenAI Embeddings (text-embedding-3-small, text-embedding-3-large, etc.)
Pipeline Onyx-aligned : content_vector séparé de title_vector, enrichissement invisible.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from loguru import logger

from rag_agent.retrieval.content_enrichment import enrich_chunk_for_embedding


# ── embedding helper ──────────────────────────────────────────────────────────


def _default_api_base() -> str | None:
    return os.getenv("LITELLM_API_BASE") or os.getenv("OPENAI_API_BASE") or None


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return float(raw)


@dataclass(frozen=True)
class _IngestionRefineryConfig:
    use_vision_refinery: bool
    use_contextual_rag: bool
    model: str
    api_base: str | None
    timeout: float
    vision_detail: str

    @property
    def enabled(self) -> bool:
        return self.use_vision_refinery or self.use_contextual_rag


def _load_ingestion_refinery_config() -> _IngestionRefineryConfig:
    use_vision_refinery = _env_flag("USE_INGEST_VISION_REFINERY", False)
    use_contextual_rag = _env_flag("USE_INGEST_CONTEXTUAL_RAG", False)
    timeout = _env_float("LLM_TIMEOUT", 60.0)
    vision_detail = "low"
    if use_vision_refinery or use_contextual_rag:
        timeout = _env_float("INGEST_REFINERY_TIMEOUT", timeout)
        vision_detail = os.getenv("INGEST_VISION_DETAIL", "low").strip().lower()

    config = _IngestionRefineryConfig(
        use_vision_refinery=use_vision_refinery,
        use_contextual_rag=use_contextual_rag,
        model=os.getenv("INGEST_REFINERY_MODEL") or os.getenv("LLM_MODEL", "gpt-4.1-mini"),
        api_base=_default_api_base(),
        timeout=timeout,
        vision_detail=vision_detail,
    )
    if config.enabled and config.timeout <= 0:
        raise ValueError("INGEST_REFINERY_TIMEOUT doit être strictement positif.")
    if config.use_vision_refinery and config.vision_detail not in {"low", "high", "auto"}:
        raise ValueError(
            "INGEST_VISION_DETAIL doit valoir 'low', 'high' ou 'auto'."
        )
    return config


def _extract_message_text(response) -> str:
    content = response.choices[0].message.content
    if isinstance(content, str):
        text = content.strip()
        if text:
            return text
    elif isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        text = "\n".join(part.strip() for part in parts if part and part.strip()).strip()
        if text:
            return text
    raise ValueError("Le provider LLM a renvoyé une réponse vide.")


class _OpenAICompatibleGenie:
    def __init__(
        self,
        *,
        model: str,
        api_key: str | None,
        api_base: str | None,
        timeout: float,
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError(
                "Le raffinage OpenAI nécessite le package 'openai'."
            ) from exc

        client_kwargs: dict[str, object] = {
            "api_key": api_key,
            "timeout": timeout,
        }
        if api_base:
            client_kwargs["base_url"] = api_base

        self.model = model
        self._client = OpenAI(**client_kwargs)

    def generate(self, prompt: str, max_tokens: int | None = None) -> str:
        from llm.usage import record_completion_usage

        kwargs: dict[str, object] = {}
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        response = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )
        record_completion_usage(self.model, response)
        return _extract_message_text(response)

    def generate_contextual(
        self,
        context: str,
        prompt: str,
        max_tokens: int | None = None,
    ) -> str:
        return self.generate(context + prompt, max_tokens=max_tokens)

    def generate_vision(
        self,
        prompt: str,
        image_b64: str,
        detail: str = "auto",
        system: str = "",
    ) -> str:
        from llm.usage import record_completion_usage

        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": image_b64, "detail": detail},
                    },
                ],
            }
        )

        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
        )
        record_completion_usage(self.model, response)
        return _extract_message_text(response)


class _LiteLLMGenie:
    def __init__(
        self,
        *,
        model: str,
        api_key: str | None,
        api_base: str | None,
        timeout: float,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.api_base = api_base
        self.timeout = timeout

    def generate(self, prompt: str, max_tokens: int | None = None) -> str:
        from llm.factory import get_llm_completion

        response = get_llm_completion(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=max_tokens or 1000,
            timeout=self.timeout,
            api_key=self.api_key,
            api_base=self.api_base,
        )
        return _extract_message_text(response)

    def generate_contextual(
        self,
        context: str,
        prompt: str,
        max_tokens: int | None = None,
    ) -> str:
        return self.generate(context + prompt, max_tokens=max_tokens)

    def generate_vision(
        self,
        prompt: str,
        image_b64: str,
        detail: str = "auto",
        system: str = "",
    ) -> str:
        from llm.factory import get_llm_completion

        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": image_b64, "detail": detail},
                    },
                ],
            }
        )
        response = get_llm_completion(
            model=self.model,
            messages=messages,
            temperature=0,
            max_tokens=1000,
            timeout=self.timeout,
            api_key=self.api_key,
            api_base=self.api_base,
        )
        return _extract_message_text(response)


def _resolve_refinery_api_key(model: str, fallback_api_key: str) -> str | None:
    from rag_agent.config import RAGConfig

    provider = RAGConfig._detect_llm_provider(model)
    provider_env_keys = {
        "openai": ("OPENAI_API_KEY",),
        "anthropic": ("ANTHROPIC_API_KEY",),
        "mistral": ("MISTRAL_API_KEY",),
        "google": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    }

    for env_name in provider_env_keys.get(provider, ()):
        value = os.getenv(env_name)
        if value:
            return value

    if fallback_api_key:
        return fallback_api_key

    return os.getenv("OPENAI_API_KEY") or None


def _build_refinery_genie(
    config: _IngestionRefineryConfig,
    *,
    api_key: str,
):
    from rag_agent.config import RAGConfig

    provider = RAGConfig._detect_llm_provider(config.model)
    resolved_api_key = _resolve_refinery_api_key(config.model, api_key)
    use_openai_client = provider == "openai" or (
        provider == "unknown" and config.api_base is not None
    )

    if use_openai_client:
        return _OpenAICompatibleGenie(
            model=config.model,
            api_key=resolved_api_key,
            api_base=config.api_base,
            timeout=config.timeout,
        )

    return _LiteLLMGenie(
        model=config.model,
        api_key=resolved_api_key,
        api_base=config.api_base,
        timeout=config.timeout,
    )


def _apply_openingestion_refineries(
    chunks,
    *,
    api_key: str,
    progress_cb: Callable[[str], None] | None = None,
):
    config = _load_ingestion_refinery_config()
    if not config.enabled:
        return chunks

    _cb = progress_cb or (lambda _msg: None)
    genie = _build_refinery_genie(config, api_key=api_key)

    if config.use_vision_refinery:
        try:
            from openingestion.refinery.vision import VisionRefinery
        except ImportError as exc:
            raise RuntimeError(
                "USE_INGEST_VISION_REFINERY nécessite openingestion.refinery.vision."
            ) from exc
        _cb(f"Raffinage vision des chunks via {config.model}…")
        chunks = VisionRefinery(
            genie=genie,
            image_detail=config.vision_detail,
        ).enrich(chunks)

    if config.use_contextual_rag:
        try:
            from openingestion.refinery.contextual_rag import ContextualRagRefinery
        except ImportError as exc:
            raise RuntimeError(
                "USE_INGEST_CONTEXTUAL_RAG nécessite openingestion.refinery.contextual_rag."
            ) from exc
        _cb(f"Raffinage contextual RAG des chunks via {config.model}…")
        chunks = ContextualRagRefinery(genie=genie).enrich(chunks)

    return chunks

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
        api_base=_default_api_base(),
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
    document_path: Path,
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

    progress_cb(f"Parsing '{document_path.name}' avec {parser} / {strategy}…")

    mineru_tmp = Path(tempfile.mkdtemp(prefix="mineru_out_"))
    try:
        chunks = ingest(
            document_path,
            parser=parser,
            strategy=strategy,
            image_mode="path",
            mineru_output_dir=mineru_tmp,
        )
        chunks = _apply_openingestion_refineries(
            chunks,
            api_key=api_key,
            progress_cb=progress_cb,
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
            "doc_summary":   getattr(c, "doc_summary", "") or "",
            "chunk_context": getattr(c, "chunk_context", "") or "",
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


# ── mode fallback robuste (extraction façon Onyx + openingestion chunker) ────────
#
# Architecture (cf. module ``parsing/`` inspiré de file_processing d'Onyx) :
#   [1] Extraction par dispatch de format → ExtractionResult page-aware
#       (texte à plat + images + metadata), via parsing.extract.extract_document
#   [2] Description vision optionnelle des images (option d'enrichissement)
#   [3] Conversion en ContentBlock page-aware (parsing.blocks)
#   [4] Chunking by_sentence via openingestion.SentenceChunker
#   [5] Conversion RagChunk → chunk dict Weaviate

_SIMPLE_FALLBACK_FORMATS = {".pdf", ".docx", ".pptx", ".xlsx", ".txt"}


# ── Description vision ────────────────────────────────────────────────────────

def _describe_images(
    images: list[tuple[bytes, str, int]],
    api_key: str,
) -> list[tuple[str, int]]:
    """Retourne (description, page_idx) pour chaque image.

    Si USE_INGEST_VISION_REFINERY=false, retourne un placeholder sans appel LLM.
    """
    import base64

    config = _load_ingestion_refinery_config()
    results: list[tuple[str, int]] = []

    for img_bytes, mime, page_idx in images:
        if not config.use_vision_refinery:
            results.append((f"[Image p. {page_idx + 1}]", page_idx))
            continue

        try:
            genie = _build_refinery_genie(config, api_key=api_key)
            b64 = base64.b64encode(img_bytes).decode()
            image_url = f"data:{mime};base64,{b64}"
            description = genie.generate_vision(
                prompt="Décris précisément le contenu de cette image dans le contexte d'un document professionnel.",
                image_b64=image_url,
                detail=config.vision_detail,
            )
            results.append((description.strip() or f"[Image p. {page_idx + 1}]", page_idx))
        except Exception as exc:
            logger.warning("Description vision image p.{} échouée : {}", page_idx, exc)
            results.append((f"[Image p. {page_idx + 1}]", page_idx))

    return results


# ── Conversion RagChunk → dict ───────────────────────────────────────────────

def _rag_chunks_to_dicts(
    rag_chunks,
    source: str,
    entity: str | None,
    validity_date: str | None,
) -> list[dict]:
    """Convertit list[RagChunk] en list[chunk dict] compatible Weaviate."""
    import json

    # Filtre les chunks vides (blocs TITLE isolés sans contenu textuel)
    non_empty = [rc for rc in rag_chunks if rc.page_content.strip()]

    chunk_dicts = []
    for i, rc in enumerate(non_empty):
        kind_str = rc.kind.value if hasattr(rc.kind, "value") else str(rc.kind).lower()
        page_idx = rc.position_int[0][0] if rc.position_int else 0
        bboxes = rc.position_int or []

        chunk_dicts.append({
            "page_content":   rc.page_content,
            "source":         source,
            "kind":           kind_str,
            "title_path":     rc.title_path or "",
            "title_level":    rc.title_level,
            "chunk_index":    i,
            "reading_order":  rc.reading_order,
            "prev_chunk":     i - 1,
            "next_chunk":     i + 1 if i < len(non_empty) - 1 else -1,
            "page_idx":       page_idx,
            "token_count":    rc.token_count or max(1, len(rc.page_content.split())),
            "html":           rc.extras.get("html", "") if rc.extras else "",
            "captions_json":  "[]",
            "footnotes_json": "[]",
            "bboxes_json":    json.dumps(bboxes),
            "entity":         entity or "",
            **({"validity_date": validity_date} if validity_date else {}),
        })

    return chunk_dicts


def _naive_chunk_segments(
    result,
    image_descriptions: list[tuple[str, int]],
    source: str,
    entity: str | None,
    validity_date: str | None,
) -> list[dict]:
    """Dernier recours (800 chars) si openingestion.SentenceChunker est absent.

    Préserve le ``page_idx`` de chaque segment. N'est utilisé que si le chunker
    by_sentence ne peut pas être importé — le chemin normal reste toujours
    by_sentence.
    """
    pieces: list[tuple[str, int]] = [(seg.text, seg.page_idx) for seg in result.segments]
    pieces.extend((desc, page_idx) for desc, page_idx in image_descriptions)

    chunk_dicts: list[dict] = []
    idx = 0
    for text, page_idx in pieces:
        for start in range(0, len(text), 800):
            block = text[start : start + 800].strip()
            if not block:
                continue
            chunk_dicts.append({
                "page_content":   block,
                "source":         source,
                "kind":           "text",
                "title_path":     "",
                "title_level":    0,
                "chunk_index":    idx,
                "reading_order":  idx,
                "prev_chunk":     idx - 1,
                "next_chunk":     idx + 1,
                "page_idx":       page_idx,
                "token_count":    max(1, len(block.split())),
                "html":           "",
                "captions_json":  "[]",
                "footnotes_json": "[]",
                "bboxes_json":    "[]",
                "entity":         entity or "",
                **({"validity_date": validity_date} if validity_date else {}),
            })
            idx += 1
    if chunk_dicts:
        chunk_dicts[-1]["next_chunk"] = -1
    return chunk_dicts


def _ingest_simple(
    document_path: Path,
    source: str,
    api_key: str,
    embedding_model: str,
    chunk_size: int = 512,
    progress_cb: Callable[[str], None] | None = None,
    entity: str | None = None,
    validity_date: str | None = None,
) -> tuple[list[dict], list[list[float]], list[list[float]]]:
    """Fallback robuste : extraction façon Onyx + chunking by_sentence.

    Délègue l'extraction au module ``parsing/`` (dispatch par format, texte à
    plat page-aware + images + metadata), décrit optionnellement les images via
    un modèle de vision, convertit en ContentBlock, puis chunke avec le
    SentenceChunker d'openingestion (stratégie by_sentence) pour préserver les
    frontières de phrases et la hiérarchie des titres (title_path). Le
    ``page_idx`` est conservé jusqu'au chunk pour le visual grounding.
    """
    from parsing.extract import SUPPORTED_EXTENSIONS, extract_document
    from parsing.blocks import extraction_to_content_blocks

    _cb = progress_cb or (lambda m: None)
    ext = document_path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise RuntimeError(f"Format non supporté en mode simple : {ext or 'sans extension'}")

    # ── [1] Extraction (dispatch robuste façon Onyx) ──────────────────────────
    _cb(f"Extraction '{document_path.name}' (mode simple)…")
    result = extract_document(document_path)
    n_titles = sum(1 for s in result.segments if s.is_title)
    _cb(
        f"  {len(result.segments)} segment(s), {n_titles} titre(s), "
        f"{len(result.images)} image(s)."
    )

    # ── [2] Descriptions vision (option d'enrichissement) ─────────────────────
    image_descriptions: list[tuple[str, int]] = []
    if result.images:
        config = _load_ingestion_refinery_config()
        action = "vision LLM" if config.use_vision_refinery else "placeholders"
        _cb(f"  Traitement images ({action})…")
        image_descriptions = _describe_images(
            [(img.data, img.mime, img.page_idx) for img in result.images],
            api_key,
        )

    # ── [3] Chunking by_sentence (chemin normal) ──────────────────────────────
    try:
        from openingestion.chunker.by_sentence import SentenceChunker as _OISentenceChunker
        _chunker_ok = True
    except ImportError:
        _chunker_ok = False
        logger.warning(
            "openingestion.SentenceChunker absent — fallback 800-chars (dernier recours)."
        )

    if _chunker_ok:
        blocks = extraction_to_content_blocks(result, image_descriptions)
        if not blocks:
            _cb("  Aucun contenu exploitable extrait.")
            return [], [], []
        _cb(f"Chunking par phrases (chunk_size={chunk_size} tokens)…")
        chunker = _OISentenceChunker(chunk_size=chunk_size, chunk_overlap=0)
        rag_chunks = chunker(blocks, source=source)
        _cb(f"  {len(rag_chunks)} chunks créés (mode simple + by_sentence).")
        chunk_dicts = _rag_chunks_to_dicts(rag_chunks, source, entity, validity_date)
    else:
        _cb("Chunking naïf (fallback 800 chars)…")
        chunk_dicts = _naive_chunk_segments(
            result, image_descriptions, source, entity, validity_date
        )
        _cb(f"  {len(chunk_dicts)} chunks créés (fallback naïf).")

    if not chunk_dicts:
        return [], [], []

    # ── [4] Embedding (inchangé) ──────────────────────────────────────────────
    _cb("Embedding des chunks (Modèle d'embedding)…")
    content_vectors, title_vectors = _embed_content_and_titles(
        chunk_dicts, api_key, embedding_model, _cb
    )

    return chunk_dicts, content_vectors, title_vectors


# ── point d'entrée public ─────────────────────────────────────────────────────

def _supports_simple_fallback(file_path: Path) -> bool:
    return file_path.suffix.lower() in _SIMPLE_FALLBACK_FORMATS


def ingest_document(
    file_path: Path,
    weaviate_store,
    api_key: str,
    embedding_model: str = "text-embedding-3-small",
    chunking_strategy: str = "by_sentence",
    parser: str = "docling",
    progress_cb: Callable[[str], None] | None = None,
    force_simple: bool = False,
    source_override: str | None = None,
    entity: str | None = None,
    validity_date: str | None = None,
) -> int:
    """Parse un document, embed ses chunks via OpenAI Embeddings et les stocke dans Weaviate.

    Parameters
    ----------
    file_path:
        Chemin vers le fichier à ingérer.
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
        Si True, utilise le mode d'extraction simple (façon Onyx) même si le
        pipeline openingestion mineru/docling est disponible.
        Supporte : PDF, DOCX, PPTX, XLSX, TXT.
    source_override:
        Si renseigné, remplace la valeur par défaut (chemin absolu du document)
        pour le champ ``source`` stocké dans Weaviate.  Utilisé par l'API
        pour stocker la clé MinIO (ex. ``abc12345-mon-doc.docx``) plutôt que
        le chemin local éphémère.

    Returns
    -------
    int
        Nombre de chunks stockés.
    """
    _cb = progress_cb or (lambda msg: logger.info(msg))
    if force_simple and not _supports_simple_fallback(file_path):
        raise ValueError(
            "Le parser simple ne supporte que : PDF, DOCX, PPTX, XLSX, TXT."
        )

    source = source_override or str(file_path.resolve())
    rfc3339_date: str | None = f"{validity_date}T00:00:00Z" if validity_date else None

    # Supprimer les éventuels chunks existants pour ce fichier
    weaviate_store.delete_source(source)

    if force_simple:
        chunk_dicts, content_vectors, title_vectors = _ingest_simple(
            file_path,
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
                file_path, source, parser, chunking_strategy,
                api_key, embedding_model, _cb,
                entity=entity,
                validity_date=rfc3339_date,
            )
        except ImportError as _oi_exc:
            logger.warning(
                "openingestion ImportError (détail) : {}", _oi_exc
            )
            if not _supports_simple_fallback(file_path):
                raise RuntimeError(
                    f"openingestion est requis pour ingérer les fichiers '{file_path.suffix.lower() or 'sans extension'}'."
                )
            logger.warning(
                "openingestion introuvable — passage en mode simple (PyMuPDF)."
            )
            _cb(" openingestion non installé, mode simple activé.")
            chunk_dicts, content_vectors, title_vectors = _ingest_simple(
                file_path,
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
    _cb(f" {n} chunks indexés pour '{file_path.name}'.")
    return n


def ingest_pdf(
    pdf_path: Path,
    weaviate_store,
    api_key: str,
    embedding_model: str = "text-embedding-3-small",
    chunking_strategy: str = "by_sentence",
    parser: str = "docling",
    progress_cb: Callable[[str], None] | None = None,
    force_simple: bool = False,
    source_override: str | None = None,
    entity: str | None = None,
    validity_date: str | None = None,
) -> int:
    """Alias rétrocompatible vers ingest_document pour les chemins historiques."""
    return ingest_document(
        file_path=pdf_path,
        weaviate_store=weaviate_store,
        api_key=api_key,
        embedding_model=embedding_model,
        chunking_strategy=chunking_strategy,
        parser=parser,
        progress_cb=progress_cb,
        force_simple=force_simple,
        source_override=source_override,
        entity=entity,
        validity_date=validity_date,
    )


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
            "doc_summary":   raw.get("doc_summary") or "",
            "chunk_context": raw.get("chunk_context") or "",
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
