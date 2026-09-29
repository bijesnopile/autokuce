"""Phase 6: newsletter double opt-in, anonymising unsubscribe, campaigns, retention."""

from __future__ import annotations

import time
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.database import utcnow
from app.models import AuditLog, Campaign, CampaignDelivery, Subscriber
from app.security import FORM_TS_SALT, email_hash, sign_value
from app.services import newsletter as nl
from tests.helpers import (
    create_user,
    csrf_from,
    eml_text,
    find_link,
    get_csrf,
    login_as,
    make_vehicle,
    outbox,
    read_eml,
)


def old_ts() -> str:
    return sign_value(int(time.time()) - 10, salt=FORM_TS_SALT)


def signup(client, email="citatelj@primjer.hr", consent="1", source="footer", **extra):
    token = csrf_from(client.get("/").text)
    data = {
        "csrf_token": token,
        "form_ts": old_ts(),
        "email": email,
        "consent": consent,
        "source": source,
        "website": "",
    }
    data.update(extra)
    response = client.post(
        "/newsletter/prijava",
        data=data,
        headers={"Referer": "http://testserver/"},
        follow_redirects=False,
    )
    return response


def confirm_link_from_outbox() -> str:
    message = read_eml(outbox()[-1])
    return find_link(eml_text(message), "http://testserver/newsletter/potvrda/").replace(
        "http://testserver", ""
    )


def test_signup_without_consent_rejected(client, db):
    response = signup(client, consent="")
    assert response.status_code == 303
    assert "potrebna je vaša privola" in client.get("/").text
    assert db.query(Subscriber).count() == 0
    assert outbox() == []


def test_double_opt_in_flow(client, db):
    response = signup(client, source="vehicle")
    assert response.status_code == 303
    assert nl.NEUTRAL_MESSAGE in client.get("/").text
    subscriber = db.scalar(select(Subscriber))
    assert subscriber.status == "pending" and subscriber.source == "vehicle"
    assert subscriber.consent_at and subscriber.consent_policy_version == "1.0"
    assert subscriber.email_hash == email_hash("citatelj@primjer.hr")
    message = read_eml(outbox()[0])
    assert message["To"] == "citatelj@primjer.hr"
    assert "Potvrdi prijavu" in eml_text(message)
    link = confirm_link_from_outbox()
    page = client.get(link)
    assert page.status_code == 200 and "Prijava je potvrđena" in page.text
    db.expire_all()
    subscriber = db.scalar(select(Subscriber))
    assert subscriber.status == "confirmed" and subscriber.confirmed_at is not None
    assert subscriber.unsubscribe_token_hash is not None
    # The confirmation token is single use.
    assert client.get(link).status_code == 400


def test_expired_confirmation_token_rejected(client, db):
    signup(client)
    subscriber = db.scalar(select(Subscriber))
    subscriber.confirm_sent_at = utcnow() - timedelta(days=8)
    db.commit()
    response = client.get(confirm_link_from_outbox())
    assert response.status_code == 400 and "nije valjana" in response.text


def test_resubscribe_confirmed_reveals_nothing_and_sends_nothing(client, db):
    signup(client)
    client.get(confirm_link_from_outbox())
    emails_before = len(outbox())
    signup(client)
    assert nl.NEUTRAL_MESSAGE in client.get("/").text
    assert len(outbox()) == emails_before
    assert db.query(Subscriber).count() == 1


def test_pending_resend_limited(client, db):
    signup(client)
    signup(client)  # within 10 min -> no second email
    assert len(outbox()) == 1
    subscriber = db.scalar(select(Subscriber))
    subscriber.confirm_sent_at = utcnow() - timedelta(minutes=11)
    db.commit()
    signup(client)
    assert len(outbox()) == 2


def test_unsubscribe_anonymises_and_resubscribe_needs_new_opt_in(client, db):
    signup(client)
    client.get(confirm_link_from_outbox())
    db.expire_all()
    subscriber = db.scalar(select(Subscriber))
    token = nl.unsubscribe_token(subscriber)
    page = client.get(f"/newsletter/odjava/{token}")
    assert "Da, odjavi me" in page.text
    response = client.post(f"/newsletter/odjava/{token}")  # one-click POST, no CSRF needed
    assert response.status_code == 200 and "Odjavljeni ste" in response.text
    db.expire_all()
    subscriber = db.scalar(select(Subscriber))
    assert subscriber.status == "unsubscribed" and subscriber.email is None
    assert subscriber.email_hash == email_hash("citatelj@primjer.hr")
    assert subscriber.unsubscribe_token_hash is None and subscriber.confirm_token_hash is None
    # The old token no longer works.
    assert client.get(f"/newsletter/odjava/{token}?potvrdi=1").status_code == 400
    # Re-subscribing goes through a new double opt-in.
    signup(client)
    db.expire_all()
    subscriber = db.scalar(select(Subscriber))
    assert subscriber.status == "pending" and subscriber.email == "citatelj@primjer.hr"
    client.get(confirm_link_from_outbox())
    db.expire_all()
    assert db.scalar(select(Subscriber)).status == "confirmed"


