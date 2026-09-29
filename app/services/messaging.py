"""WhatsApp / Viber gumbi (paket Standard, funkcija `whatsapp`).

Gumbi vode na internu rutu `/idi/{kanal}[/{vozilo}]` koja zabilježi klik (dnevni zbroj po vozilu i
kanalu, bez osobnih podataka) i preusmjeri na `https://wa.me/...` ili `viber://chat?...`. Do klika
se ništa ne učitava s vanjskih servisa.
"""

from __future__ import annotations

import re
from datetime import date
from urllib.parse import quote

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import ContactClick, Vehicle
from app.utils import local_today

CHANNELS = {
    "whatsapp": {"label": "WhatsApp", "icon": "whatsapp", "setting": "whatsapp_number"},
    "viber": {"label": "Viber", "icon": "viber", "setting": "viber_number"},
}
PLACEHOLDER_NUMBER = "+385XXXXXXXXXX"
INTL_NUMBER_RE = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize_number(value: str) -> str:
    """'+385 91 234-5678' -> '+385912345678' (spaces, dashes, dots, slashes, brackets removed)."""
    return re.sub(r"[\s\-./()]", "", value or "")


def is_valid_number(value: str) -> bool:
    return value == PLACEHOLDER_NUMBER or bool(INTL_NUMBER_RE.match(value))


def number_digits(value: str) -> str:
    """Digits for wa.me / viber (placeholder X's are kept so the demo link stays recognisable)."""
    return re.sub(r"[^\dX]", "", value or "")


def message_text(vehicle: Vehicle | None, vehicle_url: str | None = None) -> str:
    if vehicle is None:
        return "Pozdrav, imam pitanje o vozilima u vašoj ponudi."
    return f"Pozdrav, zanima me {vehicle.title} ({vehicle_url})"


def channel_url(channel: str, number: str, text: str) -> str:
    digits = number_digits(number)
    if channel == "whatsapp":
        return f"https://wa.me/{digits}?text={quote(text, safe='')}"
    # Viber's chat link opens the conversation; it does not support a pre-filled message.
    return f"viber://chat?number=%2B{digits}"


def available_channels(site: dict) -> list[dict]:
    """Channels with a configured number (the plan check is done by the caller)."""
    return [
        {"code": code, **meta}
        for code, meta in CHANNELS.items()
        if (site.get(meta["setting"]) or "").strip()
    ]


def record_click(db: Session, channel: str, vehicle_id: int | None) -> None:
    today = local_today()
    condition = (
        ContactClick.vehicle_id.is_(None)
        if vehicle_id is None
        else ContactClick.vehicle_id == vehicle_id
    )
    updated = db.execute(
        update(ContactClick)
        .where(condition, ContactClick.channel == channel, ContactClick.date == today)
        .values(count=ContactClick.count + 1)
    ).rowcount
    if not updated:
        db.add(ContactClick(vehicle_id=vehicle_id, channel=channel, date=today, count=1))
    db.commit()


def clicks_by_vehicle(db: Session, since: date) -> dict[int, int]:
    return dict(
        db.execute(
            select(ContactClick.vehicle_id, func.sum(ContactClick.count))
            .where(ContactClick.date >= since, ContactClick.vehicle_id.is_not(None))
            .group_by(ContactClick.vehicle_id)
        ).all()
    )


def clicks_total(db: Session, since: date) -> dict[str, int]:
    return dict(
        db.execute(
            select(ContactClick.channel, func.sum(ContactClick.count))
            .where(ContactClick.date >= since)
            .group_by(ContactClick.channel)
        ).all()
    )
