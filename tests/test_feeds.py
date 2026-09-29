"""Paket Standard: feedovi vozila za portale (/feed/{portal}.{fmt}?token=...) i /admin/feed."""

from __future__ import annotations

import csv
import gzip
import io
from xml.etree import ElementTree as ET

import pytest
from sqlalchemy import select

from app.models import AuditLog, FeedAccess
from app.services import feed_formats as formats
from app.services import feeds
from app.services.site import invalidate_site_cache, set_values
from tests.helpers import create_user, get_csrf, login_as, make_vehicle

VIN = "WVWZZZ1KZAW000001"


@pytest.fixture(autouse=True)
def _fresh_cache():
    feeds.clear_cache()
    yield
    feeds.clear_cache()


@pytest.fixture
def owner(client, set_plan):
    set_plan("standard")
    user_id, _ = create_user("vlasnik@test.hr", role="owner")
    login_as(client, user_id)
    return user_id


@pytest.fixture
def fleet(db):
    active = make_vehicle(
        db,
        make_name="Volkswagen",
        model_name="Golf",
        description="<p>Prvi <strong>vlasnik</strong> &amp; servisna</p><ul><li>Klima</li></ul>",
    )
    reserved = make_vehicle(db, make_name="Škoda", model_name="Octavia", status="reserved")
    draft = make_vehicle(db, make_name="Audi", model_name="A4", status="draft")
    sold = make_vehicle(db, make_name="BMW", model_name="320d", status="sold")
    return {"active": active, "reserved": reserved, "draft": draft, "sold": sold}


def feed_url(db, portal="meta", fmt="xml"):
    return f"/feed/{portal}.{fmt}?token={feeds.get_token(db, create=True)}"


def all_urls():
    for code, meta in formats.PORTALS.items():
        for fmt in meta["formats"]:
            yield code, fmt


def test_token_required_and_checked(client, db, fleet, set_plan):
    set_plan("standard")
    token = feeds.get_token(db, create=True)
    assert len(token) >= 32
    assert client.get("/feed/meta.xml").status_code == 404
    assert client.get("/feed/meta.xml?token=krivi").status_code == 404
    assert client.get(f"/feed/nepostoji.xml?token={token}").status_code == 404
    assert client.get(f"/feed/meta.pdf?token={token}").status_code == 404
    response = client.get(f"/feed/meta.xml?token={token}")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, max-age=300"
    assert "noindex" in response.headers["x-robots-tag"]


def test_every_feed_is_valid_and_contains_only_active_and_reserved(client, db, fleet, set_plan):
    set_plan("standard")
    for code, fmt in all_urls():
        response = client.get(feed_url(db, code, fmt))
        assert response.status_code == 200, (code, fmt)
        body = response.content.decode("utf-8")
        if fmt == "xml":
            ET.fromstring(response.content)  # well-formed
        else:
            delimiter = formats.PORTALS[code]["csv_delimiter"]
            header = next(csv.reader(io.StringIO(body), delimiter=delimiter))
            assert header == formats.PORTALS[code]["csv_header"], code
        for key in ("active", "reserved"):
            assert f"/vozila/{fleet[key].slug}" in body, (code, key)
        for key in ("draft", "sold"):
            assert f"/vozila/{fleet[key].slug}" not in body, (code, key)
        assert VIN not in body, code  # VIN excluded by default
        assert "<strong>" not in body and "&lt;strong" not in body, code  # plain text
        assert "Prvi vlasnik & servisna" in body or "Prvi vlasnik &amp; servisna" in body, code


def test_vin_only_when_enabled(client, db, fleet, set_plan):
    set_plan("standard")
    set_values(db, {"feed_include_vin": "true"})
    db.commit()
    invalidate_site_cache()
    assert VIN in client.get(feed_url(db, "meta", "xml")).text


def test_images_are_absolute_1600(db, fleet, set_plan):
    from app.models import VehicleImage

    set_plan("standard")
    vehicle = fleet["active"]
    db.add(VehicleImage(vehicle_id=vehicle.id, file_key="vozila/abc", sort_order=0, alt=""))
    db.commit()
    db.refresh(vehicle)
    data = feeds.record(vehicle, {"company_name": "X"})
    assert data["images"] == ["http://testserver/media/vozila/abc_1600.webp"]


def test_plain_text_strips_html():
    text = feeds.plain_text(
        "<p>Jedan&nbsp;<em>dva</em></p><ul><li>A</li><li>B</li></ul><p>x<br>y</p>"
    )
    assert "<" not in text and "&nbsp;" not in text
    assert text.splitlines()[0] == "Jedan dva"
    assert "- A" in text and "- B" in text


def test_feed_is_cached_for_five_minutes(client, db, fleet, set_plan):
    set_plan("standard")
    url = feed_url(db)
    first = client.get(url).text
    make_vehicle(db, make_name="Kia", model_name="Ceed")
    assert client.get(url).text == first  # served from cache
    feeds.clear_cache()
    assert "Kia Ceed" in client.get(url).text


def test_gzip_and_access_log(client, db, fleet, set_plan):
    set_plan("standard")
    response = client.get(feed_url(db), headers={"Accept-Encoding": "gzip"})
    assert response.headers["content-encoding"] == "gzip"
    assert b"<?xml" in response.content  # httpx decodes transparently
    raw = feeds.gzip_body(b"abc")
    assert gzip.decompress(raw) == b"abc"
    row = db.get(FeedAccess, "meta")
    assert row is not None and row.count == 1 and row.last_format == "xml"


