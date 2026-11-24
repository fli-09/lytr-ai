import os

import pytest

from app.core.config import ConfigError, load_settings


def test_health_reports_ready_state(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "keys_configured": 2, "cache_enabled": True}


def test_health_counts_loaded_keys(make_client):
    c = make_client(keys=3)
    assert c.get("/health").json()["keys_configured"] == 3


def test_health_fails_when_database_unreachable(client):
    client.app.state.db.path = "/nonexistent-dir/definitely/missing.db"
    r = client.get("/health")
    assert r.status_code == 503
    assert "detail" in r.json()


def test_schema_created_on_startup(client, tmp_path):
    import sqlite3

    conn = sqlite3.connect(tmp_path / "app.db")
    cols = [row[1] for row in conn.execute("PRAGMA table_info(messages)")]
    conn.close()
    assert cols == ["id", "session_id", "role", "content", "metadata", "created_at"]


def test_startup_rejects_fewer_than_two_keys(monkeypatch):
    monkeypatch.setenv("LLM_API_KEYS", "only-one-key")
    with pytest.raises(ConfigError):
        load_settings()


def test_key_pool_parsing_and_ids(monkeypatch):
    monkeypatch.setenv("LLM_API_KEYS", " secretAAA , secretBBB ,secretCCC ")
    monkeypatch.setenv("DATABASE_URL", "sqlite:////data/app.db")
    s = load_settings()
    assert s.api_keys == ["secretAAA", "secretBBB", "secretCCC"]
    assert s.key_ids == ["key_1", "key_2", "key_3"]
    assert s.database_path == "/data/app.db"
    assert "secret" not in repr(s)  # keys never appear in repr


def test_no_docs_endpoints_exposed(client):
    for path in ("/docs", "/openapi.json", "/redoc"):
        r = client.get(path)
        assert r.status_code == 404
        assert r.json() == {"detail": "Not Found"}
