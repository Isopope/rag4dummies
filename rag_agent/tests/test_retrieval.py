"""Tests approfondis de la couche retrieval.

Couvre :
- content_enrichment.py  (enrichissement de chunks à l'indexation)
- QueryTool              (embedder interface, get_chunk_by_index, execute_as_tool_result)
- Helpers                (_doc_key, _fingerprint_doc, _normalize_chunk_index, _safe_score)
- weighted_rrf           (cas limites : listes vides, poids nul, poids multiples)
- combine_chunks         (priorité score RRF vs score brut)
"""
from __future__ import annotations

import pytest

# ── content_enrichment ────────────────────────────────────────────────────────

from rag_agent.retrieval.content_enrichment import (
    generate_title_text,
    generate_metadata_suffix_semantic,
    generate_metadata_suffix_keyword,
    generate_enriched_content_for_chunk_embedding,
    generate_enriched_content_for_chunk_text,
    enrich_chunk_for_embedding,
    EMBEDDING_VERSION,
)


class TestGenerateTitleText:
    def test_with_title_path(self):
        chunk = {"source": "/docs/budget.pdf", "title_path": "Section 3.2 Dépenses"}
        result = generate_title_text(chunk)
        assert result == "budget.pdf - Section 3.2 Dépenses"

    def test_source_only(self):
        chunk = {"source": "/docs/rapport.pdf", "title_path": ""}
        result = generate_title_text(chunk)
        assert result == "rapport.pdf"

    def test_no_source_no_title(self):
        result = generate_title_text({})
        assert result == "document"

    def test_source_without_extension(self):
        chunk = {"source": "/data/myfile", "title_path": "Titre"}
        result = generate_title_text(chunk)
        assert result == "myfile - Titre"

    def test_empty_source_with_title(self):
        chunk = {"source": "", "title_path": "Annexe A"}
        result = generate_title_text(chunk)
        assert result == "document - Annexe A"

    def test_strips_whitespace(self):
        chunk = {"source": "/docs/a.pdf", "title_path": "  Titre   "}
        result = generate_title_text(chunk)
        assert "Titre" in result


class TestGenerateMetadataSuffixSemantic:
    def test_full_metadata(self):
        chunk = {
            "entity":        "ACME Corp",
            "validity_date": "2024-01-01",
            "kind":          "table",
            "page_idx":      5,
        }
        result = generate_metadata_suffix_semantic(chunk)
        assert "ACME Corp" in result
        assert "2024-01-01" in result
        assert "table" in result
        assert "5" in result

    def test_empty_chunk(self):
        result = generate_metadata_suffix_semantic({})
        assert result == ""

    def test_partial_metadata(self):
        chunk = {"entity": "CompanyX", "kind": "text"}
        result = generate_metadata_suffix_semantic(chunk)
        assert "CompanyX" in result
        assert "text" in result
        assert "Validity" not in result

    def test_page_idx_zero_included(self):
        """page_idx=0 doit être inclus (valeur falsy mais valide)."""
        chunk = {"page_idx": 0}
        result = generate_metadata_suffix_semantic(chunk)
        assert "Page: 0" in result


class TestGenerateMetadataSuffixKeyword:
    def test_full_fields(self):
        chunk = {
            "entity":        "ACME",
            "kind":          "table",
            "validity_date": "2025-06-01",
            "title_path":    "Budget annuel",
        }
        result = generate_metadata_suffix_keyword(chunk)
        assert "ACME" in result
        assert "table" in result
        assert "2025-06-01" in result
        assert "Budget annuel" in result

    def test_empty_chunk(self):
        result = generate_metadata_suffix_keyword({})
        assert result == ""

    def test_returns_single_line_space_separated(self):
        chunk = {"entity": "E", "kind": "K"}
        result = generate_metadata_suffix_keyword(chunk)
        assert "\n" not in result


