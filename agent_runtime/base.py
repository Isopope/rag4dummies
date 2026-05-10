"""Protocoles communs des moteurs agentiques."""
from __future__ import annotations

from typing import Iterable, Protocol

from core import AgentEvent, AgentRequest, AgentResult


class AgentEngine(Protocol):
    """Interface unifiee des moteurs agentiques."""

    def run(self, request: AgentRequest) -> AgentResult: ...

    def stream(self, request: AgentRequest) -> Iterable[AgentEvent]: ...
