from __future__ import annotations

from application.evaluation_service import EvaluationService
from application.observability_service import ObservabilityService
from core import AgentResult, StopReason
from storage.observability_store import LocalObservabilityStore


class _FakeEngine:
    def __init__(self, engine_id: str) -> None:
        self._engine_id = engine_id

    def run(self, request):
        answer = "budget confirme" if self._engine_id == "react_runtime_v2" else "reponse generique"
        sources = [{"source": "budget.pdf"}] if self._engine_id == "react_runtime_v2" else [{"source": "other.pdf"}]
        return AgentResult(
            answer=answer,
            sources=sources,
            question_id=f"q-{self._engine_id}",
            n_retrieved=len(sources),
            iterations=1 if self._engine_id == "react_runtime_v2" else 3,
            stop_reason=StopReason.COMPLETED,
            trace_id=f"q-{self._engine_id}",
            engine_id=self._engine_id,
        )


def test_compare_persists_eval_and_scores_sources(tmp_path):
    store = LocalObservabilityStore(tmp_path)
    service = EvaluationService(
        engine_factory=lambda model, engine_id: _FakeEngine(engine_id),
        observability_service=ObservabilityService(store),
        store=store,
    )

    run = service.compare(
        question="Quel est le budget ?",
        engines=["legacy_langgraph", "react_runtime_v2"],
        model="gpt-test",
        source_filter=None,
        conversation_summary="",
        user_id="eval-user",
        session_id=None,
        expected_answer="budget confirme",
        expected_sources=["budget.pdf"],
    )

    assert run["eval_id"]
    assert len(run["results"]) == 2
    assert store.get_eval_run(run["eval_id"]) is not None
    v2 = next(item for item in run["results"] if item["engine_id"] == "react_runtime_v2")
    assert v2["source_recall_score"] == 1.0
    assert v2["citation_precision_score"] == 1.0
