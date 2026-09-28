"""Phase 5: public inquiry forms, anti-spam, dealer notification, admin mini-CRM, retention."""

from __future__ import annotations

import time
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.database import utcnow
from app.models import AuditLog, Inquiry, InquiryNote
from app.security import FORM_TS_SALT, sign_value
from app.services import turnstile
from app.services.maintenance import purge_old_inquiries
from app.utils import local_now
from tests.helpers import (
    create_user,
    csrf_from,
    eml_text,
    get_csrf,
    login_as,
    make_vehicle,
    outbox,
    read_eml,
)


def old_ts(seconds: int = 10) -> str:
    return sign_value(int(time.time()) - seconds, salt=FORM_TS_SALT)


def post_inquiry(client, vehicle=None, kind=None, **overrides):
    page = client.get(f"/vozila/{vehicle.slug}" if vehicle else "/kontakt")
    data = {
        "csrf_token": csrf_from(page.text),
        "form_ts": old_ts(),
        "type": kind or ("vehicle" if vehicle else "general"),
        "name": "Ime Prezime",
        "email": "kupac1@primjer.hr",
        "phone": "091 234 5678",
        "message": "Zanima me ovo vozilo, molim više informacija.",
        "consent": "1",
        "website": "",
    }
    if vehicle is not None:
        data["vehicle_id"] = str(vehicle.id)
    data.update(overrides)
    return client.post("/upit", data=data, follow_redirects=False)


@pytest.fixture
def vehicle(db):
    return make_vehicle(db, make_name="Volkswagen", model_name="Golf")


def test_inquiry_without_consent_is_rejected(client, db, vehicle):
    response = post_inquiry(client, vehicle, consent="")
    assert response.status_code == 400
    assert "Za slanje upita potrebna je vaša privola." in response.text
    assert 'value="Ime Prezime"' in response.text  # values kept
    assert "Volkswagen Golf Test" in response.text  # vehicle context kept
    assert db.query(Inquiry).count() == 0
    assert outbox() == []


def test_inquiry_with_consent_is_saved_and_dealer_notified(client, db, vehicle):
    response = post_inquiry(client, vehicle)
    assert response.status_code == 303
    assert response.headers["location"] == f"/vozila/{vehicle.slug}"
    inquiry = db.scalar(select(Inquiry))
    assert inquiry.type == "vehicle" and inquiry.vehicle_id == vehicle.id
    assert inquiry.email == "kupac1@primjer.hr" and inquiry.phone == "+385912345678"
    assert inquiry.consent_at is not None and inquiry.consent_ip
    assert inquiry.consent_policy_version == "1.0"
    assert inquiry.consent_user_agent is not None
    assert inquiry.status == "new"
    # Success message after redirect (PRG).
    assert (
        "Hvala, javit ćemo vam se u najkraćem roku."
        in client.get(response.headers["location"]).text
    )
    # Notification email to the dealer with Reply-To = customer.
    files = outbox()
    assert len(files) == 1
    message = read_eml(files[0])
    assert message["To"] == "mailpoduzeca@domena.com"
    assert message["Reply-To"] == "kupac1@primjer.hr"
    body = eml_text(message)
    assert "Volkswagen Golf Test" in body and "Ime Prezime" in body
    assert f"/admin/upiti/{inquiry.id}" in body


def test_honeypot_fakes_success_and_saves_nothing(client, db, vehicle):
    response = post_inquiry(client, vehicle, website="http://spam.example")
    assert response.status_code == 303
    assert db.query(Inquiry).count() == 0
    assert outbox() == []


def test_too_fast_submission_is_rejected(client, db, vehicle):
    fresh = sign_value(int(time.time()), salt=FORM_TS_SALT)
    response = post_inquiry(client, vehicle, form_ts=fresh)
    assert response.status_code == 400
    assert "prebrzo" in response.text
    response = post_inquiry(client, vehicle, form_ts="krivotvoreno")
    assert response.status_code == 400
    assert db.query(Inquiry).count() == 0


def test_rate_limit_per_ip(client, db, vehicle):
    for n in range(5):
        assert post_inquiry(client, vehicle, email=f"kupac{n}@primjer.hr").status_code == 303
    response = post_inquiry(client, vehicle, email="kupac9@primjer.hr")
    assert response.status_code == 429
    assert "previše upita" in response.text
    assert db.query(Inquiry).count() == 5


def test_rate_limit_per_email(client, db, vehicle):
    from app.security import limiter

    for _ in range(3):
        assert post_inquiry(client, vehicle).status_code == 303
    limiter._hits = {k: v for k, v in limiter._hits.items() if not k.startswith("inquiry-ip")}
    assert post_inquiry(client, vehicle).status_code == 429


