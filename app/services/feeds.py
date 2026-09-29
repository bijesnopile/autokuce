"""Feedovi vozila za oglasnike (paket Standard, funkcija `feed_portali`).

GET /feed/{portal}.{xml|csv}?token=...  — samo aktivna i rezervirana vozila, apsolutni URL-ovi slika
(1600 px), opis kao običan tekst, VIN samo uz postavku `feed_include_vin`. Formati i izvori
specifikacija: docs/FEEDOVI.md. Portali bez javne specifikacije dobivaju generički, dobro
strukturirani XML označen "Format treba potvrditi s portalom".

KAKO DODATI PORTAL: zapis u `PORTALS` (formati, obavezna polja, upute) + funkcija u `BUILDERS`.
"""

from __future__ import annotations

import csv
import gzip
import html
import io
import re
import secrets
import threading
import time
from xml.etree import ElementTree as ET

import nh3
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.database import utcnow
from app.models import STATUS_ACTIVE, STATUS_RESERVED, FeedAccess, Vehicle
from app.vehicle_schema import label as vlabel

CACHE_SECONDS = 300
MAX_IMAGES = 20
TOKEN_BYTES = 32  # secrets.token_urlsafe(32) -> 43 characters

_cache: dict[tuple[str, str], tuple[float, bytes]] = {}
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Token
# ---------------------------------------------------------------------------
def get_token(db: Session, create: bool = False) -> str:
    from app.services.site import get_value, set_values

    token = get_value(db, "feed_token") or ""
    if not token and create:
        token = secrets.token_urlsafe(TOKEN_BYTES)
        set_values(db, {"feed_token": token})
        db.commit()
    return token


def regenerate_token(db: Session) -> str:
    from app.services.site import set_values

    token = secrets.token_urlsafe(TOKEN_BYTES)
    set_values(db, {"feed_token": token})
    clear_cache()
    return token


def token_valid(db: Session, supplied: str) -> bool:
    token = get_token(db)
    return bool(token) and secrets.compare_digest(token.encode(), (supplied or "").encode())


# ---------------------------------------------------------------------------
# Common vehicle record
# ---------------------------------------------------------------------------
def feed_vehicles(db: Session) -> list[Vehicle]:
    stmt = (
        select(Vehicle)
        .where(Vehicle.status.in_((STATUS_ACTIVE, STATUS_RESERVED)))
        .options(
            selectinload(Vehicle.images), selectinload(Vehicle.make), selectinload(Vehicle.model)
        )
        .order_by(Vehicle.published_at.desc().nullslast(), Vehicle.id.desc())
    )
    return list(db.scalars(stmt))


def plain_text(value: str) -> str:
    """Sanitized description HTML -> plain text with paragraph breaks (no tags, no entities)."""
    text = re.sub(r"(?i)<br\s*/?>", "\n", value or "")
    text = re.sub(r"(?i)</(p|li|h2|h3|ul|ol)>", "\n", text)
    text = re.sub(r"(?i)<li[^>]*>", "- ", text)
    text = html.unescape(nh3.clean(text, tags=set()))
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def absolute(path: str) -> str:
    if path.startswith(("http://", "https://")):
        return path
    return f"{get_settings().base_url}{path}"


def image_urls(vehicle: Vehicle) -> list[str]:
    from app.templating import media_url

    return [absolute(media_url(img, 1600)) for img in vehicle.images[:MAX_IMAGES]]


