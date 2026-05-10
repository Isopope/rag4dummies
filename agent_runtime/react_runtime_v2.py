"""Runtime ReAct v2 explicite, sans dependre du graphe LangGraph comme coeur."""
from __future__ import annotations

from typing import Any, Iterable

from openai import OpenAI

from core import AgentEvent, AgentRequest, AgentResult, StopReason
from rag_agent.config import RAGConfig
from rag_agent.llm import make_embedder, make_llm_caller
from rag_agent.nodes.compression import compress_context
from rag_agent.nodes.generation import generate, generate_follow_up, generate_title
from rag_agent.nodes.planning import analyze_and_plan
from rag_agent.nodes.reasoning import agent_action, agent_reason, consolidate_chunks, route_after_action, route_agent
from rag_agent.nodes.reranking import rerank
from rag_agent.state import UnifiedRAGState, create_unified_state
from rag_agent.tools.query import QueryTool, weaviate_with_retry


class ReactRuntimeV2Engine:
    """Premier runtime agent-first explicite, orchestré en Python séquentiel."""

    engine_id = "react_runtime_v2"

    def __init__(self, *, config: RAGConfig, weaviate_store: Any) -> None:
        self._config = config
        self._store = weaviate_store
        client = OpenAI(api_key=config.openai_key)
        self._llm_call = make_llm_caller(client, config.llm_model, config.llm_timeout)
        self._embedder = make_embedder(client, config.embedding_model, config.llm_timeout)
        self._query_tool = QueryTool(weaviate_store, self._embedder)

    def _build_initial_state(self, request: AgentRequest) -> UnifiedRAGState:
        try:
            available_sources = weaviate_with_retry(self._store.list_sources)
        except Exception:
            available_sources = []
        return create_unified_state(
            question=request.question,
            source=request.source_filter,
            conversation_summary=request.conversation_summary,
            available_sources=available_sources,
            user_id=request.user_id,
            conversation_id=request.session_id,
            max_tree_depth=self._config.max_tree_depth,
        )

    @staticmethod
    def _apply_updates(state: UnifiedRAGState, updates: dict[str, Any]) -> UnifiedRAGState:
        merged = dict(state)
        merged.update(updates)
        return merged  # type: ignore[return-value]

    @staticmethod
    def _last_log_message(state: UnifiedRAGState) -> str:
        logs = state.get("decision_log", [])
        return logs[-1].get("message", "") if logs else ""

    def _emit(self, collector: list[AgentEvent] | None, event: AgentEvent) -> None:
        if collector is not None:
            collector.append(event)

    def _execute(self, request: AgentRequest, collector: list[AgentEvent] | None = None) -> AgentResult:
        state = self._build_initial_state(request)
        trace_id = state["question_id"]
        self._emit(
            collector,
            AgentEvent(
                type="planning_started",
                node="analyze_and_plan",
                message="Initialisation du runtime ReAct v2.",
                question_id=trace_id,
                engine_id=self.engine_id,
            ),
        )

        updates = analyze_and_plan(state, llm_call=self._llm_call, rag_config=self._config)
        state = self._apply_updates(state, updates)
        self._emit(
            collector,
            AgentEvent(
                type="planning_completed",
                node="analyze_and_plan",
                message=self._last_log_message(state),
                question_id=trace_id,
                engine_id=self.engine_id,
                payload=updates,
            ),
        )

        while True:
            updates = agent_reason(state, llm_call=self._llm_call, rag_config=self._config)
            state = self._apply_updates(state, updates)
            if state.get("error"):
                break

            self._emit(
                collector,
                AgentEvent(
                    type="node_update",
                    node="agent_reason",
                    message=self._last_log_message(state),
                    question_id=trace_id,
                    engine_id=self.engine_id,
                    payload=updates,
                ),
            )

            route = route_agent({**state, "_max_agent_iter": self._config.max_agent_iter})  # type: ignore[arg-type]
            if route != "agent_action":
                break

            updates = agent_action(state, query_tool=self._query_tool, rag_config=self._config, weaviate_store=self._store)
            state = self._apply_updates(state, updates)
            self._emit(
                collector,
                AgentEvent(
                    type="tool_call_completed",
                    node="agent_action",
                    message=self._last_log_message(state),
                    question_id=trace_id,
                    engine_id=self.engine_id,
                    payload=updates,
                ),
            )

            if route_after_action(state, rag_config=self._config) == "compress_context":
                updates = compress_context(state, llm_call=self._llm_call, rag_config=self._config)
                state = self._apply_updates(state, updates)
                self._emit(
                    collector,
                    AgentEvent(
                        type="context_compressed",
                        node="compress_context",
                        message=self._last_log_message(state),
                        question_id=trace_id,
                        engine_id=self.engine_id,
                        payload=updates,
                    ),
                )

        for node_name, func in (
            ("consolidate", lambda s: consolidate_chunks(s, query_tool=self._query_tool, rag_config=self._config)),
            ("rerank", lambda s: rerank(
                s,
                llm_call=self._llm_call,
                reranker_url=self._config.reranker_url,
                rag_config=self._config,
            )),
            ("generate", lambda s: generate(s, llm_call=self._llm_call, rag_config=self._config)),
            ("generate_follow_up", lambda s: generate_follow_up(s, llm_call=self._llm_call, rag_config=self._config)),
            ("generate_title", lambda s: generate_title(s, llm_call=self._llm_call, rag_config=self._config)),
        ):
            updates = func(state)
            state = self._apply_updates(state, updates)
            event_type = "answer_completed" if node_name == "generate" else "node_update"
            self._emit(
                collector,
                AgentEvent(
                    type=event_type,
                    node=node_name,
                    message=self._last_log_message(state),
                    answer=state.get("answer") if node_name == "generate" else None,
                    sources=state.get("reranked_docs", []) if node_name in {"rerank", "generate"} else [],
                    follow_up_suggestions=state.get("follow_up_suggestions", []) if node_name == "generate_follow_up" else [],
                    conversation_title=state.get("conversation_title") if node_name == "generate_title" else None,
                    question_id=trace_id,
                    engine_id=self.engine_id,
                    payload=updates,
                ),
            )

        stop_reason = StopReason.COMPLETED
        if state.get("error"):
            stop_reason = StopReason.ERROR
        elif state.get("agent_iterations", 0) >= self._config.max_agent_iter:
            stop_reason = StopReason.MAX_ITERATIONS

        return AgentResult(
            answer=state.get("answer", ""),
            sources=state.get("reranked_docs", []),
            question_id=trace_id,
            n_retrieved=len(state.get("retrieved_docs", [])),
            decision_log=state.get("decision_log", []),
            error=state.get("error"),
            follow_up_suggestions=state.get("follow_up_suggestions", []),
            conversation_title=state.get("conversation_title"),
            trace_id=trace_id,
            engine_id=self.engine_id,
            stop_reason=stop_reason,
            iterations=state.get("agent_iterations", 0),
        )

    def run(self, request: AgentRequest) -> AgentResult:
        return self._execute(request)

    def stream(self, request: AgentRequest) -> Iterable[AgentEvent]:
        collector: list[AgentEvent] = []
        self._execute(request, collector=collector)
        yield from collector
