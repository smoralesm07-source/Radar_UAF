from radar_uaf.pipeline import run


def test_run_skip_network_produces_dashboard(tmp_path, monkeypatch):
    import radar_uaf.config as config
    import radar_uaf.storage as storage
    import radar_uaf.dashboard as dashboard

    monkeypatch.setattr(storage, "SILVER_DIR", tmp_path / "silver")
    monkeypatch.setattr(storage, "BRONZE_DIR", tmp_path / "bronze")
    monkeypatch.setattr(storage, "GOLD_DIR", tmp_path / "gold")
    monkeypatch.setattr(dashboard, "DOCS_DIR", tmp_path / "docs")

    result = run(skip_network=True)
    assert result["seed"]["facts_loaded"] > 0
    assert (tmp_path / "docs" / "data" / "dashboard.json").exists()
    assert result["dashboard_kpis"]["documents"] >= result["seed"]["facts_loaded"]
