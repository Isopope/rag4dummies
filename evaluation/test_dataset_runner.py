from __future__ import annotations

from evaluation.run_eval_dataset import _expand_case_variants, _load_cases, _validate_case


def test_load_cases_reads_jsonl(tmp_path):
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text('{"id":"case-1","question":"hello"}\n{"id":"case-2","question":"world"}\n', encoding="utf-8")

    cases = _load_cases(dataset)

    assert len(cases) == 2
    assert cases[0]["id"] == "case-1"


def test_validate_case_applies_defaults():
    case = _validate_case({"question": "Quel est le budget ?"}, 1)

    assert case["id"] == "case-001"
    assert case["enabled"] is True
    assert case["engines"] == ["legacy_langgraph", "react_runtime_v2"]
    assert case["expected_sources"] == []


def test_validate_case_requires_question():
    try:
        _validate_case({"id": "case-bad", "question": ""}, 1)
    except ValueError as exc:
        assert "question" in str(exc)
    else:
        raise AssertionError("Une ValueError etait attendue.")


def test_expand_case_variants_uses_global_model_and_engine_overrides():
    case = _validate_case(
        {
            "id": "case-42",
            "question": "Quel est le budget ?",
            "engines": ["legacy_langgraph"],
            "model": "gpt-4.1",
        },
        42,
    )

    variants = _expand_case_variants(
        case,
        override_engines=["react_runtime_v2"],
        override_models=["gpt-4.1-mini", "gpt-4.1-nano"],
    )

    assert len(variants) == 2
    assert variants[0]["engines"] == ["react_runtime_v2"]
    assert variants[0]["model"] == "gpt-4.1-mini"
    assert variants[0]["variant_id"] == "case-42::gpt-4.1-mini"
    assert variants[1]["model"] == "gpt-4.1-nano"