def record(vehicle: Vehicle, site: dict) -> dict:
    """Portal-independent data of one ad (codes stay as in vehicle_schema)."""
    attributes = vehicle.attributes or {}
    body = attributes.get("body_type") or attributes.get("van_type") or ""
    has_price = bool(vehicle.price_eur) and not vehicle.price_on_request
    data = {
        "id": str(vehicle.id),
        "url": absolute(f"/vozila/{vehicle.slug}"),
        "title": vehicle.title,
        "vehicle_type": vehicle.vehicle_type,
        "make": vehicle.make.name if vehicle.make else "",
        "model": vehicle.model.name if vehicle.model else "",
        "variant": vehicle.variant or "",
        "condition": vehicle.condition,
        "status": vehicle.status,
        "year": vehicle.year,
        "first_registration": (
            vehicle.first_registration.strftime("%Y-%m") if vehicle.first_registration else ""
        ),
        "mileage_km": vehicle.mileage_km,
        "price_eur": vehicle.price_eur if has_price else None,
        "price_on_request": not has_price,
        "tax_type": vehicle.tax_type,
        # VAT deductible only for "PDV uračunat (R1)"; margin scheme and net prices are not.
        "vat_deductible": vehicle.tax_type == "pdv",
        "fuel": vehicle.fuel or "",
        "transmission": vehicle.transmission or "",
        "drive": vehicle.drive or "",
        "body_type": body,
        "power_kw": vehicle.power_kw,
        "power_hp": vehicle.power_hp,
        "engine_ccm": vehicle.engine_ccm,
        "color": vehicle.color or "",
        "color_label": vlabel("color", vehicle.color) if vehicle.color else "",
        "doors": vehicle.doors,
        "seats": vehicle.seats,
        "euro_norm": vehicle.euro_norm or "",
        "co2_g_km": vehicle.co2_g_km,
        "fuel_l100": vehicle.fuel_consumption_l100,
        "energy_kwh100": vehicle.energy_consumption_kwh100,
        "electric_range_km": vehicle.electric_range_km,
        "battery_kwh": vehicle.battery_kwh,
        "description": plain_text(vehicle.description),
        "images": image_urls(vehicle),
        "equipment": list(vehicle.equipment or []),
        "vin": vehicle.vin if site.get("feed_include_vin") and vehicle.vin else "",
        "dealer_name": site.get("company_name", ""),
        "dealer_address": site.get("company_address", ""),
        "dealer_phone": site.get("company_phone", ""),
        "dealer_email": site.get("company_email", ""),
        "updated_at": (vehicle.updated_at or utcnow()).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return data


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------
def xml_bytes(root: ET.Element) -> bytes:
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True) + b"\n"


def sub(parent: ET.Element, tag: str, value, **attrs) -> ET.Element | None:
    """Add <tag>value</tag>; empty values are left out (no empty elements)."""
    if value is None or value == "" or value == []:
        return None
    element = ET.SubElement(parent, tag, {k: str(v) for k, v in attrs.items()})
    element.text = str(value)
    return element


def csv_bytes(header: list[str], rows: list[dict], delimiter: str = ",") -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer, fieldnames=header, delimiter=delimiter, extrasaction="ignore", lineterminator="\n"
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({k: ("" if v is None else v) for k, v in row.items()})
    return buffer.getvalue().encode("utf-8")


# ---------------------------------------------------------------------------
# Cache (5 min, per portal + format; body stored gzip-ready)
# ---------------------------------------------------------------------------
def clear_cache() -> None:
    with _lock:
        _cache.clear()


def cached_body(db: Session, portal: str, fmt: str) -> bytes:
    from app.services.feed_formats import build

    key = (portal, fmt)
    now = time.monotonic()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_SECONDS:
            return hit[1]
    body = build(db, portal, fmt)
    with _lock:
        _cache[key] = (now, body)
    return body


def gzip_body(body: bytes) -> bytes:
    return gzip.compress(body, compresslevel=6, mtime=0)


def record_access(db: Session, portal: str, fmt: str) -> None:
    row = db.get(FeedAccess, portal)
    if row is None:
        row = FeedAccess(portal=portal, count=0)
        db.add(row)
    row.last_at = utcnow()
    row.last_format = fmt
    row.count = (row.count or 0) + 1
    db.commit()


def access_by_portal(db: Session) -> dict[str, FeedAccess]:
    return {row.portal: row for row in db.scalars(select(FeedAccess))}
