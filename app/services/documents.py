"""Ispisni dokumenti (paket Standard): kartica za izlog i ponuda kupcu.

Bez novih ovisnosti: HTML s print CSS-om (`@page A4/A5`), PDF se sprema kroz dijalog ispisa
preglednika ("Spremi kao PDF"). Ponude se ne spremaju u bazu; svaki ispis se bilježi u audit
(`offer.print`, bez podataka kupca), a broj ponude je `{godina}-{id audit zapisa}` — jedinstven i
provjerljiv u audit logu.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from app.config import get_settings
from app.models import Vehicle
from app.services.auth import qr_data_uri
from app.utils import local_today
from app.vehicle_schema import EQUIPMENT_BY_CODE, label

OFFER_VALID_DAYS = 7
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def public_url(vehicle: Vehicle) -> str:
    return f"{get_settings().base_url}/vozila/{vehicle.slug}"


def vehicle_qr(vehicle: Vehicle) -> str:
    """QR code (PNG data URI) that opens the public ad — no external service involved."""
    return qr_data_uri(public_url(vehicle))


def _month(value) -> str:
    return value.strftime("%m/%Y") if value else "—"


def card_facts(vehicle: Vehicle) -> list[tuple[str, str]]:
    """The eight facts on the window card."""
    from app.templating import format_number

    color = label("color", vehicle.color) or "—"
    if vehicle.color and vehicle.color_metallic:
        color += " metalik"
    return [
        ("Godina", str(vehicle.year or "—")),
        (
            "Kilometraža",
            f"{format_number(vehicle.mileage_km)} km" if vehicle.mileage_km is not None else "—",
        ),
        ("Gorivo", label("fuel", vehicle.fuel) or "—"),
        (
            "Snaga",
            f"{vehicle.power_kw} kW ({vehicle.power_hp} KS)" if vehicle.power_kw else "—",
        ),
        ("Mjenjač", label("transmission", vehicle.transmission) or "—"),
        ("Boja", color),
        ("Prva registracija", _month(vehicle.first_registration)),
        ("Registriran do", _month(vehicle.registered_until)),
    ]


def equipment_labels(vehicle: Vehicle, limit: int | None = None) -> list[str]:
    labels = [
        EQUIPMENT_BY_CODE[code]["label"]
        for code in (vehicle.equipment or [])
        if code in EQUIPMENT_BY_CODE
    ]
    return labels[:limit] if limit else labels


def _int_or_none(value: str) -> int | None:
    value = re.sub(r"[\s.]", "", value or "").replace(",", ".")
    if not value:
        return None
    try:
        return int(round(float(value)))
    except ValueError:
        return -1


def default_valid_until() -> date:
    return local_today() + timedelta(days=OFFER_VALID_DAYS)


def parse_offer_form(form, vehicle: Vehicle) -> tuple[dict, dict]:
    """Offer form -> (data, errors). Final price = explicit final price, else price − discount."""
    data = {
        "customer_name": str(form.get("customer_name", "")).strip()[:120],
        "customer_email": str(form.get("customer_email", "")).strip()[:254],
        "discount": str(form.get("discount", "")).strip(),
        "final_price": str(form.get("final_price", "")).strip(),
        "valid_until": str(form.get("valid_until", "")).strip(),
        "note": str(form.get("note", "")).strip()[:1500],
    }
    errors: dict = {}
    if len(data["customer_name"]) < 2:
        errors["customer_name"] = "Upišite ime kupca."
    if data["customer_email"] and not EMAIL_RE.match(data["customer_email"]):
        errors["customer_email"] = "Upišite ispravnu email adresu ili ostavite prazno."
    base = None if vehicle.price_on_request else vehicle.price_eur
    discount = _int_or_none(data["discount"])
    final = _int_or_none(data["final_price"])
    if final is not None:
        if final < 0:
            errors["final_price"] = "Upišite cijenu u eurima."
    elif base is None:
        errors["final_price"] = "Vozilo ima 'cijenu na upit' — upišite konačnu cijenu."
    elif discount is not None and (discount < 0 or discount > base):
        errors["discount"] = "Popust mora biti između 0 i cijene vozila."
    try:
        valid_until = date.fromisoformat(data["valid_until"]) if data["valid_until"] else None
    except ValueError:
        valid_until = None
        errors["valid_until"] = "Neispravan datum."
    valid_until = valid_until or default_valid_until()
    if valid_until < local_today():
        errors["valid_until"] = "Ponuda ne može vrijediti do datuma u prošlosti."
    if not errors:
        if final is None:
            final = base - (discount or 0)
        data["discount_eur"] = (base - final) if base is not None and final < base else 0
        data["final_eur"] = final
        data["base_eur"] = base
        data["valid_until_date"] = valid_until
    return data, errors