def test_one_click_get_unsubscribe(client, db):
    subscriber, _ = nl.add_manual(db, "a@primjer.hr", "obrazac u salonu 2026")
    db.commit()
    response = client.get(f"/newsletter/odjava/{nl.unsubscribe_token(subscriber)}?potvrdi=1")
    assert "Odjavljeni ste" in response.text
    db.expire_all()
    assert db.get(Subscriber, subscriber.id).email is None


def test_honeypot_and_rate_limit(client, db):
    signup(client, website="spam")
    assert db.query(Subscriber).count() == 0
    for n in range(5):
        signup(client, email=f"a{n}@primjer.hr")
    signup(client, email="a9@primjer.hr")
    assert db.query(Subscriber).count() == 5


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------
def test_manual_add_requires_note(client, db):
    owner_id, _ = create_user("vlasnik@test.hr", role="owner")
    login_as(client, owner_id)
    token = get_csrf(client, "/admin/newsletter/pretplatnici")
    client.post(
        "/admin/newsletter/pretplatnici/novi",
        data={"email": "rucno@primjer.hr", "manual_consent_note": "", "csrf_token": token},
    )
    assert db.query(Subscriber).count() == 0
    client.post(
        "/admin/newsletter/pretplatnici/novi",
        data={
            "email": "rucno@primjer.hr",
            "csrf_token": token,
            "manual_consent_note": "papirnati obrazac u salonu, 12.09.2026.",
        },
    )
    subscriber = db.scalar(select(Subscriber))
    assert subscriber.status == "confirmed" and subscriber.source == "manual"
    assert "papirnati obrazac" in subscriber.manual_consent_note
    html = client.get("/admin/newsletter/pretplatnici").text
    assert "ručni unos" in html
    entry = db.scalar(select(AuditLog).where(AuditLog.action == "newsletter.manual_add"))
    assert "rucno@primjer.hr" not in str(entry.details)


def test_salesperson_read_only(client, db):
    seller_id, _ = create_user("prodavac@test.hr", role="salesperson")
    login_as(client, seller_id)
    assert client.get("/admin/newsletter/pretplatnici").status_code == 200
    assert client.get("/admin/newsletter/kampanje").status_code == 200
    token = get_csrf(client, "/admin/newsletter/kampanje")
    assert client.get("/admin/newsletter/kampanje/nova").status_code == 403
    response = client.post(
        "/admin/newsletter/kampanje/nova",
        data={"subject": "Test", "body_html": "<p>x</p>", "csrf_token": token},
    )
    assert response.status_code == 403
    campaign = Campaign(subject="Skica", body_html="<p>Lorem ipsum dolor sit</p>")
    db.add(campaign)
    db.commit()
    response = client.post(
        f"/admin/newsletter/kampanje/{campaign.id}/posalji", data={"csrf_token": token}
    )
    assert response.status_code == 403


def test_campaign_html_is_sanitized():
    dirty = (
        '<p onclick="x()">Pozdrav <script>alert(1)</script></p>'
        '<img src="http://evil.example/track.gif" alt="t">'
        '<img src="http://testserver/media/vehicles/1/a_400.webp" alt="ok">'
        '<p style="background:url(http://evil.example/x)">stil</p>'
    )
    clean = nl.clean_campaign_html(dirty)
    assert "<script" not in clean and "onclick" not in clean
    assert "evil.example" not in clean
    assert 'src="http://testserver/media/vehicles/1/a_400.webp"' in clean


@pytest.fixture
def subscribers(db):
    confirmed = []
    for n in range(3):
        sub, _ = nl.add_manual(db, f"potvrden{n}@primjer.hr", "obrazac u salonu")
        confirmed.append(sub)
    pending = Subscriber(
        email="ceka@primjer.hr", email_hash=email_hash("ceka@primjer.hr"), status="pending"
    )
    gone = Subscriber(email=None, email_hash=email_hash("gone@primjer.hr"), status="unsubscribed")
    db.add_all([pending, gone])
    db.commit()
    return confirmed


