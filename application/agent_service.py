"""Service applicatif pour l'execution des requêtes agentiques."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from core import AgentRequest, AgentResult
from llm.usage import track_usage

_QUERY_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="rag-query")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class AgentExecutionResult:
    """Resultat brut d'une execution agentique."""

    result: dict[str, Any]
    usage: dict[str, Any] | None
    started_at: str
    completed_at: str
    duration_ms: int


class AgentService:
    """Facade applicative pour declencher les executions sync/stream d'un agent."""

    def __init__(
        self,
        *,
        engine_factory: Callable[[str | None], Any],
        executor: ThreadPoolExecutor | None = None,
    ) -> None:
        self._engine_factory = engine_factory
        self._executor = executor or _QUERY_EXECUTOR

    async def execute_query(
        self,
        *,
        question: str,
        source_filter: str | None = None,
        model: str | None = None,
        engine_id: str | None = None,
    ) -> AgentExecutionResult:
        """Execute une requete agentique synchrone dans le pool dedie."""

        engine = self._engine_factory(model)
        request = AgentRequest(
            question=question,
            source_filter=source_filter,
            model=model,
            engine_id=engine_id,
        )
        loop = asyncio.get_running_loop()

        def _run_query() -> AgentExecutionResult:
            started_at = _now_iso()
            with track_usage() as tracker:
                result: AgentResult = engine.run(request)
            completed_at = _now_iso()
            usage = result.usage or tracker.snapshot()
            duration_ms = max(
                int(
                    (datetime.fromisoformat(completed_at) - datetime.fromisoformat(started_at)).total_seconds() * 1000
                ),
                0,
            )
            return AgentExecutionResult(
                result=result.to_legacy_result(),
                usage=usage,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms,
            )

        return await loop.run_in_executor(self._executor, _run_query)

    def start_stream_query(
        self,
        *,
        question: str,
        source_filter: str | None,
        conversation_summary: str,
        model: str | None,
        engine_id: str | None,
        queue: asyncio.Queue,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        """Lance une requete stream dans le pool et pousse les evenements dans `queue`."""

        engine = self._engine_factory(model)
        request = AgentRequest(
            question=question,
            source_filter=source_filter,
            conversation_summary=conversation_summary,
            model=model,
            engine_id=engine_id,
        )

        def _producer() -> None:
            tracker = None
            started_at = _now_iso()
            event_count = 0
            try:
                with track_usage() as current_tracker:
                    tracker = current_tracker
                    for event in engine.stream(request):
                        payload = event.to_dict()
                        payload["ts"] = _now_iso()
                        event_count += 1
                        loop.call_soon_threadsafe(queue.put_nowait, payload)
            except Exception as exc:
                loop.call_soon_threadsafe(queue.put_nowait, {"__error__": str(exc)})
            finally:
                completed_at = _now_iso()
                duration_ms = max(
                    int(
                        (datetime.fromisoformat(completed_at) - datetime.fromisoformat(started_at)).total_seconds() * 1000
                    ),
                    0,
                )
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    {
                        "__trace__": {
                            "started_at": started_at,
                            "completed_at": completed_at,
                            "duration_ms": duration_ms,
                            "event_count": event_count,
                        }
                    },
                )
                if tracker is not None:
                    loop.call_soon_threadsafe(queue.put_nowait, {"__usage__": tracker.snapshot()})
                loop.call_soon_threadsafe(queue.put_nowait, None)

        loop.run_in_executor(self._executor, _producer)
