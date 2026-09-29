"""Company settings (/admin/postavke, owner+): company data, contacts and social links,
appearance (logo, colours, hero texts, footer), legal switches.

Everything shown on the public site comes from these settings — no code changes
are needed to rebrand an instance.
"""

from __future__ import annotations

import re
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.database import get_db
from app.deps import csrf_protect, require_permission
from app.models import User
from app.security import client_ip
from app.services import audit
from app.services.images import LOGO_SIZES, ImageError, delete_variants, save_logo
from app.services.site import DEFAULTS, get_site, get_value, set_values
from app.templating import flash, render

router = APIRouter(prefix="/admin", dependencies=[Depends(csrf_protect)])
settings = get_settings()

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[A-Za-z]{2,}$")
PHONE_RE = re.compile(r"^[+0-9X][0-9X\s/().-]{5,24}$")
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

# (key, label, kind, max length, section)
FIELDS = [
    ("company_name", "Naziv tvrtke", "text", 120, "tvrtka"),
    ("company_address", "Adresa", "text", 200, "tvrtka"),
    ("company_oib", "OIB", "oib", 11, "tvrtka"),
    ("company_email", "Email", "email", 254, "tvrtka"),
    ("company_phone", "Telefon", "phone", 30, "tvrtka"),
    ("company_web", "Web", "text", 120, "tvrtka"),
    ("working_hours", "Radno vrijeme", "text", 200, "tvrtka"),
    ("inquiry_notify_email", "Email za obavijesti o upitima", "email", 254, "kontakt"),
    ("newsletter_sender_name", "Ime pošiljatelja newslettera", "text", 80, "kontakt"),
    ("facebook_url", "Facebook", "url", 300, "kontakt"),
    ("instagram_url", "Instagram", "url", 300, "kontakt"),
    ("maps_url", "Google Maps poveznica", "url", 500, "kontakt"),
    ("whatsapp_number", "WhatsApp broj", "intl_phone", 20, "kontakt"),
    ("viber_number", "Viber broj", "intl_phone", 20, "kontakt"),
    ("primary_color", "Primarna boja", "color", 7, "izgled"),
    ("accent_color", "Akcentna boja", "color", 7, "izgled"),
    ("hero_title", "Naslov na naslovnici", "text", 120, "izgled"),
    ("hero_subtitle", "Podnaslov na naslovnici", "textarea", 300, "izgled"),
    ("footer_text", "Tekst u podnožju", "textarea", 300, "izgled"),
    ("why_us", "Zašto kupiti kod nas", "lines", 1500, "izgled"),
    ("price_drop_badge_days", "Oznaka „Snižena cijena” (dana)", "number", 3, "oglasi"),
    ("social_proof_enabled", "Prikaži broj pregleda i oznaku „Popularno”", "bool", 0, "oglasi"),
    ("auto_reply_enabled", "Automatski odgovor kupcu nakon upita", "bool", 0, "upiti"),
    ("auto_reply_text", "Tekst automatskog odgovora", "template", 1500, "upiti"),
    ("financing_enabled", "Prikaži kalkulator rate na oglasima", "bool", 0, "upiti"),
    ("financing_rate_percent", "Kamatna stopa (% godišnje)", "number", 6, "upiti"),
    ("financing_max_months", "Najdulji rok otplate (mjeseci)", "number", 3, "upiti"),
    ("financing_min_down_percent", "Najmanje učešće (% cijene)", "number", 2, "upiti"),
    ("financing_disclaimer", "Napomena uz izračun", "textarea", 300, "upiti"),
    ("privacy_policy_version", "Verzija politike privatnosti", "text", 20, "pravno"),
    ("cookie_banner_enabled", "Prikaži traku za kolačiće", "bool", 0, "pravno"),
    (
        "plates_reminder_enabled",
        "Obavezna potvrda zamagljenih tablica pri uploadu slika",
        "bool",
        0,
        "pravno",
    ),
]
SECTIONS = [
    (
        "tvrtka",
        "Tvrtka",
        "Podaci iz impressuma — prikazuju se u podnožju svake stranice i u emailovima.",
    ),
    ("kontakt", "Kontakt i mreže", "Kamo stižu upiti i kako se potpisuje newsletter."),
    ("izgled", "Izgled", "Boje, tekstovi naslovnice i podnožja."),
    ("oglasi", "Oglasi", "Oznake na oglasima: snižena cijena i popularnost (stvarni podaci)."),
    (
        "upiti",
        "Upiti i financiranje",
        "Automatski odgovor kupcu i kalkulator rate (paket Standard).",
    ),
    ("pravno", "Pravno", "Verzija politike privatnosti sprema se uz svaku privolu kupca."),
]


