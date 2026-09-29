"""Faza 10 A: favoriti i usporedba vozila (javno, bez računa)."""

from __future__ import annotations

import pytest

from app.services import compare
from tests.helpers import make_vehicle


@pytest.fixture
def cars(db):
    golf = make_vehicle(
        db, make_name="Volkswagen", model_name="Golf", equipment=["abs", "klima", "navigacija"]
    )
    octavia = make_vehicle(
        db, make_name="Škoda", model_name="Octavia", year=2021, equipment=["abs", "tempomat"]
    )
    ceed = make_vehicle(db, make_name="Kia", model_name="Ceed", equipment=["abs"])
    passat = make_vehicle(db, make_name="Volkswagen", model_name="Passat")
    draft = make_vehicle(db, make_name="Audi", model_name="A4", status="draft")
    return {"golf": golf, "octavia": octavia, "ceed": ceed, "passat": passat, "draft": draft}


def test_parse_ids():
    assert compare.parse_ids("12, 34,x,12,-3,0,99", 5) == [12, 34, 99]
    assert compare.parse_ids("1,2,3,4,5", 3) == [1, 2, 3]
    assert compare.parse_ids(None, 3) == []
    assert compare.parse_ids("1" * 30, 3) == []


def test_favorites_page_renders_only_public_vehicles(client, cars):
    ids = f"{cars['golf'].id},{cars['draft'].id},999999,{cars['octavia'].id}"
    html = client.get(f"/favoriti?v={ids}").text
    assert cars["golf"].title in html and cars["octavia"].title in html
    assert cars["draft"].title not in html
    assert '<meta name="robots" content="noindex">' in html
    assert html.index(cars["golf"].title) < html.index(cars["octavia"].title)  # URL order
    empty = client.get("/favoriti").text
    assert "Još nemate favorita" in empty and "data-favorites-page" in empty


def test_compare_takes_first_three_and_builds_equipment_union(client, cars):
    ids = ",".join(str(cars[k].id) for k in ("golf", "octavia", "ceed", "passat"))
    response = client.get(f"/usporedba?v={ids}")
    html = response.text
    assert response.status_code == 200
    assert '<meta name="robots" content="noindex">' in html
    assert cars["passat"].title not in html  # max 3
    vehicles = [cars["golf"], cars["octavia"], cars["ceed"]]
    sections = compare.comparison(vehicles)
    rows = {r["label"]: r for s in sections for r in s["rows"]}
    assert rows["ABS"]["values"] == ["✓", "✓", "✓"] and rows["ABS"]["same"]
    assert rows["Tempomat"]["values"] == ["—", "✓", "—"] and not rows["Tempomat"]["same"]
    assert rows["Godina"]["values"] == ["2019", "2021", "2019"]
    assert "Klima uređaj" in rows or any("Klima" in label for label in rows)
    # Remove link keeps the other two vehicles.
    assert f'href="/usporedba?v={cars["octavia"].id},{cars["ceed"].id}"' in html


def test_compare_ignores_invalid_ids(client, cars):
    html = client.get(f"/usporedba?v=abc,{cars['draft'].id},0").text
    assert "Nema vozila za usporedbu" in html


def test_cards_and_detail_have_tools_hidden_without_js(client, cars):
    html = client.get("/vozila").text
    assert f'data-fav-toggle="{cars["golf"].id}"' in html
    assert 'class="card-tools" data-saved-tools hidden' in html
    detail = client.get(f"/vozila/{cars['golf'].slug}").text
    assert f'data-compare-toggle="{cars["golf"].id}"' in detail
    assert "data-fav-link hidden" in detail


def test_cookie_page_lists_local_storage(client):
    html = client.get("/kolacici").text
    assert "ak_favoriti" in html and "lokalna pohrana za favorite i usporedbu" in html


# ---------------------------------------------------------------------------
# Browser (Playwright, Chromium)
# ---------------------------------------------------------------------------
def test_browser_favorites_flow(live_server, page, cars):
    page.goto(f"{live_server}/vozila")
    page.click(f'.card-tool[data-fav-toggle="{cars["golf"].id}"]')
    assert page.inner_text("[data-fav-count]") == "1"
    assert page.get_attribute(f'[data-fav-toggle="{cars["golf"].id}"]', "aria-pressed") == "true"
    page.reload()  # state survives reloading
    assert page.inner_text("[data-fav-count]") == "1"
    page.goto(f"{live_server}/favoriti")  # JS builds ?v= from localStorage
    page.wait_for_url("**/favoriti?v=*")
    assert cars["golf"].title in page.content()
    assert page.errors == []


def test_browser_compare_flow(live_server, page, cars):
    page.goto(f"{live_server}/vozila")
    for key in ("golf", "octavia"):
        page.click(f'.card-tool[data-compare-toggle="{cars[key].id}"]')
    assert page.is_visible("[data-compare-bar]")
    page.click(f'.card-tool[data-compare-toggle="{cars["ceed"].id}"]')
    page.click(f'.card-tool[data-compare-toggle="{cars["passat"].id}"]')  # fourth
    assert "Najviše 3 vozila" in page.inner_text("[data-toast]")
    page.click("[data-compare-link]")
    page.wait_for_url("**/usporedba?v=*")
    assert page.locator(".compare-vehicle").count() == 3
    same_rows = page.locator("tr[data-same]").count()
    assert same_rows > 0
    page.check("[data-diff-toggle]")
    assert page.locator("tr[data-same]:visible").count() == 0
    assert page.locator(".compare-table tbody tr:not(.compare-section):visible").count() > 0
    assert page.errors == []
