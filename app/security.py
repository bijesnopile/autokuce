"""Security primitives: password hashing, tokens, CSRF, rate limiting, encryption, TOTP.

Keep this module free of FastAPI routing logic; routers and `deps.py` use it.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import logging
import secrets
import threading
import time
from collections import deque

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import get_settings

log = logging.getLogger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# Passwords (Argon2id)
# ---------------------------------------------------------------------------
_password_hasher = PasswordHasher()  # argon2-cffi defaults: Argon2id, RFC 9106 low-memory
# Recovery codes are random (high entropy); a lighter profile keeps verification fast.
_code_hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)

MIN_PASSWORD_LENGTH = 12

# 100 most common passwords (lower-case). Checked case-insensitively.
COMMON_PASSWORDS = frozenset(
    """
    123456 password 12345678 qwerty 123456789 12345 1234 111111 1234567 dragon
    123123 baseball abc123 football monkey letmein 696969 shadow master 666666
    qwertyuiop 123321 mustang 1234567890 michael 654321 superman 1qaz2wsx 7777777
    121212 000000 qazwsx 123qwe killer trustno1 jordan jennifer zxcvbnm asdfgh
    hunter buster soccer harley batman andrew tigger sunshine iloveyou 2000
    charlie robert thomas hockey ranger daniel starwars klaster 112233 george
    computer michelle jessica pepper 1111 zxcvbn 555555 11111111 131313 freedom
    777777 pass maggie 159753 aaaaaa ginger princess joshua cheese amanda summer
    love ashley nicole chelsea biteme matthew access yankees 987654321 dallas
    austin thunder taylor matrix password1 password123 qwerty123 admin admin123
    welcome welcome1 lozinka lozinka123 passw0rd
    """.split()
)


def secret_key_fingerprint(key: str) -> str:
    """Non-reversible fingerprint of SECRET_KEY, stored in the DB to detect a changed key."""
    return hmac.new(key.encode("utf-8"), b"autokuca:secret-key-check", hashlib.sha256).hexdigest()[
        :32
    ]


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    if not password_hash:
        return False
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    try:
        return _password_hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def validate_password_strength(password: str) -> str | None:
    """Return an error message (Croatian) or None if the password is acceptable."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Lozinka mora imati barem {MIN_PASSWORD_LENGTH} znakova."
    if len(password) > 256:
        return "Lozinka je predugačka."
    lowered = password.lower()
    if lowered in COMMON_PASSWORDS or lowered.rstrip("0123456789!?.") in COMMON_PASSWORDS:
        return "Lozinka je previše česta. Odaberite drugu."
    if len(set(password)) < 5:
        return "Lozinka je prejednostavna."
    return None


# Dummy hash for constant-time-ish handling of unknown users on login.
_DUMMY_HASH = _password_hasher.hash(secrets.token_urlsafe(16))


def burn_password_check(password: str) -> None:
    """Spend the same time as a real check (used when the user does not exist)."""
    verify_password(_DUMMY_HASH, password)


