"""Environment-backed runtime settings. No credentials are stored in source."""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass

EXAMPLE_JWT_SECRET = "replace-with-a-random-secret-before-deploying"
MIN_JWT_SECRET_LENGTH = 32
DEFAULT_MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def load_max_upload_bytes() -> int:
    raw = os.getenv("MAX_UPLOAD_BYTES", str(DEFAULT_MAX_UPLOAD_BYTES))
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError("MAX_UPLOAD_BYTES must be a positive integer") from exc
    if value < 1:
        raise RuntimeError("MAX_UPLOAD_BYTES must be a positive integer")
    return value


def format_upload_limit(value: int) -> str:
    """Return a compact binary-size label for a configured upload limit."""
    mib = 1024 * 1024
    kib = 1024
    if value >= mib:
        amount = value // mib if value % mib == 0 else round(value / mib, 1)
        return f"{amount:g} MiB"
    if value >= kib and value % kib == 0:
        return f"{value // kib} KiB"
    return f"{value} bytes"


def normalize_database_url(url: str) -> str:
    """Ensure PostgreSQL URLs select the psycopg 3 SQLAlchemy driver."""
    for scheme in ("postgresql://", "postgres://"):
        if url.startswith(scheme):
            return "postgresql+psycopg://" + url[len(scheme):]
    return url


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
    if environment.lower() in {"production", "prod"}:
        if len(secret) < MIN_JWT_SECRET_LENGTH:
            raise RuntimeError(f"JWT_SECRET must be at least {MIN_JWT_SECRET_LENGTH} characters in production")
        if secrets.compare_digest(secret, EXAMPLE_JWT_SECRET):
            raise RuntimeError("JWT_SECRET must not equal the example value in production")
    return Settings(
        database_url=normalize_database_url(
            os.getenv("DATABASE_URL", "postgresql+psycopg://localhost/stockwise")
        ),
        jwt_secret=secret,
        frontend_origin=os.getenv("FRONTEND_ORIGIN", "http://localhost:3000"),
        environment=environment,
    )
