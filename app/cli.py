"""Command line tools.

    python -m app.cli migrate
    python -m app.cli create-superadmin --email ja@domena.com --password "..." [--name "Ime"]
    python -m app.cli reset-2fa --email korisnik@domena.com
    python -m app.cli maintenance [--dry-run] [--force]
    python -m app.cli ensure-secret-key            (Docker entrypoint, prvi start)
    python -m app.cli check-secret-key [--accept]  (Docker entrypoint, svaki start)

In Docker: `docker compose exec app python -m app.cli <command>`.
"""

from __future__ import annotations

import argparse
import logging
import sys

from app.utils import ensure_utf8_console

log = logging.getLogger("cli")


def cmd_create_superadmin(email: str, password: str, name: str) -> int:
    from app.database import SessionLocal
    from app.models import ROLE_SUPERADMIN
    from app.security import hash_password, validate_password_strength
    from app.services import audit
    from app.services.auth import get_user_by_email

    error = validate_password_strength(password)
    if error:
        log.error(error)
        return 2
    db = SessionLocal()
    try:
        user = get_user_by_email(db, email)
        if user:
            user.role = ROLE_SUPERADMIN
            user.is_active = True
            user.password_hash = hash_password(password)
            action = "ažuriran"
        else:
            from app.models import User
            from app.security import normalize_email

            user = User(
                email=normalize_email(email),
                name=name,
                role=ROLE_SUPERADMIN,
                password_hash=hash_password(password),
            )
            db.add(user)
            action = "kreiran"
        db.flush()
        audit.log(db, None, "user.update", "user", user.id, {"cli": "create-superadmin"})
        db.commit()
        log.info("Superadmin %s (%s). Pri prvoj prijavi postavlja 2FA.", action, user.email)
        return 0
    finally:
        db.close()


def cmd_reset_2fa(email: str) -> int:
    from app.database import SessionLocal
    from app.services import audit
    from app.services.auth import delete_user_sessions, get_user_by_email

    db = SessionLocal()
    try:
        user = get_user_by_email(db, email)
        if user is None:
            log.error("Korisnik %s ne postoji.", email)
            return 1
        user.totp_enabled = False
        user.totp_secret = None
        user.totp_last_step = None
        user.recovery_codes = []
        delete_user_sessions(db, user.id)
        audit.log(db, None, "user.2fa_reset", "user", user.id, {"cli": True})
        db.commit()
        log.info("2FA poništena za %s; korisnik je odjavljen i mora je ponovno postaviti.", email)
        return 0
    finally:
        db.close()


def cmd_maintenance(dry_run: bool, force: bool = False) -> int:
    """Run all retention/housekeeping steps (cron at 04:00 or manually).

    Without --force, today's run is claimed first (same guard as the in-app thread), so a
    cron job and MAINTENANCE_IN_APP=true never both run on the same day.
    """
    from app.database import SessionLocal
    from app.services import maintenance
    from app.services.site import invalidate_site_cache, set_values
    from app.utils import local_today

    today = local_today().isoformat()
    db = SessionLocal()
    try:
        if not dry_run and not force and not maintenance.claim_daily_run(db, today):
            log.info("Održavanje je danas već izvedeno. Ponovno izvođenje: --force")
            return 0
        result = maintenance.run_all(db, dry_run=dry_run)
        if dry_run:
            db.rollback()
        else:
            set_values(db, {maintenance.LAST_RUN_KEY: today})
            db.commit()
            invalidate_site_cache()
        log.info(
            "Ukupno obrađeno zapisa: %s%s", sum(result.values()), " (dry-run)" if dry_run else ""
        )
        return 0
    finally:
        db.close()


def cmd_wait_db(timeout: int) -> int:
    """Wait until the database accepts connections (Docker entrypoint)."""
    import time

    from sqlalchemy import text

    from app.database import engine

    deadline = time.monotonic() + timeout
    while True:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            log.info("Baza je dostupna.")
            return 0
        except Exception as exc:  # noqa: BLE001 - any connection error: retry until timeout
            if time.monotonic() >= deadline:
                log.error("Baza nije dostupna nakon %s s: %s", timeout, exc.__class__.__name__)
                return 1
            time.sleep(1)


SECRET_FINGERPRINT_KEY = "secret_key_fingerprint"


def cmd_ensure_secret_key() -> int:
    """Create DATA_DIR/.secret_key once when SECRET_KEY is not set (never regenerates)."""
    from app.config import SecretKeyError, ensure_secret_key, get_settings

    settings = get_settings()
    try:
        status = ensure_secret_key(settings)
    except (SecretKeyError, OSError) as exc:
        log.error("GREŠKA: %s", exc)
        return 1
    if status == "env":
        log.info("SECRET_KEY je zadan u okruženju (.env).")
    elif status == "file":
        log.info("Koristim postojeći ključ iz %s.", settings.secret_key_file)
    else:
        log.warning(
            "SECRET_KEY nije zadan — generiran je jednom i trajno spremljen u %s. Mapa data/ "
            "mora ostati sačuvana (volumen, backup); ključ možete prenijeti i u .env.",
            settings.secret_key_file,
        )
    return 0