class TestGenerateEnrichedContentForChunkEmbedding:
    def test_includes_title_prefix(self):
        chunk = {"source": "/docs/loi.pdf", "title_path": "Article 1", "page_content": "Contenu."}
        result = generate_enriched_content_for_chunk_embedding(chunk)
        assert "Title:" in result
        assert "loi.pdf" in result

    def test_includes_page_content(self):
        chunk = {"source": "/docs/a.pdf", "page_content": "Texte important."}
        result = generate_enriched_content_for_chunk_embedding(chunk)
        assert "Texte important." in result

    def test_uses_existing_title_prefix(self):
        chunk = {"title_prefix": "Title: Custom Title", "page_content": "Body."}
        result = generate_enriched_content_for_chunk_embedding(chunk)
        assert "Custom Title" in result

    def test_uses_existing_metadata_suffix(self):
        chunk = {"page_content": "A", "metadata_suffix_semantic": "Entity: ForcedEntity"}
        result = generate_enriched_content_for_chunk_embedding(chunk)
        assert "ForcedEntity" in result

    def test_doc_summary_included(self):
        chunk = {"page_content": "Content.", "doc_summary": "Résumé du document."}
        result = generate_enriched_content_for_chunk_embedding(chunk)
        assert "Résumé du document." in result

    def test_empty_fields_no_separator_artefacts(self):
        """Pas de double séparateur si les champs sont vides."""
        chunk = {"page_content": "Only content."}
        result = generate_enriched_content_for_chunk_embedding(chunk)
        assert "\n\n\n" not in result


class TestGenerateEnrichedContentForChunkText:
    def test_includes_page_content(self):
        chunk = {"source": "/docs/x.pdf", "page_content": "Contenu BM25."}
        result = generate_enriched_content_for_chunk_text(chunk)
        assert "Contenu BM25." in result

    def test_uses_keyword_suffix(self):
        chunk = {"page_content": "A.", "metadata_suffix_keyword": "forced_keyword"}
        result = generate_enriched_content_for_chunk_text(chunk)
        assert "forced_keyword" in result


class TestEnrichChunkForEmbedding:
    def _base_chunk(self) -> dict:
        return {
            "source":       "/docs/contrat.pdf",
            "title_path":   "Clause 5",
            "page_content": "Le vendeur s'engage à…",
            "kind":         "text",
            "entity":       "SARL X",
            "page_idx":     3,
        }

    def test_adds_all_required_fields(self):
        chunk = self._base_chunk()
        result = enrich_chunk_for_embedding(
            chunk,
            embedding_model="text-embedding-3-small",
            embedding_provider="openai",
        )
        assert result["title_text"]               != ""
        assert result["title_prefix"]             != ""
        assert result["metadata_suffix_semantic"] != ""
        assert result["metadata_suffix_keyword"]  != ""
        assert result["embedding_content"]        != ""
        assert result["embedding_model"]          == "text-embedding-3-small"
        assert result["embedding_provider"]       == "openai"
        assert result["embedding_version"]        == EMBEDDING_VERSION
        assert "embedding_created_at"             in result

    def test_returns_same_dict(self):
        """Mutate-and-return : le dict retourné est le même objet."""
        chunk  = self._base_chunk()
        result = enrich_chunk_for_embedding(chunk, embedding_model="m", embedding_provider="p")
        assert result is chunk

    def test_embedding_dim_optional(self):
        chunk = self._base_chunk()
        enrich_chunk_for_embedding(chunk, embedding_model="m", embedding_provider="p", embedding_dim=1536)
        assert chunk["embedding_dim"] == 1536

    def test_custom_embedding_created_at(self):
        chunk = self._base_chunk()
        ts = "2025-01-01T00:00:00Z"
        enrich_chunk_for_embedding(
            chunk, embedding_model="m", embedding_provider="p", embedding_created_at=ts
        )
        assert chunk["embedding_created_at"] == ts

    def test_auto_generated_created_at_format(self):
        chunk = self._base_chunk()
        enrich_chunk_for_embedding(chunk, embedding_model="m", embedding_provider="p")
        ts = chunk["embedding_created_at"]
        assert ts.endswith("Z")
        assert "T" in ts

    def test_existing_doc_summary_preserved(self):
        chunk = self._base_chunk()
        chunk["doc_summary"] = "Résumé important."
        enrich_chunk_for_embedding(chunk, embedding_model="m", embedding_provider="p")
        assert chunk["doc_summary"] == "Résumé important."

    def test_empty_chunk_does_not_raise(self):
        chunk: dict = {}
        enrich_chunk_for_embedding(chunk, embedding_model="m", embedding_provider="p")
        assert "embedding_content" in chunk


