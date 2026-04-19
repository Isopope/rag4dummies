from worker.tasks import ingest, periodic, connectors  # noqa: F401 — force la registration

__all__ = ["ingest", "periodic", "connectors"]
