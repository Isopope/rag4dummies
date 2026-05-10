from __future__ import annotations

from application.observability_service import ObservabilityService
from storage.observability_store import LocalObservabilityStore


def test_record_trace_persists_and_can_be_read(tmp_path):
    service = ObservabilityService(LocalObservabilityStore(tmp_path))

    trace = service.record_trace(
        question="Quels sont les risques ?",
        mode="query",
        engine_id="react_runtime_v2",
        model="gpt-test",
        source_filter="doc.pdf",
        conversation_summary="",
        session_id="session-1",
        user_id="alice",
        result={
            "trace_id": "trace-1",
            "question_id": "q-1",
            "answer": "Voici les risques.",
            "sources": [{"source": "doc.pdf"}],
            "n_retrieved": 1,
            "iterations": 2,
            "stop_reason": "completed",
            "follow_up_suggestions": ["Et ensuite ?"],
        },
        usage={"total": {"call_count": 1}},
        started_at="2026-01-01T00:00:00+00:00",
        completed_at="2026-01-01T00:00:01+00:00",
        events=[{"ts": "2026-01-01T00:00:00+00:00", "type": "planning_completed", "node": "plan"}],
    )

    assert trace["trace_id"] == "trace-1"
    assert trace["duration_ms"] == 1000
    assert trace["event_count"] == 1
    assert service.get_trace("trace-1")["question"] == "Quels sont les risques ?"


def test_summarize_traces_aggregates_by_engine(tmp_path):
    service = ObservabilityService(LocalObservabilityStore(tmp_path))
    for idx, engine_id in enumerate(("legacy_langgraph", "react_runtime_v2"), start=1):
        service.record_trace(
            question=f"q-{idx}",
            mode="query",
            engine_id=engine_id,
            model="gpt-test",
            source_filter=None,
            conversation_summary="",
            session_id=None,
            user_id="tester",
            result={
                "trace_id": f"trace-{idx}",
                "answer": "ok",
                "sources": [],
                "iterations": idx,
                "stop_reason": "completed",
            },
            usage=None,
            started_at=f"2026-01-01T00:00:0{idx}+00:00",
            completed_at=f"2026-01-01T00:00:1{idx}+00:00",
        )

    summary = service.summarize_traces(limit=10)

    assert summary["total_traces"] == 2
    assert {bucket["engine_id"] for bucket in summary["by_engine"]} == {"legacy_langgraph", "react_runtime_v2"}