# ── QueryTool helpers ─────────────────────────────────────────────────────────

from rag_agent.tools.query import (
    QueryTool,
    weighted_rrf,
    combine_chunks,
    _doc_key,
    _fingerprint_doc,
    _normalize_chunk_index,
    _safe_score,
)
from rag_agent.state import create_unified_state


class TestSafeScore:
    def test_float(self):
        assert _safe_score(0.9) == pytest.approx(0.9)

    def test_string_number(self):
        assert _safe_score("0.5") == pytest.approx(0.5)

    def test_none_returns_zero(self):
        assert _safe_score(None) == 0.0

    def test_invalid_string_returns_zero(self):
        assert _safe_score("not_a_float") == 0.0


class TestNormalizeChunkIndex:
    def test_valid_int(self):
        assert _normalize_chunk_index(42) == 42

    def test_valid_string(self):
        assert _normalize_chunk_index("7") == 7

    def test_none_returns_none(self):
        assert _normalize_chunk_index(None) is None

    def test_empty_string_returns_none(self):
        assert _normalize_chunk_index("") is None

    def test_invalid_string_returns_none(self):
        assert _normalize_chunk_index("abc") is None

    def test_zero(self):
        assert _normalize_chunk_index(0) == 0


class TestFingerprintDoc:
    def test_deterministic(self):
        doc = {"source": "a.pdf", "page_content": "text", "page_idx": 1}
        assert _fingerprint_doc(doc) == _fingerprint_doc(doc)

    def test_different_content_different_fingerprint(self):
        doc1 = {"source": "a.pdf", "page_content": "AAA"}
        doc2 = {"source": "a.pdf", "page_content": "BBB"}
        assert _fingerprint_doc(doc1) != _fingerprint_doc(doc2)

    def test_empty_doc(self):
        result = _fingerprint_doc({})
        assert isinstance(result, str)
        assert len(result) == 40  # sha1 hex


class TestDocKey:
    def test_uuid_takes_priority(self):
        doc = {"uuid": "abc-123", "source": "x.pdf", "chunk_index": 0}
        kind, key = _doc_key(doc)
        assert kind == "uuid"
        assert key == "abc-123"

    def test_id_field(self):
        doc = {"id": "xyz-789", "source": "x.pdf"}
        kind, key = _doc_key(doc)
        assert kind == "id"

    def test_source_chunk_index(self):
        doc = {"source": "a.pdf", "chunk_index": 3}
        kind, key = _doc_key(doc)
        assert kind == "source_chunk"
        assert "a.pdf" in key
        assert "3" in key

    def test_fallback_fingerprint(self):
        doc = {"page_content": "texte unique", "kind": "text"}
        kind, key = _doc_key(doc)
        assert kind == "fallback"

    def test_consistent_for_same_doc(self):
        doc = {"source": "b.pdf", "chunk_index": 5}
        assert _doc_key(doc) == _doc_key(doc)


class TestQueryToolEmbed:
    def test_embed_query_method(self):
        class MockEmbedder:
            def embed_query(self, text):
                return [0.1, 0.2, 0.3]
        tool = QueryTool(weaviate_store=object(), embedder=MockEmbedder())
        result = tool.embed_query("test")
        assert result == [0.1, 0.2, 0.3]

    def test_encode_query_method(self):
        class MockEmbedder:
            def encode_query(self, text):
                return [0.4, 0.5]
        tool = QueryTool(weaviate_store=object(), embedder=MockEmbedder())
        result = tool.embed_query("test")
        assert result == [0.4, 0.5]

    def test_callable_embedder(self):
        def my_embedder(text):
            return [1.0]
        tool = QueryTool(weaviate_store=object(), embedder=my_embedder)
        result = tool.embed_query("test")
        assert result == [1.0]

    def test_no_embedder_raises(self):
        tool = QueryTool(weaviate_store=object(), embedder=None)
        with pytest.raises(RuntimeError, match="embedder"):
            tool.embed_query("test")

    def test_incompatible_embedder_raises(self):
        tool = QueryTool(weaviate_store=object(), embedder=object())
        with pytest.raises(TypeError, match="Embedder incompatible"):
            tool.embed_query("test")


