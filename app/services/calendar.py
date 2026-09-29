"""Kalendarski događaji (.ics, RFC 5545) za preglede vozila (paket Standard, `kalendar_termin`).

Zatraženi termin šalje se kao `STATUS:TENTATIVE`, potvrđeni kao `STATUS:CONFIRMED` s istim `UID`
i većim `SEQUENCE` — kalendar kupca tako ažurira postojeći događaj umjesto da doda novi.
Vremena su u UTC-u (`...Z`), pa ne treba VTIMEZONE blok.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

from app.config import get_settings

DURATION_MINUTES = 60
REMINDER_MINUTES = 60
PRODID = "-//Autokuca//Pregled vozila//HR"


def _escape(value: str) -> str:
    return (
        (value or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """Fold content lines at 75 octets (continuation lines start with a space)."""
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line
    parts, current = [], b""
    for char in line:
        piece = char.encode("utf-8")
        limit = 75 if not parts else 74  # continuation lines carry a leading space
        if len(current) + len(piece) > limit:
            parts.append(current.decode("utf-8"))
            current = b""
        current += piece
    parts.append(current.decode("utf-8"))
    return "\r\n ".join(parts)


def _stamp(value: datetime) -> str:
    """Naive UTC (as stored in the DB) or aware datetime -> 20261002T080000Z."""
    if value.tzinfo is not None:
        value = value.astimezone(UTC).replace(tzinfo=None)
    return value.strftime("%Y%m%dT%H%M%SZ")


def event_uid(inquiry_id: int) -> str:
    host = urlparse(get_settings().base_url).hostname or "localhost"
    return f"pregled-{inquiry_id}@{host}"


def viewing_event(
    *,
    inquiry_id: int,
    start_utc: datetime,
    vehicle_title: str,
    vehicle_url: str,
    location: str,
    organizer_name: str,
    organizer_email: str,
    phone: str,
    confirmed: bool,
    sequence: int = 0,
) -> bytes:
    """One VEVENT (METHOD:PUBLISH) as UTF-8 bytes with CRLF line endings."""
    end_utc = start_utc + timedelta(minutes=DURATION_MINUTES)
    status = "CONFIRMED" if confirmed else "TENTATIVE"
    note = "Termin je potvrđen." if confirmed else "Zatraženi termin — čeka potvrdu prodavača."
    description = f"{note}\nOglas: {vehicle_url}\nTelefon: {phone}"
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{event_uid(inquiry_id)}",
        f"SEQUENCE:{sequence}",
        f"DTSTAMP:{_stamp(datetime.now(UTC))}",
        f"DTSTART:{_stamp(start_utc)}",
        f"DTEND:{_stamp(end_utc)}",
        f"SUMMARY:{_escape('Pregled vozila: ' + vehicle_title)}",
        f"LOCATION:{_escape(location)}",
        f"DESCRIPTION:{_escape(description)}",
        f"URL:{vehicle_url}",
        f"STATUS:{status}",
        f"ORGANIZER;CN={_escape(organizer_name)}:mailto:{organizer_email}",
        "BEGIN:VALARM",
        "ACTION:DISPLAY",
        f"DESCRIPTION:{_escape('Pregled vozila: ' + vehicle_title)}",
        f"TRIGGER:-PT{REMINDER_MINUTES}M",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return ("\r\n".join(_fold(line) for line in lines) + "\r\n").encode("utf-8")


def parse_ics(data: bytes) -> dict[str, str]:
    """Minimal unfolding parser (tests, diagnostics): first value of each property name."""
    text = data.decode("utf-8").replace("\r\n ", "")
    values: dict[str, str] = {}
    for line in text.split("\r\n"):
        if ":" in line:
            name, value = line.split(":", 1)
            values.setdefault(name.split(";", 1)[0], value)
    return values
