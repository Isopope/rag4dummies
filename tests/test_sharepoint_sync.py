"""Tests : décision delta SharePoint + sélection des sources dues (list_due)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.models.base import Base
from db.models.connector_config import ConnectorConfig
from db.repositories.connector_config import ConnectorConfigRepository


# ── list_due ─────────────────────────────────────────────────────────────────

def test_list_due_selects_never_synced_and_elapsed():
    async def main():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        now = datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc)

        async with Session() as s:
            repo = ConnectorConfigRepository(s)
            # jamais synchronisée → due
            await repo.create(name="never", config_json="{}", interval_seconds=86400)
            # synchronisée il y a 2h, interval 7j → pas due
            c_recent = await repo.create(name="recent", config_json="{}", interval_seconds=7 * 86400)
            c_recent.last_sync_at = now - timedelta(hours=2)
            # synchronisée il y a 8j, interval 7j → due
            c_old = await repo.create(name="old", config_json="{}", interval_seconds=7 * 86400)
            c_old.last_sync_at = now - timedelta(days=8)
            # désactivée mais échue → jamais due
            c_disabled = await repo.create(name="disabled", config_json="{}", interval_seconds=86400, enabled=False)
            c_disabled.last_sync_at = now - timedelta(days=30)
            await s.commit()

        async with Session() as s:
            repo = ConnectorConfigRepository(s)
            due = await repo.list_due(now)
            names = sorted(c.name for c in due)
        await engine.dispose()
        return names

    assert asyncio.run(main()) == ["never", "old"]


# ── Décision delta dans sync_sharepoint_task ───────────────────────────────────

def test_sync_sharepoint_delta_only_fetches_new_and_modified(monkeypatch):
    from worker.tasks import connectors
    from worker.connectors import sharepoint_sync

    t_old = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t_new = datetime(2026, 6, 1, tzinfo=timezone.utc)

    items = [
        SimpleNamespace(id="1", name="a.pdf", web_url="https://sp/a", mime="application/pdf", last_modified=t_new),  # nouveau
        SimpleNamespace(id="2", name="b.pdf", web_url="https://sp/b", mime="application/pdf", last_modified=t_old),  # inchangé
        SimpleNamespace(id="3", name="c.pdf", web_url="https://sp/c", mime="application/pdf", last_modified=t_new),  # modifié
        SimpleNamespace(id="4", name="d.pdf", web_url="https://sp/d", mime="application/pdf", last_modified=t_new),  # en erreur → re-fetch
    ]

    class FakeClient:
        def __init__(self, *a, **k): pass
        def resolve_site_id(self, *a, **k): return "site"
        def default_drive_id(self, *a, **k): return "drive"
        def list_items(self, *a, **k): return items
        def download_item(self, drive_id, item_id): return b"bytes-" + item_id.encode()

    monkeypatch.setattr(sharepoint_sync, "SharepointGraphClient", FakeClient)

    states = {
        "https://sp/a": None,
        "https://sp/b": {"status": "indexed", "source_updated_at": t_old},
        "https://sp/c": {"status": "indexed", "source_updated_at": t_old},
        "https://sp/d": {"status": "error", "source_updated_at": t_new},
    }
    monkeypatch.setattr(connectors, "_doc_sync_state", lambda s: states[s])

    dispatched: list[str] = []

    def fake_upload(path, src, parser, strategy, *, source_scope=None, entity=None, validity_date=None, source_updated_at=None):
        dispatched.append(src)
        return {"status": "dispatched", "object_key": "k", "task_id": "t", "source": src}

    monkeypatch.setattr(connectors, "_upload_and_dispatch", fake_upload)
    monkeypatch.setattr(connectors, "_prune_scope", lambda scope, discovered: [])

    res = connectors.sync_sharepoint_task.apply(
        kwargs={"site_url": "https://sp", "prune": False}
    ).get()

    # a (nouveau), c (modifié), d (en erreur) → fetch ; b (inchangé) → skip
    assert set(dispatched) == {"https://sp/a", "https://sp/c", "https://sp/d"}
    assert res["dispatched"] == 3
    assert res["skipped"] == 1
