from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

from application.agent_service import AgentService
from core import AgentEvent, AgentResult


class _FakeEngine:
    def run(self, request):
        return AgentResult(
            answer=f"answer:{request.question}",
            sources=[{"source": "doc.pdf", "page_content": "content", "page_idx": 0, "chunk_index": 0}],
            question_id="qid-1",
            engine_id=request.engine_id,
            follow_up_suggestions=["next"],
            conversation_title="title",
        )

    def stream(self, request):
        yield AgentEvent(
            type="planning_completed",
            node="plan",
            message="planned",
            question_id="qid-2",
            engine_id=request.engine_id,
        )
        yield AgentEvent(
            type="answer_completed",
            node="generate",
            answer="streamed",
            question_id="qid-2",
            engine_id=request.engine_id,
        )


def test_execute_query_uses_engine_contract():
    async def _run():
        service = AgentService(
            engine_factory=lambda model: _FakeEngine(),
            executor=ThreadPoolExecutor(max_workers=1),
        )

        execution = await service.execute_query(
            question="hello",
            source_filter="doc.pdf",
            model="gpt-test",
            engine_id="react_runtime_v2",
        )

        assert execution.result["answer"] == "answer:hello"
        assert execution.result["question_id"] == "qid-1"
        assert execution.result["engine_id"] == "react_runtime_v2"
        assert execution.result["follow_up_suggestions"] == ["next"]
        assert execution.result["conversation_title"] == "title"
        assert execution.usage is not None
        assert execution.usage["total"]["call_count"] == 0
        assert execution.started_at
        assert execution.completed_at
        assert execution.duration_ms >= 0

    asyncio.run(_run())


def test_start_stream_query_emits_normalized_events():
    async def _run():
        service = AgentService(
            engine_factory=lambda model: _FakeEngine(),
            executor=ThreadPoolExecutor(max_workers=1),
        )
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        service.start_stream_query(
            question="hello",
            source_filter=None,
            conversation_summary="summary",
            model=None,
            engine_id="legacy_langgraph",
            queue=queue,
            loop=loop,
        )

        first = await asyncio.wait_for(queue.get(), timeout=2)
        second = await asyncio.wait_for(queue.get(), timeout=2)
        trace = await asyncio.wait_for(queue.get(), timeout=2)
        usage = await asyncio.wait_for(queue.get(), timeout=2)
        done = await asyncio.wait_for(queue.get(), timeout=2)

        assert first["type"] == "planning_completed"
        assert first["node"] == "plan"
        assert first["engine_id"] == "legacy_langgraph"
        assert second["type"] == "answer_completed"
        assert second["answer"] == "streamed"
        assert "__trace__" in trace
        assert trace["__trace__"]["event_count"] == 2
        assert "__usage__" in usage
        assert done is None

    asyncio.run(_run())
