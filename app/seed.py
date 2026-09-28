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
from app.models import ROLE_SUPERADMIN, Make, Page, Setting, User, VehicleModel
from app.security import hash_password, normalize_email
from app.seed_catalog import CATALOG
from app.seed_content import PAGES
from app.services.site import DEFAULTS, invalidate_site_cache
from app.utils import ensure_utf8_console, slugify

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


def seed_catalog(db: Session) -> dict:
    """Makes and models (idempotent: existing slugs are skipped)."""
    makes = {m.slug: m for m in db.scalars(select(Make))}
    existing_models = {
        (make_id, slug)
        for make_id, slug in db.execute(select(VehicleModel.make_id, VehicleModel.slug))
    }
    added_makes = added_models = 0
    for make_name, models in CATALOG.items():
        make_slug = slugify(make_name)
        make = makes.get(make_slug)
        if make is None:
            make = Make(name=make_name, slug=make_slug, is_active=True)
            db.add(make)
            db.flush()
            makes[make_slug] = make
            added_makes += 1
        for model_name, vehicle_type in models:
            model_slug = slugify(model_name)
            if (make.id, model_slug) in existing_models:
                continue
            db.add(
                VehicleModel(
                    make_id=make.id, name=model_name, slug=model_slug, vehicle_type=vehicle_type
                )
            )
            existing_models.add((make.id, model_slug))
            added_models += 1
    return {"makes": added_makes, "models": added_models}


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


def seed_minimal(db: Session, catalog: bool = True) -> dict:
    result = {
        "settings": seed_settings(db),
        "pages": seed_pages(db),
        "catalog": seed_catalog(db) if catalog else None,
        "superadmin": seed_superadmin(db),
    }
    db.commit()
    return result


def run_initial_seed(db: Session, demo: bool = False) -> dict:
    """Seed a fresh database (called by run.py / Docker entrypoint).

    demo=True adds the full demo data set (development / DEMO_SEED=true); otherwise minimal.
    """
    result = seed_minimal(db)
    if demo:
        from app.seed_demo import seed_demo

        result["demo"] = seed_demo(db)
    return result


def is_database_empty(db: Session) -> bool:
    """True when the instance was never seeded (no settings rows)."""
    return db.scalar(select(Setting.key).limit(1)) is None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Seed podataka (idempotentno).")
    parser.add_argument(
        "--minimal", action="store_true", help="samo postavke, stranice, katalog i superadmin"
    )
    parser.add_argument(
        "--reset-demo",
        action="store_true",
        help="obriši SVA vozila, upite, pretplatnike i kampanje te ponovno kreiraj demo podatke",
    )
    parser.add_argument(
        "--potvrdi",
        action="store_true",
        help="u produkciji dopusti demo podatke / --reset-demo (inače samo uz DEMO_SEED=true)",
    )
    args = parser.parse_args(argv)
    ensure_utf8_console()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = get_settings()
    if not args.minimal and settings.is_production and not (settings.DEMO_SEED or args.potvrdi):
        # A client's live instance must never get demo vehicles or lose real data by accident.
        log.error(
            "Produkcija: demo podaci se dodaju samo uz DEMO_SEED=true ili --potvrdi "
            "(za pravu instancu koristite --minimal)."
        )
        raise SystemExit(2)
    db = SessionLocal()
    try:
        log.info("Seed (minimal): %s", seed_minimal(db))
        if args.minimal:
            return
        from app.seed_demo import reset_demo, seed_demo

        if args.reset_demo:
            reset_demo(db)
            log.info("Demo podaci obrisani.")
        log.info("Seed (demo): %s", seed_demo(db))
    finally:
        db.close()


if __name__ == "__main__":
    main()
