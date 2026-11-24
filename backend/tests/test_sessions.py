import sqlite3

from tests.conftest import chat


def test_history_oldest_first_with_metadata(client):
    chat(client, "s-hist", "first question")
    chat(client, "s-hist", "second question")
    r = client.get("/sessions/s-hist/messages")
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == "s-hist"
    msgs = body["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert msgs[0]["content"] == "first question"
    assert msgs[2]["content"] == "second question"
    assert "metadata" not in msgs[0]
    for m in (msgs[1], msgs[3]):
        assert m["metadata"]["resolution_source"] in {"LIVE_INFERENCE", "LLM_CACHE"}
        assert isinstance(m["metadata"]["input_tokens"], int)
        assert isinstance(m["metadata"]["output_tokens"], int)


def test_unknown_session_returns_404(client):
    r = client.get("/sessions/does-not-exist/messages")
    assert r.status_code == 404
    assert r.json() == {"detail": "session not found"}


def test_multi_turn_sends_history_to_llm(client, provider):
    chat(client, "s-mt", "My name is Anurag.")
    chat(client, "s-mt", "What is my name?")
    sent = provider.calls[-1]["messages"]
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "user"]
    assert sent[1]["content"] == "My name is Anurag."
    assert sent[-1]["content"] == "What is my name?"


def test_sessions_are_isolated(client, provider):
    chat(client, "s-a", "secret for A")
    chat(client, "s-b", "hello from B")
    sent_b = provider.calls[-1]["messages"]
    assert all("secret for A" not in m["content"] for m in sent_b)
    msgs_b = client.get("/sessions/s-b/messages").json()["messages"]
    assert [m["content"] for m in msgs_b if m["role"] == "user"] == ["hello from B"]


def test_system_prompt_override_is_used_and_not_exposed(client, provider):
    chat(client, "s-sys", "hi", system_prompt="Talk like a pirate.")
    assert provider.calls[-1]["messages"][0] == {"role": "system", "content": "Talk like a pirate."}
    # later turns in the same session keep the override without resending it
    chat(client, "s-sys", "again")
    assert provider.calls[-1]["messages"][0]["content"] == "Talk like a pirate."
    history = client.get("/sessions/s-sys/messages").text
    assert "pirate" not in history
    # other sessions still get the default prompt
    chat(client, "s-other", "hi")
    assert provider.calls[-1]["messages"][0]["content"] == "You are a test assistant."


def test_rows_stored_with_iso_timestamps(client, tmp_path):
    chat(client, "s-db", "store me")
    conn = sqlite3.connect(tmp_path / "app.db")
    rows = conn.execute("SELECT role, content, metadata, created_at FROM messages WHERE session_id='s-db' ORDER BY id").fetchall()
    conn.close()
    assert [r[0] for r in rows] == ["user", "assistant"]
    assert rows[0][2] is None and rows[1][2] is not None
    from datetime import datetime
    for r in rows:
        datetime.fromisoformat(r[3])


def test_failed_requests_are_not_persisted(client):
    client.post("/chat", json={"session_id": "s-fail", "message": ""})
    chat(client, "s-fail", "boom", headers={"X-Simulate-Failure": "*=429"})
    assert client.get("/sessions/s-fail/messages").status_code == 404


def test_history_survives_app_restart(make_client):
    first = make_client()
    chat(first, "s-persist", "remember me")
    first.__exit__(None, None, None)
    second = make_client()  # new app, same SQLite file
    msgs = second.get("/sessions/s-persist/messages").json()["messages"]
    assert msgs[0]["content"] == "remember me"
