"""Adaptateur du moteur LangGraph historique vers l'interface AgentEngine."""
from __future__ import annotations

from typing import Any, Iterable

from core import AgentEvent, AgentRequest, AgentResult, StopReason


class LegacyLangGraphEngine:
    """Adapte `rag_agent.RAGAgent` a l'interface AgentEngine."""

    engine_id = "legacy_langgraph"

    def __init__(self, agent: Any) -> None:
        self._agent = agent

    def run(self, request: AgentRequest) -> AgentResult:
        result = self._agent.query(question=request.question, source=request.source_filter)
        return AgentResult(
            answer=result.get("answer", ""),
            sources=result.get("sources", []),
            question_id=result.get("question_id", ""),
            n_retrieved=result.get("n_retrieved", 0),
            decision_log=result.get("decision_log", []),
            error=result.get("error"),
            follow_up_suggestions=result.get("follow_up_suggestions", []),
            conversation_title=result.get("conversation_title"),
            trace_id=result.get("question_id", ""),
            engine_id=self.engine_id,
            stop_reason=StopReason.ERROR if result.get("error") else StopReason.COMPLETED,
        )

    def stream(self, request: AgentRequest) -> Iterable[AgentEvent]:
        for event in self._agent.stream_query(
            question=request.question,
            source=request.source_filter,
            conversation_summary=request.conversation_summary,
        ):
            for node_name, state_update in event.items():
                logs = state_update.get("decision_log", [])
                message = logs[-1].get("message", "") if logs else ""
                yield AgentEvent(
                    type="node_update",
                    node=node_name,
                    message=message,
                    answer=state_update.get("answer"),
                    sources=state_update.get("reranked_docs", []),
                    follow_up_suggestions=state_update.get("follow_up_suggestions", []),
                    conversation_title=state_update.get("conversation_title"),
                    question_id=state_update.get("question_id"),
                    engine_id=self.engine_id,
                    payload=state_update,
                )
