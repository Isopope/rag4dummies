"""Sélection et validation des moteurs agentiques par surface."""
from __future__ import annotations

import os

from fastapi import HTTPException, status

SUPPORTED_AGENT_ENGINES = ("legacy_langgraph", "react_runtime_v2")


def validate_agent_engine_name(engine_name: str) -> str:
    normalized = engine_name.strip() or "legacy_langgraph"
    if normalized not in SUPPORTED_AGENT_ENGINES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Moteur agentique inconnu : {normalized}",
        )
    return normalized


def get_agent_engine_name() -> str:
    return validate_agent_engine_name(os.getenv("AGENT_ENGINE", "legacy_langgraph"))


def get_default_agent_engine_name(surface: str) -> str:
    env_by_surface = {
        "query": os.getenv("QUERY_AGENT_ENGINE"),
        "query_stream": os.getenv("STREAM_AGENT_ENGINE") or os.getenv("QUERY_STREAM_AGENT_ENGINE"),
    }
    candidate = env_by_surface.get(surface) or os.getenv("AGENT_ENGINE", "legacy_langgraph")
    return validate_agent_engine_name(candidate)


def resolve_agent_engine_name(engine_name: str | None = None, *, surface: str = "query") -> str:
    return validate_agent_engine_name(engine_name) if engine_name else get_default_agent_engine_name(surface)


def list_agent_engines() -> list[str]:
    return list(SUPPORTED_AGENT_ENGINES)
