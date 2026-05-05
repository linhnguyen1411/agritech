from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.config import settings
from app.core.redis import check_rate_limit

# Endpoints exempt from rate limiting
_EXEMPT_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter backed by Redis sorted sets.

    Identifier priority: Authorization JWT subject → IP address.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Skip exempt paths
        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        identifier = self._get_identifier(request)
        allowed, remaining = await check_rate_limit(
            identifier=identifier,
            limit=settings.RATE_LIMIT_PER_MINUTE,
        )

        if not allowed:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "success": False,
                    "data": None,
                    "error": "Rate limit exceeded. Please slow down.",
                    "timestamp": _now_iso(),
                },
                headers={"Retry-After": "60"},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Limit"] = str(settings.RATE_LIMIT_PER_MINUTE)
        return response

    @staticmethod
    def _get_identifier(request: Request) -> str:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            # Use first 32 chars of token as stable key without full JWT decode
            return f"user:{auth[7:39]}"
        client = request.client
        ip = client.host if client else "unknown"
        return f"ip:{ip}"


def _now_iso() -> str:
    from datetime import UTC, datetime
    return datetime.now(UTC).isoformat()
