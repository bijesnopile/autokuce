"""Favoriti i usporedba vozila (javno, bez računa).

Stanje je u pregledniku (localStorage, samo ID-ovi); poslužitelj renderira stranice iz ID-ova u
URL-u (`/favoriti?v=12,34`, `/usporedba?v=12,34,56`), pa su dijeljive linkom. Prikazuju se samo
javno vidljiva vozila; nepostojeći i skriveni ID-ovi se preskaču.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Vehicle

MAX_FAVORITES = 50
MAX_COMPARE = 3
EMPTY = "—"


def parse_ids(raw: str | None, limit: int) -> list[int]:
    """ "12, 34,x,12" -> [12, 34] (order kept, duplicates and junk dropped, at most `limit`)."""
    ids: list[int] = []
    for part in str(raw or "").split(","):
        part = part.strip()
        if part.isdigit() and len(part) <= 9:
            value = int(part)
            if value > 0 and value not in ids:
                ids.append(value)
        if len(ids) >= limit:
            break
    return ids


def load_public(db: Session, ids: list[int]) -> list[Vehicle]:
    """Publicly visible vehicles in the order of `ids`."""
    from app.services.vehicles import public_query

    if not ids:
        return []
    found = {v.id: v for v in db.scalars(public_query().where(Vehicle.id.in_(ids)))}
    return [found[i] for i in ids if i in found]


def ids_param(vehicles: list[Vehicle]) -> str:
    return ",".join(str(v.id) for v in vehicles)


# ---------------------------------------------------------------------------
# Comparison table
# ---------------------------------------------------------------------------
def _row(label: str, values: list[str]) -> dict:
    values = [v or EMPTY for v in values]
    return {"label": label, "values": values, "same": len(set(values)) == 1}


def _consumption(vehicle: Vehicle) -> str:
    from app.services.vehicles import energy_metrics

    metrics = energy_metrics(vehicle)
    if not metrics:
        return ""
    parts = [f"{value} {unit}" for label, value, unit in metrics["rows"] if "CO2" not in label]
    return " · ".join(parts)


def comparison(vehicles: list[Vehicle]) -> list[dict]:
    """Sections of rows [{label, values: [str per vehicle], same}] ("—" where missing)."""
    from app.services.vehicles import format_value
    from app.templating import km, money
    from app.vehicle_schema import (
        COMMON_BY_KEY,
        EQUIPMENT_CATEGORIES,
        equipment_for,
        field_label,
        label,
        type_fields,
        type_label,
        with_custom_options,
    )

    def common(key: str, vehicle: Vehicle) -> str:
        return format_value(with_custom_options(COMMON_BY_KEY[key]), getattr(vehicle, key))

    def price(v: Vehicle) -> str:
        return "Cijena na upit" if v.price_on_request or v.price_eur is None else money(v.price_eur)

    def power(v: Vehicle) -> str:
        return f"{v.power_kw} kW / {v.power_hp} KS" if v.power_kw else ""

    def body(v: Vehicle) -> str:
        attrs = v.attributes or {}
        for key in ("body_type", "van_type", "moto_type", "camper_type", "truck_body"):
            if attrs.get(key):
                return label(key, attrs[key], v.vehicle_type)
        return ""

    def doors_seats(v: Vehicle) -> str:
        return " / ".join(str(x) for x in (v.doors, v.seats) if x) if (v.doors or v.seats) else ""

    basics = [
        ("Vrsta vozila", lambda v: type_label(v.vehicle_type)),
        ("Cijena", price),
        ("Način oporezivanja", lambda v: label("tax_type", v.tax_type)),
        (
            "Stara cijena",
            lambda v: money(v.price_old_eur) if v.price_old_eur and not v.price_on_request else "",
        ),
        ("Stanje", lambda v: "Novo" if v.condition == "new" else "Rabljeno"),
        ("Godina", lambda v: str(v.year or "")),
        ("Prva registracija", lambda v: common("first_registration", v)),
        ("Kilometraža", lambda v: km(v.mileage_km) if v.mileage_km is not None else ""),
    ]
    engine = [
        ("Gorivo", lambda v: label("fuel", v.fuel) if v.fuel else ""),
        ("Snaga", power),
        ("Obujam motora", lambda v: common("engine_ccm", v)),
        ("Mjenjač", lambda v: label("transmission", v.transmission) if v.transmission else ""),
        ("Pogon", lambda v: label("drive", v.drive) if v.drive else ""),
        ("Euro norma", lambda v: common("euro_norm", v)),
        ("Potrošnja (WLTP)", _consumption),
        ("Električni domet", lambda v: common("electric_range_km", v)),
        ("Kapacitet baterije", lambda v: common("battery_kwh", v)),
        ("Emisija CO2", lambda v: "0 g/km" if v.fuel == "elektricni" else common("co2_g_km", v)),
    ]
    body_rows = [
        ("Karoserija", body),
        (
            "Boja",
            lambda v: (
                (common("color", v) + (" metalik" if v.color_metallic else "")) if v.color else ""
            ),
        ),
        ("Vrata / sjedala", doors_seats),
    ]
    state = [
        ("Garancija", lambda v: common("warranty_months", v)),
        ("Registriran do", lambda v: common("registered_until", v)),
        ("Prvi vlasnik", lambda v: "Da" if v.first_owner else ""),
        ("Servisna knjiga", lambda v: "Da" if v.service_book else ""),
    ]
    sections = [
        {"label": "Osnovno", "rows": [_row(t, [f(v) for v in vehicles]) for t, f in basics]},
        {"label": "Motor i pogon", "rows": [_row(t, [f(v) for v in vehicles]) for t, f in engine]},
        {"label": "Karoserija", "rows": [_row(t, [f(v) for v in vehicles]) for t, f in body_rows]},
        {"label": "Stanje", "rows": [_row(t, [f(v) for v in vehicles]) for t, f in state]},
    ]

    # Type-specific fields: union by label (e.g. car body + camper beds side by side).
    specific: dict[str, list[str]] = {}
    for index, vehicle in enumerate(vehicles):
        attrs = vehicle.attributes or {}
        for field in type_fields(vehicle.vehicle_type):
            if field["key"] in ("body_type", "van_type", "moto_type", "camper_type", "truck_body"):
                continue
            text = format_value(field, attrs.get(field["key"]))
            if text:
                name = field_label(field, vehicle.vehicle_type)
                specific.setdefault(name, [""] * len(vehicles))[index] = text
    if specific:
        sections.append(
            {
                "label": "Posebno za vrstu vozila",
                "rows": [_row(name, values) for name, values in specific.items()],
            }
        )

    # Equipment: union of all items, ✓/— per vehicle, grouped by category.
    selected = [set(v.equipment or []) for v in vehicles]
    for cat_key, cat_label in EQUIPMENT_CATEGORIES:
        items: dict[str, str] = {}
        for vehicle in vehicles:
            for category in equipment_for(vehicle.vehicle_type):
                if category["key"] == cat_key:
                    for item in category["items"]:
                        items.setdefault(item["code"], item["label"])
        rows = [
            _row(text, ["✓" if code in chosen else EMPTY for chosen in selected])
            for code, text in items.items()
            if any(code in chosen for chosen in selected)
        ]
        if rows:
            sections.append({"label": f"Oprema: {cat_label}", "rows": rows, "equipment": True})

    # Drop rows that are empty for every vehicle.
    for section in sections:
        section["rows"] = [r for r in section["rows"] if any(v != EMPTY for v in r["values"])]
    return [s for s in sections if s["rows"]]