def test_campaign_sent_only_to_confirmed_once_with_unsubscribe(client, db, subscribers):
    owner_id, _ = create_user("vlasnik@test.hr", role="owner")
    vehicle = make_vehicle(db)
    login_as(client, owner_id)
    token = get_csrf(client, "/admin/newsletter/kampanje/nova")
    card = nl.vehicle_card_html(vehicle)
    response = client.post(
        "/admin/newsletter/kampanje/nova",
        data={
            "subject": "Nova vozila u ponudi",
            "body_html": f"<p>Lorem ipsum dolor sit amet, nova vozila.</p>{card}",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    campaign = db.scalar(select(Campaign))
    assert vehicle.title in campaign.body_html
    page = client.get(f"/admin/newsletter/kampanje/{campaign.id}")
    assert "srcdoc=" in page.text and "Pošalji svima potvrđenima (3)" in page.text
    # Test email to the logged-in user.
    client.post(f"/admin/newsletter/kampanje/{campaign.id}/test", data={"csrf_token": token})
    assert read_eml(outbox()[-1])["To"] == "vlasnik@test.hr"
    before = set(outbox())
    client.post(f"/admin/newsletter/kampanje/{campaign.id}/posalji", data={"csrf_token": token})
    new = [read_eml(p) for p in sorted(set(outbox()) - before)]
    assert sorted(m["To"] for m in new) == [f"potvrden{n}@primjer.hr" for n in range(3)]
    for message in new:
        assert message["List-Unsubscribe"].startswith("<http://testserver/newsletter/odjava/")
        assert message["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
        text = eml_text(message)
        assert "Odjava jednim klikom" in text and "IME PODUZEĆA" in text
    db.expire_all()
    campaign = db.get(Campaign, campaign.id)
    assert campaign.status == "sent" and campaign.recipients_count == 3
    assert db.query(CampaignDelivery).filter_by(status="sent").count() == 3
    # Running the sender again does not duplicate anything (idempotent).
    result = nl.send_campaign(campaign.id)
    assert result == {"sent": 0, "failed": 0, "skipped": 3}
    assert len(set(outbox()) - before) == 3
    # The unsubscribe link from a campaign email works.
    link = message["List-Unsubscribe"].strip("<>")
    assert "Odjavljeni ste" in client.get(link.replace("http://testserver", "")).text
    assert db.scalar(select(AuditLog).where(AuditLog.action == "campaign.send"))


def test_failed_deliveries_can_be_retried(client, db, subscribers, monkeypatch):
    from app.services import email as email_service

    campaign = Campaign(subject="Ponuda", body_html="<p>Lorem ipsum dolor sit amet</p>")
    db.add(campaign)
    db.commit()
    real_send = email_service._send_file

    def flaky(message, subject, attachments=None):
        if message["To"] == "potvrden1@primjer.hr":
            raise RuntimeError("SMTP pao")
        return real_send(message, subject, attachments)

    monkeypatch.setattr(email_service, "_send_file", flaky)
    result = nl.send_campaign(campaign.id)
    assert result["sent"] == 2 and result["failed"] == 1
    monkeypatch.setattr(email_service, "_send_file", real_send)
    result = nl.send_campaign(campaign.id, only_failed=True)
    assert result["sent"] == 1 and result["skipped"] == 2
    assert db.query(CampaignDelivery).filter_by(status="failed").count() == 0


def test_purge_pending_and_old_unsubscribed(db):
    now = utcnow()
    db.add_all(
        [
            Subscriber(
                email="stari@primjer.hr",
                email_hash=email_hash("stari@primjer.hr"),
                status="pending",
                confirm_sent_at=now - timedelta(days=8),
            ),
            Subscriber(
                email="novi@primjer.hr",
                email_hash=email_hash("novi@primjer.hr"),
                status="pending",
                confirm_sent_at=now - timedelta(days=2),
            ),
            Subscriber(
                email=None,
                email_hash=email_hash("x@primjer.hr"),
                status="unsubscribed",
                unsubscribed_at=now - timedelta(days=3 * 365 + 5),
            ),
            Subscriber(
                email=None,
                email_hash=email_hash("y@primjer.hr"),
                status="unsubscribed",
                unsubscribed_at=now - timedelta(days=30),
            ),
        ]
    )
    db.commit()
    assert nl.purge_pending_subscribers(db) == 1
    assert nl.purge_old_unsubscribed(db) == 1
    db.commit()
    remaining = {s.email_hash for s in db.scalars(select(Subscriber))}
    assert remaining == {email_hash("novi@primjer.hr"), email_hash("y@primjer.hr")}


def test_subscribers_csv_export(client, db, subscribers):
    owner_id, _ = create_user("vlasnik@test.hr", role="owner")
    login_as(client, owner_id)
    response = client.get("/admin/newsletter/pretplatnici/izvoz.csv")
    assert response.content.startswith(b"\xef\xbb\xbf")
    text = response.content.decode("utf-8-sig")
    assert text.count("@primjer.hr") == 3 and "ceka@" not in text
    assert db.scalar(select(AuditLog).where(AuditLog.action == "newsletter.export"))
