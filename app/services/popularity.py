"""Socijalni dokaz pregleda — isključivo stvarni podaci iz `vehicle_views` (dnevni brojač).

- Detalj: "Pregledano {n} puta u zadnjih 7 dana" samo ako je n >= VIEWS_MIN (10).
- Kartica: oznaka "Popularno" za top 5 javnih vozila po pregledima u zadnjih 7 dana s najmanje
  POPULAR_MIN (20) pregleda. Jedan upit, keš 10 min.
- Isključuje se postavkom `social_proof_enabled`. Nikad broj upita ni "X ljudi gleda sada".
"""

from __future__ import annotations

import threading
import time
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import STATUS_ACTIVE, STATUS_RESERVED, Vehicle, VehicleView

WINDOW_DAYS = 7
VIEWS_MIN = 10
POPULAR_MIN = 20
POPULAR_TOP = 5
CACHE_SECONDS = 600

_lock = threading.Lock()
_cache: dict = {"at": 0.0, "ids": frozenset()}


def enabled() -> bool:
    from app.services.site import get_site

    return bool(get_site().get("social_proof_enabled"))


def _window_start():
    from app.utils import local_today

    return local_today() - timedelta(days=WINDOW_DAYS - 1)


def invalidate() -> None:
    with _lock:
        _cache["at"] = 0.0


def recent_views(db: Session, vehicle: Vehicle) -> int:
    return (
        db.scalar(
            select(func.coalesce(func.sum(VehicleView.count), 0)).where(
                VehicleView.vehicle_id == vehicle.id, VehicleView.date >= _window_start()
            )
        )
        or 0
    )


def views_note(db: Session, vehicle: Vehicle) -> int | None:
    """Number for "Pregledano n puta u zadnjih 7 dana", or None (disabled / below the bar)."""
    if not enabled():
        return None
    views = recent_views(db, vehicle)
    return views if views >= VIEWS_MIN else None


def _load_popular() -> frozenset[int]:
    from app.database import SessionLocal

    total = func.sum(VehicleView.count)
    stmt = (
        select(VehicleView.vehicle_id)
        .join(Vehicle, Vehicle.id == VehicleView.vehicle_id)
        .where(
            VehicleView.date >= _window_start(),
            Vehicle.status.in_((STATUS_ACTIVE, STATUS_RESERVED)),
        )
        .group_by(VehicleView.vehicle_id)
        .having(total >= POPULAR_MIN)
        .order_by(total.desc(), VehicleView.vehicle_id)
        .limit(POPULAR_TOP)
    )
    with SessionLocal() as db:
        return frozenset(db.scalars(stmt))


def popular_ids() -> frozenset[int]:
    now = time.monotonic()
    if now - _cache["at"] > CACHE_SECONDS:
        ids = _load_popular()
        with _lock:
            _cache.update(at=now, ids=ids)
    return _cache["ids"]


def is_popular(vehicle: Vehicle) -> bool:
    return enabled() and vehicle.id in popular_ids()
