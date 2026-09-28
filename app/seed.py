"""Seed data. Idempotent — running it again never duplicates or overwrites data.

    python -m app.seed             # full demo (development)
    python -m app.seed --minimal   # settings, pages, catalog, superadmin (production)

`--minimal` fills company settings with placeholders (spec chapter 3) and the
five CMS pages. The full demo seed (vehicles, inquiries, subscribers...) is
added in phase 7.
"""

from __future__ import annotations

import argparse
import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import ROLE_SUPERADMIN, Page, Setting, User
from app.security import hash_password, normalize_email
from app.seed_content import PAGES
from app.services.site import DEFAULTS, invalidate_site_cache
from app.utils import ensure_utf8_console

log = logging.getLogger("seed")


def seed_settings(db: Session) -> int:
    """Insert missing settings keys with placeholder defaults. Never overwrites."""
    existing = set(db.scalars(select(Setting.key)))
    added = 0
    for key, value in DEFAULTS.items():
        if key in existing:
            continue
        if key == "privacy_policy_updated_at":
            value = date.today().isoformat()
        db.add(Setting(key=key, value=value))
        added += 1
    invalidate_site_cache()
    return added


def seed_pages(db: Session) -> int:
    existing = set(db.scalars(select(Page.slug)))
    added = 0
    for page in PAGES:
        if page["slug"] in existing:
            continue
        db.add(Page(slug=page["slug"], title=page["title"], body_html=page["body_html"]))
        added += 1
    return added


SUPERADMIN_EMAIL = "admin@domena.com"


def ensure_user(db: Session, email: str, name: str, role: str, password: str) -> bool:
    """Create a user without 2FA (first login demonstrates the forced 2FA setup)."""
    email = normalize_email(email)
    if db.scalar(select(User.id).where(User.email == email)):
        return False
    db.add(User(email=email, name=name, role=role, password_hash=hash_password(password)))
    return True


def seed_superadmin(db: Session) -> int:
    password = get_settings().SEED_PASSWORD
    return int(ensure_user(db, SUPERADMIN_EMAIL, "Administrator", ROLE_SUPERADMIN, password))


def seed_minimal(db: Session) -> dict:
    result = {
        "settings": seed_settings(db),
        "pages": seed_pages(db),
        "superadmin": seed_superadmin(db),
    }
    db.commit()
    return result


def run_initial_seed(db: Session, demo: bool = False) -> dict:
    """Seed a fresh database (called by run.py / Docker entrypoint).

    demo=True adds the full demo data set (phase 7); otherwise minimal.
    """
    return seed_minimal(db)


def is_database_empty(db: Session) -> bool:
    """True when the instance was never seeded (no settings rows)."""
    return db.scalar(select(Setting.key).limit(1)) is None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Seed podataka (idempotentno).")
    parser.add_argument("--minimal", action="store_true", help="samo postavke, stranice i katalog")
    args = parser.parse_args(argv)
    ensure_utf8_console()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    db = SessionLocal()
    try:
        result = seed_minimal(db)
        log.info("Seed (minimal): %s", result)
        if not args.minimal:
            log.info("Puni demo seed dolazi u fazi 7.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
