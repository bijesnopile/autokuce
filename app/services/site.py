"""Company/theme settings (`settings` table) with placeholder defaults.

`get_site()` returns a dict available in every template as `site`. It is
cached for 60 s per process and invalidated on save. Templates must never
hardcode company data — everything comes from here.
"""

from __future__ import annotations

import re
import threading
import time
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Setting

WHY_US_DEFAULT = "\n".join(
    [
        "Provjerena vozila | Svako vozilo prije prodaje pregledavamo, a povijest održavanja "
        "i dokumentaciju dajemo na uvid.",
        "Financiranje i leasing | Pomažemo odabrati kredit ili leasing prema vašem budžetu, "
        "uz informativnu ponudu bez obveze.",
        "Zamjena staro za novo | Vaše dosadašnje vozilo otkupljujemo ili uzimamo u zamjenu "
        "pri kupnji — procjena je besplatna.",
        "Registracija bez brige | Pripremamo dokumentaciju i pomažemo oko registracije, "
        "osiguranja i prijenosa vlasništva.",
    ]
)

# Placeholder values (specification chapter 3). The seed writes these to the DB;
# they also serve as fallbacks when a key is missing.
DEFAULTS: dict[str, str] = {
    "company_name": "IME PODUZEĆA",
    "company_email": "mailpoduzeca@domena.com",
    "company_phone": "+385XXXXXXXXXX",
    "company_address": "Ulica i broj 1, 10000 Grad",
    "company_oib": "XXXXXXXXXXX",
    "company_web": "www.domena.com",
    "working_hours": "Pon–Pet 08:00–17:00, Sub 09:00–13:00",
    "facebook_url": "https://facebook.com/imepoduzeca",
    "instagram_url": "https://instagram.com/imepoduzeca",
    "maps_url": "https://maps.google.com/?q=Ulica+i+broj+1+Grad",
    "logo_key": "",
    "primary_color": "#1e40af",
    "accent_color": "#e11d48",
    "hero_title": "Pronađite vozilo koje vam odgovara",
    "hero_subtitle": (
        "Provjerena nova i rabljena vozila — osobni automobili, kombiji, motocikli, kamperi "
        "i kamioni. Financiranje, zamjena i registracija na jednom mjestu."
    ),
    "footer_text": (
        "Prodaja novih i rabljenih vozila, financiranje, otkup i zamjena. Posjetite nas "
        "ili pošaljite upit — javit ćemo se u najkraćem roku."
    ),
    # "Zašto kupiti kod nas": one item per line, "Naslov | kratki opis" (home, O nama, vozilo).
    "why_us": WHY_US_DEFAULT,
    "inquiry_notify_email": "mailpoduzeca@domena.com",
    "newsletter_sender_name": "IME PODUZEĆA",
    "privacy_policy_version": "1.0",
    "privacy_policy_updated_at": "",
    "cookie_banner_enabled": "false",
    "plates_reminder_enabled": "true",
}

BOOL_KEYS = {"cookie_banner_enabled", "plates_reminder_enabled"}
# Internal keys stored in the same table but not editable as company settings.
INTERNAL_KEYS = {"maintenance_last_run", "plan_override"}

CACHE_SECONDS = 60
_cache: dict = {"data": None, "loaded_at": 0.0}
_lock = threading.Lock()


def _to_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on", "da"}


def load_raw(db: Session) -> dict[str, str]:
    rows = db.execute(select(Setting.key, Setting.value)).all()
    return {key: value for key, value in rows}


def build_site(raw: dict[str, str]) -> dict:
    """Merge DB values over defaults and add derived helper keys."""
    site: dict = dict(DEFAULTS)
    site.update({k: v for k, v in raw.items() if k in DEFAULTS or k in INTERNAL_KEYS})
    for key in BOOL_KEYS:
        site[key] = _to_bool(site.get(key, "false"))
    if not site.get("privacy_policy_updated_at"):
        site["privacy_policy_updated_at"] = date.today().isoformat()
    # tel: link — keep only digits and a leading plus.
    site["phone_href"] = "tel:" + re.sub(r"[^\d+]", "", site["company_phone"])
    web = site["company_web"].strip()
    site["web_url"] = web if web.startswith("http") else f"https://{web}"
    from app.services.content import why_us_items

    site["why_us_items"] = why_us_items(site.get("why_us", ""))
    site["logo_url"] = ""
    if site.get("logo_key"):
        # Imported lazily to avoid a circular import at module load.
        from app.services.storage import get_storage

        site["logo_url"] = get_storage().url(f"{site['logo_key']}_400.webp")
    return site


def get_site() -> dict:
    """Return cached site settings (reloaded at most every 60 s per process)."""
    now = time.monotonic()
    data = _cache["data"]
    if data is not None and now - _cache["loaded_at"] < CACHE_SECONDS:
        return data
    with _lock:
        db = SessionLocal()
        try:
            data = build_site(load_raw(db))
        finally:
            db.close()
        _cache["data"] = data
        _cache["loaded_at"] = now
    return data


def invalidate_site_cache() -> None:
    _cache["data"] = None
    _cache["loaded_at"] = 0.0


def get_value(db: Session, key: str, default: str = "") -> str:
    row = db.get(Setting, key)
    return row.value if row else DEFAULTS.get(key, default)


def set_values(db: Session, values: dict[str, str]) -> list[str]:
    """Upsert settings; return the list of keys whose value changed. Caller commits."""
    changed = []
    for key, value in values.items():
        value = "" if value is None else str(value)
        row = db.get(Setting, key)
        if row is None:
            db.add(Setting(key=key, value=value))
            changed.append(key)
        elif row.value != value:
            row.value = value
            changed.append(key)
    invalidate_site_cache()
    return changed