class TestQueryToolMock:
    def test_mock_results_contain_required_fields(self):
        tool = QueryTool()
        docs = tool.execute("contrat de travail")
        for doc in docs:
            assert "page_content" in doc
            assert "chunk_index" in doc
            assert "_score" in doc
            assert "source" in doc

    def test_mock_top_k_respected(self):
        tool = QueryTool()
        assert len(tool.execute("q", top_k=1)) == 1
        assert len(tool.execute("q", top_k=2)) == 2
        assert len(tool.execute("q", top_k=10)) == 3  # mock plafonne à 3

    def test_mock_scores_descending(self):
        tool = QueryTool()
        docs = tool.execute("q", top_k=3)
        scores = [d["_score"] for d in docs]
        assert scores == sorted(scores, reverse=True)

    def test_get_chunk_by_index_mock_returns_none(self):
        tool = QueryTool()
        assert tool.get_chunk_by_index("doc.pdf", 5) is None

    def test_get_chunk_by_index_invalid_range(self):
        """Index hors plage → None même avec un vrai store."""
        mock_store = object()
        tool = QueryTool(weaviate_store=mock_store, embedder=None)
        assert tool.get_chunk_by_index("doc.pdf", -1) is None
        assert tool.get_chunk_by_index("doc.pdf", 200_000) is None


class TestQueryToolExecuteAsToolResult:
    def test_writes_to_environment(self):
        tool  = QueryTool()
        state = create_unified_state("Quelle loi s'applique ?")
        state = tool.execute_as_tool_result(state, search_query="loi applicable", limit=2)
        assert "query" in state["environment"]

    def test_result_objects_have_query(self):
        tool    = QueryTool()
        state   = create_unified_state("Q ?")
        state   = tool.execute_as_tool_result(state, search_query="budget 2024")
        # structure : environment["query"][collection_name] = [ToolResult, ...]
        coll_map = state["environment"]["query"]
        all_results = [r for results in coll_map.values() for r in results]
        assert len(all_results) > 0
        for r in all_results:
            assert r.metadata["search_query"] == "budget 2024"

    def test_uses_state_collection_names(self):
        tool  = QueryTool()
        state = create_unified_state("Q ?")
        state["collection_names"] = ["CustomCollection"]  # type: ignore[index]
        state = tool.execute_as_tool_result(state, search_query="test")
        coll_map = state["environment"]["query"]
        # La collection personnalisée doit être la clé de stockage
        assert "CustomCollection" in coll_map
        all_results = [r for results in coll_map.values() for r in results]
        assert all("CustomCollection" in r.collection_names for r in all_results)

    def test_source_filter_from_state(self):
        tool  = QueryTool()
        state = create_unified_state("Q ?")
        state["source_filter"] = "/docs/specific.pdf"  # type: ignore[index]
        # Mode mock — juste vérifier que ça n'explose pas
        state = tool.execute_as_tool_result(state, search_query="test")
        assert "query" in state["environment"]


# ── weighted_rrf edge cases ───────────────────────────────────────────────────