# Fields that belong to a plan feature: locked fields are shown disabled and keep their value.
FIELD_FEATURES = {
    "whatsapp_number": "whatsapp",
    "viber_number": "whatsapp",
    "auto_reply_enabled": "auto_odgovor",
    "auto_reply_text": "auto_odgovor",
    "financing_enabled": "kalkulator_rate",
    "financing_rate_percent": "kalkulator_rate",
    "financing_max_months": "kalkulator_rate",
    "financing_min_down_percent": "kalkulator_rate",
    "financing_disclaimer": "kalkulator_rate",
}
# kind "number": (min, max, whole number only, multiple of)
NUMBER_RANGES = {
    "financing_rate_percent": (0, 30, False, None),
    "price_drop_badge_days": (1, 365, True, None),
    "financing_max_months": (12, 120, True, 12),
    "financing_min_down_percent": (0, 90, True, None),
}


def locked_fields() -> set[str]:
    from app.plans import has_feature

    return {key for key, code in FIELD_FEATURES.items() if not has_feature(code)}


def _validate(form) -> tuple[dict, dict]:
    values: dict = {}
    errors: dict = {}
    locked = locked_fields()
    current = get_site()
    for key, _label, kind, max_length, _section in FIELDS:
        if key in locked:
            values[key] = current.get(key, "")  # disabled in the form: never overwritten
            continue
        if kind == "intl_phone":
            from app.services.messaging import is_valid_number, normalize_number

            value = normalize_number(str(form.get(key, "")))
            if value and not is_valid_number(value):
                errors[key] = "Međunarodni format, npr. +385911234567."
            values[key] = value
            continue
        if kind == "bool":
            values[key] = "true" if form.get(key) in ("1", "on", "true") else "false"
            continue
        if kind == "template":
            from app.services.site import AUTO_REPLY_DEFAULT, AUTO_REPLY_FIELDS

            # Empty field = back to the default text.
            value = str(form.get(key, "")).strip().replace("\r\n", "\n") or AUTO_REPLY_DEFAULT
            unknown = sorted(set(re.findall(r"\{(\w+)\}", value)) - set(AUTO_REPLY_FIELDS))
            if len(value) > max_length:
                errors[key] = f"Najviše {max_length} znakova."
            elif unknown:
                errors[key] = "Nepoznato polje: " + ", ".join("{" + u + "}" for u in unknown)
            values[key] = value
            continue
        if kind == "number":
            # Empty field = back to the default value.
            value = str(form.get(key, "")).strip().replace(",", ".") or DEFAULTS[key]
            low, high, whole, multiple = NUMBER_RANGES[key]
            try:
                number = float(value)
            except ValueError:
                number = None
            if number is None or not low <= number <= high:
                errors[key] = f"Broj od {low} do {high}."
            elif whole and number != int(number):
                errors[key] = "Upišite cijeli broj."
            elif multiple and int(number) % multiple:
                errors[key] = f"Mora biti višekratnik broja {multiple}."
            else:
                value = str(int(number)) if whole else f"{number:g}"
            values[key] = value
            continue
        value = str(form.get(key, "")).strip()
        if max_length and len(value) > max_length:
            errors[key] = f"Najviše {max_length} znakova."
        elif kind == "email" and not EMAIL_RE.match(value):
            errors[key] = "Upišite ispravnu email adresu."
        elif kind == "phone" and not PHONE_RE.match(value):
            errors[key] = "Upišite ispravan broj telefona."
        elif kind == "oib" and not (re.fullmatch(r"\d{11}", value) or value == "X" * 11):
            errors[key] = "OIB ima 11 znamenki."
        elif kind == "color" and not HEX_RE.match(value):
            errors[key] = "Boja u obliku #rrggbb."
        elif kind == "url" and value and not re.match(r"^https?://\S+$", value):
            errors[key] = "Poveznica mora počinjati s https://"
        elif key in ("company_name", "privacy_policy_version", "hero_title") and not value:
            errors[key] = "Obavezno polje."
        elif kind == "lines":
            lines = [line.strip() for line in value.splitlines() if line.strip()]
            if len(lines) > 8:
                errors[key] = "Najviše 8 stavki (jedna po retku)."
            elif any(len(line.partition("|")[0].strip()) > 60 for line in lines):
                errors[key] = "Naslov stavke (dio prije znaka |) može imati najviše 60 znakova."
            value = chr(10).join(lines)
        values[key] = value.lower() if kind == "color" else value
    return values, errors


