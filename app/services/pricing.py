"""Povijest cijena, oznaka "Snižena cijena" i oznake na karticama vozila.

- Svaka promjena cijene kroz admin → `vehicle_price_history` (NULL = "cijena na upit").
  Prvi zapis objavljenog vozila ima `old_price = NULL` (početna cijena).
- Javno se prikazuju samo sniženja; oznaka "Snižena cijena" ako je ZADNJA promjena sniženje
  unutar postavke `price_drop_badge_days` (default 30).
- Aktivna sniženja se računaju jednim upitom i keširaju (60 s, poništava se pri promjeni cijene).
"""

from __future__ import annotations

import threading
import time
from datetime import timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.database import utcnow
from app.models import Vehicle, VehiclePriceHistory

CACHE_SECONDS = 60
PUBLIC_DROPS = 3
MAX_CARD_BADGES = 2

_lock = threading.Lock()
_cache: dict = {"at": 0.0, "drops": {}}


def effective_price(vehicle: Vehicle) -> int | None:
    """Price as the public sees it (None = "price on request")."""
    if vehicle.price_on_request or vehicle.price_eur is None:
        return None
    return vehicle.price_eur


def drop_percent(old: int, new: int) -> int:
    return round((old - new) * 100 / old) if old else 0


def invalidate() -> None:
    with _lock:
        _cache["at"] = 0.0


# ---------------------------------------------------------------------------
# Recording (admin)
# ---------------------------------------------------------------------------
def record_change(
    db: Session, vehicle: Vehicle, old: int | None, new: int | None, user_id: int | None
) -> bool:
    if old == new:
        return False
    db.add(
        VehiclePriceHistory(vehicle_id=vehicle.id, old_price=old, new_price=new, user_id=user_id)
    )
    invalidate()
    return True


def ensure_initial(db: Session, vehicle: Vehicle, user_id: int | None) -> bool:
    """On first publishing: the starting price (old_price NULL)."""
    if vehicle.published_at is None:
        return False
    db.flush()
    exists = db.scalar(
        select(VehiclePriceHistory.id).where(VehiclePriceHistory.vehicle_id == vehicle.id).limit(1)
    )
    if exists:
        return False
    db.add(
        VehiclePriceHistory(
            vehicle_id=vehicle.id,
            old_price=None,
            new_price=effective_price(vehicle),
            changed_at=vehicle.published_at,
            user_id=user_id,
        )
    )
    invalidate()
    return True


def history(db: Session, vehicle: Vehicle) -> list[VehiclePriceHistory]:
    return list(
        db.scalars(
            select(VehiclePriceHistory)
            .where(VehiclePriceHistory.vehicle_id == vehicle.id)
            .order_by(VehiclePriceHistory.changed_at.desc(), VehiclePriceHistory.id.desc())
        )
    )


def public_drops(db: Session, vehicle: Vehicle, limit: int = PUBLIC_DROPS) -> list[dict]:
    """Latest price drops (increases and "on request" changes are never public)."""
    rows = db.scalars(
        select(VehiclePriceHistory)
        .where(
            VehiclePriceHistory.vehicle_id == vehicle.id,
            VehiclePriceHistory.old_price.is_not(None),
            VehiclePriceHistory.new_price.is_not(None),
            VehiclePriceHistory.new_price < VehiclePriceHistory.old_price,
        )
        .order_by(VehiclePriceHistory.changed_at.desc(), VehiclePriceHistory.id.desc())
        .limit(limit)
    )
    return [
        {
            "at": r.changed_at,
            "old": r.old_price,
            "new": r.new_price,
            "percent": drop_percent(r.old_price, r.new_price),
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Active drops (badge, filter "samo snižena") — one query, cached
# ---------------------------------------------------------------------------
def badge_days() -> int:
    from app.services.site import get_site

    try:
        return max(1, int(get_site().get("price_drop_badge_days") or 30))
    except ValueError:
        return 30


def _load_drops() -> dict[int, dict]:
    from app.database import SessionLocal

    cutoff = utcnow() - timedelta(days=badge_days())
    latest = (
        select(func.max(VehiclePriceHistory.id).label("id"))
        .group_by(VehiclePriceHistory.vehicle_id)
        .subquery()
    )
    stmt = (
        select(VehiclePriceHistory)
        .join(latest, latest.c.id == VehiclePriceHistory.id)
        .where(
            and_(
                VehiclePriceHistory.old_price.is_not(None),
                VehiclePriceHistory.new_price.is_not(None),
                VehiclePriceHistory.new_price < VehiclePriceHistory.old_price,
                VehiclePriceHistory.changed_at >= cutoff,
            )
        )
    )
    with SessionLocal() as db:
        return {
            r.vehicle_id: {
                "at": r.changed_at,
                "old": r.old_price,
                "new": r.new_price,
                "percent": drop_percent(r.old_price, r.new_price),
            }
            for r in db.scalars(stmt)
        }


def active_drops() -> dict[int, dict]:
    """vehicle_id -> latest drop, for vehicles whose last price change is a recent drop."""
    now = time.monotonic()
    if now - _cache["at"] > CACHE_SECONDS:
        drops = _load_drops()
        with _lock:
            _cache.update(at=now, drops=drops)
    return _cache["drops"]


def price_drop(vehicle: Vehicle) -> dict | None:
    drop = active_drops().get(vehicle.id)
    # Only while the current price is the dropped one (e.g. not after "on request").
    if drop and effective_price(vehicle) == drop["new"]:
        return drop
    return None


# ---------------------------------------------------------------------------
# Card badges: fixed order, at most two (the rest is visible on the detail page)
# ---------------------------------------------------------------------------
def card_badges(vehicle: Vehicle) -> list[tuple[str, str]]:
    """[(css modifier, label)] — status, discount, popular, new, featured; max 2."""
    from app.services.popularity import is_popular

    badges: list[tuple[str, str]] = []
    if vehicle.status == "reserved":
        badges.append(("reserved", "Rezervirano"))
    elif vehicle.status == "sold":
        badges.append(("sold", "Prodano"))
    if vehicle.status != "sold":
        if price_drop(vehicle):
            badges.append(("drop", "Snižena cijena"))
        if is_popular(vehicle):
            badges.append(("popular", "Popularno"))
    if vehicle.condition == "new":
        badges.append(("new", "Novo"))
    if vehicle.featured and vehicle.status != "sold":
        badges.append(("featured", "Istaknuto"))
    return badges[:MAX_CARD_BADGES]
