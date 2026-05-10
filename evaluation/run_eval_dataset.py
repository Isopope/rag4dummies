from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_DATASET = Path(__file__).resolve().parent / "datasets" / "agent_eval_template.jsonl"


def _load_cases(dataset_path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    with dataset_path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Ligne JSONL invalide {line_number}: {exc}") from exc
            if not isinstance(item, dict):
                raise ValueError(f"Ligne {line_number}: un objet JSON est attendu.")
            cases.append(item)
    return cases


def _validate_case(case: dict[str, Any], index: int) -> dict[str, Any]:
    case_id = str(case.get("id") or f"case-{index:03d}")
    question = str(case.get("question") or "").strip()
    if not question:
        raise ValueError(f"{case_id}: le champ 'question' est requis.")
    engines = case.get("engines") or ["legacy_langgraph", "react_runtime_v2"]
    if not isinstance(engines, list) or not all(isinstance(engine, str) and engine.strip() for engine in engines):
        raise ValueError(f"{case_id}: le champ 'engines' doit etre une liste de chaines.")
    expected_sources = case.get("expected_sources") or []
    if not isinstance(expected_sources, list):
        raise ValueError(f"{case_id}: le champ 'expected_sources' doit etre une liste.")
    tags = case.get("tags") or []
    if not isinstance(tags, list):
        raise ValueError(f"{case_id}: le champ 'tags' doit etre une liste.")
    return {
        "id": case_id,
        "enabled": bool(case.get("enabled", True)),
        "question": question,
        "source_filter": case.get("source_filter"),
        "conversation_summary": str(case.get("conversation_summary") or ""),
        "model": case.get("model"),
        "engines": [engine.strip() for engine in engines],
        "expected_answer": case.get("expected_answer"),
        "expected_sources": [str(source) for source in expected_sources],
        "tags": [str(tag) for tag in tags],
        "notes": str(case.get("notes") or ""),
    }


def _expand_case_variants(
    case: dict[str, Any],
    *,
    override_engines: list[str] | None,
    override_models: list[str] | None,
) -> list[dict[str, Any]]:
    engines = override_engines if override_engines else case["engines"]
    models = override_models if override_models else [case["model"]]
    variants: list[dict[str, Any]] = []

    for model in models:
        suffix = model or "default-model"
        variants.append(
            {
                **case,
                "engines": engines,
                "model": model,
                "variant_id": f"{case['id']}::{suffix}",
            }
        )
    return variants


def _build_engine_factory(config, store):
    from agent_runtime import LegacyLangGraphEngine, ReactRuntimeV2Engine
    from rag_agent import RAGAgent
    from rag_agent.config import RAGConfig

    cache: dict[tuple[str, str], Any] = {}

    def _factory(model: str | None, engine_id: str):
        llm_model = model or config.llm_model
        key = (engine_id, llm_model)
        if key in cache:
            return cache[key]
        if engine_id == "legacy_langgraph":
            cache[key] = LegacyLangGraphEngine(
                RAGAgent(
                    weaviate_store=store,
                    openai_key=config.openai_key,
                    reranker_url=config.reranker_url,
                    embedding_model=config.embedding_model,
                    llm_model=llm_model,
                    top_k_retrieve=config.top_k_retrieve,
                    top_k_final=config.top_k_final,
                    hybrid_alpha=config.hybrid_alpha,
                    max_tokens=config.max_tokens,
                    max_agent_iter=config.max_agent_iter,
                    llm_timeout=config.llm_timeout,
                    enable_compression=config.enable_compression,
                )
            )
        elif engine_id == "react_runtime_v2":
            runtime_config = RAGConfig(**{**config.__dict__, "llm_model": llm_model})
            cache[key] = ReactRuntimeV2Engine(config=runtime_config, weaviate_store=store)
        else:
            raise ValueError(f"Moteur non supporte dans le runner: {engine_id}")
        return cache[key]

    return _factory


def _summarize_runs(dataset_run: dict[str, Any]) -> None:
    cases = dataset_run["cases"]
    total_results = sum(len(case["results"]) for case in cases)
    errors = sum(1 for case in cases for result in case["results"] if result.get("error"))
    winners = Counter(case.get("best_engine") for case in cases if case.get("best_engine"))
    print(f"Dataset run id: {dataset_run['dataset_run_id']}")
    print(f"Cases executes: {len(cases)}")
    print(f"Comparaisons executees: {total_results}")
    print(f"Resultats en erreur: {errors}")
    if winners:
        print("Moteurs gagnants par cas:")
        for engine_id, count in winners.items():
            print(f"  - {engine_id}: {count}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute un dataset JSONL d'evaluations agentiques.")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET), help="Chemin vers le fichier JSONL.")
    parser.add_argument("--output", default=None, help="Chemin du JSON de synthese a ecrire.")
    parser.add_argument("--user-id", default="eval-dataset", help="Identifiant utilisateur de trace.")
    parser.add_argument("--only-enabled", action="store_true", help="N'executer que les cas activés.")
    parser.add_argument("--engine", action="append", default=[], help="Force un moteur pour tous les cas. Option repetable.")
    parser.add_argument("--model", action="append", default=[], help="Force un modele pour tous les cas. Option repetable.")
    args = parser.parse_args()

    dataset_path = Path(args.dataset).resolve()
    if not dataset_path.is_file():
        print(f"Dataset introuvable: {dataset_path}", file=sys.stderr)
        return 1

    raw_cases = _load_cases(dataset_path)
    cases = [_validate_case(case, index + 1) for index, case in enumerate(raw_cases)]
    if args.only_enabled:
        cases = [case for case in cases if case["enabled"]]
    override_engines = [engine.strip() for engine in args.engine if engine and engine.strip()]
    override_models = [model.strip() for model in args.model if model and model.strip()]
    expanded_cases: list[dict[str, Any]] = []
    for case in cases:
        expanded_cases.extend(
            _expand_case_variants(
                case,
                override_engines=override_engines or None,
                override_models=override_models or None,
            )
        )
    cases = expanded_cases

    if not cases:
        print("Aucun cas a executer.", file=sys.stderr)
        return 1

    from application import EvaluationService, ObservabilityService
    from rag_agent.config import RAGConfig
    from storage import LocalObservabilityStore
    from weaviate_store import WeaviateStore

    config = RAGConfig.from_env()
    store = WeaviateStore(host=config.weaviate_host, port=config.weaviate_port)
    store.connect()
    observability_store = LocalObservabilityStore()
    evaluation_service = EvaluationService(
        engine_factory=_build_engine_factory(config, store),
        observability_service=ObservabilityService(observability_store),
        store=observability_store,
    )

    dataset_run = {
        "dataset_run_id": str(uuid.uuid4()),
        "dataset_path": str(dataset_path),
        "cases": [],
    }

    try:
        for case in cases:
            run = evaluation_service.compare(
                question=case["question"],
                engines=case["engines"],
                model=case["model"],
                source_filter=case["source_filter"],
                conversation_summary=case["conversation_summary"],
                user_id=args.user_id,
                session_id=None,
                expected_answer=case["expected_answer"],
                expected_sources=case["expected_sources"],
                debug=False,
            )
            dataset_run["cases"].append(
                {
                    "id": case["id"],
                    "variant_id": case["variant_id"],
                    "model": case["model"],
                    "engines": case["engines"],
                    "tags": case["tags"],
                    "notes": case["notes"],
                    "eval_id": run["eval_id"],
                    "best_engine": run.get("best_engine"),
                    "results": run["results"],
                }
            )
    finally:
        store.close()

    output_path = Path(args.output).resolve() if args.output else dataset_path.with_suffix(".results.json")
    output_path.write_text(json.dumps(dataset_run, ensure_ascii=False, indent=2), encoding="utf-8")
    _summarize_runs(dataset_run)
    print(f"Resultats ecrits dans: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
