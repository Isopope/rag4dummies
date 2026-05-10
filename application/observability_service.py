"""Services applicatifs d'observabilite et de traces."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from statistics import mean
from typing import Any


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_iso(value: datetime | str | None) -> str:
    if value is None:
        return _now_utc().isoformat()
    if isinstance(value, str):
        return value
    return value.astimezone(timezone.utc).isoformat()


def _duration_ms(started_at: datetime | str, completed_at: datetime | str) -> int:
    start = datetime.fromisoformat(started_at) if isinstance(started_at, str) else started_at
    end = datetime.fromisoformat(completed_at) if isinstance(completed_at, str) else completed_at
    return max(int((end - start).total_seconds() * 1000), 0)


class ObservabilityService:
    """Construit, persiste et agrège les traces d'execution."""

    def __init__(self, store) -> None:
        self._store = store

    def record_trace(
        self,
        *,
        question: str,
        mode: str,
        engine_id: str,
        model: str | None,
        source_filter: str | None,
        conversation_summary: str,
        session_id: str | None,
        user_id: str,
        result: dict[str, Any],
        usage: dict[str, Any] | None,
        started_at: datetime | str | None,
        completed_at: datetime | str | None,
        events: list[dict[str, Any]] | None = None,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        trace_id = str(result.get("trace_id") or result.get("question_id") or uuid.uuid4())
        started_iso = _ensure_iso(started_at)
        completed_iso = _ensure_iso(completed_at)
        final_error = error or result.get("error")
        sources = result.get("sources") or []
        normalized_events = events or []

        trace = {
            "trace_id": trace_id,
            "question_id": result.get("question_id"),
            "question": question,
            "mode": mode,
            "engine_id": engine_id,
            "model": model,
            "source_filter": source_filter,
            "conversation_summary": conversation_summary,
            "session_id": session_id,
            "user_id": user_id,
            "started_at": started_iso,
            "completed_at": completed_iso,
            "duration_ms": _duration_ms(started_iso, completed_iso),
            "stop_reason": result.get("stop_reason"),
            "iterations": int(result.get("iterations", 0) or 0),
            "n_retrieved": int(result.get("n_retrieved", 0) or 0),
            "source_paths": [source.get("source", "") for source in sources if isinstance(source, dict)],
            "follow_up_suggestions": result.get("follow_up_suggestions", []),
            "conversation_title": result.get("conversation_title"),
            "usage": usage,
            "error": final_error,
            "answer_preview": (result.get("answer") or "")[:500],
            "decision_log": result.get("decision_log", []),
            "events": normalized_events,
            "event_count": len(normalized_events),
            "metadata": metadata or {},
        }
        return self._store.save_trace(trace)

    def get_trace(self, trace_id: str) -> dict[str, Any] | None:
        return self._store.get_trace(trace_id)

    def list_traces(self, *, limit: int = 20, engine_id: str | None = None, mode: str | None = None) -> list[dict[str, Any]]:
        return self._store.list_traces(limit=limit, engine_id=engine_id, mode=mode)

    def summarize_traces(self, *, limit: int = 100) -> dict[str, Any]:
        traces = self._store.list_traces(limit=limit)
        durations = [int(trace.get("duration_ms", 0) or 0) for trace in traces]
        iterations = [int(trace.get("iterations", 0) or 0) for trace in traces if trace.get("iterations") is not None]
        by_engine: dict[str, dict[str, Any]] = {}
        by_mode: dict[str, dict[str, Any]] = {}
        stop_reasons: dict[str, int] = {}
        error_count = 0

        for trace in traces:
            engine_id = str(trace.get("engine_id") or "unknown")
            mode = str(trace.get("mode") or "unknown")
            stop_reason = str(trace.get("stop_reason") or "unknown")
            duration_ms = int(trace.get("duration_ms", 0) or 0)
            has_error = bool(trace.get("error"))
            if has_error:
                error_count += 1

            engine_bucket = by_engine.setdefault(engine_id, {"engine_id": engine_id, "count": 0, "errors": 0, "durations": []})
            engine_bucket["count"] += 1
            engine_bucket["errors"] += int(has_error)
            engine_bucket["durations"].append(duration_ms)

            mode_bucket = by_mode.setdefault(mode, {"mode": mode, "count": 0, "errors": 0, "durations": []})
            mode_bucket["count"] += 1
            mode_bucket["errors"] += int(has_error)
            mode_bucket["durations"].append(duration_ms)

            stop_reasons[stop_reason] = stop_reasons.get(stop_reason, 0) + 1

        return {
            "total_traces": len(traces),
            "error_count": error_count,
            "avg_duration_ms": mean(durations) if durations else 0.0,
            "avg_iterations": mean(iterations) if iterations else 0.0,
            "by_engine": [
                {
                    "engine_id": bucket["engine_id"],
                    "count": bucket["count"],
                    "errors": bucket["errors"],
                    "avg_duration_ms": mean(bucket["durations"]) if bucket["durations"] else 0.0,
                }
                for bucket in by_engine.values()
            ],
            "by_mode": [
                {
                    "mode": bucket["mode"],
                    "count": bucket["count"],
                    "errors": bucket["errors"],
                    "avg_duration_ms": mean(bucket["durations"]) if bucket["durations"] else 0.0,
                }
                for bucket in by_mode.values()
            ],
            "stop_reasons": stop_reasons,
        }