# ---------------------------------------------------------------------------
# Tokens and hashing
# ---------------------------------------------------------------------------
def generate_token(nbytes: int = 32) -> str:
    """Random URL-safe token. Only its hash is stored in the DB."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def email_hash(email: str) -> str:
    """SHA-256 of the normalized email (used for suppression lists and logs)."""
    return hashlib.sha256(normalize_email(email).encode("utf-8")).hexdigest()


def mask_email(email: str) -> str:
    """For logs: k***@primjer.hr."""
    email = normalize_email(email)
    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    return f"{local[:1]}***@{domain}"


def mask_ip(ip: str | None) -> str:
    """For display: hide the host part of an IP address."""
    if not ip:
        return "—"
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return "—"
    if addr.version == 4:
        parts = ip.split(".")
        return ".".join(parts[:3]) + ".xxx"
    groups = addr.exploded.split(":")
    return ":".join(groups[:3]) + "::xxxx"


def generate_recovery_codes(n: int = 10) -> list[str]:
    """Human-friendly one-time codes, e.g. `k7m2-p9qx-4tzr`."""
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    codes = []
    for _ in range(n):
        raw = "".join(secrets.choice(alphabet) for _ in range(12))
        codes.append(f"{raw[:4]}-{raw[4:8]}-{raw[8:]}")
    return codes


def hash_recovery_code(code: str) -> str:
    return _code_hasher.hash(code.strip().lower().replace(" ", ""))


def match_recovery_code(hashes: list[str], code: str) -> int | None:
    """Return the index of the matching hash, or None."""
    code = code.strip().lower().replace(" ", "")
    for index, stored in enumerate(hashes or []):
        try:
            if _code_hasher.verify(stored, code):
                return index
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            continue
    return None


# ---------------------------------------------------------------------------
# Signed values (itsdangerous) and symmetric encryption (Fernet)
# ---------------------------------------------------------------------------
def serializer(salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt=salt)


def sign_value(value, salt: str) -> str:
    return serializer(salt).dumps(value)


def unsign_value(token: str, salt: str, max_age: int):
    """Return the original value or None if invalid/expired."""
    try:
        return serializer(salt).loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None


def _fernet() -> Fernet:
    digest = hashlib.sha256(("fernet:" + settings.secret_key).encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(ciphertext: str | None) -> str | None:
    if not ciphertext:
        return None
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        log.error("TOTP secret could not be decrypted (SECRET_KEY changed?)")
        return None


# ---------------------------------------------------------------------------
# TOTP (RFC 6238, 30 s steps, 6 digits)
# ---------------------------------------------------------------------------
def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, account: str, issuer: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=account, issuer_name=issuer)


def verify_totp(secret: str, code: str, last_step: int | None) -> int | None:
    """Verify a 6-digit code (±1 step). Returns the matched time step or None.

    A step that is <= `last_step` is rejected (replay protection).
    """
    code = (code or "").strip().replace(" ", "")
    if not (len(code) == 6 and code.isdigit()):
        return None
    totp = pyotp.TOTP(secret)
    now_step = int(time.time()) // 30
    for step in (now_step - 1, now_step, now_step + 1):
        if hmac.compare_digest(totp.at(step * 30), code):
            if last_step is not None and step <= last_step:
                return None
            return step
    return None


# ---------------------------------------------------------------------------
# CSRF (token stored in the signed client-state cookie, see main.py)
# ---------------------------------------------------------------------------
CSRF_FIELD = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"


def get_csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = generate_token(24)
        request.session["csrf"] = token
    return token


def rotate_csrf_token(request: Request) -> str:
    """Issue a fresh token (called after login, binding the token to the new session)."""
    token = generate_token(24)
    request.session["csrf"] = token
    return token


async def verify_csrf(request: Request) -> None:
    """FastAPI dependency for every state-changing request (403 on mismatch)."""
    expected = request.session.get("csrf")
    supplied = request.headers.get(CSRF_HEADER)
    if not supplied:
        content_type = request.headers.get("content-type", "")
        if content_type.startswith(("application/x-www-form-urlencoded", "multipart/form-data")):
            form = await request.form()
            supplied = form.get(CSRF_FIELD)
    if not expected or not supplied or not hmac.compare_digest(str(expected), str(supplied)):
        raise HTTPException(status_code=403, detail="CSRF token nedostaje ili nije ispravan.")


# ---------------------------------------------------------------------------
# Rate limiting (in-memory, per process)
# ---------------------------------------------------------------------------
class RateLimiter:
    """Sliding-window limiter kept in process memory.

    NOTE: with several uvicorn workers each worker has its own counters, so the
    effective limit is `limit * workers`. For strict limits across workers use
    Redis (see docs/SIGURNOST.md).
    """

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_s: int) -> bool:
        """Register a hit; return False if the limit is exceeded."""
        now = time.monotonic()
        with self._lock:
            bucket = self._hits.setdefault(key, deque())
            while bucket and bucket[0] <= now - window_s:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            if len(self._hits) > 50_000:  # simple memory guard
                self._prune(now)
            return True

    def _prune(self, now: float) -> None:
        for key in [k for k, v in self._hits.items() if not v or v[-1] < now - 3600]:
            self._hits.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def client_ip(request: Request) -> str:
    """Client IP (already resolved from proxy headers by RealIPMiddleware if trusted)."""
    return request.client.host if request.client else "unknown"


def check_rate_limit(
    request: Request, scope: str, limit: int, window_s: int, key: str | None = None
) -> bool:
    """Return True if allowed. `key` defaults to the client IP."""
    return limiter.hit(f"{scope}:{key or client_ip(request)}", limit, window_s)


def rate_limit(scope: str, limit: int, window_s: int):
    """Dependency factory: `Depends(rate_limit("api", 100, 60))` -> 429 when exceeded."""

    async def _dependency(request: Request) -> None:
        if not check_rate_limit(request, scope, limit, window_s):
            raise HTTPException(status_code=429, detail="Previše zahtjeva. Pokušajte kasnije.")

    return _dependency


# ---------------------------------------------------------------------------
# Rich text sanitization (nh3 / ammonia allowlist)
# ---------------------------------------------------------------------------
BASIC_TAGS = {"p", "br", "strong", "b", "em", "i", "ul", "ol", "li", "h2", "h3", "a"}


def clean_html(
    html: str | None,
    extra_tags: set[str] | None = None,
    extra_attributes: dict | None = None,
    attribute_filter=None,
) -> str:
    """Sanitize rich text (vehicle descriptions, CMS pages, campaigns).

    Default allowlist: p, br, strong, b, em, i, ul, ol, li, h2, h3, a[href]; links get
    rel="nofollow noopener"; only http(s)/mailto/tel URLs. Everything else is removed.
    """
    import nh3

    tags = set(BASIC_TAGS) | set(extra_tags or ())
    attributes = {"a": {"href"}}
    for tag, attrs in (extra_attributes or {}).items():
        attributes.setdefault(tag, set()).update(attrs)
    cleaned = nh3.clean(
        html or "",
        tags=tags,
        attributes=attributes,
        link_rel="nofollow noopener",
        url_schemes={"http", "https", "mailto", "tel"},
        attribute_filter=attribute_filter,
        strip_comments=True,
    )
    return cleaned.strip()


# ---------------------------------------------------------------------------
# Public form timing check (bots submit instantly)
# ---------------------------------------------------------------------------
FORM_TS_SALT = "form-ts"
MIN_FORM_SECONDS = 3
MAX_FORM_AGE = 24 * 3600


def form_timestamp() -> str:
    """Signed render time embedded in every public form (hidden field `form_ts`)."""
    return sign_value(int(time.time()), salt=FORM_TS_SALT)


def check_form_timestamp(token: str | None) -> str | None:
    """Return None if OK, "fast" if submitted too quickly, "invalid" if missing/expired."""
    rendered = unsign_value(token or "", salt=FORM_TS_SALT, max_age=MAX_FORM_AGE)
    if not isinstance(rendered, int):
        return "invalid"
    if time.time() - rendered < MIN_FORM_SECONDS:
        return "fast"
    return None
