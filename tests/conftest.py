"""Test configuration: isolated temp DATA_DIR + SQLite DB, fresh data per test.

Environment variables are set BEFORE the app is imported, so the engine and
settings point at the temporary directory. To run the suite against
PostgreSQL set TEST_DATABASE_URL (the database is wiped!), e.g.
    TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:54329/autokuca_test pytest
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="autokuca-test-"))
os.environ.update(
    {
        "APP_ENV": "test",
        "DATA_DIR": str(_TMP / "data"),
        "OVERRIDES_DIR": str(_TMP / "overrides"),
        "SECRET_KEY": "test-secret-key-that-is-long-enough-0123456789",
        "EMAIL_BACKEND": "file",
        "BASE_URL": "http://testserver",
        "MAINTENANCE_IN_APP": "false",
        "LOG_LEVEL": "WARNING",
    }
)
for key in ("DATABASE_URL", "TURNSTILE_SITE_KEY", "TURNSTILE_SECRET_KEY", "UMAMI_SCRIPT_URL"):
    os.environ.pop(key, None)
if os.environ.get("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from app import models  # noqa: E402,F401
from app.config import get_settings  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.security import limiter  # noqa: E402
from app.seed import seed_minimal  # noqa: E402
from app.services.site import invalidate_site_cache  # noqa: E402

settings = get_settings()


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    engine.dispose()
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.fixture(autouse=True)
def _clean_state():
    """Empty all tables, outbox and media; reset limiter and caches; minimal seed."""
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(delete(table))
    for folder in (settings.outbox_dir, settings.media_dir):
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True, exist_ok=True)
    limiter.reset()
    invalidate_site_cache()
    from app.services import custom_options

    custom_options.invalidate()
    from app.services import pricing

    pricing.invalidate()
    from app.services import popularity

    popularity.invalidate()
    db = SessionLocal()
    try:
        seed_minimal(db, catalog=False)  # tests create their own catalog rows
    finally:
        db.close()
    invalidate_site_cache()
    yield


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def set_plan(monkeypatch):
    """Set the PLAN env value for one test: `set_plan("standard")` (app/plans.py)."""

    def _set(value: str) -> None:
        monkeypatch.setattr(settings, "PLAN", value)
        invalidate_site_cache()

    return _set


def outbox_files() -> list[Path]:
    return sorted(settings.outbox_dir.glob("*.eml"))


# ---------------------------------------------------------------------------
# Browser tests (Playwright + Chromium) against a live server on the test database
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def live_server():
    """uvicorn in a thread (same process, same test DB; tables are cleaned per test)."""
    import socket
    import threading
    import time

    import uvicorn

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="session")
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    try:
        playwright = sync_api.sync_playwright().start()
        instance = playwright.chromium.launch()
    except Exception as exc:  # noqa: BLE001 - Chromium not installed
        pytest.skip(f"Chromium nije dostupan: {exc}")
    yield instance
    instance.close()
    playwright.stop()


@pytest.fixture
def page(browser):
    """Fresh browser context per test; console errors are collected in `page.errors`."""
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    new_page = context.new_page()
    new_page.errors = []
    new_page.on(
        "console", lambda msg: new_page.errors.append(msg.text) if msg.type == "error" else None
    )
    yield new_page
    context.close()
