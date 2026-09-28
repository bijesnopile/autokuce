"""Application configuration loaded from environment variables / `.env`.

All secrets come from the environment. In production (`APP_ENV=production`)
the app refuses to start without a strong `SECRET_KEY` or with SQLite.
"""

from __future__ import annotations

import os
import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root (folder that contains `app/`, `run.py`, `alembic.ini`).
BASE_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BASE_DIR / "app"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
        # Empty values in .env (e.g. copied .env.example) mean "use the default".
        env_ignore_empty=True,
    )

    # --- Core -------------------------------------------------------------
    APP_ENV: str = "development"  # development | production | test
    SECRET_KEY: str = ""
    DATABASE_URL: str = ""  # empty -> SQLite in DATA_DIR/app.db
    BASE_URL: str = "http://localhost:8000"
    HTTPS: bool = False
    TRUST_PROXY: bool = False
    LANGUAGE: str = "hr"
    DATA_DIR: Path = BASE_DIR / "data"
    OVERRIDES_DIR: Path = BASE_DIR / "overrides"
    LOG_LEVEL: str = "INFO"

    # --- Storage ------------------------------------------------------------
    STORAGE_BACKEND: str = "local"  # local | s3
    S3_ENDPOINT: str = ""
    S3_BUCKET: str = ""
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_REGION: str = "auto"
    MEDIA_URL: str = ""  # public CDN base URL for media (optional)

    # --- Email --------------------------------------------------------------
    EMAIL_BACKEND: str = "file"  # console | file | brevo
    EMAIL_FROM: str = "noreply@domena.com"
    BREVO_API_KEY: str = ""

    # --- External services (all optional) -----------------------------------
    TURNSTILE_SITE_KEY: str = ""
    TURNSTILE_SECRET_KEY: str = ""
    UMAMI_SCRIPT_URL: str = ""
    UMAMI_WEBSITE_ID: str = ""

    # --- Limits and retention ----------------------------------------------
    INQUIRY_RETENTION_DAYS: int = 365
    SOLD_VISIBLE_DAYS: int = 30
    SESSION_HOURS: int = 12
    MAX_IMAGES_PER_VEHICLE: int = 30
    MAX_UPLOAD_MB: int = 10

    # --- Admin / operations -------------------------------------------------
    ADMIN_IP_ALLOWLIST: str = ""  # comma separated IPs / CIDRs; empty = allow all
    MAINTENANCE_IN_APP: bool = True
    SEED_PASSWORD: str = "Promijeni-me-2026!"
    DEMO_SEED: bool = False

    @field_validator("APP_ENV")
    @classmethod
    def _check_env(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"development", "production", "test"}:
            raise ValueError("APP_ENV mora biti development, production ili test")
        return value

    # ------------------------------------------------------------------------
    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"

    @property
    def database_url(self) -> str:
        if self.DATABASE_URL:
            url = self.DATABASE_URL
            # Accept plain postgres:// URLs and use the psycopg (v3) driver.
            if url.startswith("postgres://"):
                url = "postgresql+psycopg://" + url[len("postgres://") :]
            elif url.startswith("postgresql://"):
                url = "postgresql+psycopg://" + url[len("postgresql://") :]
            return url
        return f"sqlite:///{(self.DATA_DIR / 'app.db').as_posix()}"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def media_dir(self) -> Path:
        return self.DATA_DIR / "media"

    @property
    def outbox_dir(self) -> Path:
        return self.DATA_DIR / "outbox"

    @property
    def backups_dir(self) -> Path:
        return self.DATA_DIR / "backups"

    @property
    def base_url(self) -> str:
        return self.BASE_URL.rstrip("/")

    @property
    def turnstile_enabled(self) -> bool:
        return bool(self.TURNSTILE_SITE_KEY and self.TURNSTILE_SECRET_KEY)

    @property
    def umami_enabled(self) -> bool:
        return bool(self.UMAMI_SCRIPT_URL and self.UMAMI_WEBSITE_ID)

    @property
    def secret_key(self) -> str:
        """Return SECRET_KEY; in development a random key is persisted in DATA_DIR."""
        if self.SECRET_KEY:
            return self.SECRET_KEY
        key_file = self.DATA_DIR / ".dev_secret_key"
        if key_file.exists():
            return key_file.read_text(encoding="utf-8").strip()
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        key = secrets.token_urlsafe(48)
        key_file.write_text(key, encoding="utf-8")
        return key

    def validate_for_startup(self) -> None:
        """Refuse to start with an insecure production configuration."""
        if not self.is_production:
            return
        problems = []
        if len(self.SECRET_KEY) < 32:
            problems.append("SECRET_KEY mora biti postavljen i imati barem 32 znaka")
        if self.is_sqlite:
            problems.append("DATABASE_URL mora pokazivati na PostgreSQL (ne SQLite)")
        if self.STORAGE_BACKEND not in {"local", "s3"}:
            problems.append("STORAGE_BACKEND mora biti local ili s3")
        if problems:
            raise RuntimeError("Neispravna produkcijska konfiguracija: " + "; ".join(problems))


@lru_cache
def get_settings() -> Settings:
    # Tests must not pick up a developer's local .env (e.g. real Turnstile keys).
    if os.environ.get("APP_ENV") == "test":
        return Settings(_env_file=None)
    return Settings()
