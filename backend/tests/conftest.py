"""Test fixtures.

Tests run the real stack: FastAPI -> ChatService -> LiteLLM Router (failover,
caching groups, built-in cache) -> SQLite. Only the network call to the
provider is replaced, using LiteLLM's own `mock_response` mechanism, injected
by a test hook. Simulated failures from X-Simulate-Failure still go through
the production hook and LiteLLM's real fallback path.
"""

from __future__ import annotations

from typing import Any

import litellm
import pytest
from fastapi.testclient import TestClient
from litellm.integrations.custom_logger import CustomLogger

from app.core.config import Settings
from app.main import create_app

LIVE_DELAY_SECONDS = 0.15


class FakeProvider(CustomLogger):
    """Answers like a provider: reply derived from the prompt, usage from its size."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[dict[str, Any]] = []
        self.fail_keys: dict[str, Exception] = {}  # simulate *real* provider errors per key

    async def async_pre_call_deployment_hook(self, kwargs: dict[str, Any], call_type: Any):
        key_id = (kwargs.get("model_info") or {}).get("id")
        messages = kwargs.get("messages") or []
        self.calls.append({"key_id": key_id, "messages": [dict(m) for m in messages]})
        if isinstance(kwargs.get("mock_response"), Exception):
            return kwargs  # production simulation hook already decided this attempt fails
        if key_id in self.fail_keys:
            kwargs["mock_response"] = self.fail_keys[key_id]
            return kwargs
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        turn = sum(1 for m in messages if m["role"] == "user")
        reply = f"Reply #{turn} via {key_id}: {last_user}"
        prompt_tokens = sum(len(str(m["content"]).split()) + 4 for m in messages)
        kwargs["mock_response"] = {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 0,
            "model": str(kwargs.get("model")),
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": reply}}],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": len(reply.split()),
                "total_tokens": prompt_tokens + len(reply.split()),
            },
        }
        kwargs["mock_delay"] = LIVE_DELAY_SECONDS  # only paid on live calls, after the cache check
        return kwargs

    def live_calls_for(self, text: str) -> int:
        return sum(1 for c in self.calls if c["messages"] and c["messages"][-1]["content"] == text)


def make_settings(tmp_path, *, keys: int = 2, simulation: bool = True) -> Settings:
    return Settings(
        api_keys=[f"sk-test-secret-{i}" for i in range(1, keys + 1)],
        database_url=f"sqlite:///{tmp_path}/app.db",
        allowed_origins=["http://localhost:3000"],
        enable_failure_simulation=simulation,
        llm_model="gemini/gemini-3.5-flash-lite",
        default_system_prompt="You are a test assistant.",
        llm_timeout_seconds=10,
        cache_ttl_seconds=3600,
    )


@pytest.fixture
def provider():
    fake = FakeProvider()
    yield fake
    litellm.callbacks = [cb for cb in litellm.callbacks if cb is not fake]


def _client(tmp_path, provider, **kwargs):
    app = create_app(make_settings(tmp_path, **kwargs))
    client = TestClient(app)
    client.__enter__()  # run lifespan (creates gateway, which resets callbacks/cache)
    litellm.callbacks.append(provider)  # after the production hook
    return client


@pytest.fixture
def client(tmp_path, provider):
    c = _client(tmp_path, provider)
    yield c
    c.__exit__(None, None, None)


@pytest.fixture
def make_client(tmp_path, provider):
    clients = []

    def factory(**kwargs):
        c = _client(tmp_path, provider, **kwargs)
        clients.append(c)
        return c

    yield factory
    for c in clients:
        c.__exit__(None, None, None)


def chat(client, session_id: str, message: str, headers: dict | None = None, **extra):
    return client.post("/chat", json={"session_id": session_id, "message": message, **extra}, headers=headers or {})
