from radar_uaf.quality import evaluate_consistency


def test_evaluate_consistency_flags_duplicate_entities(tmp_path, monkeypatch):
    import radar_uaf.storage as storage

    monkeypatch.setattr(storage, "SILVER_DIR", tmp_path)
    storage.upsert_jsonl(
        "entities",
        [
            {"entity_id": "ENT-1", "name": "Empresa Ejemplo SpA"},
            {"entity_id": "ENT-2", "name": "EMPRESA EJEMPLO SPA"},
        ],
        "entity_id",
    )
    result = evaluate_consistency()
    duplicate_check = next(c for c in result["checks"] if c["id"] == "duplicate_entity_names")
    assert duplicate_check["count"] == 1
    assert result["overall_status"] == "REVIEW_RECOMMENDED"


def test_evaluate_consistency_ok_when_clean(tmp_path, monkeypatch):
    import radar_uaf.storage as storage

    monkeypatch.setattr(storage, "SILVER_DIR", tmp_path)
    result = evaluate_consistency()
    assert result["overall_status"] == "OK"
    assert all(c["severity"] == "OK" for c in result["checks"])