def test_viewing_requires_future_date(client, db, vehicle):
    response = post_inquiry(client, vehicle, kind="viewing", preferred_date="")
    assert response.status_code == 400 and "Odaberite željeni termin" in response.text
    past = (local_now() - timedelta(days=1)).strftime("%Y-%m-%dT10:00")
    response = post_inquiry(client, vehicle, kind="viewing", preferred_date=past)
    assert response.status_code == 400 and "najranije sutra" in response.text
    future = (local_now() + timedelta(days=3)).strftime("%Y-%m-%dT10:30")
    response = post_inquiry(client, vehicle, kind="viewing", preferred_date=future)
    assert response.status_code == 303
    inquiry = db.scalar(select(Inquiry))
    assert inquiry.type == "viewing" and inquiry.preferred_date is not None


def test_inquiry_for_draft_or_missing_vehicle_rejected(client, db, vehicle):
    draft = make_vehicle(db, make_name="Volkswagen", model_name="Up", status="draft")
    page = client.get(f"/vozila/{vehicle.slug}")
    base = {
        "csrf_token": csrf_from(page.text),
        "form_ts": old_ts(),
        "type": "vehicle",
        "name": "Ime Prezime",
        "email": "a@primjer.hr",
        "message": "Poruka dovoljno duga.",
        "consent": "1",
    }
    assert client.post("/upit", data=dict(base, vehicle_id=str(draft.id))).status_code == 400
    assert client.post("/upit", data=dict(base, vehicle_id="99999")).status_code == 400
    assert db.query(Inquiry).count() == 0


def test_general_inquiry_from_contact_page(client, db):
    response = post_inquiry(client, None)
    assert response.status_code == 303 and response.headers["location"] == "/kontakt"
    inquiry = db.scalar(select(Inquiry))
    assert inquiry.type == "general" and inquiry.vehicle_id is None


def test_invalid_fields_show_errors(client, db):
    response = post_inquiry(
        client, None, email="nije-email", phone="12", message="kratko", name="X"
    )
    assert response.status_code == 400
    for text in ("ispravnu email adresu", "broj telefona", "barem 10 znakova", "Upišite ime"):
        assert text in response.text


def test_turnstile_disabled_without_key():
    assert turnstile.verify_turnstile(None, "1.2.3.4") is True


def test_turnstile_with_key_success_and_failure(monkeypatch):
    monkeypatch.setattr(turnstile.settings, "TURNSTILE_SECRET_KEY", "secret")
    calls = []

    class FakeResponse:
        def __init__(self, ok):
            self.ok = ok

        def json(self):
            return {"success": self.ok}

    def fake_post(url, data, timeout):
        calls.append((url, data))
        return FakeResponse(data["response"] == "dobar-token")

    monkeypatch.setattr(turnstile.httpx, "post", fake_post)
    assert turnstile.verify_turnstile("dobar-token", "1.2.3.4") is True
    assert turnstile.verify_turnstile("los-token", "1.2.3.4") is False
    assert turnstile.verify_turnstile("", "1.2.3.4") is False
    assert calls[0][0] == turnstile.VERIFY_URL and calls[0][1]["remoteip"] == "1.2.3.4"


def test_turnstile_failure_blocks_inquiry(client, db, vehicle, monkeypatch):
    monkeypatch.setattr(turnstile.settings, "TURNSTILE_SECRET_KEY", "secret")

    class Fail:
        def json(self):
            return {"success": False}

    monkeypatch.setattr(turnstile.httpx, "post", lambda *a, **k: Fail())
    response = post_inquiry(client, vehicle, **{"cf-turnstile-response": "x"})
    assert response.status_code == 400
    assert db.query(Inquiry).count() == 0


# ---------------------------------------------------------------------------
# Admin CRM
# ---------------------------------------------------------------------------
@pytest.fixture
def inquiry(client, db, vehicle):
    post_inquiry(client, vehicle)
    client.cookies.clear()
    return db.scalar(select(Inquiry))


def test_admin_inbox_and_detail(client, db, inquiry):
    user_id, _ = create_user("prodavac@test.hr", role="salesperson")
    login_as(client, user_id)
    html = client.get("/admin/upiti").text
    assert "Ime Prezime" in html and "Volkswagen Golf Test" in html
    assert 'class="nav-count"' in html  # new inquiries badge in the sidebar
    html = client.get("/admin/upiti?q=kupac1").text
    assert "Ime Prezime" in html
    assert "Ime Prezime" not in client.get("/admin/upiti?status=closed").text.split("<tbody>")[-1]
    detail = client.get(f"/admin/upiti/{inquiry.id}")
    assert detail.status_code == 200
    assert "mailto:kupac1@primjer.hr?subject=Va%C5%A1%20upit" in detail.text
    assert "testclient" not in detail.text  # raw consent IP is never shown


