from __future__ import annotations

from dataclasses import dataclass

import pytest

from rag_agent.retrieval.ragas_eval import (
    RetrievalEvalSample,
    aggregate_numeric_scores,
    build_retrieval_dataset_rows,
    evaluate_retrieval_with_ragas,
)


def test_build_retrieval_dataset_rows_extracts_contexts_and_propagates_filters():
    class FakeQueryTool:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def execute(self, query: str, source_filter: str | None = None, top_k: int = 5):
            self.calls.append(
                {"query": query, "source_filter": source_filter, "top_k": top_k}
            )
            return [
                {"page_content": "  chunk A  "},
                {"page_content": ""},
                {"page_content": "chunk B"},
                {"foo": "bar"},
            ]

    tool = FakeQueryTool()
    rows = build_retrieval_dataset_rows(
        query_tool=tool,  # type: ignore[arg-type]
        samples=[RetrievalEvalSample(query="Q1", reference="R1", source_filter="src.pdf")],
        top_k=7,
    )
    assert tool.calls == [{"query": "Q1", "source_filter": "src.pdf", "top_k": 7}]
    assert rows == [
        {
            "user_input": "Q1",
            "reference": "R1",
            "retrieved_contexts": ["chunk A", "chunk B"],
        }
    ]


def test_build_retrieval_dataset_rows_rejects_non_positive_top_k():
    class FakeQueryTool:
        def execute(self, query: str, source_filter: str | None = None, top_k: int = 5):
            return []

    with pytest.raises(ValueError, match="top_k"):
        build_retrieval_dataset_rows(
            query_tool=FakeQueryTool(),  # type: ignore[arg-type]
            samples=[RetrievalEvalSample(query="Q", reference="R")],
            top_k=0,
        )


def test_aggregate_numeric_scores_ignores_non_numeric_and_bool():
    aggregate = aggregate_numeric_scores(
        [
            {"context_precision": 0.5, "context_recall": 1.0, "label": "x", "ok": True},
            {"context_precision": 1.0, "context_recall": 0.0, "ok": False},
        ]
    )
    assert aggregate == {"context_precision": 0.75, "context_recall": 0.5}


def test_evaluate_retrieval_with_ragas_wires_dataset_and_returns_aggregate(monkeypatch):
    class FakeQueryTool:
        def execute(self, query: str, source_filter: str | None = None, top_k: int = 5):
            assert top_k == 3
            return [{"page_content": f"ctx:{query}:{source_filter or 'all'}"}]

    @dataclass
    class FakeSingleTurnSample:
        user_input: str
        reference: str
        retrieved_contexts: list[str]

    class FakeDataset:
        def __init__(self, samples):
            self.samples = samples

    class FakeResult:
        scores = [{"context_precision": 0.6, "context_recall": 0.4}]

    captured: dict[str, object] = {}

    def fake_evaluate(*, dataset, metrics, llm, embeddings, show_progress):
        captured["dataset"] = dataset
        captured["metrics"] = metrics
        captured["llm"] = llm
        captured["embeddings"] = embeddings
        captured["show_progress"] = show_progress
        return FakeResult()

    monkeypatch.setattr(
        "rag_agent.retrieval.ragas_eval._load_ragas",
        lambda: {
            "evaluate": fake_evaluate,
            "EvaluationDataset": FakeDataset,
            "SingleTurnSample": FakeSingleTurnSample,
            "default_metrics": ["m1", "m2"],
        },
    )

    llm = object()
    out = evaluate_retrieval_with_ragas(
        query_tool=FakeQueryTool(),  # type: ignore[arg-type]
        samples=[
            RetrievalEvalSample(query="Q1", reference="A1"),
            RetrievalEvalSample(query="Q2", reference="A2", source_filter="src.pdf"),
        ],
        top_k=3,
        llm=llm,
        show_progress=True,
    )

    assert out["aggregate_scores"] == {"context_precision": 0.6, "context_recall": 0.4}
    dataset = captured["dataset"]
    assert isinstance(dataset, FakeDataset)
    assert [s.user_input for s in dataset.samples] == ["Q1", "Q2"]
    assert [s.retrieved_contexts for s in dataset.samples] == [
        ["ctx:Q1:all"],
        ["ctx:Q2:src.pdf"],
    ]
    assert captured["metrics"] == ["m1", "m2"]
    assert captured["llm"] is llm
    assert captured["show_progress"] is True


def test_evaluate_retrieval_with_ragas_requires_llm_for_default_metrics(monkeypatch):
    monkeypatch.setattr(
        "rag_agent.retrieval.ragas_eval._load_ragas",
        lambda: {
            "evaluate": lambda **_: None,
            "EvaluationDataset": lambda samples: samples,
            "SingleTurnSample": lambda **kwargs: kwargs,
            "default_metrics": ["m1", "m2"],
        },
    )

    class FakeQueryTool:
        def execute(self, query: str, source_filter: str | None = None, top_k: int = 5):
            return [{"page_content": "x"}]

    with pytest.raises(ValueError, match="llm"):
        evaluate_retrieval_with_ragas(
            query_tool=FakeQueryTool(),  # type: ignore[arg-type]
            samples=[RetrievalEvalSample(query="Q", reference="R")],
        )
