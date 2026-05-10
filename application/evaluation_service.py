"""Service applicatif de comparaison entre moteurs agentiques."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from core import AgentRequest, AgentResult
from llm.usage import track_usage


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z0-9_]+", text.lower()))


def _answer_overlap_score(answer: str, expected_answer: str | None) -> float | None:
    if not expected_answer:
        return None
    answer_tokens = _tokenize(answer)
    expected_tokens = _tokenize(expected_answer)
    if not answer_tokens or not expected_tokens:
        return 0.0
    return len(answer_tokens & expected_tokens) / len(expected_tokens)


def _source_recall_score(returned_sources: list[str], expected_sources: list[str]) -> float | None:
    if not expected_sources:
        return None
    expected = set(expected_sources)
    if not expected:
        return 0.0
    return len(set(returned_sources) & expected) / len(expected)


def _citation_precision_score(returned_sources: list[str], expected_sources: list[str]) -> float | None:
    if not expected_sources:
        return None
    returned = set(returned_sources)
    if not returned:
        return 0.0
    return len(returned & set(expected_sources)) / len(returned)


class EvaluationService:
    """Exécute et persiste des comparaisons entre moteurs."""

    def __init__(self, *, engine_factory: Callable[[str | None, str], Any], observability_service, store) -> None:
        self._engine_factory = engine_factory
        self._observability_service = observability_service
        self._store = store

    def compare(
        self,
        *,
        question: str,
        engines: list[str],
        model: str | None,
        source_filter: str | None,
        conversation_summary: str,
        user_id: str,
        session_id: str | None,
        expected_answer: str | None,
        expected_sources: list[str],
        debug: bool = False,
    ) -> dict[str, Any]:
        created_at = _now_utc().isoformat()
        eval_id = str(uuid.uuid4())
        results: list[dict[str, Any]] = []

        for engine_id in engines:
            request = AgentRequest(
                question=question,
                source_filter=source_filter,
                conversation_summary=conversation_summary,
                model=model,
                engine_id=engine_id,
                user_id=user_id,
                session_id=session_id,
                debug=debug,
            )
            engine = self._engine_factory(model, engine_id)
            started_at = _now_utc()
            with track_usage() as tracker:
                result: AgentResult = engine.run(request)
            completed_at = _now_utc()
            usage = result.usage or tracker.snapshot()
            legacy_result = result.to_legacy_result()
            trace = self._observability_service.record_trace(
                question=question,
                mode="eval",
                engine_id=engine_id,
                model=model,
                source_filter=source_filter,
                conversation_summary=conversation_summary,
                session_id=session_id,
                user_id=user_id,
                result=legacy_result,
                usage=usage,
                started_at=started_at,
                completed_at=completed_at,
                metadata={"eval_id": eval_id},
            )
            source_paths = [source.get("source", "") for source in legacy_result.get("sources", []) if isinstance(source, dict)]
            results.append(
                {
                    "engine_id": engine_id,
                    "trace_id": trace["trace_id"],
                    "answer": legacy_result.get("answer", ""),
                    "error": legacy_result.get("error"),
                    "duration_ms": trace["duration_ms"],
                    "iterations": legacy_result.get("iterations", 0),
                    "stop_reason": legacy_result.get("stop_reason"),
                    "n_retrieved": legacy_result.get("n_retrieved", 0),
                    "source_paths": source_paths,
                    "usage": usage,
                    "answer_overlap_score": _answer_overlap_score(legacy_result.get("answer", ""), expected_answer),
                    "source_recall_score": _source_recall_score(source_paths, expected_sources),
                    "citation_precision_score": _citation_precision_score(source_paths, expected_sources),
                }
            )

        best_engine = None
        successful = [item for item in results if not item.get("error")]
        if successful:
            best_engine = min(successful, key=lambda item: (item["duration_ms"], -len(item["source_paths"])))[
                "engine_id"
            ]

        run = {
            "eval_id": eval_id,
            "created_at": created_at,
            "question": question,
            "model": model,
            "engines": engines,
            "expected_answer": expected_answer,
            "expected_sources": expected_sources,
            "results": results,
            "best_engine": best_engine,
        }
        return self._store.save_eval_run(run)

    def get_eval_run(self, eval_id: str) -> dict[str, Any] | None:
        return self._store.get_eval_run(eval_id)
