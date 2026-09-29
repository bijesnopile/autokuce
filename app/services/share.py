"""Dijeljenje oglasa, favorita i usporedbe (faza 10 D).

Poveznice na WhatsApp/Viber/Facebook idu preko internog preusmjeravanja `/podijeli/{kanal}?u=`
(kao `/idi/whatsapp`): stranica ne sadrži vanjske URL-ove, ništa vanjsko se ne učitava dok
korisnik ne klikne, a `u` smije biti samo put na ovoj stranici (nema otvorenog preusmjeravanja).
QR kod se generira na poslužitelju (biblioteka `qrcode`) i kešira po URL-u.
"""

from __future__ import annotations

import re
from functools import lru_cache
from urllib.parse import quote, urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Vehicle

CHANNELS = ("whatsapp", "viber", "facebook")
_PATH_RE = re.compile(r"^/(vozila/[a-z0-9-]{1,200}|usporedba|favoriti)(\?v=[0-9,]{1,600})?$")


def safe_path(path: str | None) -> str | None:
    """Only shareable pages of this site (vehicle ad, comparison, favourites)."""
    path = str(path or "").strip()
    return path if _PATH_RE.match(path) else None


def absolute(path: str) -> str:
    from app.config import get_settings

    return f"{get_settings().base_url}{path}"


def share_text(db: Session, path: str) -> str:
    """ "Title – price" for an ad, a generic line for comparison/favourites."""
    from app.services.site import get_site
    from app.templating import money

    site = get_site()
    if path.startswith("/vozila/"):
        slug = path.split("/", 2)[2]
        vehicle = db.scalar(select(Vehicle).where(Vehicle.slug == slug))
        if vehicle is not None:
            price = (
                "cijena na upit"
                if vehicle.price_on_request or vehicle.price_eur is None
                else money(vehicle.price_eur)
            )
            return f"{vehicle.title} – {price}"
    if path.startswith("/usporedba"):
        return f"Usporedba vozila – {site.get('company_name', '')}"
    return f"Izdvojena vozila – {site.get('company_name', '')}"


def target_url(channel: str, url: str, text: str) -> str | None:
    if channel == "whatsapp":
        return "https://wa.me/?" + urlencode({"text": f"{text} {url}"}, quote_via=quote)
    if channel == "viber":
        return "viber://forward?" + urlencode({"text": f"{text} {url}"}, quote_via=quote)
    if channel == "facebook":
        return "https://www.facebook.com/sharer/sharer.php?" + urlencode({"u": url})
    return None


@lru_cache(maxsize=512)
def qr(url: str) -> str:
    """PNG data URI of the URL (cached per URL = per vehicle slug)."""
    from app.services.auth import qr_data_uri

    return qr_data_uri(url)
