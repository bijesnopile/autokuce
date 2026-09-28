"""Run Alembic migrations programmatically (used by run.py, CLI and Docker entrypoint)."""

from __future__ import annotations

from alembic import command
from alembic.config import Config

from app.config import BASE_DIR


def alembic_config() -> Config:
    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "migrations"))
    return cfg


def upgrade_head() -> None:
    command.upgrade(alembic_config(), "head")
