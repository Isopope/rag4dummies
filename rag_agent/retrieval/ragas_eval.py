"""Utilities to evaluate retrieval quality with RAGAS."""
from __future__ import annotations

from dataclasses import dataclass
from numbers import Number
from typing import Any, Mapping, Optional, Sequence

from rag_agent.tools import QueryTool


@dataclass(frozen=True)
class RetrievalEvalSample:
    """Single retrieval evaluation sample."""

    query: str
    reference: str
    source_filter: Optional[str] = None


def _load_ragas() -> dict[str, Any]:
    try:
        from ragas import evaluate
        from ragas.dataset_schema import EvaluationDataset, SingleTurnSample
        from ragas.metrics import context_precision, context_recall
    except ImportError as exc:
        raise RuntimeError(
            "RAGAS n'est pas disponible. Installez-le via `pip install ragas>=0.4,<0.5`."
        ) from exc

    return {
        "evaluate": evaluate,
        "EvaluationDataset": EvaluationDataset,
        "SingleTurnSample": SingleTurnSample,
        "default_metrics": [context_precision, context_recall],
    }


def build_retrieval_dataset_rows(
    query_tool: QueryTool,
    samples: Sequence[RetrievalEvalSample],
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Build rows consumable by RAGAS from QueryTool retrieval results."""
    if top_k <= 0:
        raise ValueError("top_k doit être strictement positif")

    rows: list[dict[str, Any]] = []
    for sample in samples:
        docs = query_tool.execute(
            query=sample.query,
            source_filter=sample.source_filter,
            top_k=top_k,
        )
        retrieved_contexts = [
            text
            for text in (str(doc.get("page_content", "")).strip() for doc in docs)
            if text
        ]
        rows.append(
            {
                "user_input": sample.query,
                "reference": sample.reference,
                "retrieved_contexts": retrieved_contexts,
            }
        )
    return rows


def _extract_score_rows(result: Any) -> list[dict[str, Any]]:
    scores = getattr(result, "scores", None)
    if isinstance(scores, list):
        return [dict(row) for row in scores if isinstance(row, Mapping)]

    to_pandas = getattr(result, "to_pandas", None)
    if callable(to_pandas):
        frame = to_pandas()
        to_dict = getattr(frame, "to_dict", None)
        if callable(to_dict):
            rows = to_dict(orient="records")
            if isinstance(rows, list):
                return [dict(row) for row in rows if isinstance(row, Mapping)]
    return []


def aggregate_numeric_scores(score_rows: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    """Compute arithmetic mean for numeric metric columns."""
    totals: dict[str, float] = {}
    counts: dict[str, int] = {}

    for row in score_rows:
        for key, value in row.items():
            if isinstance(value, Number) and not isinstance(value, bool):
                totals[key] = totals.get(key, 0.0) + float(value)
                counts[key] = counts.get(key, 0) + 1

    return {key: totals[key] / counts[key] for key in totals if counts[key] > 0}


def evaluate_retrieval_with_ragas(
    query_tool: QueryTool,
    samples: Sequence[RetrievalEvalSample],
    *,
    top_k: int = 5,
    metrics: Optional[Sequence[Any]] = None,
    llm: Any = None,
    embeddings: Any = None,
    show_progress: bool = False,
) -> dict[str, Any]:
    """Evaluate retrieval quality with RAGAS and return detailed + aggregate scores."""
    ragas = _load_ragas()
    rows = build_retrieval_dataset_rows(query_tool=query_tool, samples=samples, top_k=top_k)
    sample_cls = ragas["SingleTurnSample"]
    dataset_cls = ragas["EvaluationDataset"]
    evaluate = ragas["evaluate"]

    if metrics is None:
        if llm is None:
            raise ValueError(
                "llm est requis quand metrics est omis (métriques par défaut: context_precision/context_recall)."
            )
        metrics = ragas["default_metrics"]

    dataset = dataset_cls(samples=[sample_cls(**row) for row in rows])
    result = evaluate(
        dataset=dataset,
        metrics=list(metrics),
        llm=llm,
        embeddings=embeddings,
        show_progress=show_progress,
    )
    score_rows = _extract_score_rows(result)
    return {
        "dataset_rows": rows,
        "score_rows": score_rows,
        "aggregate_scores": aggregate_numeric_scores(score_rows),
        "result": result,
    }
