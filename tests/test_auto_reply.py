"""Paket Standard: automatski odgovor kupcu, .ics za termin pregleda, potvrda termina."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog, Inquiry
from app.services.calendar import event_uid, parse_ics
from app.services.site import get_site, invalidate_site_cache, set_values
from app.utils import LOCAL_TZ, local_now
from tests.helpers import create_user, eml_text, get_csrf, login_as, make_vehicle, outbox, read_eml
from tests.test_inquiries import post_inquiry
from tests.test_settings import _settings_form


@pytest.fixture
def vehicle(db):
    return make_vehicle(db, make_name="Volkswagen", model_name="Golf")


def messages_to(address: str):
    return [m for m in (read_eml(p) for p in outbox()) if m["To"] == address]


def ics_parts(message) -> list[bytes]:
    return [
        part.get_content().encode("utf-8")
        if isinstance(part.get_content(), str)
        else part.get_content()
        for part in message.iter_attachments()
        if part.get_content_type() == "text/calendar"
    ]


def future_local(days: int = 3, hour: int = 10) -> datetime:
    return (local_now() + timedelta(days=days)).replace(
        hour=hour, minute=30, second=0, microsecond=0
    )


def test_auto_reply_only_when_enabled_and_in_plan(client, db, vehicle, set_plan):
    set_plan("osnovni")
    post_inquiry(client, vehicle)
    assert messages_to("kupac1@primjer.hr") == []  # not in the plan

    set_plan("standard")
    set_values(db, {"auto_reply_enabled": "false"})
    db.commit()
    invalidate_site_cache()
    post_inquiry(client, vehicle, email="kupac2@primjer.hr")
    assert messages_to("kupac2@primjer.hr") == []  # switched off in settings

    set_values(db, {"auto_reply_enabled": "true"})
    db.commit()
    invalidate_site_cache()
    post_inquiry(client, vehicle, email="kupac3@primjer.hr")
    [message] = messages_to("kupac3@primjer.hr")
    site = get_site()
    text = eml_text(message)
    assert "Poštovani Ime Prezime" in text
    assert vehicle.title in text and site["working_hours"] in text
    assert site["company_name"] in message["Subject"]
    assert "odjav" not in text.lower() and "List-Unsubscribe" not in message  # not marketing
    assert ics_parts(message) == []  # an ordinary inquiry gets no calendar file


def test_unknown_placeholder_rejected_and_locked_in_basic(client, db, set_plan):
    owner_id, _ = create_user("vlasnik@test.hr", role="owner")
    login_as(client, owner_id)
    set_plan("standard")
    response = _settings_form(client, auto_reply_text="Hvala {ime}, {nepoznato}")
    assert response.status_code == 400 and "{nepoznato}" in response.text
    response = _settings_form(client, auto_reply_text="Hvala {ime} na upitu za {vozilo}.")
    assert response.status_code == 303
    assert get_site()["auto_reply_text"] == "Hvala {ime} na upitu za {vozilo}."

    set_plan("osnovni")  # locked field: posted value is ignored, stored one kept
    _settings_form(client, auto_reply_text="Drugi tekst {ime}")
    assert get_site()["auto_reply_text"] == "Hvala {ime} na upitu za {vozilo}."


def test_viewing_ics_for_customer_and_dealer(client, db, vehicle, set_plan):
    set_plan("standard")
    start_local = future_local()
    post_inquiry(
        client, vehicle, kind="viewing", preferred_date=start_local.strftime("%Y-%m-%dT%H:%M")
    )
    inquiry = db.scalar(select(Inquiry))
    site = get_site()
    [customer] = messages_to("kupac1@primjer.hr")
    [ics] = ics_parts(customer)
    event = parse_ics(ics)
    assert event["DTSTART"] == start_local.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    assert event["UID"] == event_uid(inquiry.id)
    assert event["STATUS"] == "TENTATIVE" and event["METHOD"] == "PUBLISH"
    assert event["SUMMARY"] == f"Pregled vozila: {vehicle.title}"
    assert event["LOCATION"] == site["company_address"].replace(",", "\\,")
    assert event["TRIGGER"] == "-PT60M"
    assert f"/vozila/{vehicle.slug}" in ics.decode("utf-8").replace("\r\n ", "")
    assert b"\r\n" in ics and ics.endswith(b"END:VCALENDAR\r\n")

    dealer = [m for m in (read_eml(p) for p in outbox()) if m["To"] != "kupac1@primjer.hr"]
    assert len(dealer) == 1 and len(ics_parts(dealer[0])) == 1
    # file backend also drops the .ics next to the .eml
    assert list(outbox()[0].parent.glob("*_pregled-vozila.ics"))


def test_no_calendar_in_basic_plan(client, db, vehicle, set_plan):
    set_plan("osnovni")
    post_inquiry(
        client, vehicle, kind="viewing", preferred_date=future_local().strftime("%Y-%m-%dT%H:%M")
    )
    for message in (read_eml(p) for p in outbox()):
        assert ics_parts(message) == []


def test_confirm_viewing_same_uid_and_status(client, db, vehicle, set_plan):
    set_plan("standard")
    post_inquiry(
        client, vehicle, kind="viewing", preferred_date=future_local().strftime("%Y-%m-%dT%H:%M")
    )
    client.cookies.clear()
    inquiry = db.scalar(select(Inquiry))
    [first] = messages_to("kupac1@primjer.hr")
    tentative = parse_ics(ics_parts(first)[0])

    seller_id, _ = create_user("prodavac@test.hr", role="salesperson")
    login_as(client, seller_id)
    detail = client.get(f"/admin/upiti/{inquiry.id}").text
    assert "Potvrdi termin" in detail
    prefilled = inquiry.preferred_date.replace(tzinfo=UTC).astimezone(LOCAL_TZ)
    assert f'value="{prefilled.strftime("%Y-%m-%dT%H:%M")}"' in detail

    token = get_csrf(client, f"/admin/upiti/{inquiry.id}")
    confirmed_local = future_local(days=4, hour=14)
    response = client.post(
        f"/admin/upiti/{inquiry.id}/termin",
        data={"scheduled_at": confirmed_local.strftime("%Y-%m-%dT%H:%M"), "csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code == 303
    db.expire_all()
    inquiry = db.get(Inquiry, inquiry.id)
    assert inquiry.status == "contacted"
    assert inquiry.scheduled_at == confirmed_local.astimezone(UTC).replace(tzinfo=None)
    entry = db.scalar(select(AuditLog).where(AuditLog.action == "inquiry.schedule"))
    assert entry is not None and "kupac1" not in str(entry.details)

    confirmation = messages_to("kupac1@primjer.hr")[-1]
    assert "Potvrđen termin" in confirmation["Subject"]
    event = parse_ics(ics_parts(confirmation)[0])
    assert event["UID"] == tentative["UID"]
    assert event["STATUS"] == "CONFIRMED"
    assert int(event["SEQUENCE"]) > int(tentative["SEQUENCE"])
    assert event["DTSTART"] == confirmed_local.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def test_confirm_viewing_validation_and_lock(client, db, vehicle, set_plan):
    set_plan("standard")
    post_inquiry(
        client, vehicle, kind="viewing", preferred_date=future_local().strftime("%Y-%m-%dT%H:%M")
    )
    post_inquiry(client, vehicle, email="drugi@primjer.hr")
    client.cookies.clear()
    viewing, ordinary = db.scalars(select(Inquiry).order_by(Inquiry.id)).all()
    seller_id, _ = create_user("prodavac@test.hr", role="salesperson")
    login_as(client, seller_id)
    token = get_csrf(client, f"/admin/upiti/{viewing.id}")
    past = (local_now() - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
    response = client.post(
        f"/admin/upiti/{viewing.id}/termin", data={"scheduled_at": past, "csrf_token": token}
    )
    assert "Termin mora biti u budućnosti" in response.text
    db.expire_all()
    assert db.get(Inquiry, viewing.id).scheduled_at is None

    later = future_local().strftime("%Y-%m-%dT%H:%M")
    response = client.post(
        f"/admin/upiti/{ordinary.id}/termin", data={"scheduled_at": later, "csrf_token": token}
    )
    assert response.status_code == 404  # only viewing requests have a schedule

    set_plan("osnovni")
    assert "Potvrdi termin" not in client.get(f"/admin/upiti/{viewing.id}").text
    response = client.post(
        f"/admin/upiti/{viewing.id}/termin", data={"scheduled_at": later, "csrf_token": token}
    )
    assert response.status_code == 403
