# Memory — Lyftr AI build log

Statuses: VERIFIED = run and checked · IMPLEMENTED = written, not yet run against the real target · NOT VERIFIED / NOT STARTED.

## Current state (2026-11-24, ~21:45 IST)

| Phase | Status | Notes |
|---|---|---|
| 0 Foundation | VERIFIED | Root structure, .gitignore, .gitattributes (LF for Windows), pinned deps |
| 1 Config/SQLite/health | VERIFIED | pytest + live uvicorn |
| 2 LiteLLM failover + simulation | VERIFIED (real Gemini keys) | key_1=429 -> real answer from key_2, fallback_attempts 1; *=429 -> 503 shown in UI, not persisted |
| 3 Chat/history/cache/tokens | VERIFIED (real Gemini keys) | Same first message in new session: LLM_CACHE 4 ms vs LIVE 8311 ms, identical reply, same tokens (32/8); 2nd turn input grew 32->45 |
| 4 Frontend | VERIFIED | Playwright: test IDs, Enter/send, clear, 422/503 UI, failover, cache, reload = new session, mobile no overflow |
| 5 Tests | VERIFIED | 61 passed (`cd backend && python -m pytest`) |
| 6 Docker/make | VERIFIED on user's Windows machine (`docker compose up -d --build`; make not installed on Windows) | Both images build; backend healthy; history for `persist-test` survived `docker compose down` + `up -d` (named volume /data) |
| 7 Deployment | NOT STARTED | Needs user accounts (Railway + Vercel) and real keys |
| 8 README/demo | README written; Live URLs and editor are placeholders; demo NOT STARTED | |

## Key technical facts (verified against litellm==1.110.3)

- Router setup: one model group per key (`key_1`…), `fallbacks=[{"key_1": ["key_2", …]}]`, `num_retries=0`, `disable_cooldowns=True`, `caching_groups=[tuple(key_ids)]`.
- Router falls back on 429, 500, 502, 503, 401, 400 and 403 (probed with mock exceptions).
- `response._hidden_params["cache_hit"] is True` on hits; `_hidden_params["model_id"]` = answering deployment id.
- `api_key` and `mock_response` are NOT part of LiteLLM's cache key; through the Router the cache "model" is the model group/caching group.
- `async_pre_call_deployment_hook` runs per deployment attempt, BEFORE the cache check; `mock_delay` runs AFTER the cache check (so only live calls pay it).
- LiteLLM's cache-hit path imports proxy modules that need `orjson` and `soundfile` → both pinned in requirements.txt. Without them a cache hit raises ModuleNotFoundError.
- Default local cache TTL is 600s, max 200 items → we pass `ttl=CACHE_TTL_SECONDS` (default 86400).

## Decisions

- Requests with `X-Simulate-Failure` skip cache reads (otherwise `*=429` on a cached message returns 200 instead of the PDF's 503). Documented in README.
- Invalid simulation header → 422 (not persisted). Header ignored when the flag is off.
- System prompt override stored in an extra `sessions` table; history endpoint never returns it.
- Empty provider reply → treated as failure (503), since the contract requires a non-empty reply.
- `/docs`, `/openapi.json` disabled ("exactly three endpoints").
- Frontend backend URL: runtime `/config.js` (Docker `API_BASE_URL`) > build-time `VITE_API_BASE_URL` > localhost in dev only.
- Default model `gemini/gemini-3.5-flash-lite` (configurable via `LLM_MODEL`). gemini-2.5-flash returned 404 "no longer available to new users"; 3.x flash models returned 503 high demand on 2026-11-24; 3.5-flash-lite answered (direct API test).

## Model finding (2026-11-24)

- Direct API test with user's key: gemini-2.5-flash -> 404 'no longer available to new users'; gemini-3.8-flash / 3.5-flash / flash-latest -> 503 high demand; gemini-3.5-flash-lite -> OK twice. Default switched to gemini/gemini-3.5-flash-lite.

## Next exact steps

1. User: put 2 real keys (separate projects) in `.env`; run `make up` (Git Bash/WSL on Windows); check /health, a live chat, a cache hit, `key_1=429`, `*=429`.
2. Check real cache-hit latency < live latency and token counts look right.
3. `docker compose restart backend` → history still there.
4. Deploy backend (Railway, volume at /data) and frontend (Vercel, `VITE_API_BASE_URL`); set `ALLOWED_ORIGINS`.
5. Fill in README Live URLs + editor; record the demo.
