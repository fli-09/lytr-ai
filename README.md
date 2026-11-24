# Lyftr AI — LLM Chatbot with Key Failover and Response Caching

React + FastAPI + LiteLLM + SQLite. A multi-turn chatbot backed by a pool of API keys with automatic, ordered failover, LiteLLM's built-in response cache, per-request token/latency metadata, and SQLite session history.

## 1. Live URLs

| Tier | URL |
|---|---|
| Frontend | https://lytr-ai.vercel.app |
| Backend | https://lytr-ai-production.up.railway.app (try `/health`) |
| Demo video | _add link_ |

**Deploying (what this repo is set up for):**

- **Backend → Railway** (or Fly.io). New service from this repo, root directory `backend` (Dockerfile is detected). Add a **volume mounted at `/data`** so SQLite survives restarts/redeploys. Set variables: `LLM_API_KEYS`, `LLM_MODEL`, `DATABASE_URL=sqlite:////data/app.db`, `ALLOWED_ORIGINS=https://<your-frontend-domain>`, `ENABLE_FAILURE_SIMULATION=true`. The container listens on `$PORT`, which Railway injects.
  Avoid hosts without persistent disks (e.g. Render's free tier): the SQLite file would be wiped on every restart.
- **Frontend → Vercel** (or Netlify/Cloudflare Pages). Root directory `frontend`, framework preset Vite, build `npm run build`, output `dist`. Set `VITE_API_BASE_URL=https://<your-backend-domain>` (no trailing slash) **before** building.
- Check: `GET https://<backend>/health` returns 200, then send a message from the deployed frontend.

## 2. Run locally: with Docker and without

### With Docker

```bash
cp .env.example .env        # then put at least two real keys in LLM_API_KEYS
make up                     # backend http://localhost:8000, frontend http://localhost:3000
make down
```

Windows: run `make` from Git Bash or WSL, or use `docker compose up -d --build` / `docker compose down` directly.

SQLite lives at `/data/app.db` on the named volume `lyftr-data`, so history survives `docker compose restart backend` and `make down && make up`. `docker compose down -v` deletes it.

### Without Docker

Backend (Python 3.11+, tested on 3.13):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
export LLM_API_KEYS="key_one,key_two" DATABASE_URL="sqlite:///./data/app.db" \
       ALLOWED_ORIGINS="http://localhost:3000" ENABLE_FAILURE_SIMULATION=true
uvicorn app.asgi:app --port 8000
python -m pytest                                       # backend tests (no network or real keys needed)
```

Frontend (Node 20+):

```bash
cd frontend
npm install
npm run dev            # http://localhost:3000, talks to http://localhost:8000 in dev
```

## 3. Design decisions: key fallback, caching, SQLite session storage

**Key fallback — LiteLLM Router, not a hand-written loop.**
`LLM_API_KEYS` is parsed in order into `key_1`, `key_2`, …. Each key becomes its own Router model group (named after its key id), and one fallback chain `key_1 → [key_2, key_3, …]` gives deterministic, ordered failover. `LLM_MODEL` may list a **backup model** after the primary (comma-separated). Provider overload ("503 high demand") hits a *model*, so every key fails at once; with a backup model the chain continues `… → key_1@backup → key_2@backup`. `key_id` still names the key that answered, `model` the model that answered, and `fallback_attempts` counts every failed attempt before it. Keys can also be bound to a provider with a prefix (`LLM_API_KEYS=k1,k2,groq:k3`). Each key is paired only with models of its own provider, and plain keys belong to the primary model's provider. With a Groq model at the end of `LLM_MODEL`, an outage of the whole primary provider still leaves a working path. `num_retries=0` means each key is tried once per request. `disable_cooldowns=True` means a failure never puts a key into a global cooldown, so a simulated failure in one request can't affect the next. LiteLLM fails over on any provider error: 429 rate limit, quota exhaustion (often 403/429), 5xx, and also a revoked key (401). If every key fails, the API returns `503 {"detail": "all providers unavailable"}` and nothing is written to history. `key_id` comes from the Router's `model_id` of the deployment that answered. `fallback_attempts` counts the keys that failed before it in that request.

**Self-hosted fallback (optional).** When every key in the pool has failed, one last attempt goes to a self-hosted OpenAI-compatible model: Qwen3-14B in LM Studio, exposed through ngrok, set with `FALLBACK_LLM_*`. It runs through `litellm.acompletion` (non-blocking) with `api_base`, `api_key`, a 120 s timeout and the `ngrok-skip-browser-warning` header. ` /no_think` is appended to a copy of the last user message, and any `<think>…</think>` block is stripped from the reply. If the laptop is offline or the call fails, the response is the same 503, and nothing is cached or stored. A fallback reply reports `key_id: "fallback"`, `model: openai/qwen/qwen3-14b`, and `fallback_attempts` = the number of pool attempts that failed. If any `FALLBACK_LLM_*` value is empty, the fallback is off and the app behaves exactly as before. Every response logs `served_by=<key_id|fallback|cache>`.

**Failure simulation.** `X-Simulate-Failure` is parsed per request, only when `ENABLE_FAILURE_SIMULATION=true`. A LiteLLM `CustomLogger.async_pre_call_deployment_hook` runs for each deployment the Router tries. For targeted keys it sets a `mock_response` exception (`RateLimitError` for 429, `InternalServerError`/`BadGatewayError`/`ServiceUnavailableError` for 500/502/503). The simulated failure therefore goes through LiteLLM's normal exception and fallback path, and the key that succeeds makes a real provider call. State lives in a `contextvar`, so it is request-scoped. An invalid header (unknown key, unsupported status) returns 422. Besides `key_N`, the header accepts three more targets. `*` fails every pool key **and** the self-hosted fallback, so `*=429` always returns the 503 the assignment requires. `keys` fails every pool key but leaves the fallback alive, to test it. `fallback` fails only the fallback.
*Edge case:* a request carrying the simulation header **skips cache reads** (`cache={"no-cache": True}`). Without that, sending `*=429` with an already-cached message (e.g. the README's "What is the capital of France?") would return 200 `LLM_CACHE` instead of the required 503, and `key_1=429` would report `key_id: null` instead of `key_2`. The fresh reply is still written to the cache.

**Caching — LiteLLM's built-in in-memory cache.** `litellm.cache = Cache(type="local")`. The cache key is built by LiteLLM from the model (group) plus the full message list sent to the LLM: system prompt + history + new message. `caching_groups` makes all keys of the same model share one cache namespace (one group per model, so the cache key stays model + messages). The API key is not part of LiteLLM's cache key (checked in litellm 1.110.3 source), so a reply generated by `key_2` is a valid hit for a later request. A cache hit is detected from LiteLLM's own `response._hidden_params["cache_hit"]`, never from latency. On a hit the reply text and token usage are the cached ones, `key_id` is `null` and `fallback_attempts` is `0`. `session_id` is deliberately **not** in the LLM request, so the same first message in a new session is a hit, while any difference in system prompt or history is a miss. TTL is set by `CACHE_TTL_SECONDS` (default 24h; LiteLLM's own default is 10 min). The cache is in-memory, so it resets when the backend restarts.

**SQLite session storage.** stdlib `sqlite3`, schema created on startup:
- the required `messages` table, plus an index on `(session_id, id)`;
- a small `sessions` table holding the optional system-prompt override. It is kept out of `messages` so it never appears in the history endpoint, and later turns keep the override without resending it.

The user row and the assistant row (with its metadata as JSON) are inserted in **one transaction, only after a successful LLM result**, so a 422 or 503 leaves no partial history. Timestamps are server UTC ISO-8601. History is returned oldest first.

**Other choices.** `latency_ms` is measured server-side around the whole chat handling. Interactive docs (`/docs`, `/openapi.json`) are disabled so the public surface is exactly the three contract endpoints. API keys never leave the backend, and a logging filter redacts key values from every log line.

## 4. Verification: how to see failover, cache hits and per-message token usage

```bash
B=http://localhost:8000            # or your deployed backend URL

curl -s $B/health
# {"status":"ok","keys_configured":2,"cache_enabled":true}

# Live call, then the same first message in a NEW session -> LLM_CACHE, identical reply, key_id null
curl -s -XPOST $B/chat -H 'Content-Type: application/json' -d '{"session_id":"demo-1","message":"What is the capital of France?"}'
curl -s -XPOST $B/chat -H 'Content-Type: application/json' -d '{"session_id":"demo-2","message":"What is the capital of France?"}'

# Failover: key_1 fails -> 200 answered by key_2, fallback_attempts 1
curl -s -XPOST $B/chat -H 'Content-Type: application/json' -H 'X-Simulate-Failure: key_1=429' -d '{"session_id":"demo-3","message":"Name three rivers."}'
curl -s -XPOST $B/chat -H 'Content-Type: application/json' -H 'X-Simulate-Failure: key_1=500' -d '{"session_id":"demo-3","message":"And three mountains?"}'

# All keys fail -> 503 {"detail":"all providers unavailable"}, nothing stored
curl -s -i -XPOST $B/chat -H 'Content-Type: application/json' -H 'X-Simulate-Failure: *=429' -d '{"session_id":"demo-4","message":"hello"}'
curl -s -i $B/sessions/demo-4/messages        # 404 {"detail":"session not found"}

# Self-hosted fallback (only if FALLBACK_LLM_* is set): every pool key fails, Qwen answers -> key_id "fallback"
curl -s -XPOST $B/chat -H 'Content-Type: application/json' -H 'X-Simulate-Failure: keys=429' -d '{"session_id":"demo-5","message":"Name a planet."}'

# History (oldest first, no system prompt) with per-message metadata
curl -s $B/sessions/demo-3/messages

# Validation -> 422
curl -s -i -XPOST $B/chat -H 'Content-Type: application/json' -d '{"session_id":"x","message":"   "}'
```

**Per-message token usage:** every assistant reply in the UI shows `source`, `model`, `latency`, `in` (input tokens) and `out` (output tokens) for that request only. In a multi-turn session, `in` grows with the history (it covers system + history + new message) and `out` covers only that reply. Two equal-length first messages in new sessions report about the same `in`.

**In the UI:** the left panel's **Failover test** selector sends `X-Simulate-Failure` with your next messages, and each reply shows which key answered and how many keys failed first. Reload the page (new session) and resend a first message to see `LLM_CACHE`.

**Automated:** `cd backend && python -m pytest` runs 87 tests through the real FastAPI → Router → cache → SQLite stack, with only the provider network call mocked (via LiteLLM's `mock_response`). They cover the contract, validation boundaries, failover for each status, the 503 path, cache hits/misses, token semantics, session isolation, no persistence on failure, and restart persistence.

## 5. Setup Used: your editor and AI tools

- AI: Claude (Anthropic) as the coding agent: read the assignment and spec pack, verified LiteLLM internals, wrote the code and tests, ran browser checks.
- Editor: _fill in (e.g. VS Code)_.

## 6. Bonus features (if any): what you added beyond the requirements and why

- **Self-hosted fallback** (Qwen3-14B via LM Studio + ngrok). Free-tier keys hit rate limits regularly, so a last-resort provider with no shared quota keeps the chat answering. It's off unless configured, and never changes the `*=429 → 503` contract.
- **Failover test control in the UI** — sends `X-Simulate-Failure` from the browser, so failover can be shown against the deployed app without curl.
- **Routing note per reply** ("answered by key_2 after 1 failed key" / "served from LiteLLM cache") — uses the response's own `key_id`/`fallback_attempts`, so you can see each request's path.
- **Honest backend status pill** — driven by real `/health` polling (keys loaded, cache on). It does not claim provider keys are valid.
- **Markdown rendering** (no raw HTML, so model output can't inject markup) and **copy reply**.
- **Readable failure states** — 422/503/network errors appear in the chat. The failed message is marked "not saved to history" and can be put back in the composer.
- **System prompt persisted per session** in a separate table, so later turns keep it and the history endpoint never exposes it.
- **Key redaction in logs** and docs endpoints disabled, to keep the public surface to the contract.
