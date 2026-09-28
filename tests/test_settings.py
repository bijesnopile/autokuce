"""Company settings, logo, colours, cookie banner (phase 7)."""

from __future__ import annotations

import io
import json

import pytest
from PIL import Image
from sqlalchemy import select

from app.models import (
    AuditLog,
    Setting,
)
from app.services.site import get_site, invalidate_site_cache
from app.services.storage import get_storage
from tests.helpers import create_user, csrf_from, get_csrf, login_as


@pytest.fixture
def owner(client):
    user_id, _ = create_user("vlasnik@test.hr", role="owner")
    login_as(client, user_id)
    return user_id


def _settings_form(client, **changes):
    page = client.get("/admin/postavke")
    site = get_site()
    data = {"csrf_token": csrf_from(page.text)}
    for key in (
        "company_name",
        "company_address",
        "company_oib",
        "company_email",
        "company_phone",
        "company_web",
        "working_hours",
        "inquiry_notify_email",
        "newsletter_sender_name",
        "facebook_url",
        "instagram_url",
        "maps_url",
        "primary_color",
        "accent_color",
        "hero_title",
        "hero_subtitle",
        "footer_text",
        "privacy_policy_version",
    ):
        data[key] = site[key]
    data["plates_reminder_enabled"] = "1"
    data.update(changes)
    return client.post("/admin/postavke", data=data, follow_redirects=False)


def test_settings_change_company_name_updates_public_site(client, db, owner):
    response = _settings_form(client, company_name="Auto Primjer d.o.o.", primary_color="#0B3D2E")
    assert response.status_code == 303
    invalidate_site_cache()
    html = client.get("/").text
    assert "Auto Primjer d.o.o." in html and "IME PODUZEĆA" not in html
    assert "--color-primary:#0b3d2e" in html
    entry = db.scalar(select(AuditLog).where(AuditLog.action == "settings.update"))
    assert "company_name" in entry.details["keys"]
    assert "Auto Primjer" not in json.dumps(entry.details)


def test_settings_validation(client, owner):
    response = _settings_form(
        client,
        company_email="nije-email",
        company_oib="123",
        primary_color="plava",
        facebook_url="facebook.com/x",
    )
    assert response.status_code == 400
    for text in ("ispravnu email adresu", "OIB ima 11 znamenki", "#rrggbb", "https://"):
        assert text in response.text
    assert _settings_form(client, company_oib="12345678901").status_code == 303


def test_privacy_version_change_records_date(client, db, owner):
    db.merge(Setting(key="privacy_policy_updated_at", value="2020-01-01"))
    db.commit()
    _settings_form(client, privacy_policy_version="1.1")
    db.expire_all()
    assert db.get(Setting, "privacy_policy_updated_at").value != "2020-01-01"
    invalidate_site_cache()
    html = client.get("/privatnost").text
    assert "Verzija 1.1" in html


def test_logo_upload_replaces_text_logo(client, db, owner):
    buffer = io.BytesIO()
    Image.new("RGBA", (600, 200), (30, 60, 200, 255)).save(buffer, "PNG")
    token = get_csrf(client, "/admin/postavke")
    client.post(
        "/admin/postavke/logo",
        data={"csrf_token": token},
        files={"logo": ("logo.png", buffer.getvalue(), "image/png")},
    )
    invalidate_site_cache()
    key = get_site()["logo_key"]
    assert key.startswith("branding/")
    assert get_storage().exists(f"{key}_400.webp")
    html = client.get("/").text
    assert f"/media/{key}_400.webp" in html
    assert '<span class="logo-box">LOGO</span>' not in html
    # Non-image is rejected.
    client.post(
        "/admin/postavke/logo",
        data={"csrf_token": token},
        files={"logo": ("logo.png", b"<svg></svg>", "image/png")},
    )
    invalidate_site_cache()
    assert get_site()["logo_key"] == key
    # Removing the logo brings the text back.
    client.post("/admin/postavke/logo/ukloni", data={"csrf_token": token})
    invalidate_site_cache()
    assert '<span class="logo-box">LOGO</span>' in client.get("/").text
    assert not get_storage().exists(f"{key}_400.webp")


def test_salesperson_cannot_access_settings_pages_gdpr(client):
    seller_id, _ = create_user("prodavac@test.hr", role="salesperson")
    login_as(client, seller_id)
    for path in ("/admin/postavke", "/admin/stranice", "/admin/gdpr", "/admin/sustav"):
        assert client.get(path).status_code == 403


def test_cookie_banner_only_when_enabled(client, db, owner):
    assert "data-cookie-banner" not in client.get("/").text
    _settings_form(client, cookie_banner_enabled="1")
    invalidate_site_cache()
    html = client.get("/").text
    assert "data-cookie-banner" in html and "Prihvaćam" in html and "Odbijam" in html
