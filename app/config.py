"""Application configuration loaded from environment variables / `.env`.

All secrets come from the environment. In production (`APP_ENV=production`)
the app refuses to start without a strong `SECRET_KEY` or with SQLite.

SECRET_KEY resolution (`Settings.secret_key`): the environment variable, else the key file
`DATA_DIR/.secret_key` (created once by `python -m app.cli ensure-secret-key` — the Docker
entrypoint does this on the first start). In production nothing is ever generated silently;
in development/test a key is generated and kept in `DATA_DIR/.dev_secret_key`.
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

SECRET_KEY_FILE = ".secret_key"  # production / Docker (created once, never regenerated)
DEV_SECRET_KEY_FILE = ".dev_secret_key"  # development / test (generated automatically)
MIN_SECRET_KEY_LENGTH = 32


class SecretKeyError(RuntimeError):
    """No usable SECRET_KEY (production never falls back to a generated key)."""


@lru_cache
def _read_key_file(path: str) -> str:
    """Key file content; raises FileNotFoundError when missing (exceptions are not cached)."""
    return Path(path).read_text(encoding="utf-8").strip()


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
    def secret_key_file(self) -> Path:
        return self.DATA_DIR / SECRET_KEY_FILE

    @property
    def secret_key(self) -> str:
        """SECRET_KEY from the environment, else from `DATA_DIR/.secret_key`.

        Production raises `SecretKeyError` instead of generating a key: a key that silently
        changes would invalidate sessions, unsubscribe links and every 2FA secret.
        """
        if self.SECRET_KEY:
            return self.SECRET_KEY
        try:
            return _read_key_file(str(self.secret_key_file))
        except FileNotFoundError:
            pass
        if self.is_production:
            raise SecretKeyError(
                "SECRET_KEY nije postavljen, a ne postoji ni "
                f"{self.secret_key_file}. Postavite SECRET_KEY u .env ili pokrenite "
                "`python -m app.cli ensure-secret-key` (Docker entrypoint to radi pri prvom "
                "startu)."
            )
        key_file = self.DATA_DIR / DEV_SECRET_KEY_FILE
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
        try:
            key = self.secret_key
        except SecretKeyError:
            key = ""
        if len(key) < MIN_SECRET_KEY_LENGTH:
            problems.append(
                "SECRET_KEY mora biti postavljen (u .env ili u data/.secret_key) i imati "
                f"barem {MIN_SECRET_KEY_LENGTH} znaka"
            )
        if self.is_sqlite:
            problems.append("DATABASE_URL mora pokazivati na PostgreSQL (ne SQLite)")
        if self.STORAGE_BACKEND not in {"local", "s3"}:
            problems.append("STORAGE_BACKEND mora biti local ili s3")
        if problems:
            raise RuntimeError("Neispravna produkcijska konfiguracija: " + "; ".join(problems))


def running_in_container() -> bool:
    return Path("/.dockerenv").exists()


def ensure_secret_key(settings: Settings) -> str:
    """Make sure a persistent SECRET_KEY exists; returns "env", "file" or "generated".

    The key is generated only once and written to `DATA_DIR/.secret_key` (0400). Inside a
    container DATA_DIR must be a mounted volume, otherwise the key would be lost when the
    container is recreated — then this refuses instead of generating a throw-away key.
    """
    if settings.SECRET_KEY:
        return "env"
    key_file = settings.secret_key_file
    if key_file.exists():
        if len(key_file.read_text(encoding="utf-8").strip()) < MIN_SECRET_KEY_LENGTH:
            raise SecretKeyError(f"{key_file} je prazan ili prekratak (min 32 znaka).")
        return "file"
    if running_in_container() and not os.path.ismount(settings.DATA_DIR):
        raise SecretKeyError(
            f"SECRET_KEY nije postavljen, a {settings.DATA_DIR} nije trajni volumen — "
            "generirani ključ bio bi izgubljen pri ponovnom kreiranju kontejnera (svi korisnici "
            "izgubili bi 2FA). Postavite SECRET_KEY u .env ili montirajte data/ kao volumen."
        )
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    fd = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(secrets.token_urlsafe(48))
    os.chmod(key_file, 0o400)  # read-only for the owner: the key must never be rewritten
    return "generated"


@lru_cache
def get_settings() -> Settings:
    # Tests must not pick up a developer's local .env (e.g. real Turnstile keys).
    if os.environ.get("APP_ENV") == "test":
        return Settings(_env_file=None)
    return Settings()
