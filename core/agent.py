"""Contrats coeur de l'execution agentique."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StopReason(str, Enum):
    """Raison terminale d'une execution agentique."""

    COMPLETED = "completed"
    MAX_ITERATIONS = "max_iterations"
    ERROR = "error"


@dataclass(slots=True)
class AgentRequest:
    """Requete portable, independante du transport."""

    question: str
    source_filter: str | None = None
    conversation_summary: str = ""
    model: str | None = None
    engine_id: str | None = None
    user_id: str = "anonymous"
    session_id: str | None = None
    debug: bool = False


@dataclass(slots=True)
class AgentEvent:
    """Evenement normalise emis par un moteur agentique."""

    type: str
    node: str | None = None
    message: str | None = None
    answer: str | None = None
    sources: list[dict[str, Any]] = field(default_factory=list)
    follow_up_suggestions: list[str] = field(default_factory=list)
    conversation_title: str | None = None
    question_id: str | None = None
    session_id: str | None = None
    engine_id: str | None = None
    error: str | None = None
    usage: dict[str, Any] | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "node": self.node,
            "message": self.message,
            "answer": self.answer,
            "sources": self.sources,
            "follow_up_suggestions": self.follow_up_suggestions,
            "conversation_title": self.conversation_title,
            "question_id": self.question_id,
            "session_id": self.session_id,
            "engine_id": self.engine_id,
            "error": self.error,
            "usage": self.usage,
            "payload": self.payload,
        }


@dataclass(slots=True)
class AgentResult:
    """Resultat normalise d'une execution agentique."""

    answer: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    question_id: str = ""
    n_retrieved: int = 0
    decision_log: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    follow_up_suggestions: list[str] = field(default_factory=list)
    conversation_title: str | None = None
    usage: dict[str, Any] | None = None
    trace_id: str | None = None
    engine_id: str | None = None
    stop_reason: StopReason = StopReason.COMPLETED
    iterations: int = 0

    def to_legacy_result(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "sources": self.sources,
            "question_id": self.question_id,
            "n_retrieved": self.n_retrieved,
            "decision_log": self.decision_log,
            "error": self.error,
            "follow_up_suggestions": self.follow_up_suggestions,
            "conversation_title": self.conversation_title,
            "usage": self.usage,
            "trace_id": self.trace_id,
            "engine_id": self.engine_id,
            "stop_reason": self.stop_reason.value,
            "iterations": self.iterations,
        }
