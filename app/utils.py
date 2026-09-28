"""Small, dependency-free helpers shared across the app."""

from __future__ import annotations

import re
import sys
import unicodedata
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

# All dates shown to users and "per day" statistics use Croatian local time.
LOCAL_TZ = ZoneInfo("Europe/Zagreb")

# Croatian/common letters that NFKD does not decompose into ASCII.
_TRANSLIT = str.maketrans(
    {
        "đ": "d",
        "Đ": "D",
        "ß": "ss",
        "æ": "ae",
        "Æ": "AE",
        "ø": "o",
        "Ø": "O",
        "ł": "l",
        "Ł": "L",
    }
)


def slugify(text: str, max_length: int = 80) -> str:
    """ASCII slug: `Škoda Octavia 2.0 TDI` -> `skoda-octavia-2-0-tdi` (č/ć→c, š→s, ž→z, đ→d)."""
    text = (text or "").translate(_TRANSLIT)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:max_length].strip("-")


def ensure_utf8_console() -> None:
    """Windows consoles/pipes default to cp1252; make print() of č/ć/š/ž/đ safe."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def local_now() -> datetime:
    return datetime.now(LOCAL_TZ)


def local_today() -> date:
    return local_now().date()


def local_day_start_utc(day: date) -> datetime:
    """Local midnight (Europe/Zagreb) of `day` as a naive UTC datetime (DB format)."""
    return datetime.combine(day, time.min, tzinfo=LOCAL_TZ).astimezone(UTC).replace(tzinfo=None)


def to_local_date(value: datetime) -> date:
    """Naive UTC datetime from the DB -> local calendar date."""
    return value.replace(tzinfo=UTC).astimezone(LOCAL_TZ).date()
