import litellm
import pytest

from app.services.failure_simulation import InvalidSimulationHeader, parse_simulation_header
from tests.conftest import chat

KEYS = ["key_1", "key_2"]


@pytest.mark.parametrize("status", ["429", "500", "502", "503"])
def test_simulated_first_key_failure_falls_through(client, provider, status):
    r = chat(client, f"s-sim-{status}", "Fail over please", headers={"X-Simulate-Failure": f"key_1={status}"})
    assert r.status_code == 200
    meta = r.json()["metadata"]
    assert meta["key_id"] == "key_2"
    assert meta["fallback_attempts"] == 1
    assert meta["resolution_source"] == "LIVE_INFERENCE"
    assert r.json()["reply"].startswith("Reply #1 via key_2")  # a real (mock-provider) answer, not an error
    assert [c["key_id"] for c in provider.calls] == ["key_1", "key_2"]


def test_all_keys_simulated_returns_exact_503(client):
    r = chat(client, "s-all", "nobody home", headers={"X-Simulate-Failure": "*=429"})
    assert r.status_code == 503
    assert r.json() == {"detail": "all providers unavailable"}


def test_all_keys_failing_even_for_cached_message(client):
    # The PDF's example message may already be cached; *=429 must still be 503.
    assert chat(client, "s-c1", "What is the capital of France?").status_code == 200
    r = chat(client, "s-c2", "What is the capital of France?", headers={"X-Simulate-Failure": "*=429"})
    assert r.status_code == 503
    r = chat(client, "s-c3", "What is the capital of France?", headers={"X-Simulate-Failure": "key_1=429"})
    assert r.status_code == 200 and r.json()["metadata"]["key_id"] == "key_2"


def test_simulation_is_request_scoped(client):
    assert chat(client, "s-scope", "one", headers={"X-Simulate-Failure": "key_1=429"}).json()["metadata"]["key_id"] == "key_2"
    nxt = chat(client, "s-scope", "two").json()["metadata"]
    assert nxt["key_id"] == "key_1" and nxt["fallback_attempts"] == 0


def test_three_keys_two_failures(make_client, provider):
    c = make_client(keys=3)
    r = chat(c, "s-three", "deep", headers={"X-Simulate-Failure": "key_1=429,key_2=500"})
    assert r.status_code == 200
    assert r.json()["metadata"]["key_id"] == "key_3"
    assert r.json()["metadata"]["fallback_attempts"] == 2


def test_simulation_disabled_is_ignored(make_client):
    c = make_client(simulation=False)
    r = chat(c, "s-off", "hello", headers={"X-Simulate-Failure": "*=429"})
    assert r.status_code == 200
    assert r.json()["metadata"]["key_id"] == "key_1"


def test_invalid_simulation_header_is_422_and_not_persisted(client):
    r = chat(client, "s-bad", "hi", headers={"X-Simulate-Failure": "key_1=418"})
    assert r.status_code == 422 and "detail" in r.json()
    assert client.get("/sessions/s-bad/messages").status_code == 404


def test_real_provider_errors_trigger_failover(client, provider):
    provider.fail_keys["key_1"] = litellm.RateLimitError(message="quota exceeded", llm_provider="gemini", model="m")
    r = chat(client, "s-real", "real failure")
    assert r.status_code == 200
    assert r.json()["metadata"]["key_id"] == "key_2"
    assert r.json()["metadata"]["fallback_attempts"] == 1


def test_real_all_keys_down_returns_503(client, provider):
    for k in KEYS:
        provider.fail_keys[k] = litellm.InternalServerError(message="down", llm_provider="gemini", model="m")
    r = chat(client, "s-down", "anyone?")
    assert r.status_code == 503 and r.json() == {"detail": "all providers unavailable"}
    assert client.get("/sessions/s-down/messages").status_code == 404


def test_keys_never_leak(client, caplog):
    chat(client, "s-leak", "hi", headers={"X-Simulate-Failure": "*=500"})
    r1 = chat(client, "s-leak", "hi")
    for text in (r1.text, client.get("/health").text, client.get("/sessions/s-leak/messages").text, caplog.text):
        assert "sk-test-secret" not in text


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, {}),
        ("", {}),
        ("key_1=429", {"key_1": 429}),
        ("key_1=429, key_2=500", {"key_1": 429, "key_2": 500}),
        ("*=503", {"key_1": 503, "key_2": 503, "fallback": 503}),
    ],
)
def test_parse_simulation_header(raw, expected):
    assert parse_simulation_header(raw, KEYS) == expected


@pytest.mark.parametrize("raw", ["key_1", "key_1=abc", "key_1=404", "key_9=429"])
def test_parse_simulation_header_rejects(raw):
    with pytest.raises(InvalidSimulationHeader):
        parse_simulation_header(raw, KEYS)