def test_admin_status_assign_and_notes(client, db, inquiry):
    owner_id, _ = create_user("vlasnik@test.hr", role="owner")
    seller_id, _ = create_user("prodavac@test.hr", role="salesperson", name="Prodavač 1")
    login_as(client, owner_id)
    token = get_csrf(client, f"/admin/upiti/{inquiry.id}")
    client.post(
        f"/admin/upiti/{inquiry.id}/status", data={"status": "contacted", "csrf_token": token}
    )
    client.post(
        f"/admin/upiti/{inquiry.id}/dodjela",
        data={"assigned_to": str(seller_id), "csrf_token": token},
    )
    client.post(
        f"/admin/upiti/{inquiry.id}/biljeske", data={"body": "Nazvao kupca.", "csrf_token": token}
    )
    db.expire_all()
    fresh = db.get(Inquiry, inquiry.id)
    assert fresh.status == "contacted" and fresh.contacted_at is not None
    assert fresh.assigned_to == seller_id
    assert [n.body for n in fresh.notes] == ["Nazvao kupca."]
    # Own note can be deleted within 15 minutes; someone else's cannot.
    note = fresh.notes[0]
    login_as(client, seller_id)
    token = get_csrf(client, f"/admin/upiti/{inquiry.id}")
    response = client.post(
        f"/admin/upiti/{inquiry.id}/biljeske/{note.id}/obrisi", data={"csrf_token": token}
    )
    assert response.status_code == 403
    login_as(client, owner_id)
    token = get_csrf(client, f"/admin/upiti/{inquiry.id}")
    client.post(f"/admin/upiti/{inquiry.id}/biljeske/{note.id}/obrisi", data={"csrf_token": token})
    assert db.query(InquiryNote).count() == 0
    # Closing and reopening.
    client.post(f"/admin/upiti/{inquiry.id}/status", data={"status": "closed", "csrf_token": token})
    db.expire_all()
    assert db.get(Inquiry, inquiry.id).closed_at is not None
    # Audit entries contain no customer data.
    entries = list(db.scalars(select(AuditLog).where(AuditLog.action.like("inquiry.%"))))
    assert {e.action for e in entries} >= {"inquiry.status", "inquiry.assign", "inquiry.note"}
    for entry in entries:
        assert "kupac1@primjer.hr" not in str(entry.details)
        assert "Ime Prezime" not in str(entry.details)


def test_csv_export_has_bom_and_semicolons(client, db, inquiry):
    owner_id, _ = create_user("vlasnik@test.hr", role="owner")
    login_as(client, owner_id)
    response = client.get("/admin/upiti/izvoz.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.content.startswith(b"\xef\xbb\xbf")
    text = response.content.decode("utf-8-sig")
    header = text.splitlines()[0]
    assert header.startswith("ID;Primljeno;Tip;Status;Ime i prezime;Email")
    assert "kupac1@primjer.hr" in text and "Volkswagen Golf Test" in text
    assert db.scalar(select(AuditLog).where(AuditLog.action == "inquiry.export"))


def test_salesperson_cannot_delete_or_export(client, db, inquiry):
    seller_id, _ = create_user("prodavac@test.hr", role="salesperson")
    login_as(client, seller_id)
    token = get_csrf(client, f"/admin/upiti/{inquiry.id}")
    assert (
        client.post(f"/admin/upiti/{inquiry.id}/obrisi", data={"csrf_token": token}).status_code
        == 403
    )
    assert client.get("/admin/upiti/izvoz.csv").status_code == 403
    assert db.get(Inquiry, inquiry.id) is not None


def test_owner_can_delete_inquiry(client, db, inquiry):
    owner_id, _ = create_user("vlasnik@test.hr", role="owner")
    login_as(client, owner_id)
    token = get_csrf(client, f"/admin/upiti/{inquiry.id}")
    inquiry_id = inquiry.id
    client.post(f"/admin/upiti/{inquiry_id}/obrisi", data={"csrf_token": token})
    db.expire_all()
    assert db.get(Inquiry, inquiry_id) is None
    assert db.scalar(select(AuditLog).where(AuditLog.action == "inquiry.delete"))


def test_dashboard_shows_new_inquiries(client, db, inquiry):
    owner_id, _ = create_user("vlasnik@test.hr", role="owner")
    login_as(client, owner_id)
    html = client.get("/admin").text
    assert "Novi upiti" in html


def test_purge_old_inquiries_only_older_than_retention(db, vehicle):
    old = Inquiry(
        type="general",
        name="Stari",
        email="s@primjer.hr",
        message="x" * 20,
        created_at=utcnow() - timedelta(days=400),
    )
    recent = Inquiry(
        type="general",
        name="Novi",
        email="n@primjer.hr",
        message="x" * 20,
        created_at=utcnow() - timedelta(days=10),
    )
    db.add_all([old, recent])
    db.flush()
    db.add(InquiryNote(inquiry_id=old.id, body="bilješka"))
    db.commit()
    assert purge_old_inquiries(db, dry_run=True) == 1
    db.rollback()
    assert db.query(Inquiry).count() == 2
    assert purge_old_inquiries(db) == 1
    db.commit()
    names = [i.name for i in db.scalars(select(Inquiry))]
    assert names == ["Novi"]
    assert db.query(InquiryNote).count() == 0
