"""Full demo seed (phase 7)."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.database import utcnow
from app.models import (
    AuditLog,
    Campaign,
    Inquiry,
    InquiryNote,
    Subscriber,
    User,
    Vehicle,
    VehicleImage,
)
from app.services.storage import get_storage


def test_demo_seed_is_complete_and_idempotent(db):
    from app.seed import seed_catalog
    from app.seed_demo import seed_demo
    from app.vehicle_schema import validate_attributes

    seed_catalog(db)
    db.commit()
    result = seed_demo(db, image_size=(480, 360))
    assert result["vehicles"] == 16
    vehicles = list(db.scalars(select(Vehicle)))
    statuses = [v.status for v in vehicles]
    assert statuses.count("active") == 12 and statuses.count("reserved") == 1
    assert statuses.count("sold") == 2 and statuses.count("draft") == 1
    assert sum(v.featured for v in vehicles) == 3
    assert sum(v.price_on_request for v in vehicles) == 1
    assert sum(1 for v in vehicles if v.price_old_eur) == 2  # BMW and Škoda (price drops)
    from app.services.pricing import active_drops, invalidate

    invalidate()
    drops = active_drops()
    assert len(drops) == 2  # Toyota's increase is not a drop
    types = [v.vehicle_type for v in vehicles]
    assert (
        types.count("car"),
        types.count("van"),
        types.count("motorcycle"),
        types.count("camper"),
        types.count("truck"),
    ) == (8, 3, 2, 2, 1)
    storage = get_storage()
    for vehicle in vehicles:
        assert 5 <= len(vehicle.images) <= 8
        _, errors = validate_attributes(vehicle.vehicle_type, vehicle.attributes)
        assert errors == {}
        if vehicle.condition == "new" and vehicle.fuel == "elektricni":
            assert vehicle.energy_consumption_kwh100 and vehicle.electric_range_km
            assert vehicle.fuel_consumption_l100 is None and vehicle.co2_g_km is None
        elif vehicle.condition == "new":
            assert vehicle.co2_g_km is not None and vehicle.fuel_consumption_l100 is not None
        for image in vehicle.images:
            for size in (400, 1000, 1600):
                assert storage.exists(f"{image.file_key}_{size}.webp")
    assert db.query(Inquiry).count() == 11 and db.query(InquiryNote).count() == 4
    # Paket Standard demo: one financing request, one confirmed viewing, WhatsApp placeholder.
    financing = db.query(Inquiry).filter(Inquiry.type == "financing").one()
    assert financing.extra["financing"]["months"] == 60 and financing.vehicle.price_eur
    assert db.query(Inquiry).filter(Inquiry.scheduled_at.is_not(None)).count() == 1
    from app.services.site import get_value

    assert get_value(db, "whatsapp_number") == "+385XXXXXXXXXX"
    assert db.query(Inquiry).filter(Inquiry.assigned_to.is_not(None)).count() == 3
    subs = [s.status for s in db.scalars(select(Subscriber))]
    assert (subs.count("confirmed"), subs.count("pending"), subs.count("unsubscribed")) == (
        10,
        3,
        2,
    )
    campaigns = {c.status: c for c in db.scalars(select(Campaign))}
    assert set(campaigns) == {"sent", "draft"}
    sent = campaigns["sent"]
    assert [d.status for d in sent.deliveries].count("sent") == 9
    assert [d.status for d in sent.deliveries].count("failed") == 1
    assert {u.email for u in db.scalars(select(User))} >= {
        "admin@domena.com",
        "vlasnik@domena.com",
        "prodavac1@domena.com",
    }
    assert db.query(AuditLog).count() >= 10
    sold_45 = [
        v for v in vehicles if v.status == "sold" and v.sold_at < utcnow() - timedelta(days=40)
    ]
    assert len(sold_45) == 1
    images_before = db.query(VehicleImage).count()
    # Second run does not duplicate anything.
    assert seed_demo(db, image_size=(480, 360)) == {"skipped": True}
    assert db.query(Vehicle).count() == 16 and db.query(VehicleImage).count() == images_before


def test_demo_seed_refused_in_production(monkeypatch):
    import pytest

    from app import seed
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "APP_ENV", "production")
    monkeypatch.setattr(get_settings(), "DEMO_SEED", False)
    with pytest.raises(SystemExit) as exc:
        seed.main(["--reset-demo"])
    assert exc.value.code == 2


def test_seed_if_empty_skips_existing_instance(db):
    from sqlalchemy import delete, func, select

    from app import seed
    from app.models import Make, Setting

    # conftest seeded settings/pages/superadmin (no catalog) -> the instance is not empty;
    # a restart must not add catalog entries (the client may have removed them on purpose).
    db.execute(delete(Setting).where(Setting.key == "cookie_banner_enabled"))
    db.commit()
    makes_before = db.scalar(select(func.count()).select_from(Make))
    seed.main(["--minimal", "--if-empty"])
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Make)) == makes_before
    assert db.get(Setting, "cookie_banner_enabled") is not None  # new settings keys are added
