"""Stockage local des traces d'execution et des runs d'evaluation."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


class LocalObservabilityStore:
    """Persiste les artefacts d'observabilite en JSON sur disque."""

    def __init__(self, base_dir: Path | str | None = None) -> None:
        root = Path(base_dir) if base_dir is not None else _project_root() / os.getenv("OBSERVABILITY_DIR", "observability")
        self._base_dir = root
        self._traces_dir = root / "traces"
        self._evals_dir = root / "evals"
        self._traces_dir.mkdir(parents=True, exist_ok=True)
        self._evals_dir.mkdir(parents=True, exist_ok=True)

    def save_trace(self, trace: dict[str, Any]) -> dict[str, Any]:
        trace_id = str(trace["trace_id"])
        path = self._traces_dir / f"{trace_id}.json"
        path.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
        return trace

    def get_trace(self, trace_id: str) -> dict[str, Any] | None:
        path = self._traces_dir / f"{trace_id}.json"
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def list_traces(
        self,
        *,
        limit: int = 20,
        engine_id: str | None = None,
        mode: str | None = None,
    ) -> list[dict[str, Any]]:
        traces = [json.loads(path.read_text(encoding="utf-8")) for path in self._traces_dir.glob("*.json")]
        if engine_id:
            traces = [trace for trace in traces if trace.get("engine_id") == engine_id]
        if mode:
            traces = [trace for trace in traces if trace.get("mode") == mode]
        traces.sort(key=lambda item: item.get("started_at", ""), reverse=True)
        return traces[:limit]

    def save_eval_run(self, run: dict[str, Any]) -> dict[str, Any]:
        eval_id = str(run["eval_id"])
        path = self._evals_dir / f"{eval_id}.json"
        path.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
        return run

    def get_eval_run(self, eval_id: str) -> dict[str, Any] | None:
        path = self._evals_dir / f"{eval_id}.json"
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
