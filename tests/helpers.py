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


# ---------------------------------------------------------------------------
# Catalog / vehicles / images
# ---------------------------------------------------------------------------
def make_catalog(db, make_name="Škoda", model_name="Octavia", vehicle_type=None):
    from app.models import Make, VehicleModel
    from app.utils import slugify

    make = db.query(Make).filter_by(slug=slugify(make_name)).first()
    if make is None:
        make = Make(name=make_name, slug=slugify(make_name))
        db.add(make)
        db.flush()
    model = db.query(VehicleModel).filter_by(make_id=make.id, slug=slugify(model_name)).first()
    if model is None:
        model = VehicleModel(
            make_id=make.id, name=model_name, slug=slugify(model_name), vehicle_type=vehicle_type
        )
        db.add(model)
    db.commit()
    return make, model


def make_vehicle(db, user_id=None, vehicle_type="car", status="active", **overrides):
    """Create a valid vehicle through the service layer (title/slug generated)."""
    from app.models import User
    from app.services.vehicles import change_status, create_vehicle

    make_name = overrides.pop("make_name", "Škoda")
    model_name = overrides.pop("model_name", f"Model {vehicle_type}")
    make, model = make_catalog(db, make_name, model_name)
    attributes = {
        "car": {"body_type": "karavan"},
        "van": {"van_type": "furgon"},
        "motorcycle": {"moto_type": "naked"},
        "camper": {"camper_type": "alkoven"},
        "truck": {"truck_body": "sanduk"},
    }[vehicle_type]
    values = {
        "vehicle_type": vehicle_type,
        "make_id": make.id,
        "model_id": model.id,
        "variant": "Test",
        "condition": "used",
        "year": 2019,
        "mileage_km": 120000,
        "price_eur": 15000,
        "tax_type": "marza",
        "fuel": "dizel",
        "transmission": "rucni",
        "power_kw": 110,
        "power_hp": 150,
        "attributes": attributes,
        "equipment": ["abs", "klima"],
        "description": "<p>Lorem ipsum</p>",
        "status": "draft",
        "vin": "WVWZZZ1KZAW000001",
    }
    values.update(overrides)
    if user_id is None:
        user_id = db.query(User).first().id
    user = db.get(User, user_id)
    vehicle = create_vehicle(db, values, user)
    if status != "draft":
        change_status(vehicle, "active")
        if status != "active":
            change_status(vehicle, status)
    db.commit()
    return vehicle


def image_bytes(fmt="JPEG", size=(1200, 900), color=(180, 40, 40), exif=None) -> bytes:
    import io

    from PIL import Image

    image = Image.new("RGB", size, color)
    buffer = io.BytesIO()
    kwargs = {"exif": exif.tobytes()} if exif is not None else {}
    image.save(buffer, fmt, **kwargs)
    return buffer.getvalue()


def gps_exif(orientation=None):
    from PIL import Image

    exif = Image.Exif()
    exif[0x010F] = "TestCam"
    if orientation:
        exif[0x0112] = orientation
    gps = exif.get_ifd(0x8825)
    gps[1] = "N"
    gps[2] = (45.0, 48.0, 1.5)
    gps[3] = "E"
    gps[4] = (15.0, 58.0, 2.0)
    return exif
