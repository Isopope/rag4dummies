from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import ingestor


class _FakeChunk:
    def __init__(self) -> None:
        self.page_content = "original content"
        self.source = "fake-source"
        self.kind = SimpleNamespace(value="table")
        self.title_path = "Titre"
        self.title_level = 1
        self.position_int = [[0, 10, 20, 30, 40]]
        self.extras = {"html": "<table></table>", "captions": ["caption"], "footnotes": ["note"]}
        self.chunk_index = 0
        self.reading_order = 0
        self.prev_chunk_index = None
        self.next_chunk_index = None
        self.token_count = 42
        self.doc_summary = ""
        self.chunk_context = ""


def _install_fake_openingestion(monkeypatch, fake_ingest) -> None:
    root_module = ModuleType("openingestion")
    refinery_module = ModuleType("openingestion.refinery")
    root_module.ingest = fake_ingest
    root_module.refinery = refinery_module
    monkeypatch.setitem(sys.modules, "openingestion", root_module)
    monkeypatch.setitem(sys.modules, "openingestion.refinery", refinery_module)


def test_openai_compatible_genie_generate_vision_uses_multimodal_messages(monkeypatch):
    captured: dict = {}

    class FakeOpenAI:
        def __init__(self, **kwargs) -> None:
            captured["client_kwargs"] = kwargs
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=self._create)
            )

        def _create(self, **kwargs):
            captured["create_kwargs"] = kwargs
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="vision result"))]
            )

    openai_module = ModuleType("openai")
    openai_module.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", openai_module)

    import llm.usage as usage

    usage_calls: list[tuple[str, object]] = []
    monkeypatch.setattr(
        usage,
        "record_completion_usage",
        lambda model, response: usage_calls.append((model, response)),
    )

    genie = ingestor._OpenAICompatibleGenie(
        model="gpt-4.1-mini",
        api_key="secret",
        api_base="https://example.test/v1",
        timeout=12.5,
    )

    result = genie.generate_vision(
        prompt="décrire le schéma",
        image_b64="data:image/png;base64,abc",
        detail="high",
        system="réponds en français",
    )

    assert result == "vision result"
    assert captured["client_kwargs"]["api_key"] == "secret"
    assert captured["client_kwargs"]["base_url"] == "https://example.test/v1"
    assert captured["client_kwargs"]["timeout"] == 12.5
    assert captured["create_kwargs"]["model"] == "gpt-4.1-mini"
    assert captured["create_kwargs"]["messages"][0] == {"role": "system", "content": "réponds en français"}
    assert captured["create_kwargs"]["messages"][1]["content"][0]["text"] == "décrire le schéma"
    assert captured["create_kwargs"]["messages"][1]["content"][1]["image_url"]["url"] == "data:image/png;base64,abc"
    assert captured["create_kwargs"]["messages"][1]["content"][1]["image_url"]["detail"] == "high"
    assert usage_calls and usage_calls[0][0] == "gpt-4.1-mini"


