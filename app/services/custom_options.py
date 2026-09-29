"""Vlastite opcije autokuće: nove vrijednosti padajućih izbornika i stavke opreme koje admin
dopiše u formi vozila. Prikazuju se zajedno s ugrađenima (forma, detalj oglasa, filteri, feed).

Ugrađene opcije su u `app/vehicle_schema.py`; ovdje su samo dodane (tablica `custom_options`).
Keš po procesu (15 s) — obrazac vozila prije validacije zove `refresh()`, pa drugi worker nikad
ne odbije opciju koju je upravo dodao prvi.
"""

from __future__ import annotations

import threading
import time

from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.models import CustomOption, Vehicle
from app.utils import slugify

CACHE_SECONDS = 15
MAX_LABEL = 60
EQUIPMENT_SCOPE = "equipment"

_lock = threading.Lock()
_cache: dict = {"at": 0.0, "options": {}, "equipment": []}


def invalidate() -> None:
    with _lock:
        _cache["at"] = 0.0


@event.listens_for(Session, "after_commit")
def _invalidate_after_commit(session: Session) -> None:
    # A new/renamed option becomes visible to every request only after the commit.
    if session.info.pop("custom_options_changed", False):
        invalidate()


def _mark_changed(db: Session) -> None:
    db.info["custom_options_changed"] = True
    invalidate()


def refresh() -> None:
    """Reload from the database (own session; missing table = no custom options)."""
    from app.database import SessionLocal

    options: dict[str, list[tuple[str, str]]] = {}
    equipment: list[dict] = []
    try:
        with SessionLocal() as db:
            rows = db.scalars(select(CustomOption).order_by(CustomOption.label)).all()
    except Exception:  # noqa: BLE001 - e.g. before migrations; built-in options still work
        rows = []
    for row in rows:
        if row.scope == EQUIPMENT_SCOPE:
            equipment.append(
                {
                    "code": row.code,
                    "label": row.label,
                    "cat": row.category or "ostalo",
                    "types": (row.vehicle_type,) if row.vehicle_type else (),
                    "custom": True,
                }
            )
        else:
            options.setdefault(row.scope, []).append((row.code, row.label))
    with _lock:
        _cache.update(at=time.monotonic(), options=options, equipment=equipment)


def _fresh() -> dict:
    if time.monotonic() - _cache["at"] > CACHE_SECONDS:
        refresh()
    return _cache


def extra_options(scope: str) -> list[tuple[str, str]]:
    return list(_fresh()["options"].get(scope, []))


def extra_equipment() -> list[dict]:
    return list(_fresh()["equipment"])


# ---------------------------------------------------------------------------
# Creating
# ---------------------------------------------------------------------------
def clean_label(raw: str) -> str:
    return " ".join(str(raw or "").split())[:MAX_LABEL]


def _unique_code(label: str, taken: set[str], prefix: str = "") -> str:
    base = (prefix + (slugify(label, 30) or "opcija"))[:36]
    code, n = base, 2
    while code in taken:
        code = f"{base}-{n}"
        n += 1
    return code


def add_option(
    db: Session, scope: str, label: str, builtin: list[tuple[str, str]], user_id: int | None
) -> tuple[str, bool]:
    """Return (code, created). An existing option with the same label (built-in or custom,
    case-insensitive) is reused instead of creating a duplicate."""
    label = clean_label(label)
    wanted = label.casefold()
    for code, text in builtin + extra_options(scope):
        if text.casefold() == wanted:
            return code, False
    existing = db.scalar(
        select(CustomOption).where(
            CustomOption.scope == scope, func.lower(CustomOption.label) == label.lower()
        )
    )
    if existing:
        return existing.code, False
    taken = {code for code, _ in builtin}
    taken |= set(db.scalars(select(CustomOption.code).where(CustomOption.scope == scope)))
    code = _unique_code(label, taken)
    db.add(CustomOption(scope=scope, code=code, label=label, created_by=user_id))
    db.flush()
    _mark_changed(db)
    return code, True


