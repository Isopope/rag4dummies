"""Logique de citations inline pour le pipeline RAG.

Fournit un mode unique HYPERLINK : [N] → [[N]](presigned_url).
Le post-traitement se fait sur la réponse complète (pas de streaming token-by-token).

Usage typique dans generate() :
    answer   = sanitize_citations(raw_answer, len(docs))
    infos    = build_citation_infos(answer, docs)
    cited    = extract_cited_docs(answer, docs)

Usage dans le router (url disponibles) :
    url_map  = {c.source: c.pdf_url for c in sources if c.pdf_url}
    answer_hl = hyperlink_citations(answer, infos, url_map)
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


# ── Dataclass ─────────────────────────────────────────────────────────────────

@dataclass
class CitationInfo:
    """Métadonnées d'une citation [N] utilisée dans la réponse du LLM."""

    citation_number: int
    """Numéro tel qu'il apparaît dans la réponse : [1] → 1."""

    document_id: str
    """Chemin complet de la source (équivalent Onyx document_id)."""

    source: str
    """Nom de fichier (basename de document_id)."""

    page_idx: int
    """Index de page 0-based (0 = inconnu)."""

    title_path: str
    """Titre de section, ou chaîne vide."""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Regex ─────────────────────────────────────────────────────────────────────

_CITATION_RE = re.compile(r"\[(\d+)\]")
"""Détecte les marqueurs [N] dans la réponse du LLM."""

_HYPERLINK_RE = re.compile(r"\[(\d+)\]")
"""Même pattern — utilisé séparément pour la substitution hyperlink."""


# ── Fonctions publiques ────────────────────────────────────────────────────────

def extract_cited_indices(answer: str) -> list[int]:
    """Retourne la liste ordonnée (sans doublons) des indices [N] présents.

    L'ordre de première apparition est préservé.

    >>> extract_cited_indices("Voir [1] et [2], puis encore [1].")
    [1, 2]
    """
    seen: set[int] = set()
    result: list[int] = []
    for m in _CITATION_RE.finditer(answer):
        n = int(m.group(1))
        if n not in seen:
            seen.add(n)
            result.append(n)
    return result


def sanitize_citations(answer: str, n_docs: int) -> str:
    """Supprime silencieusement les marqueurs [N] hors plage 1..n_docs.

    Évite d'exposer des références fantômes inventées par le LLM.
    Les marqueurs valides ([1] à [n_docs]) sont conservés tels quels.

    >>> sanitize_citations("OK [1] mais [99] fantôme.", 2)
    'OK [1] mais  fantôme.'
    """
    if n_docs <= 0:
        return _CITATION_RE.sub("", answer)

    def _replace(m: re.Match) -> str:
        n = int(m.group(1))
        return m.group(0) if 1 <= n <= n_docs else ""

    return _CITATION_RE.sub(_replace, answer)


def build_citation_infos(answer: str, docs: list[dict]) -> list[CitationInfo]:
    """Construit la liste des CitationInfo pour chaque [N] valide dans la réponse.

    L'ordre correspond à l'ordre de première apparition dans `answer`.
    Les indices hors plage sont ignorés silencieusement.

    Args:
        answer: Réponse déjà sanitisée du LLM.
        docs:   Liste des chunks (dicts) envoyés au LLM (1-indexés).

    Returns:
        Liste de CitationInfo dans l'ordre d'apparition.
    """
    infos: list[CitationInfo] = []
    for n in extract_cited_indices(answer):
        if 1 <= n <= len(docs):
            doc = docs[n - 1]
            infos.append(CitationInfo(
                citation_number = n,
                document_id     = doc.get("source", ""),
                source          = Path(doc.get("source", "inconnu")).name,
                page_idx        = doc.get("page_idx", 0),
                title_path      = (doc.get("title_path") or "").strip(),
            ))
    return infos


def extract_cited_docs(answer: str, docs: list[dict]) -> list[dict]:
    """Retourne les chunks effectivement cités [N] dans la réponse.

    Ordre : ordre de première apparition dans `answer`.
    """
    indices = extract_cited_indices(answer)
    return [docs[i - 1] for i in indices if 1 <= i <= len(docs)]


def hyperlink_citations(
    answer: str,
    citation_infos: list[CitationInfo] | list[dict],
    url_map: dict[str, str],
) -> str:
    """Remplace chaque [N] par [[N]](url) si une presigned URL est disponible.

    Si `url_map` ne contient pas la source du chunk N, le marqueur [N] est
    conservé tel quel (pas de lien cassé).

    Args:
        answer:         Réponse du LLM (sanitisée).
        citation_infos: Liste de CitationInfo (ou dicts équivalents) produite
                        par build_citation_infos().
        url_map:        Mapping {source_path: presigned_url}.

    Returns:
        Réponse avec les citations transformées en liens Markdown.

    >>> hyperlink_citations("[1] est cité.", [CitationInfo(1, "/f.pdf", "f.pdf", 0, "")], {"/f.pdf": "https://..."})
    '[[1]](https://...) est cité.'
    """
    # Construire le mapping number → url
    num_to_url: dict[int, str] = {}
    for info in citation_infos:
        if isinstance(info, dict):
            num  = info.get("citation_number", 0)
            src  = info.get("document_id", "")
        else:
            num  = info.citation_number
            src  = info.document_id
        url = url_map.get(src, "")
        if url:
            num_to_url[num] = url

    if not num_to_url:
        return answer

    def _replace(m: re.Match) -> str:
        n = int(m.group(1))
        url = num_to_url.get(n)
        return f"[[{n}]]({url})" if url else m.group(0)

    return _HYPERLINK_RE.sub(_replace, answer)
