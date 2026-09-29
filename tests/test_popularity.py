"""Faza 10 C: socijalni dokaz pregleda (samo stvarni podaci)."""

from __future__ import annotations

from datetime import timedelta

from app.models import VehicleView
from app.services import popularity
from app.services.site import invalidate_site_cache, set_values
from app.utils import local_today
from tests.helpers import make_vehicle


def _views(db, vehicle, per_day, days=7, offset=0):
    today = local_today()
    for n in range(days):
        db.add(
            VehicleView(
                vehicle_id=vehicle.id, date=today - timedelta(days=n + offset), count=per_day
            )
        )
    db.commit()
    popularity.invalidate()


def test_counter_threshold_is_ten(client, db):
    vehicle = make_vehicle(db)
    _views(db, vehicle, 1, days=9)  # 7 inside the window, 2 older
    assert popularity.recent_views(db, vehicle) == 7
    assert "u zadnjih 7 dana" not in client.get(f"/vozila/{vehicle.slug}").text
    _views(db, vehicle, 1, days=3, offset=9)  # outside the window: still 7
    db.query(VehicleView).filter_by(vehicle_id=vehicle.id).update({"count": 2})
    db.commit()
    html = client.get(f"/vozila/{vehicle.slug}").text
    assert "Pregledano 14 puta u zadnjih 7 dana" in html


def test_popular_badge_only_top_five_with_twenty_views(client, db):
    vehicles = [make_vehicle(db, model_name=f"Model {n}") for n in range(7)]
    for n, vehicle in enumerate(vehicles):
        _views(db, vehicle, 10 - n)  # 70, 63, 56, 49, 42, 35, 28 per week
    weak = make_vehicle(db, model_name="Slabi")
    _views(db, weak, 2)  # 14 < 20
    ids = popularity.popular_ids()
    assert ids == {v.id for v in vehicles[:5]}
    assert weak.id not in ids
    html = client.get("/vozila").text
    assert html.count("badge-popular") == 5


def test_below_twenty_is_never_popular(db):
    vehicle = make_vehicle(db)
    _views(db, vehicle, 2)  # 14
    assert popularity.popular_ids() == frozenset()


def test_disabled_by_setting(client, db):
    vehicle = make_vehicle(db)
    _views(db, vehicle, 5)
    set_values(db, {"social_proof_enabled": "false"})
    db.commit()
    invalidate_site_cache()
    html = client.get(f"/vozila/{vehicle.slug}").text
    assert "u zadnjih 7 dana" not in html and "badge-popular" not in html


def test_popular_list_is_cached(db):
    vehicle = make_vehicle(db)
    _views(db, vehicle, 5)
    assert vehicle.id in popularity.popular_ids()
    db.query(VehicleView).delete()
    db.commit()
    assert vehicle.id in popularity.popular_ids()  # cached (10 min)
    popularity.invalidate()
    assert vehicle.id not in popularity.popular_ids()


def test_no_inquiry_counts_or_live_viewers(client, db):
    vehicle = make_vehicle(db)
    _views(db, vehicle, 5)
    html = client.get(f"/vozila/{vehicle.slug}").text.lower()
    assert "upravo sada" not in html and "upita" not in html.split("pregledano")[1][:80]
