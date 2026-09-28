"""Phase 4: public pages, filters, detail page, SEO, views, no external resources."""

from __future__ import annotations

import json
import re
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.database import utcnow
from app.models import Page, Vehicle, VehicleView
from app.services.vehicles import change_status
from tests.helpers import external_urls, make_vehicle

JSONLD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


def jsonld_blocks(html: str) -> list[dict]:
    return [json.loads(block) for block in JSONLD_RE.findall(html)]


@pytest.fixture
def fleet(db):
    """Six public vehicles with different attributes + one draft."""
    vehicles = {
        "golf": make_vehicle(
            db,
            make_name="Volkswagen",
            model_name="Golf",
            year=2018,
            price_eur=12000,
            mileage_km=150000,
            fuel="dizel",
            transmission="rucni",
        ),
        "passat": make_vehicle(
            db,
            make_name="Volkswagen",
            model_name="Passat",
            year=2021,
            price_eur=24000,
            mileage_km=60000,
            fuel="dizel",
            transmission="automatski",
        ),
        "clio": make_vehicle(
            db,
            make_name="Renault",
            model_name="Clio",
            year=2023,
            price_eur=16500,
            mileage_km=15000,
            fuel="benzin",
            transmission="rucni",
        ),
        "novi": make_vehicle(
            db,
            make_name="Škoda",
            model_name="Enyaq",
            year=2026,
            price_eur=45000,
            mileage_km=10,
            fuel="elektricni",
            transmission="automatski",
            condition="new",
            fuel_consumption_l100=16.5,
            co2_g_km=0,
        ),
        "kombi": make_vehicle(
            db,
            vehicle_type="van",
            make_name="Ford",
            model_name="Transit",
            year=2020,
            price_eur=28000,
            mileage_km=90000,
        ),
        "motor": make_vehicle(
            db,
            vehicle_type="motorcycle",
            make_name="Yamaha",
            model_name="MT-07",
            year=2022,
            price_eur=None,
            price_on_request=True,
            mileage_km=8000,
            fuel="benzin",
        ),
        "skica": make_vehicle(db, make_name="Volkswagen", model_name="Tiguan", status="draft"),
    }
    return vehicles


def titles(html: str) -> list[str]:
    return re.findall(r'class="vehicle-card-title"><a href="/vozila/[^"]+">([^<]+)</a>', html)


def test_public_pages_render_with_placeholders(client, fleet):
    for path in (
        "/",
        "/vozila",
        f"/vozila/{fleet['golf'].slug}",
        "/kontakt",
        "/o-nama",
        "/usluge",
        "/privatnost",
        "/kolacici",
        "/uvjeti",
    ):
        response = client.get(path)
        assert response.status_code == 200, path
        html = response.text
        for placeholder in (
            "IME PODUZEĆA",
            "mailpoduzeca@domena.com",
            "+385XXXXXXXXXX",
            "LOGO",
            "XXXXXXXXXXX",
        ):
            assert placeholder in html, (path, placeholder)


def test_legal_pages_show_version_and_lawyer_markers(client):
    html = client.get("/privatnost").text
    assert "Verzija 1.0" in html and "ažurirano" in html
    assert "[PRAVNIK: dopuniti]" in html
    for heading in ("Voditelj obrade", "Pravne osnove", "Prava ispitanika", "AZOP"):
        assert heading in html


def test_unpublished_page_is_404(client, db):
    page = db.scalar(select(Page).where(Page.slug == "usluge"))
    page.is_published = False
    db.commit()
    assert client.get("/usluge").status_code == 404


def test_draft_404_archived_410_old_slug_301(client, db, fleet):
    assert client.get(f"/vozila/{fleet['skica'].slug}").status_code == 404
    assert client.get("/vozila/ne-postoji-123").status_code == 404
    golf = fleet["golf"]
    golf.status = "archived"
    db.commit()
    response = client.get(f"/vozila/{golf.slug}")
    assert response.status_code == 410
    assert response.headers["x-robots-tag"] == "noindex"
    # Old slug -> 301 to the current one.
    from app.models import VehicleSlugHistory

    passat = fleet["passat"]
    db.add(VehicleSlugHistory(vehicle_id=passat.id, old_slug="stari-passat-99"))
    db.commit()
    response = client.get("/vozila/stari-passat-99", follow_redirects=False)
    assert response.status_code == 301
    assert response.headers["location"] == f"/vozila/{passat.slug}"


def test_sold_visible_then_disappears(client, db, fleet):
    clio = fleet["clio"]
    change_status(clio, "sold")
    db.commit()
    assert "PRODANO" in client.get(f"/vozila/{clio.slug}").text.upper()
    assert "Renault Clio Test" in titles(client.get("/vozila").text)
    clio.sold_at = utcnow() - timedelta(days=31)
    db.commit()
    assert client.get(f"/vozila/{clio.slug}").status_code == 410
    assert "Renault Clio Test" not in titles(client.get("/vozila").text)


