"""Command line tools.

    python -m app.cli migrate
    python -m app.cli create-superadmin --email ja@domena.com --password "..." [--name "Ime"]
    python -m app.cli reset-2fa --email korisnik@domena.com
    python -m app.cli maintenance [--dry-run]      (phase 5+)

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
    return 1


if __name__ == "__main__":
    sys.exit(main())