def add_equipment(
    db: Session,
    vehicle_type: str,
    category: str,
    label: str,
    builtin: list[dict],
    user_id: int | None,
) -> tuple[str, bool]:
    """Custom equipment item for one vehicle type and category. Same label reuses the item."""
    label = clean_label(label)
    wanted = label.casefold()
    for item in builtin + extra_equipment():
        if vehicle_type in item["types"] and item["label"].casefold() == wanted:
            return item["code"], False
    existing = db.scalar(
        select(CustomOption).where(
            CustomOption.scope == EQUIPMENT_SCOPE,
            CustomOption.vehicle_type == vehicle_type,
            func.lower(CustomOption.label) == label.lower(),
        )
    )
    if existing:
        return existing.code, False
    taken = {item["code"] for item in builtin}
    taken |= set(db.scalars(select(CustomOption.code).where(CustomOption.scope == EQUIPMENT_SCOPE)))
    code = _unique_code(label, taken, prefix="x-")
    db.add(
        CustomOption(
            scope=EQUIPMENT_SCOPE,
            code=code,
            label=label,
            category=category,
            vehicle_type=vehicle_type,
            created_by=user_id,
        )
    )
    db.flush()
    _mark_changed(db)
    return code, True


# ---------------------------------------------------------------------------
# Management (Katalog → Vlastite opcije)
# ---------------------------------------------------------------------------
def describe(option: CustomOption) -> dict:
    """Field name, vehicle type and category of an option (for the management page)."""
    from app.vehicle_schema import (
        COMMON_BY_KEY,
        EQUIPMENT_CATEGORIES,
        TYPE_FIELDS,
        field_label,
        type_label,
    )

    if option.scope == EQUIPMENT_SCOPE:
        category = dict(EQUIPMENT_CATEGORIES).get(option.category or "", option.category or "")
        return {
            "field": "Oprema",
            "detail": category,
            "vehicle_type": type_label(option.vehicle_type),
        }
    if "." in option.scope:
        type_code, key = option.scope.split(".", 1)
        field = next((f for f in TYPE_FIELDS.get(type_code, []) if f["key"] == key), None)
        name = field_label(field, type_code) if field else key
        return {"field": name, "detail": "", "vehicle_type": type_label(type_code)}
    field = COMMON_BY_KEY.get(option.scope)
    return {"field": field["label"] if field else option.scope, "detail": "", "vehicle_type": ""}


def rename(db: Session, option: CustomOption, label: str) -> str | None:
    """New label (code stays, so vehicles keep the option). Returns an error or None."""
    label = clean_label(label)
    if not label:
        return "Upišite naziv."
    duplicate = db.scalar(
        select(CustomOption).where(
            CustomOption.scope == option.scope,
            CustomOption.id != option.id,
            CustomOption.vehicle_type.is_(option.vehicle_type)
            if option.vehicle_type is None
            else CustomOption.vehicle_type == option.vehicle_type,
            func.lower(CustomOption.label) == label.lower(),
        )
    )
    if duplicate:
        return "Opcija s tim nazivom već postoji."
    option.label = label
    _mark_changed(db)
    return None


def usage_count(db: Session, option: CustomOption) -> int:
    """How many vehicles use the option (JSON columns are checked in Python — small tables)."""
    if option.scope == EQUIPMENT_SCOPE:
        rows = db.scalars(
            select(Vehicle.equipment).where(Vehicle.vehicle_type == option.vehicle_type)
        )
        return sum(1 for codes in rows if option.code in (codes or []))
    if "." in option.scope:
        vehicle_type, key = option.scope.split(".", 1)
        rows = db.scalars(select(Vehicle.attributes).where(Vehicle.vehicle_type == vehicle_type))
        return sum(1 for attrs in rows if (attrs or {}).get(key) == option.code)
    column = getattr(Vehicle, option.scope, None)
    if column is None:
        return 0
    return db.scalar(select(func.count(Vehicle.id)).where(column == option.code)) or 0
