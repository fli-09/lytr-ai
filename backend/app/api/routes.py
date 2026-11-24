"""The three public endpoints. Routes stay thin; logic lives in services."""

from __future__ import annotations

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from app.schemas.chat import ChatRequest, ChatResponse, HealthResponse
from app.services.failure_simulation import InvalidSimulationHeader, parse_simulation_header
from app.services.litellm_gateway import AllProvidersUnavailable

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(request: Request):
    state = request.app.state
    db_ok = await state.db.ping()
    keys = len(state.gateway.key_ids)
    if not db_ok or keys < 2:
        return JSONResponse(status_code=503, content={"detail": "service not ready"})
    return {"status": "ok", "keys_configured": keys, "cache_enabled": state.gateway.cache_enabled}


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    request: Request,
    x_simulate_failure: str | None = Header(default=None, alias="X-Simulate-Failure"),
):
    state = request.app.state
    simulation: dict[str, int] = {}
    if state.settings.enable_failure_simulation:
        try:
            simulation = parse_simulation_header(x_simulate_failure, state.gateway.key_ids)
        except InvalidSimulationHeader as exc:
            return JSONResponse(status_code=422, content={"detail": str(exc)})
    try:
        return await state.chat_service.chat(body.session_id, body.message, body.system_prompt, simulation)
    except AllProvidersUnavailable:
        return JSONResponse(status_code=503, content={"detail": "all providers unavailable"})


@router.get("/sessions/{session_id}/messages")
async def session_messages(session_id: str, request: Request):
    messages = await request.app.state.db.get_history(session_id)
    if not messages:
        return JSONResponse(status_code=404, content={"detail": "session not found"})
    return {"session_id": session_id, "messages": messages}
