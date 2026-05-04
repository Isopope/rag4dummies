"""Tracking centralise de la consommation LLM/embedding.

Expose un context manager par requete et des helpers pour enregistrer
les usages renvoyes par LiteLLM/OpenAI de maniere thread-safe.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from threading import Lock
from typing import Any, Iterator


@dataclass
class UsageCall:
    kind: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    raw_usage: dict[str, Any] = field(default_factory=dict)


class UsageTracker:
    def __init__(self) -> None:
        self._calls: list[UsageCall] = []
        self._lock = Lock()

    def record(
        self,
        *,
        kind: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
        raw_usage: dict[str, Any] | None = None,
    ) -> None:
        call = UsageCall(
            kind=kind,
            model=model,
            input_tokens=max(int(input_tokens), 0),
            output_tokens=max(int(output_tokens), 0),
            total_tokens=max(int(total_tokens), 0),
            raw_usage=raw_usage or {},
        )
        with self._lock:
            self._calls.append(call)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            calls = [asdict(call) for call in self._calls]

        llm_calls = [call for call in calls if call["kind"] == "completion"]
        embedding_calls = [call for call in calls if call["kind"] == "embedding"]

        def _bucket(items: list[dict[str, Any]]) -> dict[str, int]:
            return {
                "input_tokens": sum(int(item.get("input_tokens", 0) or 0) for item in items),
                "output_tokens": sum(int(item.get("output_tokens", 0) or 0) for item in items),
                "total_tokens": sum(int(item.get("total_tokens", 0) or 0) for item in items),
                "call_count": len(items),
            }

        llm = _bucket(llm_calls)
        embeddings = _bucket(embedding_calls)
        total = _bucket(calls)

        return {
            "llm": llm,
            "embeddings": embeddings,
            "total": total,
            "calls": calls,
        }


_current_tracker: ContextVar[UsageTracker | None] = ContextVar("llm_usage_tracker", default=None)


@contextmanager
def track_usage() -> Iterator[UsageTracker]:
    tracker = UsageTracker()
    token = _current_tracker.set(tracker)
    try:
        yield tracker
    finally:
        _current_tracker.reset(token)


def _usage_to_dict(usage: Any) -> dict[str, Any]:
    if usage is None:
        return {}
    if isinstance(usage, dict):
        return dict(usage)
    if hasattr(usage, "model_dump"):
        dumped = usage.model_dump()
        return dumped if isinstance(dumped, dict) else {}
    if hasattr(usage, "dict"):
        dumped = usage.dict()
        return dumped if isinstance(dumped, dict) else {}

    result: dict[str, Any] = {}
    for key in (
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "prompt_tokens_details",
        "completion_tokens_details",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    ):
        if hasattr(usage, key):
            result[key] = getattr(usage, key)
    return result


def _record_usage(kind: str, model: str, usage: Any) -> None:
    tracker = _current_tracker.get()
    if tracker is None:
        return

    payload = _usage_to_dict(usage)
    input_tokens = int(payload.get("prompt_tokens", 0) or 0)
    output_tokens = int(payload.get("completion_tokens", 0) or 0)
    total_tokens = int(payload.get("total_tokens", 0) or (input_tokens + output_tokens))
    tracker.record(
        kind=kind,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        raw_usage=payload,
    )


def record_completion_usage(model: str, response: Any) -> None:
    _record_usage("completion", model, getattr(response, "usage", None))


def record_embedding_usage(model: str, response: Any) -> None:
    _record_usage("embedding", model, getattr(response, "usage", None))