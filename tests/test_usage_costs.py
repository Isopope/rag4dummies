from types import SimpleNamespace

from llm.usage import record_embedding_usage, track_usage


def _response_with_usage(**usage):
    return SimpleNamespace(usage=usage)


def test_tracks_openai_embedding_cost_for_text_embedding_3_small():
    with track_usage() as tracker:
        record_embedding_usage(
            "text-embedding-3-small",
            _response_with_usage(prompt_tokens=500_000, total_tokens=500_000),
        )

    snapshot = tracker.snapshot()

    assert snapshot["embeddings"]["input_tokens"] == 500_000
    assert snapshot["embeddings"]["cost_usd"] == 0.01
    assert snapshot["total"]["cost_usd"] == 0.01
    assert snapshot["calls"][0]["cost_usd"] == 0.01
    assert snapshot["calls"][0]["input_cost_per_1m_tokens"] == 0.02


def test_tracks_openai_embedding_cost_for_prefixed_model_name():
    with track_usage() as tracker:
        record_embedding_usage(
            "openai/text-embedding-3-large",
            _response_with_usage(prompt_tokens=1_000_000, total_tokens=1_000_000),
        )

    snapshot = tracker.snapshot()

    assert snapshot["embeddings"]["cost_usd"] == 0.13
    assert snapshot["calls"][0]["input_cost_per_1m_tokens"] == 0.13
