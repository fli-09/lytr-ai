"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import router
from app.core.config import Settings, load_settings
from app.core.logging import configure_logging
from app.db.database import Database
from app.services.chat_service import ChatService
from app.services.litellm_gateway import LiteLLMGateway, split_key

logger = logging.getLogger("lyftr")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    configure_logging(settings.api_keys + [split_key(k)[1] for k in settings.api_keys])

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = Database(settings.database_path)
        await db.init_schema()
        gateway = LiteLLMGateway(
            api_keys=settings.api_keys,
            models=settings.llm_models,
            timeout_seconds=settings.llm_timeout_seconds,
            cache_ttl_seconds=settings.cache_ttl_seconds,
        )
        app.state.settings = settings
        app.state.db = db
        app.state.gateway = gateway
        app.state.chat_service = ChatService(db, gateway, settings.default_system_prompt)
        logger.info(
            "ready: keys=%d models=%s db=%s simulation=%s",
            len(gateway.key_ids), ",".join(settings.llm_models), settings.database_path, settings.enable_failure_simulation,
        )
        yield

    # Interactive docs are disabled so the public surface is exactly the three contract endpoints.
    app = FastAPI(title="Lyftr AI", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Simulate-Failure"],
    )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        # FastAPI's default 422 shape, minus echoed input values (could be 4000+ chars).
        errors = [{k: v for k, v in err.items() if k not in {"input", "ctx", "url"}} for err in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": errors})

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception):
        logger.error("unhandled error on %s %s: %s", request.method, request.url.path, type(exc).__name__)
        return JSONResponse(status_code=500, content={"detail": "internal server error"})

    app.include_router(router)
    return app
