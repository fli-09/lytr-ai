"""Chat orchestration: history -> LLM messages -> gateway -> atomic persistence."""

from __future__ import annotations

import time
from typing import Any

from app.db.database import Database
from app.services.litellm_gateway import LiteLLMGateway


class ChatService:
    def __init__(self, db: Database, gateway: LiteLLMGateway, default_system_prompt: str) -> None:
        self.db = db
        self.gateway = gateway
        self.default_system_prompt = default_system_prompt

    async def chat(
        self,
        session_id: str,
        message: str,
        system_prompt: str | None,
        simulation: dict[str, int],
    ) -> dict[str, Any]:
        started = time.perf_counter()

        history = await self.db.get_history(session_id)
        if system_prompt is not None:
            effective_prompt = system_prompt
        else:
            effective_prompt = await self.db.get_system_prompt(session_id) or self.default_system_prompt

        # Exactly what the LLM sees, and therefore what the cache key covers:
        # system prompt + prior turns (oldest first) + the new user message.
        llm_messages = [{"role": "system", "content": effective_prompt}]
        llm_messages += [{"role": m["role"], "content": m["content"]} for m in history]
        llm_messages.append({"role": "user", "content": message})

        result = await self.gateway.complete(llm_messages, simulation)  # raises AllProvidersUnavailable

        metadata = {
            "resolution_source": result.resolution_source,
            "model": result.model,
            "latency_ms": int(round((time.perf_counter() - started) * 1000)),
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "key_id": result.key_id,
            "fallback_attempts": result.fallback_attempts,
        }
        # Persist only after success; both rows in one transaction.
        await self.db.save_exchange(session_id, message, result.reply, metadata, system_prompt)
        return {"session_id": session_id, "reply": result.reply, "metadata": metadata}
