"""Paket Standard: kalkulator rate i upit za financiranje."""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import Inquiry
from app.services import financing
from app.services.site import invalidate_site_cache, set_values
from tests.helpers import create_user, eml_text, login_as, make_vehicle, outbox, read_eml
from tests.test_inquiries import post_inquiry
from tests.test_settings import _settings_form

PUBLIC_JS = Path(__file__).resolve().parent.parent / "app" / "static" / "js" / "public.js"
CASES = [
    (10000, 6.9, 60),
    (12000, 6.9, 84),
    (8765.43, 4.25, 36),
    (25000, 0, 48),
    (1500, 29.9, 12),
    (99999, 7.5, 120),
]


@pytest.fixture
def vehicle(db):
    return make_vehicle(db, make_name="Volkswagen", model_name="Golf")


def settings(db, **values):
    set_values(db, values)
    db.commit()
    invalidate_site_cache()


def test_annuity_formula():
    assert financing.monthly_payment(10000, 6.9, 60) == pytest.approx(197.5, abs=0.05)
    assert financing.monthly_payment(10000, 6.9, 60) == 197.54
    assert financing.monthly_payment(1200, 0, 12) == 100.0
    assert financing.monthly_payment(0, 6.9, 60) == 0.0
    assert financing.format_eur(197.54) == "197,54 €"
    assert financing.format_eur(12345.5) == "12.345,50 €"


def test_js_calculator_matches_python():
    """public.js (`window.AutokucaFinance`) gives exactly the same rate as the server."""
    sync_api = pytest.importorskip("playwright.sync_api")
    try:
        with sync_api.sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.set_content("<!doctype html><html><body></body></html>")
            page.add_script_tag(content=PUBLIC_JS.read_text(encoding="utf-8"))
            for principal, rate, months in CASES:
                js = page.evaluate(
                    "([p, r, n]) => window.AutokucaFinance.payment(p, r, n)",
                    [principal, rate, months],
                )
                assert js == financing.monthly_payment(principal, rate, months)
                text = page.evaluate("(v) => window.AutokucaFinance.formatEur(v, 2)", js)
                assert text == financing.format_eur(js)
            browser.close()
    except sync_api.Error as exc:  # pragma: no cover - browser not installed
        pytest.skip(f"Chromium nije dostupan: {exc}")


def test_calculator_only_in_plan_with_price(client, db, vehicle, set_plan):
    detail = f"/vozila/{vehicle.slug}"
    set_plan("osnovni")
    html = client.get(detail).text
    assert "data-financing" not in html and "€/mj" not in html
    assert "€/mj" not in client.get("/vozila").text

    set_plan("standard")
    html = client.get(detail).text
    assert 'id="financiranje"' in html and "Zatraži ponudu financiranja" in html
    example = financing.example(vehicle)  # 15.000 €, 20 % down, 84 months, 6,9 %
    assert example["principal"] == 12000 and example["months"] == 84
    assert financing.format_eur(example["payment"]) in html  # no-JS example from the server
    assert "Informativni izračun, ne predstavlja ponudu" in html
    card = client.get("/vozila").text
    assert f"od {math.ceil(example['payment'])} €/mj" in card

    settings(db, financing_enabled="false")
    assert "data-financing" not in client.get(detail).text
    settings(db, financing_enabled="true")

    on_request = make_vehicle(db, model_name="Passat", price_on_request=True)
    html = client.get(f"/vozila/{on_request.slug}").text
    assert "data-financing" not in html
    assert financing.card_from(on_request) is None


def test_financing_inquiry_saves_params_and_notifies(client, db, vehicle, set_plan):
    set_plan("standard")
    response = post_inquiry(
        client, vehicle, kind="financing", down_payment="5000", months="60", message="Leasing?"
    )
    assert response.status_code == 400  # message too short -> form re-rendered with values
    assert 'value="5000"' in response.text
    response = post_inquiry(client, vehicle, kind="financing", down_payment="5000", months="60")
    assert response.status_code == 303
    inquiry = db.scalar(select(Inquiry))
    assert inquiry.type == "financing"
    params = inquiry.extra["financing"]
    assert params["down_payment"] == 5000 and params["amount"] == 10000
    assert params["months"] == 60 and params["payment"] == 197.54

    dealer = [m for m in (read_eml(p) for p in outbox()) if m["To"] != "kupac1@primjer.hr"]
    text = eml_text(dealer[0])
    assert "Upit za financiranje" in text
    assert "Učešće: 5.000,00 €" in text and "Rok otplate: 60 mj." in text
    assert "197,54 €" in text

    client.cookies.clear()
    seller_id, _ = create_user("prodavac@test.hr", role="salesperson")
    login_as(client, seller_id)
    assert "type-financing" in client.get("/admin/upiti").text
    detail = client.get(f"/admin/upiti/{inquiry.id}").text
    assert "Zatraženo financiranje" in detail and "10.000,00 €" in detail


def test_financing_inquiry_validation(client, db, vehicle, set_plan):
    set_plan("standard")
    response = post_inquiry(client, vehicle, kind="financing", down_payment="1000", months="60")
    assert response.status_code == 400 and "Najmanje učešće je 20 %" in response.text
    response = post_inquiry(client, vehicle, kind="financing", down_payment="5000", months="96")
    assert response.status_code == 400 and "Rok otplate od 12 do 84" in response.text
    on_request = make_vehicle(db, model_name="Passat", price_on_request=True)
    response = post_inquiry(client, on_request, kind="financing", down_payment="5000", months="60")
    assert response.status_code == 400
    assert db.scalar(select(Inquiry)) is None


def test_financing_locked_in_basic_plan(client, db, vehicle, set_plan):
    set_plan("osnovni")
    assert "Zatraži ponudu financiranja" not in client.get(f"/vozila/{vehicle.slug}").text
    response = post_inquiry(client, vehicle, kind="financing", down_payment="5000", months="60")
    assert response.status_code == 404
    assert db.scalar(select(Inquiry)) is None


def test_settings_validation(client, db, set_plan):
    owner_id, _ = create_user("vlasnik@test.hr", role="owner")
    login_as(client, owner_id)
    set_plan("standard")
    fields = {
        "financing_enabled": "1",
        "financing_rate_percent": "5,5",
        "financing_max_months": "72",
        "financing_min_down_percent": "10",
        "financing_disclaimer": "Informativno.",
    }
    assert _settings_form(client, **fields).status_code == 303
    cfg = financing.config()
    assert cfg["rate"] == 5.5 and cfg["max_months"] == 72 and cfg["min_down"] == 10
    response = _settings_form(client, **(fields | {"financing_max_months": "90"}))
    assert response.status_code == 400 and "višekratnik" in response.text.lower()
    response = _settings_form(client, **(fields | {"financing_rate_percent": "45"}))
    assert response.status_code == 400


def test_gdpr_export_includes_financing_request(client, db, vehicle, set_plan):
    from app.routers.admin_privacy import export_data, find_person

    set_plan("standard")
    post_inquiry(client, vehicle, kind="financing", down_payment="5000", months="60")
    data = export_data(find_person(db, "kupac1@primjer.hr"))
    [item] = data["upiti"]
    assert item["financiranje"]["months"] == 60 and item["potvrdeni_termin"] is None
