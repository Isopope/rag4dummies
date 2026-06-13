"""Tests : identité source stable, suppression découplée, échecs honnêtes connecteurs."""
from __future__ import annotations

import asyncio
import hashlib
from types import SimpleNamespace

import storage
from api.document_cleanup import delete_tracked_document
from worker.tasks import connectors


# ── delete_tracked_document : identité (Weaviate/DB) vs stockage (object_key) ────

class _FakeDoc:
    def __init__(self, source_path: str, object_key: str | None) -> None:
        self.source_path = source_path
        self.object_key = object_key


class _FakeRepo:
    def __init__(self, doc: _FakeDoc | None) -> None:
        self._doc = doc
        self.deleted_source: str | None = None

    async def get_by_source(self, s: str):
        return self._doc if self._doc and self._doc.source_path == s else None

    async def get_by_object_key(self, k: str):
        return self._doc if self._doc and self._doc.object_key == k else None

    async def delete_by_source(self, s: str) -> bool:
        if self._doc and self._doc.source_path == s:
            self.deleted_source = s
            return True
        return False

    async def list_source_paths(self):
        return [self._doc.source_path] if self._doc else []


class _FakeDocStore:
    def __init__(self, existing: set[str]) -> None:
        self.existing = set(existing)
        self.deleted: list[str] = []

    def exists(self, k: str) -> bool:
        return k in self.existing

    def download(self, k: str) -> bytes:
        return b"%PDF-fake"

    def delete(self, k: str) -> None:
        self.deleted.append(k)
        self.existing.discard(k)


class _FakeWeaviate:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def delete_source(self, s: str) -> int:
        self.deleted.append(s)
        return 3


class _FakeSession:
    async def commit(self) -> None:
        pass


def test_delete_resolves_by_object_key_splits_identity_and_storage():
    doc = _FakeDoc(source_path="/data/a.pdf", object_key="ab12-a.pdf")
    repo = _FakeRepo(doc)
    doc_store = _FakeDocStore({"ab12-a.pdf"})
    weav = _FakeWeaviate()

    # handle = object_key (ce que le frontend envoie)
    res = asyncio.run(
        delete_tracked_document(
            "ab12-a.pdf",
            repo=repo,
            db_session=_FakeSession(),
            doc_store=doc_store,
            weaviate_store=weav,
        )
    )

    assert weav.deleted == ["/data/a.pdf"]    # Weaviate supprimé par l'identité stable
    assert doc_store.deleted == ["ab12-a.pdf"]  # stockage supprimé par l'object_key
    assert repo.deleted_source == "/data/a.pdf"
    assert res.deleted_db is True
    assert res.deleted_file is True


def test_delete_legacy_doc_without_object_key_uses_source_for_storage():
    # Doc legacy : object_key NULL, source_path == ancien object_key (sans slash)
    doc = _FakeDoc(source_path="ab12-a.pdf", object_key=None)
    repo = _FakeRepo(doc)
    doc_store = _FakeDocStore({"ab12-a.pdf"})
    weav = _FakeWeaviate()

    res = asyncio.run(
        delete_tracked_document(
            "ab12-a.pdf",
            repo=repo,
            db_session=_FakeSession(),
            doc_store=doc_store,
            weaviate_store=weav,
        )
    )
    assert weav.deleted == ["ab12-a.pdf"]
    assert doc_store.deleted == ["ab12-a.pdf"]
    assert res.deleted_db is True


# ── _process_fetched_docs : discovered-set + échec par document ─────────────────

def test_process_fetched_docs_collects_errors_and_discovered(monkeypatch):
    docs = [
        SimpleNamespace(path="/x/a.pdf", source="/x/a.pdf"),
        SimpleNamespace(path="/x/b.pdf", source="/x/b.pdf"),
        SimpleNamespace(path=None, source="/x/none"),  # ignoré
    ]

    def fake_upload(doc_path, src, parser, strategy, *, source_scope=None, entity=None, validity_date=None):
        if src.endswith("a.pdf"):
            return {"status": "dispatched", "object_key": "k", "task_id": "t", "source": src}
        raise RuntimeError("boom")

    monkeypatch.setattr(connectors, "_upload_and_dispatch", fake_upload)

    summary = connectors._process_fetched_docs(
        docs, "mineru", "by_sentence", source_scope="local:/x"
    )

    assert summary["discovered"] == {"/x/a.pdf", "/x/b.pdf"}
    assert len(summary["results"]) == 1
    assert len(summary["errors"]) == 1
    assert summary["errors"][0]["source"] == "/x/b.pdf"


# ── _upload_and_dispatch : skip si contenu inchangé / dispatch sinon ────────────

def test_upload_and_dispatch_skips_unchanged(monkeypatch, tmp_path):
    f = tmp_path / "a.pdf"
    f.write_bytes(b"hello")
    h = hashlib.sha256(b"hello").hexdigest()
    monkeypatch.setattr(connectors, "_indexed_content_hash", lambda s: h)

    r = connectors._upload_and_dispatch(f, "/x/a.pdf", "mineru", "by_sentence")
    assert r["status"] == "skipped"
    assert r["source"] == "/x/a.pdf"


def test_upload_and_dispatch_dispatches_changed(monkeypatch, tmp_path):
    f = tmp_path / "a.pdf"
    f.write_bytes(b"new-content")
    monkeypatch.setattr(connectors, "_indexed_content_hash", lambda s: None)

    captured: dict = {}

    class _DS:
        def make_object_key(self, name, content):
            return "key-" + name
        def upload(self, content, object_key, content_type="application/pdf"):
            captured["uploaded"] = object_key

    monkeypatch.setattr(storage, "make_document_store", lambda: _DS())

    def fake_upsert(source_path, parser, strategy, *, object_key, content_hash, source_scope=None, filename=None, entity=None, validity_date=None, source_updated_at=None):
        captured["upsert"] = {"source_path": source_path, "object_key": object_key, "scope": source_scope, "content_hash": content_hash}
    monkeypatch.setattr(connectors, "_db_upsert_pending", fake_upsert)

    def fake_dispatch(object_key, parser, strategy, filename, source, entity=None, validity_date=None):
        captured["dispatch"] = {"object_key": object_key, "source": source}
        return "task-123"
    monkeypatch.setattr(connectors, "_dispatch_ingest", fake_dispatch)

    r = connectors._upload_and_dispatch(
        f, "/x/a.pdf", "mineru", "by_sentence", source_scope="local:/x"
    )

    assert r["status"] == "dispatched"
    assert r["task_id"] == "task-123"
    # Identité stable = chemin source ; stockage = object_key adressé contenu
    assert captured["upsert"]["source_path"] == "/x/a.pdf"
    assert captured["upsert"]["object_key"] == "key-a.pdf"
    assert captured["upsert"]["scope"] == "local:/x"
    assert captured["dispatch"]["source"] == "/x/a.pdf"
    assert captured["dispatch"]["object_key"] == "key-a.pdf"
