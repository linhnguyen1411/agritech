from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings


def setup_cors(app: FastAPI) -> None:
    """Attach CORSMiddleware with environment-aware origins."""
    origins = settings.get_all_cors_origins()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Accept",
            "X-Request-ID",
        ],
        expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining"],
        max_age=600,
    )
