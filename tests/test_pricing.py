"""Faza 10 B: povijest cijena i oznaka "Snižena cijena"."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.database import utcnow
from app.models import AuditLog, Vehicle, VehiclePriceHistory
from app.services import pricing
from app.services.site import invalidate_site_cache, set_values
from app.services.vehicles import change_status
from tests.helpers import create_user, get_csrf, login_as, make_vehicle
from tests.test_vehicles import _form_data


def _owner(client):
    user_id, _ = create_user("vlasnik@test.hr", role="owner")
    login_as(client, user_id)
    return user_id


def _save(client, vehicle, **changes):
    """Submit the edit form with the vehicle's current price/status plus `changes`."""
    token = get_csrf(client, f"/admin/vozila/{vehicle.id}")
    data = _form_data(
        vehicle.make,
        vehicle.model,
        "car",
        csrf_token=token,
        price_eur=str(vehicle.price_eur or ""),
        price_old_eur=str(vehicle.price_old_eur or ""),
        status=vehicle.status,
    )
    data.update(changes)
    return client.post(f"/admin/vozila/{vehicle.id}", data=data, follow_redirects=False)


def _history(db, vehicle):
    db.expire_all()
    return [
        (h.old_price, h.new_price)
        for h in db.scalars(
            select(VehiclePriceHistory)
            .where(VehiclePriceHistory.vehicle_id == vehicle.id)
            .order_by(VehiclePriceHistory.id)
        )
    ]


def test_price_change_is_recorded_and_drop_fills_old_price(client, db):
    _owner(client)
    vehicle = make_vehicle(db, price_eur=20000)
    pricing.ensure_initial(db, vehicle, None)
    db.commit()
    assert _history(db, vehicle) == [(None, 20000)]

    assert _save(client, vehicle, price_eur="19000").status_code == 303
    assert _history(db, vehicle) == [(None, 20000), (20000, 19000)]
    vehicle = db.get(Vehicle, vehicle.id)
    assert vehicle.price_old_eur == 20000  # filled automatically on a drop
    entry = db.scalar(select(AuditLog).where(AuditLog.action == "vehicle.price"))
    assert entry.details == {"from": 20000, "to": 19000}

    # Dealer clears the old price: stays empty while the price does not drop again.
    _save(client, vehicle, price_old_eur="")
    db.expire_all()
    assert db.get(Vehicle, vehicle.id).price_old_eur is None
    # Increase: recorded, old price untouched.
    _save(client, vehicle, price_eur="19500", price_old_eur="")
    vehicle = db.get(Vehicle, vehicle.id)
    assert vehicle.price_old_eur is None and _history(db, vehicle)[-1] == (19000, 19500)
    # Existing old price is kept on a further drop.
    assert _save(client, vehicle, price_eur="18000", price_old_eur="25000").status_code == 303
    db.expire_all()
    vehicle = db.get(Vehicle, vehicle.id)
    assert vehicle.price_old_eur == 25000
    # "Price on request" <-> price is recorded too.
    _save(client, vehicle, price_on_request="1")
    assert _history(db, vehicle)[-1] == (18000, None)


def test_first_publish_records_starting_price(client, db):
    _owner(client)
    vehicle = make_vehicle(db, status="draft", price_eur=15000)
    _save(client, vehicle, price_eur="14000")  # draft: no history yet
    assert _history(db, vehicle) == []
    vehicle = db.get(Vehicle, vehicle.id)
    _save(client, vehicle, status="active")
    assert _history(db, vehicle) == [(None, 14000)]


def _drop(db, vehicle, old, new, days_ago=2):
    db.add(
        VehiclePriceHistory(
            vehicle_id=vehicle.id,
            old_price=old,
            new_price=new,
            changed_at=utcnow() - timedelta(days=days_ago),
        )
    )
    vehicle.price_eur = new
    db.commit()
    pricing.invalidate()


def test_badge_only_for_recent_drops_and_percent(client, db):
    dropped = make_vehicle(db, make_name="BMW", model_name="X1", price_eur=19000)
    _drop(db, dropped, 20000, 19000)
    old_drop = make_vehicle(db, make_name="Audi", model_name="A3", price_eur=9000)
    _drop(db, old_drop, 10000, 9000, days_ago=40)
    raised = make_vehicle(db, make_name="Kia", model_name="Rio", price_eur=12000)
    _drop(db, raised, 11000, 12000)

    drops = pricing.active_drops()
    assert set(drops) == {dropped.id}
    assert drops[dropped.id]["percent"] == 5
    listing = client.get("/vozila").text
    assert listing.count("badge-drop") == 1
    detail = client.get(f"/vozila/{dropped.slug}").text
    assert "Snižena cijena" in detail and "(−5 %)" in detail
    raised_detail = client.get(f"/vozila/{raised.slug}").text
    assert "11.000" not in raised_detail  # increases are never public
    assert "Povijest cijene" not in raised_detail

    # Badge window is a setting.
    set_values(db, {"price_drop_badge_days": "60"})
    db.commit()
    invalidate_site_cache()
    pricing.invalidate()
    assert set(pricing.active_drops()) == {dropped.id, old_drop.id}


def test_public_history_shows_last_three_drops_only(client, db):
    vehicle = make_vehicle(db, price_eur=16000)
    for days, (old, new) in zip(
        (20, 15, 10, 5, 3),
        ((20000, 19000), (19000, 18000), (18000, 18500), (18500, 17000), (17000, 16000)),
        strict=True,
    ):
        _drop(db, vehicle, old, new, days_ago=days)
    drops = pricing.public_drops(db, vehicle)
    assert [(d["old"], d["new"]) for d in drops] == [(17000, 16000), (18500, 17000), (19000, 18000)]


def test_filter_only_discounted(client, db):
    dropped = make_vehicle(db, make_name="BMW", model_name="X1", price_eur=19000)
    _drop(db, dropped, 20000, 19000)
    other = make_vehicle(db, make_name="Kia", model_name="Rio")
    html = client.get("/vozila?snizeno=1").text
    assert dropped.title in html and other.title not in html
    assert "Samo snižena" in html


def test_card_shows_at_most_two_badges_in_order(db):
    vehicle = make_vehicle(db, condition="new", featured=True, price_eur=19000)
    change_status(vehicle, "reserved")
    _drop(db, vehicle, 20000, 19000)
    assert [kind for kind, _ in pricing.card_badges(vehicle)] == ["reserved", "drop"]


def test_admin_sort_recently_discounted(client, db):
    _owner(client)
    first = make_vehicle(db, make_name="BMW", model_name="X1", price_eur=19000)
    second = make_vehicle(db, make_name="Audi", model_name="A3", price_eur=9000)
    _drop(db, first, 20000, 19000, days_ago=9)
    _drop(db, second, 10000, 9000, days_ago=1)
    html = client.get("/admin/vozila?sort=snizeno").text
    assert html.index(second.title) < html.index(first.title)
    page = client.get(f"/admin/vozila/{first.id}").text
    assert "Povijest cijene" in page and "−5 %" in page
