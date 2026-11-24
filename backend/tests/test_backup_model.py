"""Backup model: provider overload hits a whole model, so after every key fails on
the primary model, the same keys are tried on the backup model."""

import litellm

from app.core.config import load_settings
from tests.conftest import chat

PRIMARY = "gemini/gemini-3.5-flash-lite"
BACKUP = "gemini/backup-model"


def overloaded(model: str):
    return litellm.ServiceUnavailableError(message="high demand", llm_provider="gemini", model=model)


def test_primary_model_overloaded_falls_back_to_backup_model(make_client, provider):
    c = make_client(models=[PRIMARY, BACKUP])
    provider.fail_keys["key_1"] = overloaded(PRIMARY)
    provider.fail_keys["key_2"] = overloaded(PRIMARY)
    r = chat(c, "s-bk1", "write an article about chips")
    assert r.status_code == 200
    meta = r.json()["metadata"]
    assert meta["model"] == BACKUP
    assert meta["key_id"] == "key_1"
    assert meta["fallback_attempts"] == 2
    assert [call["key_id"] for call in provider.calls] == ["key_1", "key_2", "key_1@m2"]


def test_healthy_primary_never_touches_backup(make_client, provider):
    c = make_client(models=[PRIMARY, BACKUP])
    meta = chat(c, "s-bk2", "hello").json()["metadata"]
    assert meta["model"] == PRIMARY and meta["key_id"] == "key_1" and meta["fallback_attempts"] == 0
    assert [call["key_id"] for call in provider.calls] == ["key_1"]


def test_simulation_with_backup_model(make_client):
    c = make_client(models=[PRIMARY, BACKUP])
    one = chat(c, "s-bk3", "rivers", headers={"X-Simulate-Failure": "key_1=429"}).json()["metadata"]
    assert one["key_id"] == "key_2" and one["model"] == PRIMARY and one["fallback_attempts"] == 1
    # *=429 fails every key on every model -> exact 503, nothing stored
    r = chat(c, "s-bk4", "nobody", headers={"X-Simulate-Failure": "*=429"})
    assert r.status_code == 503 and r.json() == {"detail": "all providers unavailable"}
    assert c.get("/sessions/s-bk4/messages").status_code == 404


def test_cache_is_per_model(make_client, provider):
    c = make_client(models=[PRIMARY, BACKUP])
    provider.fail_keys["key_1"] = overloaded(PRIMARY)
    provider.fail_keys["key_2"] = overloaded(PRIMARY)
    first = chat(c, "s-bk5", "cached on backup").json()
    assert first["metadata"]["model"] == BACKUP
    # primary still down: the backup model's cache entry is found on its own model
    again = chat(c, "s-bk6", "cached on backup").json()
    assert again["metadata"]["resolution_source"] == "LLM_CACHE"
    assert again["metadata"]["model"] == BACKUP
    assert again["reply"] == first["reply"]


def test_llm_model_accepts_comma_separated_list(monkeypatch):
    monkeypatch.setenv("LLM_API_KEYS", "k1,k2")
    monkeypatch.setenv("LLM_MODEL", f"{PRIMARY}, {BACKUP}")
    assert load_settings().llm_models == [PRIMARY, BACKUP]
    monkeypatch.setenv("LLM_MODEL", PRIMARY)
    assert load_settings().llm_models == [PRIMARY]


# ---- mixed providers: keys bound to a provider with a "provider:" prefix ----

GROQ = "groq/test-llama"
MIXED_KEYS = ["sk-test-secret-g1", "sk-test-secret-g2", "groq:sk-test-secret-q3"]


def test_provider_prefixed_key_only_used_for_its_models(make_client, provider):
    c = make_client(models=[PRIMARY, BACKUP, GROQ], api_keys=MIXED_KEYS)
    assert c.get("/health").json()["keys_configured"] == 3
    gw = c.app.state.gateway
    assert gw.deployments == {
        "key_1": ("key_1", PRIMARY), "key_2": ("key_2", PRIMARY),
        "key_1@m2": ("key_1", BACKUP), "key_2@m2": ("key_2", BACKUP),
        "key_3@m3": ("key_3", GROQ),
    }


def test_all_gemini_down_falls_through_to_groq(make_client, provider):
    c = make_client(models=[PRIMARY, BACKUP, GROQ], api_keys=MIXED_KEYS)
    for dep in ("key_1", "key_2", "key_1@m2", "key_2@m2"):
        provider.fail_keys[dep] = overloaded(PRIMARY)
    r = chat(c, "s-groq", "hello")
    assert r.status_code == 200
    meta = r.json()["metadata"]
    assert meta["key_id"] == "key_3" and meta["model"] == GROQ and meta["fallback_attempts"] == 4


def test_mixed_simulation_and_total_failure(make_client):
    c = make_client(models=[PRIMARY, BACKUP, GROQ], api_keys=MIXED_KEYS)
    meta = chat(c, "s-m1", "x", headers={"X-Simulate-Failure": "key_1=429"}).json()["metadata"]
    assert meta["key_id"] == "key_2" and meta["model"] == PRIMARY
    r = chat(c, "s-m2", "y", headers={"X-Simulate-Failure": "*=429"})
    assert r.status_code == 503 and r.json() == {"detail": "all providers unavailable"}


def test_prefixed_secret_never_logged(make_client, caplog):
    c = make_client(models=[PRIMARY, GROQ], api_keys=MIXED_KEYS)
    chat(c, "s-m3", "z", headers={"X-Simulate-Failure": "*=500"})
    assert "sk-test-secret" not in caplog.text


def test_model_without_matching_key_fails_fast():
    import pytest
    from app.services.litellm_gateway import LiteLLMGateway
    with pytest.raises(ValueError):
        LiteLLMGateway(["a", "b"], [PRIMARY, GROQ], timeout_seconds=5, cache_ttl_seconds=60)
