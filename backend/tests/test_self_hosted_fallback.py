"""Self-hosted fallback (LM Studio / Qwen via ngrok): used only after the whole key pool failed."""

import logging

import litellm
import pytest

from app.services.failure_simulation import parse_simulation_header
from app.services.litellm_gateway import strip_think
from tests.conftest import chat

QWEN = "openai/qwen/qwen3-14b"


def down(model="m"):
    return litellm.ServiceUnavailableError(message="high demand", llm_provider="gemini", model=model)


def test_fallback_disabled_by_default_keeps_503(client):
    r = chat(client, "s-f0", "hi", headers={"X-Simulate-Failure": "keys=429"})
    assert r.status_code == 503 and r.json() == {"detail": "all providers unavailable"}


def test_keys_target_lets_fallback_answer(make_client, provider):
    c = make_client(fallback=True)
    r = chat(c, "s-f1", "Name a planet.", headers={"X-Simulate-Failure": "keys=429"})
    assert r.status_code == 200
    meta = r.json()["metadata"]
    assert meta["key_id"] == "fallback"
    assert meta["model"] == QWEN
    assert meta["resolution_source"] == "LIVE_INFERENCE"
    assert meta["fallback_attempts"] == 2
    call = provider.calls[-1]
    assert call["key_id"] == "fallback"
    assert call["messages"][-1]["content"] == "Name a planet. /no_think"
    # history keeps the user's original text
    msgs = c.get("/sessions/s-f1/messages").json()["messages"]
    assert msgs[0]["content"] == "Name a planet."
    assert msgs[1]["metadata"]["key_id"] == "fallback"


def test_star_still_returns_503_with_fallback_enabled(make_client, provider):
    c = make_client(fallback=True)
    r = chat(c, "s-f2", "x", headers={"X-Simulate-Failure": "*=429"})
    assert r.status_code == 503 and r.json() == {"detail": "all providers unavailable"}
    assert all(call["key_id"] != "fallback" for call in provider.calls)
    assert c.get("/sessions/s-f2/messages").status_code == 404


def test_real_pool_outage_uses_fallback(make_client, provider):
    c = make_client(fallback=True)
    provider.fail_keys["key_1"] = down()
    provider.fail_keys["key_2"] = down()
    meta = chat(c, "s-f3", "hello").json()["metadata"]
    assert meta["key_id"] == "fallback" and meta["fallback_attempts"] == 2


def test_fallback_offline_returns_same_503(make_client, provider):
    c = make_client(fallback=True)
    provider.fail_keys["fallback"] = litellm.APIConnectionError(message="endpoint offline", llm_provider="openai", model=QWEN)
    r = chat(c, "s-f4", "hi", headers={"X-Simulate-Failure": "keys=500"})
    assert r.status_code == 503 and r.json() == {"detail": "all providers unavailable"}
    assert c.get("/sessions/s-f4/messages").status_code == 404


def test_healthy_pool_never_calls_fallback(make_client, provider):
    c = make_client(fallback=True)
    assert chat(c, "s-f5", "hi").json()["metadata"]["key_id"] == "key_1"
    assert all(call["key_id"] != "fallback" for call in provider.calls)


def test_think_block_is_stripped(make_client, provider):
    c = make_client(fallback=True)
    provider.fallback_raw_reply = "<think>\nlet me reason about it\n</think>\n\nJupiter."
    r = chat(c, "s-f6", "Largest planet?", headers={"X-Simulate-Failure": "keys=429"})
    assert r.json()["reply"] == "Jupiter."


def test_only_thinking_counts_as_failure(make_client, provider):
    c = make_client(fallback=True)
    provider.fallback_raw_reply = "<think>still thinking when it was cut off"
    r = chat(c, "s-f7", "?", headers={"X-Simulate-Failure": "keys=429"})
    assert r.status_code == 503


def test_fallback_errors_are_not_cached(make_client, provider):
    c = make_client(fallback=True)
    provider.fail_keys["key_1"] = down()
    provider.fail_keys["key_2"] = down()
    provider.fail_keys["fallback"] = litellm.Timeout(message="slow laptop", llm_provider="openai", model=QWEN)
    assert chat(c, "s-f8", "retry me").status_code == 503
    del provider.fail_keys["fallback"]  # laptop back online
    r = chat(c, "s-f9", "retry me").json()
    assert r["metadata"]["resolution_source"] == "LIVE_INFERENCE" and r["metadata"]["key_id"] == "fallback"


def test_fallback_key_never_logged(make_client, caplog):
    caplog.set_level(logging.INFO, logger="lyftr.gateway")
    c = make_client(fallback=True)
    chat(c, "s-f10", "hi", headers={"X-Simulate-Failure": "keys=429"})
    assert "sk-test-secret" not in caplog.text
    assert "served_by=fallback" in caplog.text


def test_served_by_logged_for_pool(client, caplog):
    caplog.set_level(logging.INFO, logger="lyftr.gateway")
    chat(client, "s-f11", "hi")
    assert "served_by=key_1" in caplog.text


@pytest.mark.parametrize("text,expected", [
    ("Paris.", "Paris."),
    ("<think>a</think>Paris.", "Paris."),
    ("<THINK>\nx\n</THINK>\n Paris. ", "Paris."),
    ("<think>never closed", ""),
])
def test_strip_think(text, expected):
    assert strip_think(text) == expected


def test_parser_targets():
    keys = ["key_1", "key_2"]
    assert parse_simulation_header("*=429", keys) == {"key_1": 429, "key_2": 429, "fallback": 429}
    assert parse_simulation_header("keys=500", keys) == {"key_1": 500, "key_2": 500}
    assert parse_simulation_header("fallback=503", keys) == {"fallback": 503}