def test_filters_return_exact_set(client, fleet):
    def listed(query):
        return set(titles(client.get("/vozila" + query).text))

    all_public = listed("")
    assert len(all_public) == 6 and "Volkswagen Tiguan Test" not in all_public
    assert listed("?tip=van") == {"Ford Transit Test"}
    vw = fleet["golf"].make_id
    assert listed(f"?marka={vw}") == {"Volkswagen Golf Test", "Volkswagen Passat Test"}
    assert listed(f"?marka={vw}&model={fleet['golf'].model_id}") == {"Volkswagen Golf Test"}
    assert listed("?cijena_do=17000") == {"Volkswagen Golf Test", "Renault Clio Test"}
    assert listed("?cijena_od=20000&cijena_do=30000") == {
        "Volkswagen Passat Test",
        "Ford Transit Test",
    }
    assert listed("?godina_od=2022") == {
        "Renault Clio Test",
        "Škoda Enyaq Test",
        "Yamaha MT-07 Test",
    }
    assert listed("?km_do=20000") == {"Renault Clio Test", "Škoda Enyaq Test", "Yamaha MT-07 Test"}
    assert listed("?gorivo=benzin") == {"Renault Clio Test", "Yamaha MT-07 Test"}
    assert listed("?mjenjac=automatski&gorivo=dizel") == {"Volkswagen Passat Test"}
    assert listed("?stanje=novo") == {"Škoda Enyaq Test"}
    # Invalid values are ignored.
    assert listed("?tip=svemirski&cijena_do=abc&godina_od=1") == all_public


def test_sorting_and_price_on_request_last(client, fleet):
    ordered = titles(client.get("/vozila?sort=cijena_uzlazno").text)
    assert ordered[0] == "Volkswagen Golf Test"
    assert ordered[-1] == "Yamaha MT-07 Test"  # price on request at the end
    ordered = titles(client.get("/vozila?sort=cijena_silazno").text)
    assert ordered[0] == "Škoda Enyaq Test"
    ordered = titles(client.get("/vozila?sort=km_uzlazno").text)
    assert ordered[0] == "Škoda Enyaq Test"


def test_pagination_with_rel_links(client, db):
    for n in range(14):
        make_vehicle(db, make_name="Kia", model_name=f"Ceed {n}", year=2015 + n % 8)
    page1 = client.get("/vozila").text
    assert len(titles(page1)) == 12
    assert 'rel="next"' in page1 and 'rel="prev"' not in page1
    page2 = client.get("/vozila?stranica=2").text
    assert len(titles(page2)) == 2
    assert 'rel="prev"' in page2
    assert '<link rel="canonical" href="http://testserver/vozila?stranica=2">' in page2


def test_detail_jsonld_and_no_vin(client, fleet):
    golf = fleet["golf"]
    html = client.get(f"/vozila/{golf.slug}").text
    assert '"@type"' in html and '"priceCurrency":"EUR"' in html
    blocks = jsonld_blocks(html)
    car = next(b for b in blocks if b["@type"] == "Car")
    assert car["offers"]["price"] == 12000
    assert car["offers"]["availability"] == "https://schema.org/InStock"
    assert car["brand"]["name"] == "Volkswagen"
    assert car["mileageFromOdometer"]["value"] == 150000
    assert any(b["@type"] == "BreadcrumbList" for b in blocks)
    assert golf.vin and golf.vin not in html
    assert "VIN" not in html
    # Meta title format: "{title}, {year}, {km} – {company}"
    assert "<title>Volkswagen Golf Test, 2018, 150.000 km – IME PODUZEĆA</title>" in html
    assert 'property="og:image"' in html


def test_price_on_request_has_no_price_in_offer(client, fleet):
    html = client.get(f"/vozila/{fleet['motor'].slug}").text
    motorcycle = next(b for b in jsonld_blocks(html) if b["@type"] == "Motorcycle")
    assert "price" not in motorcycle["offers"]
    assert "Cijena na upit" in html


def test_new_vehicle_shows_consumption_and_co2(client, fleet):
    html = client.get(f"/vozila/{fleet['novi'].slug}").text
    assert "Potrošnja i emisije" in html
    assert "16,5 kWh/100 km" in html
    assert "0 g/km" in html


def test_home_has_autodealer_jsonld_and_sections(client, fleet):
    html = client.get("/").text
    types = [b["@type"] for b in jsonld_blocks(html)]
    assert "AutoDealer" in types
    assert "Zadnje dodano" in html and "Brza pretraga" in html
    assert "Zašto mi" in html


def test_sitemap_contains_only_active_and_reserved(client, db, fleet):
    change_status(fleet["passat"], "reserved")
    change_status(fleet["clio"], "sold")
    db.commit()
    xml = client.get("/sitemap.xml").text
    assert client.get("/sitemap.xml").headers["content-type"].startswith("application/xml")
    assert f"/vozila/{fleet['golf'].slug}</loc>" in xml
    assert f"/vozila/{fleet['passat'].slug}</loc>" in xml
    assert f"/vozila/{fleet['clio'].slug}</loc>" not in xml
    assert f"/vozila/{fleet['skica'].slug}</loc>" not in xml
    assert "http://testserver/privatnost</loc>" in xml


