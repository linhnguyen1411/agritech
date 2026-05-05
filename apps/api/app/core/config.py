from typing import Literal

from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── App ───────────────────────────────────────────────────────────────────
    APP_NAME: str = "AgriTech Game API"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = False
    API_PREFIX: str = "/api/v1/game"

    # ── Security ──────────────────────────────────────────────────────────────
    SECRET_KEY: str = "change-me-use-openssl-rand-hex-32"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/agritech"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_ECHO: bool = False

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379"
    REDIS_CACHE_TTL: int = 300          # seconds
    RATE_LIMIT_PER_MINUTE: int = 60

    # ── CORS ──────────────────────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
    ]
    CORS_PRODUCTION_ORIGIN: str = ""    # e.g. https://agritech.game

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return list(v)  # type: ignore[arg-type]

    def get_all_cors_origins(self) -> list[str]:
        origins = list(self.CORS_ORIGINS)
        if self.CORS_PRODUCTION_ORIGIN:
            origins.append(self.CORS_PRODUCTION_ORIGIN)
        return origins

    # ── Game ──────────────────────────────────────────────────────────────────
    GACHA_BASE_COST_FTK: float = 100.0
    MARKET_FEE_PERCENT: float = 2.5     # % of sale price
    MARKET_BURN_PERCENT: float = 1.0    # % burned from fee
    DAILY_LOGIN_BONUS_FTK: float = 10.0

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


settings = Settings()
