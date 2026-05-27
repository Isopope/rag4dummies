"""Tests de résolution des clés provider pour LiteLLM."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from rag_agent.config import RAGConfig
from rag_agent.llm import make_llm_caller


def test_rag_config_loads_anthropic_key_from_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    monkeypatch.setenv("LLM_MODEL", "claude-sonnet-4-5")
    cfg = RAGConfig.from_env()
    assert cfg.anthropic_key == "sk-ant"
    assert cfg.llm_model == "claude-sonnet-4-5"


def test_make_llm_caller_passes_anthropic_key(monkeypatch):
    captured: dict = {}

    def _fake_completion(**kwargs):
        captured.update(kwargs)
        return MagicMock()

    import llm.factory as llm_factory

    monkeypatch.setattr(llm_factory, "get_llm_completion", _fake_completion)
    caller = make_llm_caller(
        client=None,
        model="claude-sonnet-4-5",
        timeout=5.0,
        provider_api_keys={"anthropic": "sk-ant"},
    )

    caller([{"role": "user", "content": "Bonjour"}])
    assert captured["api_key"] == "sk-ant"
    assert captured["api_base"] is None


def test_make_llm_caller_requires_anthropic_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    caller = make_llm_caller(
        client=None,
        model="claude-sonnet-4-5",
        timeout=5.0,
        provider_api_keys={},
    )
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        caller([{"role": "user", "content": "Test"}])


def test_make_llm_caller_keeps_openai_client_key(monkeypatch):
    captured: dict = {}

    def _fake_completion(**kwargs):
        captured.update(kwargs)
        return MagicMock()

    import llm.factory as llm_factory

    monkeypatch.setattr(llm_factory, "get_llm_completion", _fake_completion)
    dummy_client = SimpleNamespace(api_key="sk-openai-client", base_url="https://api.openai.com/v1")
    caller = make_llm_caller(
        client=dummy_client,
        model="gpt-4.1-mini",
        timeout=5.0,
        provider_api_keys={"openai": "sk-openai-fallback"},
    )

    caller([{"role": "user", "content": "Hello"}])
    assert captured["api_key"] == "sk-openai-client"
    assert captured["api_base"] == "https://api.openai.com/v1"
