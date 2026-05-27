"""Tests unitaires pour rag_agent/utils/citations.py."""
from __future__ import annotations

import pytest

from rag_agent.utils.citations import (
    CitationInfo,
    build_citation_infos,
    extract_cited_docs,
    extract_cited_indices,
    hyperlink_citations,
    sanitize_citations,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def docs():
    return [
        {"source": "/docs/rh.pdf",       "page_idx": 1, "title_path": "Section RH",  "page_content": "contenu rh"},
        {"source": "/docs/finance.pdf",   "page_idx": 3, "title_path": "Budget 2024", "page_content": "contenu finance"},
        {"source": "/docs/legal.pdf",     "page_idx": 0, "title_path": "",            "page_content": "contenu legal"},
    ]


# ── extract_cited_indices ─────────────────────────────────────────────────────

def test_extract_basic():
    assert extract_cited_indices("Voir [1] et [2].") == [1, 2]

def test_extract_deduplication():
    assert extract_cited_indices("[1] puis encore [1] et [2]") == [1, 2]

def test_extract_order_preserved():
    assert extract_cited_indices("[3] avant [1] puis [2]") == [3, 1, 2]

def test_extract_empty():
    assert extract_cited_indices("aucune citation ici") == []

def test_extract_consecutive():
    assert extract_cited_indices("[1][2][3]") == [1, 2, 3]


# ── sanitize_citations ────────────────────────────────────────────────────────

def test_sanitize_valid_kept():
    assert "[1]" in sanitize_citations("Valide [1].", n_docs=3)
    assert "[3]" in sanitize_citations("Valide [3].", n_docs=3)

def test_sanitize_out_of_range_removed():
    result = sanitize_citations("Fantôme [99].", n_docs=3)
    assert "[99]" not in result
    assert "Fantôme" in result

def test_sanitize_zero_docs():
    result = sanitize_citations("[1] et [2]", n_docs=0)
    assert "[1]" not in result
    assert "[2]" not in result

def test_sanitize_boundary():
    assert "[3]" in sanitize_citations("[3]", n_docs=3)
    assert "[4]" not in sanitize_citations("[4]", n_docs=3)


# ── build_citation_infos ─────────────────────────────────────────────────────

def test_build_basic(docs):
    answer = "Résultat [1] et [3]."
    infos = build_citation_infos(answer, docs)
    assert len(infos) == 2
    assert infos[0].citation_number == 1
    assert infos[0].source == "rh.pdf"
    assert infos[0].page_idx == 1
    assert infos[0].title_path == "Section RH"
    assert infos[1].citation_number == 3
    assert infos[1].source == "legal.pdf"

def test_build_out_of_range_ignored(docs):
    infos = build_citation_infos("[99] hors plage", docs)
    assert infos == []

def test_build_no_citations(docs):
    assert build_citation_infos("Pas de citations.", docs) == []

def test_build_dedup(docs):
    infos = build_citation_infos("[1] texte [1] encore", docs)
    assert len(infos) == 1

def test_build_document_id(docs):
    infos = build_citation_infos("[2]", docs)
    assert infos[0].document_id == "/docs/finance.pdf"

def test_build_to_dict(docs):
    infos = build_citation_infos("[1]", docs)
    d = infos[0].to_dict()
    assert d["citation_number"] == 1
    assert "source" in d


# ── extract_cited_docs ────────────────────────────────────────────────────────

def test_extract_cited_docs_basic(docs):
    cited = extract_cited_docs("[1] et [3]", docs)
    assert len(cited) == 2
    assert cited[0]["source"] == "/docs/rh.pdf"
    assert cited[1]["source"] == "/docs/legal.pdf"

def test_extract_cited_docs_empty(docs):
    assert extract_cited_docs("aucune citation", docs) == []

def test_extract_cited_docs_out_of_range(docs):
    assert extract_cited_docs("[99]", docs) == []


# ── hyperlink_citations ───────────────────────────────────────────────────────

@pytest.fixture
def citation_infos_list(docs):
    return build_citation_infos("[1] et [2] et [3]", docs)

def test_hyperlink_replaces(citation_infos_list):
    url_map = {
        "/docs/rh.pdf":      "https://minio/rh.pdf?token=abc",
        "/docs/finance.pdf": "https://minio/finance.pdf?token=xyz",
    }
    result = hyperlink_citations("[1] et [2]", citation_infos_list, url_map)
    assert "[[1]](https://minio/rh.pdf?token=abc)" in result
    assert "[[2]](https://minio/finance.pdf?token=xyz)" in result

def test_hyperlink_no_url_kept(citation_infos_list):
    # [3] → legal.pdf, pas dans url_map → conservé tel quel
    result = hyperlink_citations("[3]", citation_infos_list, {})
    assert result == "[3]"

def test_hyperlink_empty_url_map(citation_infos_list):
    result = hyperlink_citations("Voir [1] et [2].", citation_infos_list, {})
    assert result == "Voir [1] et [2]."

def test_hyperlink_partial_url_map(citation_infos_list):
    url_map = {"/docs/rh.pdf": "https://minio/rh.pdf"}
    result = hyperlink_citations("[1] et [2]", citation_infos_list, url_map)
    assert "[[1]](https://minio/rh.pdf)" in result
    assert "[2]" in result
    assert "[[2]]" not in result

def test_hyperlink_accepts_dicts(docs):
    """hyperlink_citations doit accepter des dicts (pas seulement des CitationInfo)."""
    infos = [{"citation_number": 1, "document_id": "/docs/rh.pdf"}]
    url_map = {"/docs/rh.pdf": "https://url"}
    result = hyperlink_citations("[1]", infos, url_map)
    assert "[[1]](https://url)" in result
