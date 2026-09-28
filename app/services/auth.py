"""Authentication helpers: server-side sessions, lockout, one-time tokens, 2FA state.

Flow: password OK -> signed `ak_pending` cookie (10 min, "password OK, waiting
for 2FA") -> TOTP/recovery code (or forced 2FA setup) -> session row + `session`
cookie. Only the SHA-256 hash of the session token is stored in the DB.
"""

from __future__ import annotations

import base64
import io
import re
from datetime import timedelta

import qrcode
from fastapi import Request, Response
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import utcnow
from app.models import AuthToken, User, UserSession
from app.security import (
    client_ip,
    generate_token,
    hash_token,
    normalize_email,
    sign_value,
    unsign_value,
)

settings = get_settings()

SESSION_COOKIE = "session"
PENDING_COOKIE = "ak_pending"
PENDING_MAX_AGE = 600  # 10 minutes between password and 2FA code
LOCK_THRESHOLD = 5
LOCK_MINUTES = 15
LAST_SEEN_INTERVAL = timedelta(minutes=5)
INVITE_HOURS = 48
RESET_HOURS = 1


# ---------------------------------------------------------------------------
# Users and lockout
# ---------------------------------------------------------------------------
def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == normalize_email(email)))


def is_locked(user: User) -> bool:
    return bool(user.locked_until and user.locked_until > utcnow())


def register_failure(user: User) -> None:
    """Count a failed password/2FA attempt; lock the account after 5 in a row."""
    user.failed_attempts = (user.failed_attempts or 0) + 1
    if user.failed_attempts >= LOCK_THRESHOLD:
        user.locked_until = utcnow() + timedelta(minutes=LOCK_MINUTES)
        user.failed_attempts = 0


def reset_failures(user: User) -> None:
    user.failed_attempts = 0
    user.locked_until = None


# ---------------------------------------------------------------------------
# Server-side sessions
# ---------------------------------------------------------------------------
def create_session(db: Session, user: User, request: Request) -> str:
    """Create a new session row and return the raw token (goes only into the cookie)."""
    token = generate_token(32)
    now = utcnow()
    db.add(
        UserSession(
            token_hash=hash_token(token),
            user_id=user.id,
            ip=client_ip(request),
            user_agent=(request.headers.get("user-agent") or "")[:300],
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(hours=settings.SESSION_HOURS),
        )
    )
    return token


def load_session(db: Session, token: str | None) -> UserSession | None:
    """Return a valid session (not expired, active user) or None. Touches last_seen_at."""
    if not token:
        return None
    session = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token)))
    if session is None:
        return None
    now = utcnow()
    if session.expires_at <= now or not session.user.is_active:
        db.delete(session)
        db.commit()
        return None
    if now - session.last_seen_at > LAST_SEEN_INTERVAL:
        session.last_seen_at = now
        db.commit()
    return session


def delete_session(db: Session, token: str | None) -> None:
    if token:
        db.execute(delete(UserSession).where(UserSession.token_hash == hash_token(token)))


def delete_user_sessions(db: Session, user_id: int, except_session_id: int | None = None) -> int:
    stmt = delete(UserSession).where(UserSession.user_id == user_id)
    if except_session_id is not None:
        stmt = stmt.where(UserSession.id != except_session_id)
    return db.execute(stmt).rowcount or 0


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.SESSION_HOURS * 3600,
        path="/admin",
        httponly=True,
        secure=settings.HTTPS,
        samesite="lax",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/admin", httponly=True, secure=settings.HTTPS)


# ---------------------------------------------------------------------------
# Pending 2FA state (signed cookie, not a DB session)
# ---------------------------------------------------------------------------
def set_pending_cookie(response: Response, user_id: int, next_url: str) -> None:
    value = sign_value({"uid": user_id, "next": next_url}, salt="pending-2fa")
    response.set_cookie(
        PENDING_COOKIE,
        value,
        max_age=PENDING_MAX_AGE,
        path="/admin",
        httponly=True,
        secure=settings.HTTPS,
        samesite="lax",
    )


def read_pending(request: Request) -> dict | None:
    raw = request.cookies.get(PENDING_COOKIE)
    if not raw:
        return None
    data = unsign_value(raw, salt="pending-2fa", max_age=PENDING_MAX_AGE)
    return data if isinstance(data, dict) and "uid" in data else None


def clear_pending_cookie(response: Response) -> None:
    response.delete_cookie(PENDING_COOKIE, path="/admin", httponly=True, secure=settings.HTTPS)


# ---------------------------------------------------------------------------
# One-time tokens (invite / password reset)
# ---------------------------------------------------------------------------
def create_auth_token(db: Session, user: User, purpose: str, hours: int) -> str:
    """Invalidate older unused tokens of the same purpose and create a new one."""
    now = utcnow()
    db.execute(
        update(AuthToken)
        .where(
            AuthToken.user_id == user.id,
            AuthToken.purpose == purpose,
            AuthToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    raw = generate_token(32)
    db.add(
        AuthToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=hash_token(raw),
            expires_at=now + timedelta(hours=hours),
        )
    )
    return raw


def get_valid_token(db: Session, raw: str, purpose: str) -> AuthToken | None:
    token = db.scalar(select(AuthToken).where(AuthToken.token_hash == hash_token(raw or "")))
    if token is None or token.purpose != purpose or token.used_at is not None:
        return None
    if token.expires_at <= utcnow() or not token.user.is_active:
        return None
    return token


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------
def safe_next(url: str | None, default: str = "/admin") -> str:
    """Only allow local admin paths as redirect targets (no open redirects)."""
    if not url or not url.startswith("/admin") or url.startswith("//") or "\\" in url:
        return default
    if url.startswith(("/admin/prijava", "/admin/2fa", "/admin/odjava", "/admin/lozinka")):
        return default
    return url


def qr_data_uri(uri: str) -> str:
    image = qrcode.make(uri, box_size=6, border=2)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def format_secret(secret: str) -> str:
    """Group a base32 secret in blocks of 4 for manual entry."""
    return " ".join(secret[i : i + 4] for i in range(0, len(secret), 4))


def describe_user_agent(ua: str | None) -> str:
    """Very small UA summary for the sessions list, e.g. 'Chrome · Windows'."""
    ua = ua or ""
    browser = "Preglednik"
    for pattern, name in (
        (r"Edg/", "Edge"),
        (r"OPR/|Opera", "Opera"),
        (r"Firefox/", "Firefox"),
        (r"Chrome/", "Chrome"),
        (r"Safari/", "Safari"),
    ):
        if re.search(pattern, ua):
            browser = name
            break
    system = "nepoznat sustav"
    for pattern, name in (
        (r"iPhone|iPad", "iOS"),
        (r"Android", "Android"),
        (r"Windows", "Windows"),
        (r"Mac OS X|Macintosh", "macOS"),
        (r"Linux", "Linux"),
    ):
        if re.search(pattern, ua):
            system = name
            break
    return f"{browser} · {system}"