class TestWeightedRRFEdgeCases:
    def test_empty_lists(self):
        result = weighted_rrf([[], []], [1.0, 1.0])
        assert result == []

    def test_single_empty_list(self):
        docs = [{"source": "a.pdf", "chunk_index": 0, "_score": 0.9}]
        result = weighted_rrf([docs, []], [1.0, 1.0])
        assert len(result) == 1

    def test_weight_zero(self):
        docs = [{"source": "a.pdf", "chunk_index": 0, "_score": 0.9}]
        result = weighted_rrf([docs], [0.0])
        assert result[0]["_score"] == 0.0

    def test_mismatched_lengths_raises(self):
        with pytest.raises(ValueError):
            weighted_rrf([[]], [1.0, 2.0])

    def test_higher_weight_gives_higher_score(self):
        doc_a = [{"source": "a.pdf", "chunk_index": 0, "_score": 0.9}]
        doc_b = [{"source": "b.pdf", "chunk_index": 1, "_score": 0.9}]
        # Même rang (1er dans leur liste) mais poids différents
        result_high = weighted_rrf([doc_a], [2.0])
        result_low  = weighted_rrf([doc_a], [1.0])
        assert result_high[0]["_score"] > result_low[0]["_score"]

    def test_same_doc_across_lists_sums_scores(self):
        doc = {"source": "a.pdf", "chunk_index": 0, "_score": 0.9}
        result_once  = weighted_rrf([[doc]], [1.0])
        result_twice = weighted_rrf([[doc], [doc]], [1.0, 1.0])
        assert result_twice[0]["_score"] > result_once[0]["_score"]

    def test_k_parameter_affects_score(self):
        doc = {"source": "a.pdf", "chunk_index": 0, "_score": 0.9}
        result_k60  = weighted_rrf([[doc]], [1.0], k=60)
        result_k1   = weighted_rrf([[doc]], [1.0], k=1)
        # k plus petit → score plus élevé
        assert result_k1[0]["_score"] > result_k60[0]["_score"]

    def test_output_sorted_by_score_descending(self):
        docs = [
            {"source": "a.pdf", "chunk_index": 0, "_score": 0.3},
            {"source": "b.pdf", "chunk_index": 1, "_score": 0.9},
            {"source": "c.pdf", "chunk_index": 2, "_score": 0.6},
        ]
        result = weighted_rrf([docs], [1.0])
        scores = [d["_score"] for d in result]
        assert scores == sorted(scores, reverse=True)

    def test_preserves_original_fields(self):
        doc = {"source": "a.pdf", "chunk_index": 0, "_score": 0.9, "page_content": "Texte"}
        result = weighted_rrf([[doc]], [1.0])
        assert result[0]["page_content"] == "Texte"


# ── combine_chunks edge cases ─────────────────────────────────────────────────

class TestCombineChunksEdgeCases:
    def test_empty_input(self):
        assert combine_chunks([]) == []

    def test_single_empty_list(self):
        assert combine_chunks([[]]) == []

    def test_prefers_rrf_score_over_raw_score(self):
        """Un doc avec _rrf_score doit être classé via _rrf_score."""
        doc_rrf = {"source": "a.pdf", "chunk_index": 0, "_score": 0.1, "_rrf_score": 0.9}
        doc_raw = {"source": "b.pdf", "chunk_index": 1, "_score": 0.8}
        result = combine_chunks([[doc_rrf, doc_raw]])
        assert result[0]["source"] == "a.pdf"

    def test_keeps_higher_score_on_merge(self):
        doc_high = {"source": "a.pdf", "chunk_index": 0, "_score": 0.9, "page_content": "A"}
        doc_low  = {"source": "a.pdf", "chunk_index": 0, "_score": 0.4, "page_content": "A_old"}
        result = combine_chunks([[doc_low], [doc_high]])
        assert result[0]["_score"] == pytest.approx(0.9)

    def test_meta_fields_carried_over_on_merge(self):
        """Les champs _meta du doc moins bien scoré sont préservés si absents du meilleur."""
        doc_high = {"source": "a.pdf", "chunk_index": 0, "_score": 0.9}
        doc_low  = {"source": "a.pdf", "chunk_index": 0, "_score": 0.4, "_expanded": True}
        result = combine_chunks([[doc_low], [doc_high]])
        # _expanded vient du doc_low mais doit être transféré au vainqueur
        assert result[0].get("_expanded") is True

    def test_multiple_docs_no_dedup(self):
        docs = [
            {"source": "a.pdf", "chunk_index": 0, "_score": 0.9},
            {"source": "b.pdf", "chunk_index": 0, "_score": 0.8},
            {"source": "c.pdf", "chunk_index": 0, "_score": 0.7},
        ]
        result = combine_chunks([docs])
        assert len(result) == 3

    def test_output_sorted_descending(self):
        docs = [
            {"source": "c.pdf", "chunk_index": 2, "_score": 0.3},
            {"source": "a.pdf", "chunk_index": 0, "_score": 0.9},
            {"source": "b.pdf", "chunk_index": 1, "_score": 0.6},
        ]
        result = combine_chunks([docs])
        scores = [d["_score"] for d in result]
        assert scores == sorted(scores, reverse=True)
