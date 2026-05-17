"""Runtime d'exécution pour les routes RAG synchrones et streaming."""
from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from loguru import logger


def _read_positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default

    try:
        value = int(raw)
    except ValueError:
        logger.warning("Variable d'environnement invalide {}={!r}, fallback={}", name, raw, default)
        return default

    if value < 1:
        logger.warning("Variable d'environnement invalide {}={!r}, fallback={}", name, raw, default)
        return default

    return value


@dataclass(frozen=True)
class QueryExecutorSettings:
    query_workers: int
    query_inflight: int
    stream_workers: int
    stream_inflight: int


def load_query_executor_settings() -> QueryExecutorSettings:
    query_workers = _read_positive_int_env("RAG_QUERY_MAX_WORKERS", 16)
    stream_workers = _read_positive_int_env("RAG_STREAM_MAX_WORKERS", 8)
    query_inflight = _read_positive_int_env("RAG_QUERY_MAX_INFLIGHT", query_workers)
    stream_inflight = _read_positive_int_env("RAG_STREAM_MAX_INFLIGHT", stream_workers)

    return QueryExecutorSettings(
        query_workers=query_workers,
        query_inflight=query_inflight,
        stream_workers=stream_workers,
        stream_inflight=stream_inflight,
    )


class ExecutorCapacityGate:
    """Couple un ThreadPoolExecutor et une limite d'admission explicite."""

    def __init__(
        self,
        *,
        name: str,
        max_workers: int,
        max_inflight: int,
        thread_name_prefix: str,
    ) -> None:
        if max_workers < 1:
            raise ValueError("max_workers doit être >= 1")
        if max_inflight < 1:
            raise ValueError("max_inflight doit être >= 1")

        self.name = name
        self.max_workers = max_workers
        self.max_inflight = max_inflight
        self.executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=thread_name_prefix,
        )
        self._semaphore = threading.BoundedSemaphore(value=max_inflight)

    def try_acquire(self) -> bool:
        return self._semaphore.acquire(blocking=False)

    def release(self) -> None:
        self._semaphore.release()

    def shutdown(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)


def build_query_executor_gates() -> tuple[ExecutorCapacityGate, ExecutorCapacityGate]:
    settings = load_query_executor_settings()
    return (
        ExecutorCapacityGate(
            name="query",
            max_workers=settings.query_workers,
            max_inflight=settings.query_inflight,
            thread_name_prefix="rag-query",
        ),
        ExecutorCapacityGate(
            name="query-stream",
            max_workers=settings.stream_workers,
            max_inflight=settings.stream_inflight,
            thread_name_prefix="rag-query-stream",
        ),
    )