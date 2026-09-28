"""Local development server (Windows and Linux).

    python run.py                 # http://localhost:8000, auto-reload, SQLite, file email backend
    python run.py --port 8001 --no-reload

Steps: load `.env` (if present) -> `alembic upgrade head` -> seed on an empty
database -> uvicorn with reload.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Lokalni razvojni server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--no-reload", action="store_true", help="bez automatskog ponovnog učitavanja"
    )
    parser.add_argument("--no-seed", action="store_true", help="ne pokreći seed na praznoj bazi")
    args = parser.parse_args()

    os.chdir(BASE_DIR)
    sys.path.insert(0, str(BASE_DIR))
    from app.utils import ensure_utf8_console

    ensure_utf8_console()
    # Sensible local defaults; values from .env or the shell take precedence.
    os.environ.setdefault("APP_ENV", "development")
    os.environ.setdefault("EMAIL_BACKEND", "file")

    from app.config import get_settings

    settings = get_settings()
    for folder in (
        settings.DATA_DIR,
        settings.media_dir,
        settings.outbox_dir,
        settings.backups_dir,
    ):
        folder.mkdir(parents=True, exist_ok=True)

    print(f"[run] Baza: {settings.database_url}")
    print("[run] Migracije (alembic upgrade head)...")
    from app.migrate import upgrade_head

    upgrade_head()

    if not args.no_seed:
        from app.database import SessionLocal
        from app.seed import is_database_empty, run_initial_seed

        db = SessionLocal()
        try:
            if is_database_empty(db):
                print("[run] Prazna baza — pokrećem seed...")
                run_initial_seed(db, demo=settings.is_development or settings.DEMO_SEED)
        finally:
            db.close()

    import uvicorn

    print(f"[run] Javna stranica: http://{args.host}:{args.port}/   Admin: /admin")
    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=not args.no_reload,
        reload_dirs=[str(BASE_DIR / "app")],
        proxy_headers=False,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