def test_validation_lists_missing_required_fields(db, fleet, set_plan):
    set_plan("standard")
    vehicle = fleet["active"]
    vehicle.fuel = None
    db.commit()
    problems = formats.validate(db)
    item = next(p for p in problems if p["vehicle"].id == vehicle.id)
    assert any(field == "Gorivo" for field, _portals in item["missing"])
    assert all(p["vehicle"].status in ("active", "reserved") for p in problems)


def test_admin_page_token_regenerate_and_vin_setting(client, db, fleet, owner):
    page = client.get("/admin/feed")
    assert page.status_code == 200
    token = feeds.get_token(db)
    assert token and f"/feed/meta.xml?token={token}" in page.text
    assert "Provjera podataka" in page.text
    preview = client.get("/admin/feed/pregled/meta.xml")
    assert preview.status_code == 200 and preview.headers["cache-control"] == "no-store"
    assert db.get(FeedAccess, "meta") is None  # preview is not a portal download

    csrf = get_csrf(client, "/admin/feed")
    client.post("/admin/feed/token", data={"csrf_token": csrf})
    db.expire_all()
    new_token = feeds.get_token(db)
    assert new_token != token
    client.cookies.clear()
    assert client.get(f"/feed/meta.xml?token={token}").status_code == 404
    assert client.get(f"/feed/meta.xml?token={new_token}").status_code == 200
    login_as(client, owner)
    csrf = get_csrf(client, "/admin/feed")
    response = client.post(
        "/admin/feed/postavke",
        data={"csrf_token": csrf, "feed_include_vin": "1", "feed_latitude": "sjever"},
    )
    assert "decimalne brojeve" in response.text
    client.post(
        "/admin/feed/postavke",
        data={
            "csrf_token": csrf,
            "feed_include_vin": "1",
            "feed_region": "Grad Zagreb",
            "feed_latitude": "45,815",
            "feed_longitude": "15.9819",
        },
    )
    invalidate_site_cache()
    actions = {a for a in db.scalars(select(AuditLog.action))}
    assert {"feed.token", "feed.settings"} <= actions


def test_salesperson_has_no_access(client, db, set_plan):
    set_plan("standard")
    user_id, _ = create_user("prodavac@test.hr", role="salesperson")
    login_as(client, user_id)
    assert client.get("/admin/feed").status_code == 403


def test_locked_in_basic_plan(client, db, fleet, set_plan):
    set_plan("standard")
    url = feed_url(db)
    set_plan("osnovni")
    assert client.get(url).status_code == 404
    user_id, _ = create_user("vlasnik@test.hr", role="owner")
    login_as(client, user_id)
    response = client.get("/admin/feed")
    assert response.status_code == 403 and "paketu Standard" in response.text


def test_meta_feed_follows_reference(client, db, fleet, set_plan):
    set_plan("standard")
    set_values(
        db, {"feed_region": "Grad Zagreb", "feed_latitude": "45.815", "feed_longitude": "15.98"}
    )
    db.commit()
    invalidate_site_cache()
    root = ET.fromstring(client.get(feed_url(db, "meta", "xml")).content)
    assert root.tag == "listings"
    listings = {item.findtext("vehicle_id"): item for item in root.iter("listing")}
    golf = listings[str(fleet["active"].id)]
    assert golf.findtext("price") == "15000 EUR"
    assert golf.findtext("mileage/unit") == "KM" and golf.findtext("mileage/value") == "120000"
    assert golf.findtext("fuel_type") == "DIESEL" and golf.findtext("transmission") == "Manual"
    assert golf.findtext("body_style") == "WAGON" and golf.findtext("state_of_vehicle") == "Used"
    assert golf.findtext("availability") == "available"
    assert listings[str(fleet["reserved"].id)].findtext("availability") == "not_available"
    address = {c.get("name"): c.text for c in golf.find("address")}
    assert address["region"] == "Grad Zagreb" and address["country"] == "HR"
    assert golf.findtext("latitude") == "45.815"
    csv_text = client.get(feed_url(db, "meta", "csv")).text
    row = next(csv.DictReader(io.StringIO(csv_text)))
    assert row["mileage.unit"] == "KM" and '"region": "Grad Zagreb"' in row["address"]


def test_generic_feed_carries_portal_codes(client, db, fleet, set_plan):
    set_plan("standard")
    root = ET.fromstring(client.get(feed_url(db, "mobile_de", "xml")).content)
    assert root.get("napomena") == "Format treba potvrditi s portalom"
    vehicle = root.find(f"vozilo[@id='{fleet['active'].id}']")
    assert vehicle.find("gorivo").get("kod") == "DIESEL"
    assert vehicle.find("mjenjac").get("kod") == "MANUAL_GEAR"
    assert vehicle.find("cijena").get("odbitni_pdv") == "ne"  # margin scheme
    root = ET.fromstring(client.get(feed_url(db, "autoscout24", "xml")).content)
    vehicle = root.find(f"vozilo[@id='{fleet['active'].id}']")
    assert vehicle.find("gorivo").get("kod") == "D" and vehicle.find("stanje").get("kod") == "U"
    root = ET.fromstring(client.get(feed_url(db, "njuskalo", "xml")).content)
    assert root.find("vozilo/gorivo").get("kod") is None  # no public spec -> no invented codes
