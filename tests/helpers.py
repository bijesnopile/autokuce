"""Shared helpers for tests (users, login, CSRF, TOTP codes, outbox)."""

from __future__ import annotations

import email
import re
import time
from email import policy
from pathlib import Path

import pyotp

from app.config import get_settings
from app.database import SessionLocal
from app.models import User
from app.security import (
    encrypt_secret,
    generate_token,
    hash_password,
    hash_recovery_code,
    hash_token,
)
from app.services.auth import SESSION_COOKIE

PASSWORD = "Testna-Lozinka-2026!"
CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


def create_user(
    email: str = "vlasnik@test.hr",
    role: str = "owner",
    password: str = PASSWORD,
    totp: bool = True,
    name: str = "Test Korisnik",
    recovery_codes: list[str] | None = None,
) -> tuple[int, str | None]:
    """Create a user directly in the DB. Returns (user_id, totp_secret)."""
    db = SessionLocal()
    try:
        secret = pyotp.random_base32() if totp else None
        user = User(
            email=email,
            name=name,
            role=role,
            password_hash=hash_password(password) if password else None,
            totp_secret=encrypt_secret(secret) if secret else None,
            totp_enabled=bool(totp),
            recovery_codes=[hash_recovery_code(c) for c in (recovery_codes or [])],
        )
        db.add(user)
        db.commit()
        return user.id, secret
    finally:
        db.close()


def login_as(client, user_id: int) -> str:
    """Fast login: create a session row directly and set the cookie on the client."""
    from datetime import timedelta

    from app.database import utcnow
    from app.models import UserSession

    token = generate_token(32)
    db = SessionLocal()
    try:
        now = utcnow()
        db.add(
            UserSession(
                token_hash=hash_token(token),
                user_id=user_id,
                ip="testclient",
                user_agent="pytest",
                created_at=now,
                last_seen_at=now,
                expires_at=now + timedelta(hours=12),
            )
        )
        db.commit()
    finally:
        db.close()
    client.cookies.set(SESSION_COOKIE, token, domain="testserver.local", path="/admin")
    return token


def csrf_from(html: str) -> str:
    match = CSRF_RE.search(html)
    assert match, "CSRF token not found in page"
    return match.group(1)


def get_csrf(client, path: str = "/admin/prijava") -> str:
    return csrf_from(client.get(path).text)


def totp_now(secret: str, step_offset: int = 0) -> str:
    return pyotp.TOTP(secret).at(time.time() + 30 * step_offset)


def login_via_ui(client, email: str, password: str, secret: str, step_offset: int = 0):
    """Full login: password form -> 2FA form. Returns the final response."""
    token = get_csrf(client)
    response = client.post(
        "/admin/prijava",
        data={"email": email, "password": password, "csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text[:500]
    assert response.headers["location"] == "/admin/prijava/2fa"
    token = get_csrf(client, "/admin/prijava/2fa")
    return client.post(
        "/admin/prijava/2fa",
        data={"code": totp_now(secret, step_offset), "csrf_token": token},
        follow_redirects=False,
    )


def outbox() -> list[Path]:
    return sorted(get_settings().outbox_dir.glob("*.eml"))


def read_eml(path: Path) -> email.message.EmailMessage:
    return email.message_from_bytes(path.read_bytes(), policy=policy.default)


def eml_text(message) -> str:
    return message.get_body(preferencelist=("plain",)).get_content()


def find_link(text: str, prefix: str) -> str:
    match = re.search(re.escape(prefix) + r"[^\s\"<]+", text)
    assert match, f"link {prefix} not found"
    return match.group(0)
