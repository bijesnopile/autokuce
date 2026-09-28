"""Marketing content: service cards, "why us" items, O nama stats, vehicle highlights/specs."""

from __future__ import annotations

import re
from datetime import date

import pytest

from app.models import Page
from app.services.content import pick_icon, split_lead, split_sections, why_us_items
from app.services.site import get_site, invalidate_site_cache, set_values
from tests.helpers import create_user, csrf_from, login_as, make_vehicle


def test_split_sections_intro_cards_outro():
    html = (
        "<p>Uvod.</p><h3>Financiranje i leasing</h3><p>Tekst A.</p>"
        "<h3>Otkup vozila</h3><ul><li>x</li></ul><h2>Za tvrtke</h2><p>Kraj.</p>"
    )
    parts = split_sections(html)
    assert str(parts["intro"]) == "<p>Uvod.</p>"
    assert [c["title"] for c in parts["cards"]] == ["Financiranje i leasing", "Otkup vozila"]
    assert [c["icon"] for c in parts["cards"]] == ["tag", "refresh"]
    assert str(parts["cards"][1]["body"]) == "<ul><li>x</li></ul>"
    assert str(parts["outro"]).startswith("<h2>Za tvrtke</h2>")
    assert split_sections("<p>Samo tekst</p>")["cards"] == []


def test_split_lead_and_icons():
    lead, rest = split_lead("<p>Prvi.</p>\n<h2>Dalje</h2><p>Drugi.</p>")
    assert str(lead) == "<p>Prvi.</p>" and str(rest).startswith("<h2>Dalje</h2>")
    assert split_lead("<h2>Bez uvoda</h2>")[0] == ""
    assert pick_icon("Registracija bez brige") == "file"
    assert pick_icon("Nešto sasvim drugo", 1) == "handshake"


def test_why_us_items_parsing():
    items = why_us_items("Provjerena vozila | Opis A\n\n  Samo naslov  \n| bez naslova")
    assert [(i["title"], i["text"]) for i in items] == [
        ("Provjerena vozila", "Opis A"),
        ("Samo naslov", ""),
    ]
    assert len(why_us_items("\n".join(f"Stavka {n}" for n in range(12)))) == 8


def test_services_page_renders_editable_cards(client, db):
    page = db.query(Page).filter_by(slug="usluge").one()
    page.body_html = (
        "<p>Naš uvod.</p><h3>Otkup vozila</h3><p>Otkupljujemo.</p>"
        "<h3>Jamstvo</h3><p>Do 24 mjeseca.</p><h2>Za tvrtke</h2><p>R1 račun.</p>"
    )
    db.commit()
    html = client.get("/usluge").text
    assert html.count('class="service-card"') == 2
    assert "Otkupljujemo." in html and "Za tvrtke" in html
    assert 'class="page-lead"><p>Naš uvod.</p>' in html
    assert "Kako do vašeg vozila" in html  # purchase steps
    assert get_site()["company_phone"] in html  # CTA band uses company data from settings
    assert '<meta name="description" content="Naš uvod.">' in html


def test_about_page_stats_company_card_and_why_us(client, db):
    make_vehicle(db)
    make_vehicle(db, vehicle_type="van", make_name="Ford", model_name="Transit")
    make_vehicle(db, status="draft")  # drafts are not "in the offer"
    html = client.get("/o-nama").text
    assert re.search(r"<strong>2</strong><span>vozila u ponudi</span>", html)
    assert re.search(r"<strong>2</strong><span>vrsta vozila</span>", html)
    site = get_site()
    assert site["company_address"] in html and site["working_hours"] in html
    assert "Zašto kupiti kod nas" in html and site["why_us_items"][0]["title"] in html


@pytest.fixture
def owner(client):
    user_id, _ = create_user("vlasnik@test.hr", role="owner")
    login_as(client, user_id)
    return user_id


def test_why_us_setting_drives_home_about_and_vehicle(client, db, owner):
    vehicle = make_vehicle(db)
    page = client.get("/admin/postavke")
    data = {"csrf_token": csrf_from(page.text)}
    site = get_site()
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
    data["why_us"] = "Dostava na kućnu adresu | Vozilo dovozimo do vas.\r\nBesplatna procjena"
    response = client.post("/admin/postavke", data=data, follow_redirects=False)
    assert response.status_code == 303
    for path in ("/", "/o-nama", f"/vozila/{vehicle.slug}"):
        html = client.get(path).text
        assert "Dostava na kućnu adresu" in html and "Besplatna procjena" in html, path
        assert "Provjerena vozila" not in html, path

    data["why_us"] = "\n".join(f"Stavka {n}" for n in range(9))
    response = client.post("/admin/postavke", data=data)
    assert response.status_code == 400 and "Najviše 8 stavki" in response.text


def test_vehicle_highlights_and_spec_cards(client, db):
    vehicle = make_vehicle(
        db,
        first_owner=True,
        service_book=True,
        warranty_months=12,
        registered_until=date(2099, 5, 1),
        tax_type="pdv",
    )
    html = client.get(f"/vozila/{vehicle.slug}").text
    for text in (
        "Prvi vlasnik",
        "Servisna knjižica",
        "Garancija 12 mj.",
        "Registriran do 05/2099",
        "Moguć R1 račun",
    ):
        assert f"{text}</li>" in html, text
    assert html.count('class="spec-card"') >= 2
    assert 'class="count-badge">2</span>' in html  # two equipment items (ABS, klima)
    expired = make_vehicle(db, registered_until=date(2020, 1, 1))
    assert "Registriran do" not in client.get(f"/vozila/{expired.slug}").text.split("spec-cards")[0]


def test_admin_preview_uses_page_layout(client, db, owner):
    html = client.get("/admin/stranice/usluge/pregled").text
    assert 'class="service-card"' in html and "Kako do vašeg vozila" in html


def test_reset_demo_content_restores_marketing_texts(db):
    from app.seed_content import PAGES
    from app.seed_demo import reset_demo_content

    set_values(db, {"why_us": "Nešto drugo", "hero_title": "Moj naslov"})
    page = db.query(Page).filter_by(slug="o-nama").one()
    page.body_html = "<p>izmijenjeno</p>"
    privacy = db.query(Page).filter_by(slug="privatnost").one()
    privacy_before = privacy.body_html
    db.commit()
    reset_demo_content(db)
    db.commit()
    invalidate_site_cache()
    site = get_site()
    assert site["hero_title"] == "Pronađite vozilo koje vam odgovara"
    assert site["why_us_items"][0]["title"] == "Provjerena vozila"
    db.refresh(page)
    assert page.body_html == next(p["body_html"] for p in PAGES if p["slug"] == "o-nama")
    db.refresh(privacy)
    assert privacy.body_html == privacy_before  # legal pages are never touched


def test_split_columns_balances_card_heights():
    from app.services.vehicles import spec_columns

    groups = [
        {"label": n, "rows": [("x", "y")] * rows}
        for n, rows in (("Osnovno", 5), ("Motor", 6), ("Karoserija", 4), ("Stanje", 3))
    ]
    left, right = spec_columns(groups)
    assert [g["label"] for g in left] == ["Osnovno", "Karoserija"]
    assert [g["label"] for g in right] == ["Motor", "Stanje"]
    assert [g["order"] for g in left + right] == [0, 2, 1, 3]  # original order for mobile
    assert [[g["label"] for g in col] for col in spec_columns(groups[:1])] == [["Osnovno"]]
