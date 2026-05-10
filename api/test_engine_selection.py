from __future__ import annotations

import pytest
from fastapi import HTTPException

from api.engine_selection import get_default_agent_engine_name, list_agent_engines, resolve_agent_engine_name


def test_list_agent_engines_contains_supported_runtimes():
    assert list_agent_engines() == ["legacy_langgraph", "react_runtime_v2"]


def test_default_engine_can_differ_by_surface(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_ENGINE", "legacy_langgraph")
    monkeypatch.setenv("QUERY_AGENT_ENGINE", "react_runtime_v2")
    monkeypatch.setenv("STREAM_AGENT_ENGINE", "legacy_langgraph")

    assert get_default_agent_engine_name("query") == "react_runtime_v2"
    assert get_default_agent_engine_name("query_stream") == "legacy_langgraph"


def test_resolve_agent_engine_name_prefers_request_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_ENGINE", "legacy_langgraph")

    assert resolve_agent_engine_name("react_runtime_v2", surface="query") == "react_runtime_v2"


def test_resolve_agent_engine_name_rejects_unknown_engine(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_ENGINE", "legacy_langgraph")

    with pytest.raises(HTTPException):
        resolve_agent_engine_name("unknown-runtime", surface="query")
