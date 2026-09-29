"""Kartica za izlog i ponuda kupcu (paket Standard: `izlog_kartica`, `ponuda_pdf`)."""

from __future__ import annotations

from datetime import date

import pytest

from app.models import AuditLog, Inquiry, VehicleImage
from app.services.site import get_site
from tests.helpers import create_user, csrf_from, image_bytes, login_as, make_vehicle

VIN = "WVWZZZ1KZAW000001"  # make_vehicle default


@pytest.fixture
def vehicle(db):
    from app.services.images import save_vehicle_image

    v = make_vehicle(
        db,
        price_eur=18900,
        price_old_eur=19900,
        tax_type="pdv",
        first_registration=date(2019, 3, 1),
        registered_until=date(2027, 3, 1),
        equipment=["abs", "klima", "navigacija", "tempomat"],
    )
    key, processed = save_vehicle_image(v.id, image_bytes())
    db.add(VehicleImage(vehicle_id=v.id, file_key=key, sort_order=0,
                        width=processed.width, height=processed.height))  # fmt: skip
    db.commit()
    return v


@pytest.mark.parametrize("role", ["owner", "salesperson"])
def test_window_card_for_owner_and_salesperson(client, vehicle, set_plan, role):
    set_plan("standard")
    user_id, _ = create_user(f"{role}@test.hr", role=role)
    login_as(client, user_id)
    response = client.get(f"/admin/vozila/{vehicle.id}/izlog")
    assert response.status_code == 200
    html = response.text
    site = get_site()
    assert "18.900 €" in html and "19.900 €" in html  # price + struck old price
    assert "PDV uračunat u cijenu (R1)" in html
    assert 'src="data:image/png;base64,' in html  # QR code, no external service
    assert site["company_phone"] in html and site["company_address"] in html
    assert "03/2019" in html and "03/2027" in html  # first registration, registered until
    assert "Navigacija" in html
    assert VIN not in html  # VIN never on the public-facing window card
    assert "@page{size:A4 portrait" in html
    assert 'class="wc-image"' in html


def test_window_card_variants(client, vehicle, set_plan):
    set_plan("standard")
    user_id, _ = create_user("vlasnik@test.hr", role="owner")
    login_as(client, user_id)
    no_image = client.get(f"/admin/vozila/{vehicle.id}/izlog?slika=0").text
    assert 'class="wc-image"' not in no_image and "no-image" in no_image
    a5 = client.get(f"/admin/vozila/{vehicle.id}/izlog?format=a5").text
    assert "@page{size:A5 landscape" in a5 and "sheet-a5" in a5


def test_offer_form_prefilled_from_inquiry_and_document(client, db, vehicle, set_plan):
    set_plan("standard")
    user_id, _ = create_user("prodavac@test.hr", role="salesperson", name="Prodavač Test")
    login_as(client, user_id)
    inquiry = Inquiry(
        type="vehicle", vehicle_id=vehicle.id, name="Kupac Kupčić",
        email="kupac@primjer.hr", message="Zanima me.",
    )  # fmt: skip
    db.add(inquiry)
    db.commit()
    detail = client.get(f"/admin/upiti/{inquiry.id}").text
    assert f"/admin/vozila/{vehicle.id}/ponuda?upit={inquiry.id}" in detail

    form = client.get(f"/admin/vozila/{vehicle.id}/ponuda?upit={inquiry.id}")
    assert form.status_code == 200
    assert 'value="Kupac Kupčić"' in form.text and 'value="kupac@primjer.hr"' in form.text

    response = client.post(
        f"/admin/vozila/{vehicle.id}/ponuda",
        data={
            "customer_name": "Kupac Kupčić",
            "customer_email": "kupac@primjer.hr",
            "discount": "900",
            "valid_until": "2099-01-31",
            "note": "Uključen servis.",
            "csrf_token": csrf_from(form.text),
        },
    )
    assert response.status_code == 200
    html = response.text
    site = get_site()
    assert "Ponuda br." in html and "18.000 €" in html and "900 €" in html
    assert site["company_oib"] in html and site["company_name"] in html
    assert VIN in html  # the offer goes to the buyer, so it carries the VIN
    assert "31.01.2099." in html and "Uključen servis." in html
    assert "informativna i ne predstavlja obvezujuću ponudu" in html
    entry = db.query(AuditLog).filter_by(action="offer.print").one()
    assert f"{date.today().year}-{entry.id}" in html  # offer number = audit entry
    assert "Kupčić" not in str(entry.details) and "primjer.hr" not in str(entry.details)


def test_offer_validation(client, db, vehicle, set_plan):
    set_plan("standard")
    user_id, _ = create_user("vlasnik@test.hr", role="owner")
    login_as(client, user_id)
    form = client.get(f"/admin/vozila/{vehicle.id}/ponuda")
    token = csrf_from(form.text)
    bad = client.post(
        f"/admin/vozila/{vehicle.id}/ponuda",
        data={"customer_name": "", "discount": "50000", "csrf_token": token},
    )
    assert bad.status_code == 400
    assert "Upišite ime kupca." in bad.text and "Popust mora biti" in bad.text
    ok = client.post(
        f"/admin/vozila/{vehicle.id}/ponuda",
        data={"customer_name": "Ana", "final_price": "17.500", "csrf_token": token},
    )
    assert ok.status_code == 200 and "17.500 €" in ok.text and "1.400 €" in ok.text


@pytest.mark.parametrize(
    "path", ["/admin/vozila/{id}/izlog", "/admin/vozila/{id}/ponuda"], ids=["izlog", "ponuda"]
)
def test_locked_in_osnovni(client, vehicle, set_plan, path):
    set_plan("osnovni")
    user_id, _ = create_user("vlasnik@test.hr", role="owner")
    login_as(client, user_id)
    response = client.get(path.format(id=vehicle.id))
    assert response.status_code == 403 and "Dostupno u paketu Standard" in response.text
    edit = client.get(f"/admin/vozila/{vehicle.id}").text
    assert "Kartica za izlog" in edit and 'class="plan-badge"' in edit  # visible, badged