def test_robots_txt(client):
    text = client.get("/robots.txt").text
    assert "Disallow: /admin" in text and "Disallow: /api" in text
    assert "Sitemap: http://testserver/sitemap.xml" in text


def test_view_counting_skips_bots_and_repeats(client, db, fleet):
    golf = fleet["golf"]
    client.get(f"/vozila/{golf.slug}", headers={"User-Agent": "Googlebot/2.1"})
    db.expire_all()
    assert db.get(Vehicle, golf.id).views_total == 0
    browser = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/140"}
    client.get(f"/vozila/{golf.slug}", headers=browser)
    client.get(f"/vozila/{golf.slug}", headers=browser)  # same visitor within 6 h
    db.expire_all()
    assert db.get(Vehicle, golf.id).views_total == 1
    assert db.scalar(select(VehicleView.count).where(VehicleView.vehicle_id == golf.id)) == 1
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as other:
        other.get(f"/vozila/{golf.slug}", headers=browser)
    db.expire_all()
    assert db.get(Vehicle, golf.id).views_total == 2


def test_similar_vehicles_same_type(client, fleet):
    html = client.get(f"/vozila/{fleet['golf'].slug}").text
    similar = html.split("Slična vozila")[1]
    assert "Volkswagen Passat Test" in similar
    assert "Ford Transit" not in similar


@pytest.mark.parametrize("path", ["/", "/vozila", "/kontakt", "/o-nama", "/privatnost"])
def test_no_external_resources_on_public_pages(client, fleet, path):
    assert external_urls(client.get(path).text) == []


def test_no_external_resources_on_detail(client, fleet):
    assert external_urls(client.get(f"/vozila/{fleet['golf'].slug}").text) == []


def test_turnstile_and_umami_only_when_configured(client, fleet, monkeypatch):
    from app import templating

    html = client.get("/kontakt").text
    assert "challenges.cloudflare.com" not in html and "data-website-id" not in html
    configured = dict(templating.env.globals["config"])
    configured.update(
        TURNSTILE_SITE_KEY="0x4AAAAAAAtest",
        UMAMI_SCRIPT_URL="https://analytics.primjer.hr/script.js",
        UMAMI_WEBSITE_ID="abc-123",
    )
    monkeypatch.setitem(templating.env.globals, "config", configured)
    html = client.get("/kontakt").text
    assert '<script defer src="https://challenges.cloudflare.com/turnstile/v0/api.js">' in html
    assert 'class="cf-turnstile' in html
    assert 'src="https://analytics.primjer.hr/script.js" data-website-id="abc-123"' in html
    bad = external_urls(
        html, extra_allowed=("https://challenges.cloudflare.com/", "https://analytics.primjer.hr/")
    )
    assert bad == []


def test_csp_includes_turnstile_host_only_when_configured():
    from app.config import Settings
    from app.main import build_csp

    plain = build_csp(Settings(_env_file=None))
    assert "challenges.cloudflare.com" not in plain
    configured = build_csp(
        Settings(
            _env_file=None,
            TURNSTILE_SITE_KEY="x",
            TURNSTILE_SECRET_KEY="y",
            UMAMI_SCRIPT_URL="https://a.primjer.hr/s.js",
            UMAMI_WEBSITE_ID="1",
            MEDIA_URL="https://media.primjer.hr",
        )
    )
    assert "script-src 'self' https://challenges.cloudflare.com https://a.primjer.hr" in configured
    assert "img-src 'self' data: https://media.primjer.hr" in configured


def test_api_models_is_public_json(client, fleet):
    response = client.get(f"/api/modeli?marka={fleet['golf'].make_id}")
    assert response.status_code == 200
    assert {"Golf", "Passat", "Tiguan"} <= {m["name"] for m in response.json()}


VOID = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "source",
    "track",
    "wbr",
    "path",
    "circle",
    "rect",
    "line",
    "polyline",
    "polygon",
    "ellipse",
}


def _balance_errors(html: str) -> list[str]:
    from html.parser import HTMLParser

    class Checker(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack: list[str] = []
            self.errors: list[str] = []

        def handle_starttag(self, tag, attrs):
            if tag not in VOID:
                self.stack.append(tag)

        def handle_startendtag(self, tag, attrs):
            pass

        def handle_endtag(self, tag):
            if tag in VOID:
                return
            if not self.stack or self.stack[-1] != tag:
                self.errors.append(f"unexpected </{tag}> (open: {self.stack[-3:]})")
                if tag in self.stack:
                    while self.stack and self.stack.pop() != tag:
                        pass
                return
            self.stack.pop()

    checker = Checker()
    checker.feed(html)
    checker.close()
    return checker.errors + [f"unclosed <{t}>" for t in checker.stack]


@pytest.mark.parametrize("path", ["/", "/vozila", "/kontakt", "/privatnost", "/nepostoji"])
def test_html_is_well_formed(client, fleet, path):
    assert _balance_errors(client.get(path).text) == []


def test_detail_html_is_well_formed(client, fleet):
    assert _balance_errors(client.get(f"/vozila/{fleet['golf'].slug}").text) == []