def _context(values: dict, errors: dict) -> dict:
    site = get_site()
    return {
        "section": "postavke",
        "fields": FIELDS,
        "sections": SECTIONS,
        "values": values,
        "errors": errors,
        "logo_url": site.get("logo_url"),
        "policy_updated": site.get("privacy_policy_updated_at"),
        "defaults": DEFAULTS,
        "locked_fields": locked_fields(),
        "field_features": FIELD_FEATURES,
    }


@router.get("/postavke/paket/{code}")
async def settings_locked_feature(
    request: Request,
    code: str,
    user: User = Depends(require_permission("settings")),
):
    """Target of the plan badge next to a locked setting: explains the feature (403 page)."""
    from app.errors import FeatureLocked
    from app.plans import FEATURES, has_feature

    if code not in FEATURES or has_feature(code):
        return RedirectResponse("/admin/postavke", status_code=303)
    raise FeatureLocked(code)


@router.get("/postavke")
async def settings_form(
    request: Request,
    user: User = Depends(require_permission("settings")),
):
    site = get_site()
    values = {}
    for key, _label, kind, _max, _section in FIELDS:
        value = site.get(key, "")
        values[key] = ("true" if value else "false") if kind == "bool" else value
    return render(request, "admin/settings.html", _context(values, {}))


@router.post("/postavke")
async def settings_save(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("settings")),
):
    values, errors = _validate(await request.form())
    if errors:
        flash(request, "Postavke nisu spremljene — provjerite označena polja.", "error")
        return render(request, "admin/settings.html", _context(values, errors), status_code=400)
    old_version = get_value(db, "privacy_policy_version")
    if values["privacy_policy_version"] != old_version:
        values["privacy_policy_updated_at"] = date.today().isoformat()
    changed = set_values(db, values)
    if changed:
        audit.log(
            db,
            user.id,
            "settings.update",
            "settings",
            None,
            {"keys": sorted(changed)},
            client_ip(request),
        )
    db.commit()
    flash(request, "Postavke su spremljene." if changed else "Nema promjena.", "success")
    return RedirectResponse("/admin/postavke", status_code=303)


@router.post("/postavke/logo")
async def logo_upload(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("settings")),
):
    form = await request.form()
    upload = form.get("logo")
    if upload is None or not hasattr(upload, "read") or not getattr(upload, "filename", ""):
        flash(request, "Odaberite datoteku s logotipom (PNG, WebP ili JPEG).", "error")
        return RedirectResponse("/admin/postavke#izgled", status_code=303)
    data = await upload.read(2 * 1024 * 1024 + 1)
    try:
        key = await run_in_threadpool(save_logo, data)
    except ImageError as exc:
        flash(request, f"Logo nije spremljen: {exc}", "error")
        return RedirectResponse("/admin/postavke#izgled", status_code=303)
    old_key = get_value(db, "logo_key")
    set_values(db, {"logo_key": key})
    if old_key:
        delete_variants(old_key, LOGO_SIZES)
    audit.log(
        db, user.id, "settings.update", "settings", None, {"keys": ["logo_key"]}, client_ip(request)
    )
    db.commit()
    flash(request, "Logo je spremljen i prikazuje se na cijeloj stranici.", "success")
    return RedirectResponse("/admin/postavke#izgled", status_code=303)


@router.post("/postavke/logo/ukloni")
async def logo_remove(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("settings")),
):
    old_key = get_value(db, "logo_key")
    if old_key:
        delete_variants(old_key, LOGO_SIZES)
        set_values(db, {"logo_key": ""})
        audit.log(
            db,
            user.id,
            "settings.update",
            "settings",
            None,
            {"keys": ["logo_key"]},
            client_ip(request),
        )
        db.commit()
    flash(request, "Logo je uklonjen — prikazuje se tekst LOGO.", "success")
    return RedirectResponse("/admin/postavke#izgled", status_code=303)
