"""AgriTech Game API – application entry point."""
import time
import uuid
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.redis import close_redis, get_redis
from app.middleware.cors import setup_cors
from app.middleware.rate_limit import RateLimitMiddleware
from app.routers import (
    auth,
    chickens,
    gacha,
    game_wallet,
    leaderboard,
    market,
    missions,
    websocket,
)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup
    await get_redis()  # warm up connection pool
    yield
    # Shutdown
    await close_redis()


# ── App factory ───────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "AgriTech Farm Game REST API\n\n"
            "All endpoints return `{success, data, error, timestamp}`.\n\n"
            "Authenticate via **Bearer** token obtained from `/api/v1/game/auth/login`."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ── Middleware (order matters – outermost first) ───────────────────────
    setup_cors(app)
    app.add_middleware(RateLimitMiddleware)

    # ── Request-ID + timing middleware ────────────────────────────────────
    @app.middleware("http")
    async def request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = round((time.perf_counter() - start) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-Ms"] = str(elapsed)
        return response

    # ── Exception handlers ────────────────────────────────────────────────
    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        from datetime import UTC, datetime
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "success": False,
                "data": None,
                "error": "; ".join(
                    f"{' → '.join(str(loc) for loc in e['loc'])}: {e['msg']}"
                    for e in exc.errors()
                ),
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        from datetime import UTC, datetime
        error_msg = str(exc) if settings.DEBUG else "Internal server error"
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "data": None,
                "error": error_msg,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

    # ── Health (no prefix, no auth) ───────────────────────────────────────
    @app.get("/health", tags=["system"], include_in_schema=not settings.is_production)
    async def health() -> dict:
        return {"status": "ok", "version": settings.APP_VERSION}

    # ── Game routes ───────────────────────────────────────────────────────
    PREFIX = settings.API_PREFIX

    app.include_router(auth.router,        prefix=f"{PREFIX}/auth",        tags=["auth"])
    app.include_router(game_wallet.router, prefix=f"{PREFIX}/wallet",      tags=["wallet"])
    app.include_router(chickens.router,    prefix=f"{PREFIX}/chickens",    tags=["chickens"])
    app.include_router(gacha.router,       prefix=f"{PREFIX}/gacha",       tags=["gacha"])
    app.include_router(market.router,      prefix=f"{PREFIX}/market",      tags=["market"])
    app.include_router(missions.router,    prefix=f"{PREFIX}/missions",    tags=["missions"])
    app.include_router(leaderboard.router, prefix=f"{PREFIX}/leaderboard", tags=["leaderboard"])

    # WebSocket (prefix stripped to /ws for clean URLs)
    app.include_router(websocket.router, prefix="/ws", tags=["websocket"])

    return app


app = create_app()