def cmd_check_secret_key(accept: bool) -> int:
    """Compare the key with the fingerprint stored in the DB (first start: store it).

    A different key means sessions, unsubscribe links and every 2FA secret stop working —
    usually a lost data/.secret_key or a wrong .env — so the start is refused.
    """
    from app.config import SecretKeyError, get_settings
    from app.database import SessionLocal
    from app.models import Setting
    from app.security import secret_key_fingerprint

    try:
        key = get_settings().secret_key
    except SecretKeyError as exc:
        log.error("GREŠKA: %s", exc)
        return 1
    fingerprint = secret_key_fingerprint(key)
    db = SessionLocal()
    try:
        row = db.get(Setting, SECRET_FINGERPRINT_KEY)
        if row is None:
            db.add(Setting(key=SECRET_FINGERPRINT_KEY, value=fingerprint))
            db.commit()
            log.info("Otisak SECRET_KEY zapisan (prvi start).")
            return 0
        if row.value == fingerprint:
            log.info("SECRET_KEY odgovara ovoj bazi.")
            return 0
        if accept:
            row.value = fingerprint
            db.commit()
            log.warning(
                "Prihvaćen NOVI SECRET_KEY. Postojeće 2FA tajne su nečitljive: svakom korisniku "
                "pokrenite `python -m app.cli reset-2fa --email ...`."
            )
            return 0
        log.error(
            "GREŠKA: SECRET_KEY se ne podudara s ključem s kojim je ova baza radila. Start je "
            "odbijen jer bi sve 2FA tajne, sesije i poveznice za odjavu prestale vrijediti.\n"
            "  Najčešći uzrok: izgubljen data/.secret_key (data/ nije trajni volumen) ili "
            "pogrešan SECRET_KEY u .env, ili je vraćen backup druge instance.\n"
            "  Rješenje: vratite stari ključ (data/.secret_key iz backupa ili stari SECRET_KEY "
            "u .env). Ako je promjena namjerna: `python -m app.cli check-secret-key --accept`, "
            "zatim reset-2fa za sve korisnike."
        )
        return 1
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Autokuća CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="primijeni Alembic migracije (upgrade head)")

    p_admin = sub.add_parser("create-superadmin", help="kreiraj ili ažuriraj superadmina")
    p_admin.add_argument("--email", required=True)
    p_admin.add_argument("--password", required=True)
    p_admin.add_argument("--name", default="Administrator")

    p_2fa = sub.add_parser("reset-2fa", help="poništi 2FA korisnika (izgubljen mobitel)")
    p_2fa.add_argument("--email", required=True)

    p_maint = sub.add_parser("maintenance", help="dnevno održavanje (retencija podataka)")
    p_maint.add_argument("--dry-run", action="store_true", help="samo prikaži, ništa ne briši")
    p_maint.add_argument(
        "--force", action="store_true", help="izvedi i ako je održavanje danas već izvedeno"
    )

    p_wait = sub.add_parser("wait-db", help="čekaj da baza postane dostupna (Docker)")
    p_wait.add_argument("--timeout", type=int, default=60, help="sekundi (default 60)")

    sub.add_parser(
        "ensure-secret-key",
        help="jednom generiraj trajni data/.secret_key ako SECRET_KEY nije zadan",
    )
    p_check = sub.add_parser(
        "check-secret-key", help="provjeri da SECRET_KEY odgovara bazi (odbij start ako ne)"
    )
    p_check.add_argument(
        "--accept", action="store_true", help="namjerna promjena ključa: prihvati novi ključ"
    )

    args = parser.parse_args(argv)
    ensure_utf8_console()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.command == "migrate":
        from app.migrate import upgrade_head

        upgrade_head()
        return 0
    if args.command == "create-superadmin":
        return cmd_create_superadmin(args.email, args.password, args.name)
    if args.command == "reset-2fa":
        return cmd_reset_2fa(args.email)
    if args.command == "maintenance":
        return cmd_maintenance(args.dry_run, args.force)
    if args.command == "wait-db":
        return cmd_wait_db(args.timeout)
    if args.command == "ensure-secret-key":
        return cmd_ensure_secret_key()
    if args.command == "check-secret-key":
        return cmd_check_secret_key(args.accept)
    return 1


if __name__ == "__main__":
    sys.exit(main())
