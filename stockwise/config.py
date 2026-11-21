"""Environment-backed runtime settings. No credentials are stored in source."""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    jwt_secret: str
    frontend_origin: str
    environment: str

    @property
    def secure_cookies(self) -> bool:
        return self.environment.lower() in {"production", "prod"}


def load_settings() -> Settings:
    environment = os.getenv("ENVIRONMENT", "development")
    secret = os.getenv("JWT_SECRET")
    if not secret:
        if environment.lower() in {"production", "prod"}:
            raise RuntimeError("JWT_SECRET must be set in production")
        # A per-process secret keeps local development usable without checking a secret into source.
        secret = secrets.token_urlsafe(48)
    return Settings(
        database_url=os.getenv("DATABASE_URL", "postgresql+psycopg://localhost/stockwise"),
        jwt_secret=secret,
        frontend_origin=os.getenv("FRONTEND_ORIGIN", "http://localhost:3000"),
        environment=environment,
    )
