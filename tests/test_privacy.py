"""Data subject rights tool (phase 7)."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.database import utcnow
from app.models import (
    AuditLog,
    EmailLog,
    Inquiry,
    InquiryNote,
    Subscriber,
)
from app.security import email_hash
from app.services.newsletter import add_manual
from tests.helpers import create_user, get_csrf, login_as, make_vehicle


@pytest.fixture
def owner(client):
    user_id, _ = create_user("vlasnik@test.hr", role="owner")
    login_as(client, user_id)
    return user_id


@pytest.fixture
def person(db):
    vehicle = make_vehicle(db)
    inquiry = Inquiry(
        type="vehicle",
        vehicle_id=vehicle.id,
        name="Ime Prezime",
        email="Osoba@Primjer.hr",
        phone="+385912345678",
        message="Zanima me vozilo",
        consent_at=utcnow(),
        consent_ip="192.0.2.5",
        consent_policy_version="1.0",
    )
    other = Inquiry(type="general", name="Drugi", email="drugi@primjer.hr", message="x" * 20)
    db.add_all([inquiry, other])
    db.flush()
    db.add(InquiryNote(inquiry_id=inquiry.id, body="Nazvao"))
    add_manual(db, "osoba@primjer.hr", "obrazac u salonu")
    db.add(EmailLog(to_hash=email_hash("osoba@primjer.hr"), template="x", status="sent"))
    db.commit()
    return inquiry.id


def test_gdpr_search_and_export(client, db, owner, person):
    token = get_csrf(client, "/admin/gdpr")
    html = client.post("/admin/gdpr", data={"email": "osoba@primjer.hr", "csrf_token": token}).text
    assert "Upiti (1)" in html and "bilješki: 1" in html
    response = client.post(
        "/admin/gdpr/izvoz", data={"email": "osoba@primjer.hr", "csrf_token": token}
    )
    data = json.loads(response.content)
    assert len(data["upiti"]) == 1 and data["upiti"][0]["biljeske"][0]["tekst"] == "Nazvao"
    assert data["upiti"][0]["privola"]["verzija_politike"] == "1.0"
    assert data["newsletter"]["email"] == "osoba@primjer.hr"
    assert data["zapisi_o_slanju_emaila"] == 1
    entry = db.scalar(select(AuditLog).where(AuditLog.action == "privacy.export"))
    assert entry.details["email_hash"] == email_hash("osoba@primjer.hr")
    assert "osoba@primjer.hr" not in json.dumps(entry.details)


def test_gdpr_delete_requires_confirmation_and_erases(client, db, owner, person):
    token = get_csrf(client, "/admin/gdpr")
    client.post(
        "/admin/gdpr/obrisi",
        data={"email": "osoba@primjer.hr", "confirm": "da", "csrf_token": token},
    )
    assert db.query(Inquiry).count() == 2
    client.post(
        "/admin/gdpr/obrisi",
        data={"email": "osoba@primjer.hr", "confirm": "OBRIŠI", "csrf_token": token},
    )
    db.expire_all()
    assert [i.email for i in db.scalars(select(Inquiry))] == ["drugi@primjer.hr"]
    assert db.query(InquiryNote).count() == 0
    subscriber = db.scalar(select(Subscriber))
    assert subscriber.email is None and subscriber.status == "unsubscribed"
    assert subscriber.email_hash == email_hash("osoba@primjer.hr")
    assert db.query(EmailLog).count() == 0
    entry = db.scalar(select(AuditLog).where(AuditLog.action == "privacy.delete"))
    assert entry.details["inquiries"] == 1 and entry.details["notes"] == 1
    assert "osoba@primjer.hr" not in json.dumps(entry.details)