def test_ingest_with_openingestion_applies_enabled_refineries(monkeypatch):
    order: list[str] = []
    progress: list[str] = []

    def fake_ingest(*_args, **_kwargs):
        return [_FakeChunk()]

    _install_fake_openingestion(monkeypatch, fake_ingest)

    class FakeVisionRefinery:
        def __init__(self, genie, image_detail: str = "low") -> None:
            assert genie.model == "gpt-4.1-mini"
            assert image_detail == "high"

        def enrich(self, chunks):
            order.append("vision")
            chunks[0].page_content = "vision output"
            return chunks

    class FakeContextualRagRefinery:
        def __init__(self, genie) -> None:
            assert genie.model == "gpt-4.1-mini"

        def enrich(self, chunks):
            order.append("contextual")
            chunks[0].doc_summary = "document summary"
            chunks[0].chunk_context = "chunk context"
            return chunks

    vision_module = ModuleType("openingestion.refinery.vision")
    vision_module.VisionRefinery = FakeVisionRefinery
    contextual_module = ModuleType("openingestion.refinery.contextual_rag")
    contextual_module.ContextualRagRefinery = FakeContextualRagRefinery
    monkeypatch.setitem(sys.modules, "openingestion.refinery.vision", vision_module)
    monkeypatch.setitem(
        sys.modules,
        "openingestion.refinery.contextual_rag",
        contextual_module,
    )

    monkeypatch.setenv("USE_INGEST_VISION_REFINERY", "true")
    monkeypatch.setenv("USE_INGEST_CONTEXTUAL_RAG", "true")
    monkeypatch.setenv("INGEST_REFINERY_MODEL", "gpt-4.1-mini")
    monkeypatch.setenv("INGEST_VISION_DETAIL", "high")
    monkeypatch.setattr(
        ingestor,
        "_build_refinery_genie",
        lambda *_args, **_kwargs: SimpleNamespace(model="gpt-4.1-mini"),
    )
    monkeypatch.setattr(
        ingestor,
        "_embed_content_and_titles",
        lambda chunk_dicts, *_args: ([[0.1] for _ in chunk_dicts], [[0.2] for _ in chunk_dicts]),
    )

    chunk_dicts, content_vectors, title_vectors = ingestor._ingest_with_openingestion(
        document_path=Path("fake.pdf"),
        source="source-id",
        parser="docling",
        strategy="by_token",
        api_key="api-key",
        embedding_model="text-embedding-3-small",
        progress_cb=progress.append,
    )

    assert order == ["vision", "contextual"]
    assert any("Raffinage vision" in message for message in progress)
    assert any("Raffinage contextual RAG" in message for message in progress)
    assert chunk_dicts[0]["page_content"] == "vision output"
    assert chunk_dicts[0]["doc_summary"] == "document summary"
    assert chunk_dicts[0]["chunk_context"] == "chunk context"
    assert content_vectors == [[0.1]]
    assert title_vectors == [[0.2]]


def test_ingest_jsonl_preserves_contextual_fields(monkeypatch, tmp_path):
    jsonl_path = tmp_path / "chunks.jsonl"
    jsonl_path.write_text(
        json.dumps(
            {
                "page_content": "contenu",
                "source": "jsonl-source",
                "kind": "text",
                "title_path": "Titre",
                "title_level": 1,
                "chunk_index": 0,
                "reading_order": 0,
                "prev_chunk_index": None,
                "next_chunk_index": None,
                "token_count": 12,
                "position_int": [[0, 1, 2, 3, 4]],
                "doc_summary": "resume document",
                "chunk_context": "contexte chunk",
                "extras": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    captured: dict = {}

    class FakeStore:
        def delete_source(self, source: str) -> None:
            captured["deleted_source"] = source

        def insert_chunks(self, chunks, content_vectors, title_vectors) -> int:
            captured["chunks"] = chunks
            captured["content_vectors"] = content_vectors
            captured["title_vectors"] = title_vectors
            return len(chunks)

    monkeypatch.setattr(
        ingestor,
        "_embed_content_and_titles",
        lambda chunk_dicts, *_args: ([[0.1] for _ in chunk_dicts], [[0.2] for _ in chunk_dicts]),
    )

    inserted = ingestor.ingest_jsonl(
        jsonl_path=jsonl_path,
        weaviate_store=FakeStore(),
        api_key="api-key",
    )

    assert inserted == 1
    assert captured["deleted_source"] == "jsonl-source"
    assert captured["chunks"][0]["doc_summary"] == "resume document"
    assert captured["chunks"][0]["chunk_context"] == "contexte chunk"


def test_resolve_refinery_api_key_prefers_provider_specific_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")

    assert (
        ingestor._resolve_refinery_api_key("claude-sonnet-4-5", "fallback-openai")
        == "sk-ant"
    )


def test_build_refinery_genie_prefers_openai_client_for_openai_models(monkeypatch):
    class FakeOpenAI:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=lambda **_kwargs: None)
            )

    openai_module = ModuleType("openai")
    openai_module.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", openai_module)

    config = ingestor._IngestionRefineryConfig(
        use_vision_refinery=True,
        use_contextual_rag=True,
        model="gpt-4.1-mini",
        api_base="https://example.test/v1",
        timeout=30.0,
        vision_detail="low",
    )

    genie = ingestor._build_refinery_genie(config, api_key="secret")

    assert isinstance(genie, ingestor._OpenAICompatibleGenie)
