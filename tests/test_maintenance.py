"""Retention / maintenance jobs (phase 7)."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.database import utcnow
from app.models import (
    AuditLog,
    AuthToken,
    EmailLog,
    Inquiry,
    UserSession,
    Vehicle,
    VehicleView,
)
from app.services import maintenance
from app.utils import local_today
from tests.helpers import create_user, make_vehicle


def test_maintenance_steps_touch_only_what_they_should(db):
    now = utcnow()
    user_id, _ = create_user("vlasnik@test.hr")
    old_sold = make_vehicle(db, model_name="Stari", status="sold")
    old_sold.sold_at = now - timedelta(days=31)
    fresh_sold = make_vehicle(db, model_name="Novi", status="sold")
    active = make_vehicle(db, model_name="Aktivni")
    db.add_all(
        [
            Inquiry(
                type="general",
                name="Stari",
                email="s@primjer.hr",
                message="x" * 20,
                created_at=now - timedelta(days=366),
            ),
            Inquiry(type="general", name="Novi", email="n@primjer.hr", message="x" * 20),
            UserSession(token_hash="a" * 64, user_id=user_id, expires_at=now - timedelta(hours=1)),
            UserSession(token_hash="b" * 64, user_id=user_id, expires_at=now + timedelta(hours=1)),
            AuthToken(
                user_id=user_id,
                purpose="reset",
                token_hash="c" * 64,
                expires_at=now - timedelta(hours=1),
            ),
            EmailLog(to_hash="x", status="sent", created_at=now - timedelta(days=91)),
            EmailLog(to_hash="y", status="sent", created_at=now - timedelta(days=10)),
            AuditLog(action="old", created_at=now - timedelta(days=800)),
            AuditLog(action="recent", created_at=now - timedelta(days=100)),
            VehicleView(vehicle_id=active.id, date=local_today() - timedelta(days=401), count=3),
            VehicleView(vehicle_id=active.id, date=local_today(), count=3),
        ]
    )
    db.commit()
    preview = maintenance.run_all(db, dry_run=True)
    db.rollback()
    assert preview == {
        "old_inquiries": 1,
        "pending_subscribers": 0,
        "old_unsubscribed": 0,
        "archived_sold_vehicles": 1,
        "expired_sessions_tokens": 2,
        "old_email_log": 1,
        "old_audit": 1,
        "old_vehicle_views": 1,
    }
    # Dry run changed nothing.
    assert db.query(Inquiry).count() == 2 and db.get(Vehicle, old_sold.id).status == "sold"
    result = maintenance.run_all(db)
    db.commit()
    assert result == preview
    db.expire_all()
    assert db.get(Vehicle, old_sold.id).status == "archived"
    assert db.get(Vehicle, fresh_sold.id).status == "sold"
    assert [i.name for i in db.scalars(select(Inquiry))] == ["Novi"]
    assert db.query(UserSession).count() == 1 and db.query(AuthToken).count() == 0
    assert db.query(EmailLog).count() == 1 and db.query(VehicleView).count() == 1
    actions = {a.action for a in db.scalars(select(AuditLog))}
    assert "old" not in actions and "recent" in actions and "system.maintenance" in actions


def test_daily_guard_runs_once_per_day(db):
    assert maintenance.claim_daily_run(db, "2026-09-28") is True
    assert maintenance.claim_daily_run(db, "2026-09-28") is False
    assert maintenance.claim_daily_run(db, "2026-09-29") is True


def test_cli_maintenance_dry_run(db):
    from app.cli import main

    old = Inquiry(
        type="general",
        name="Stari",
        email="s@primjer.hr",
        message="x" * 20,
        created_at=utcnow() - timedelta(days=400),
    )
    db.add(old)
    db.commit()
    assert main(["maintenance", "--dry-run"]) == 0
    assert db.query(Inquiry).count() == 1
    assert main(["maintenance"]) == 0
    db.expire_all()
    assert db.query(Inquiry).count() == 0
