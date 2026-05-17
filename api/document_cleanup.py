"""Helpers de suppression cohérente entre DB, Weaviate et document store."""
from __future__ import annotations

import json
from dataclasses import dataclass


class TrackedDocumentNotFoundError(LookupError):
    """Levée quand un document suivi en base est introuvable."""


@dataclass(frozen=True)
class DocumentDeletionResult:
    """Résultat d'une suppression coordonnée."""

    source_path: str
    indexed_sources: tuple[str, ...]
    deleted_db: bool
    deleted_file: bool
    deleted_chunks: int


def _extract_indexed_source_from_jsonl_bytes(content: bytes) -> str | None:
    """Extrait la source logique d'un JSONL ingéré dans Weaviate.

    Le pipeline JSONL stocke parfois les chunks sous une source différente de la
    clé d'objet persistée en DB. On récupère alors la première source déclarée.
    """
    if content.startswith(b"%PDF"):
        return None

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return None

        source = payload.get("source")
        if isinstance(source, str):
            source = source.strip()
            if source:
                return source
        return None

    return None


def indexed_source_candidates(source_path: str, doc_store) -> list[str]:
    """Retourne les sources Weaviate plausibles pour un document suivi."""
    candidates = [source_path]

    try:
        if not doc_store.exists(source_path):
            return candidates
        alt_source = _extract_indexed_source_from_jsonl_bytes(doc_store.download(source_path))
    except Exception:
        return candidates

    if alt_source and alt_source not in candidates:
        candidates.append(alt_source)
    return candidates


async def find_tracked_source_for_indexed_source(indexed_source: str, *, repo, doc_store) -> str | None:
    """Résout une source Weaviate vers la clé source_path suivie en DB si possible."""
    if await repo.get_by_source(indexed_source) is not None:
        return indexed_source

    for source_path in await repo.list_source_paths():
        if indexed_source in indexed_source_candidates(source_path, doc_store)[1:]:
            return source_path

    return None


async def delete_tracked_document(
    source_path: str,
    *,
    repo,
    db_session,
    doc_store,
    weaviate_store,
    require_db_record: bool = True,
) -> DocumentDeletionResult:
    """Supprime un document suivi dans toutes les surfaces du système.

    La suppression externe (Weaviate + object store) est effectuée avant le
    commit SQL pour éviter un état DB « supprimé » alors que les chunks restent.
    """
    doc = await repo.get_by_source(source_path)
    if doc is None and require_db_record:
        raise TrackedDocumentNotFoundError(source_path)

    candidates = indexed_source_candidates(source_path, doc_store)
    deleted_chunks = 0
    for indexed_source in candidates:
        deleted_chunks += int(weaviate_store.delete_source(indexed_source) or 0)

    deleted_file = False
    if doc_store.exists(source_path):
        doc_store.delete(source_path)
        deleted_file = True

    deleted_db = False
    if doc is not None:
        deleted_db = await repo.delete_by_source(source_path)
        if deleted_db:
            await db_session.commit()

    return DocumentDeletionResult(
        source_path=source_path,
        indexed_sources=tuple(candidates),
        deleted_db=deleted_db,
        deleted_file=deleted_file,
        deleted_chunks=deleted_chunks,
    )