"""Runtime asyncio dédié aux workers sync.

Les tâches Celery de ce projet sont synchrones mais s'appuient sur des repositories
SQLAlchemy async. Pour éviter de recréer un event loop par appel DB et de réutiliser
un AsyncEngine singleton sur plusieurs boucles, on maintient une boucle asyncio
persistante par process worker.
"""
from __future__ import annotations

import atexit
import asyncio
import threading
from collections.abc import Coroutine
from typing import Any, TypeVar

_T = TypeVar("_T")


class _WorkerAsyncRuntime:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    def _start_locked(self) -> asyncio.AbstractEventLoop:
        ready = threading.Event()
        errors: list[BaseException] = []

        def _run_loop() -> None:
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                self._loop = loop
                ready.set()
                loop.run_forever()
            except BaseException as exc:  # pragma: no cover - démarrage exceptionnel
                errors.append(exc)
                ready.set()
                raise
            finally:
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                loop.run_until_complete(loop.shutdown_asyncgens())
                loop.close()
                asyncio.set_event_loop(None)
                self._loop = None

        self._thread = threading.Thread(
            target=_run_loop,
            name="worker-asyncio-runtime",
            daemon=True,
        )
        self._thread.start()
        ready.wait()

        if errors:
            raise RuntimeError("Impossible de démarrer le runtime asyncio worker") from errors[0]
        if self._loop is None:
            raise RuntimeError("Le runtime asyncio worker n'a pas exposé de boucle active")
        return self._loop

    def get_loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is not None and self._thread is not None and self._thread.is_alive():
                return self._loop
            return self._start_locked()

    def run(self, coro: Coroutine[Any, Any, _T]) -> _T:
        loop = self.get_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result()

    def shutdown(self) -> None:
        with self._lock:
            loop = self._loop
            thread = self._thread

        if loop is None or thread is None:
            return

        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=2)


_RUNTIME = _WorkerAsyncRuntime()
atexit.register(_RUNTIME.shutdown)


def run_async(coro: Coroutine[Any, Any, _T]) -> _T:
    """Exécute une coroutine sur la boucle persistante du process worker."""
    return _RUNTIME.run(coro)


def shutdown_async_runtime() -> None:
    """Arrête explicitement la boucle de fond, utile en test."""
    _RUNTIME.shutdown()