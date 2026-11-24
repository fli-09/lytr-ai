import pytest

from tests.conftest import chat

REQUIRED_META = {"resolution_source", "model", "latency_ms", "input_tokens", "output_tokens", "key_id", "fallback_attempts"}


def test_chat_returns_exact_contract(client):
    r = chat(client, "s-7f3a", "What is the capital of France?")
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == "s-7f3a"
    assert isinstance(body["reply"], str) and body["reply"]
    meta = body["metadata"]
    assert REQUIRED_META <= meta.keys()
    assert meta["resolution_source"] == "LIVE_INFERENCE"
    assert meta["model"] == "gemini/gemini-3.5-flash-lite"
    assert isinstance(meta["latency_ms"], int) and meta["latency_ms"] >= 0
    assert isinstance(meta["input_tokens"], int) and meta["input_tokens"] > 0
    assert isinstance(meta["output_tokens"], int) and meta["output_tokens"] > 0
    assert meta["key_id"] == "key_1"
    assert meta["fallback_attempts"] == 0


def test_message_is_trimmed_before_use(client, provider):
    r = chat(client, "s-trim", "   hello there   ")
    assert r.status_code == 200
    assert provider.calls[-1]["messages"][-1]["content"] == "hello there"


@pytest.mark.parametrize(
    "payload",
    [
        {"message": "hi"},
        {"session_id": "s1"},
        {"session_id": "", "message": "hi"},
        {"session_id": "   ", "message": "hi"},
        {"session_id": "s1", "message": ""},
        {"session_id": "s1", "message": "     \n\t "},
        {"session_id": "s1", "message": "x" * 4001},
        {"session_id": "x" * 129, "message": "hi"},
        {"session_id": 123, "message": "hi"},
        {"session_id": "s1", "message": 42},
    ],
)
def test_invalid_requests_return_422_json(client, payload):
    r = client.post("/chat", json=payload)
    assert r.status_code == 422
    assert "detail" in r.json()


def test_boundaries_are_accepted(client):
    assert chat(client, "x" * 128, "y" * 4000).status_code == 200
    # 4000 chars after trimming is fine even with surrounding whitespace
    assert chat(client, "s-pad", "  " + "z" * 4000 + "  ").status_code == 200


def test_malformed_json_returns_422(client):
    r = client.post("/chat", content=b'{"session_id": "s1", "message": ', headers={"Content-Type": "application/json"})
    assert r.status_code == 422
    assert "detail" in r.json()


def test_unknown_route_and_method_are_json(client):
    r = client.get("/nope")
    assert r.status_code == 404 and r.json() == {"detail": "Not Found"}
    r = client.get("/chat")
    assert r.status_code == 405 and "detail" in r.json()


def test_422_does_not_echo_input(client):
    r = client.post("/chat", json={"session_id": "s1", "message": "x" * 4001})
    assert "x" * 100 not in r.text


def test_cors_allows_configured_origin_only(client):
    ok = client.options(
        "/chat",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST",
                 "Access-Control-Request-Headers": "content-type,x-simulate-failure"},
    )
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
    bad = client.options("/chat", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"})
    assert bad.headers.get("access-control-allow-origin") is None
