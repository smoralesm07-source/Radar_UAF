import json

from radar_uaf.storage import _semantic, read_jsonl, upsert_jsonl


def test_upsert_inserts_new_rows(tmp_path, monkeypatch):
    import radar_uaf.storage as storage

    monkeypatch.setattr(storage, "SILVER_DIR", tmp_path)
    inserted, updated = storage.upsert_jsonl("documents", [{"document_id": "DOC-1", "title": "A"}], "document_id")
    assert inserted == 1
    assert updated == 0
    rows = read_jsonl(tmp_path / "documents.jsonl")
    assert rows[0]["title"] == "A"


def test_upsert_ignores_volatile_fields(tmp_path, monkeypatch):
    import radar_uaf.storage as storage

    monkeypatch.setattr(storage, "SILVER_DIR", tmp_path)
    storage.upsert_jsonl("documents", [{"document_id": "DOC-1", "title": "A", "retrieved_at": "2026-01-01T00:00:00Z"}], "document_id")
    inserted, updated = storage.upsert_jsonl(
        "documents", [{"document_id": "DOC-1", "title": "A", "retrieved_at": "2026-02-01T00:00:00Z"}], "document_id"
    )
    assert inserted == 0
    assert updated == 0


def test_upsert_detects_semantic_change(tmp_path, monkeypatch):
    import radar_uaf.storage as storage

    monkeypatch.setattr(storage, "SILVER_DIR", tmp_path)
    storage.upsert_jsonl("documents", [{"document_id": "DOC-1", "title": "A"}], "document_id")
    inserted, updated = storage.upsert_jsonl("documents", [{"document_id": "DOC-1", "title": "B"}], "document_id")
    assert inserted == 0
    assert updated == 1


def test_semantic_strips_volatile_fields():
    row = {"document_id": "DOC-1", "retrieved_at": "x", "last_seen": "y", "title": "A"}
    assert _semantic(row) == {"document_id": "DOC-1", "title": "A"}
