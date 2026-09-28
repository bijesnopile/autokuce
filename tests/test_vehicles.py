"""Phase 3: vehicle schema validation, admin CRUD, statuses, slugs, duplication, deletion."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import AuditLog, Vehicle, VehicleSlugHistory
from app.services.storage import get_storage
from app.services.vehicles import change_status
from app.vehicle_schema import (
    TYPE_CODES,
    equipment_for,
    label,
    schema_for,
    validate_attributes,
    validate_common,
)
from tests.helpers import (
    create_user,
    csrf_from,
    get_csrf,
    image_bytes,
    login_as,
    make_catalog,
    make_vehicle,
)

REQUIRED_SPECIFIC = {
    "car": "body_type",
    "van": "van_type",
    "motorcycle": "moto_type",
    "camper": "camper_type",
    "truck": "truck_body",
}
VALID_SPECIFIC = {
    "car": {"body_type": "suv", "doors": "5"},
    "van": {
        "van_type": "furgon",
        "payload_kg": "1.200",
        "cargo_volume_m3": "10,5",
        "roof_height": "H2",
    },
    "motorcycle": {"moto_type": "naked", "cylinders": "2", "abs": "1", "a2_suitable": "1"},
    "camper": {"camper_type": "alkoven", "berths": "6", "length_m": "7,4", "wc_shower": "1"},
    "truck": {"truck_body": "kiper", "axles": "3", "gross_weight_kg": "26000", "tachograph": "1"},
}


@pytest.mark.parametrize("vehicle_type", TYPE_CODES)
def test_schema_required_and_specific_fields(vehicle_type):
    schema = schema_for(vehicle_type)
    assert schema["sections"]["karoserija"], "type-specific section must not be empty"
    assert equipment_for(vehicle_type)
    clean, errors = validate_attributes(vehicle_type, {})
    assert REQUIRED_SPECIFIC[vehicle_type] in errors
    clean, errors = validate_attributes(vehicle_type, VALID_SPECIFIC[vehicle_type])
    assert errors == {}
    assert (
        clean[REQUIRED_SPECIFIC[vehicle_type]]
        == VALID_SPECIFIC[vehicle_type][REQUIRED_SPECIFIC[vehicle_type]]
    )


def test_schema_parsing_and_ranges():
    clean, errors = validate_attributes(
        "van", {"van_type": "furgon", "payload_kg": "1.200", "cargo_volume_m3": "10,5"}
    )
    assert clean["payload_kg"] == 1200 and clean["cargo_volume_m3"] == 10.5
    _, errors = validate_attributes("van", {"van_type": "nepostojeci"})
    assert "van_type" in errors
    base = {
        "condition": "used",
        "year": "2019",
        "mileage_km": "145.000",
        "price_eur": "12.500",
        "tax_type": "marza",
        "fuel": "dizel",
        "transmission": "rucni",
    }
    clean, errors = validate_common("car", base)
    assert errors == {} and clean["mileage_km"] == 145000 and clean["price_eur"] == 12500
    _, errors = validate_common("car", dict(base, year="1890", mileage_km="3000000"))
    assert "year" in errors and "mileage_km" in errors
    _, errors = validate_common("car", dict(base, price_eur=""))
    assert "price_eur" in errors
    clean, errors = validate_common("car", dict(base, price_eur="", price_on_request="1"))
    assert errors == {} and clean["price_on_request"] is True
    _, errors = validate_common("car", dict(base, vin="KRATAK"))
    assert "vin" in errors
    # Motorcycles have no doors; the value is cleared.
    clean, _ = validate_common("motorcycle", dict(base, doors="5"))
    assert clean["doors"] is None
    assert label("fuel", "dizel") == "Dizel"


def test_new_vehicle_requires_consumption_and_co2():
    base = {
        "condition": "new",
        "year": "2026",
        "mileage_km": "10",
        "price_eur": "30000",
        "tax_type": "pdv",
        "fuel": "benzin",
        "transmission": "automatski",
    }
    _, errors = validate_common("car", base)
    assert "co2_g_km" in errors and "fuel_consumption_l100" in errors
    _, errors = validate_common("car", dict(base, co2_g_km="128", fuel_consumption_l100="5,6"))
    assert errors == {}


def _form_data(make, model, vehicle_type="car", **extra):
    data = {
        "vehicle_type": vehicle_type,
        "make_id": str(make.id),
        "model_id": str(model.id),
        "variant": "2.0 TDI Style",
        "condition": "used",
        "year": "2019",
        "mileage_km": "145000",
        "price_eur": "18500",
        "tax_type": "marza",
        "fuel": "dizel",
        "transmission": "rucni",
        "power_kw": "110",
        "status": "draft",
        "description": "<p>Opis <script>alert(1)</script><strong>vozila</strong></p>",
        "equipment": ["abs", "klima", "nepostojeca"],
    }
    for key, value in VALID_SPECIFIC[vehicle_type].items():
        data[f"{vehicle_type}__{key}"] = value
    data.update(extra)
    return data


@pytest.mark.parametrize("vehicle_type", TYPE_CODES)
def test_create_vehicle_of_every_type_via_admin(client, db, vehicle_type):
    user_id, _ = create_user("vlasnik@test.hr")
    make, model = make_catalog(db, "Volkswagen", f"Golf {vehicle_type}")
    login_as(client, user_id)
    page = client.get(f"/admin/vozila/novo?tip={vehicle_type}")
    assert page.status_code == 200
    data = _form_data(make, model, vehicle_type, csrf_token=csrf_from(page.text))
    response = client.post("/admin/vozila/novo", data=data, follow_redirects=False)
    assert response.status_code == 303, response.text[:2000]
    vehicle = db.scalar(select(Vehicle).order_by(Vehicle.id.desc()))
    assert vehicle.vehicle_type == vehicle_type
    assert vehicle.slug == f"volkswagen-golf-{vehicle_type}-2019-{vehicle.id}"
    assert vehicle.title == f"Volkswagen Golf {vehicle_type} 2.0 TDI Style"
    assert vehicle.power_hp == 150
    assert (
        "<script>" not in vehicle.description and "<strong>vozila</strong>" in vehicle.description
    )
    assert "nepostojeca" not in vehicle.equipment
    assert vehicle.attributes[REQUIRED_SPECIFIC[vehicle_type]]
    assert response.headers["location"] == f"/admin/vozila/{vehicle.id}/slike"
    assert db.scalar(select(AuditLog).where(AuditLog.action == "vehicle.create"))


def test_form_errors_keep_values(client, db):
    user_id, _ = create_user("vlasnik@test.hr")
    make, model = make_catalog(db, "Volkswagen", "Golf")
    login_as(client, user_id)
    token = get_csrf(client, "/admin/vozila/novo")
    data = _form_data(make, model, "car", csrf_token=token, condition="new", variant="Posebna")
    response = client.post("/admin/vozila/novo", data=data)
    assert response.status_code == 400
    assert "Obavezno polje" in response.text  # CO2 / consumption for new vehicles
    assert 'value="Posebna"' in response.text
    assert db.query(Vehicle).count() == 0


def test_status_transitions(db):
    vehicle = make_vehicle(db, status="draft")
    assert change_status(vehicle, "sold") is not None  # draft -> sold not allowed
    assert change_status(vehicle, "active") is None
    assert vehicle.published_at is not None
    assert change_status(vehicle, "sold") is None and vehicle.sold_at is not None
    assert change_status(vehicle, "archived") is not None  # only automatic
    assert change_status(vehicle, "active") is None and vehicle.sold_at is None


def test_status_change_from_list(client, db):
    user_id, _ = create_user("vlasnik@test.hr")
    vehicle = make_vehicle(db, user_id, status="active")
    login_as(client, user_id)
    token = get_csrf(client, "/admin/vozila")
    client.post(
        f"/admin/vozila/{vehicle.id}/status",
        data={"status": "reserved", "csrf_token": token, "next": "/admin/vozila"},
    )
    db.expire_all()
    assert db.get(Vehicle, vehicle.id).status == "reserved"
    client.post(
        f"/admin/vozila/{vehicle.id}/status", data={"status": "draft", "csrf_token": token}
    )  # reserved -> draft not allowed
    db.expire_all()
    assert db.get(Vehicle, vehicle.id).status == "reserved"


def test_slug_regenerates_and_keeps_history(client, db):
    user_id, _ = create_user("vlasnik@test.hr")
    vehicle = make_vehicle(db, user_id, make_name="BMW", model_name="320d", year=2019)
    old_slug = vehicle.slug
    assert old_slug == f"bmw-320d-2019-{vehicle.id}"
    login_as(client, user_id)
    page = client.get(f"/admin/vozila/{vehicle.id}")
    make, model = vehicle.make, vehicle.model
    data = _form_data(
        make, model, "car", csrf_token=csrf_from(page.text), year="2020", status="active"
    )
    response = client.post(f"/admin/vozila/{vehicle.id}", data=data, follow_redirects=False)
    assert response.status_code == 303
    db.expire_all()
    vehicle = db.get(Vehicle, vehicle.id)
    assert vehicle.slug == f"bmw-320d-2020-{vehicle.id}"
    history = db.scalars(select(VehicleSlugHistory.old_slug)).all()
    assert history == [old_slug]


def test_duplicate_vehicle(client, db):
    user_id, _ = create_user("vlasnik@test.hr")
    vehicle = make_vehicle(db, user_id)
    login_as(client, user_id)
    token = get_csrf(client, f"/admin/vozila/{vehicle.id}")
    response = client.post(
        f"/admin/vozila/{vehicle.id}/dupliciraj", data={"csrf_token": token}, follow_redirects=False
    )
    copy = db.scalar(select(Vehicle).where(Vehicle.id != vehicle.id))
    assert response.headers["location"] == f"/admin/vozila/{copy.id}"
    assert copy.status == "draft" and copy.images == [] and copy.vin is None
    assert copy.title == vehicle.title and copy.equipment == vehicle.equipment
    assert copy.slug != vehicle.slug


def test_delete_vehicle_removes_image_files(client, db):
    user_id, _ = create_user("vlasnik@test.hr")
    vehicle = make_vehicle(db, user_id)
    login_as(client, user_id)
    token = get_csrf(client, f"/admin/vozila/{vehicle.id}/slike")
    client.post(
        f"/admin/vozila/{vehicle.id}/slike",
        data={"csrf_token": token, "plates_confirmed": "1"},
        files=[("files", ("a.jpg", image_bytes(), "image/jpeg"))],
    )
    db.expire_all()
    key = db.get(Vehicle, vehicle.id).images[0].file_key
    storage = get_storage()
    assert storage.exists(f"{key}_1000.webp")
    vehicle_id = vehicle.id
    client.post(f"/admin/vozila/{vehicle_id}/obrisi", data={"csrf_token": token})
    db.expire_all()
    assert db.get(Vehicle, vehicle_id) is None
    for size in (400, 1000, 1600):
        assert not storage.exists(f"{key}_{size}.webp")


def test_salesperson_delete_rules(client, db):
    owner_id, _ = create_user("vlasnik@test.hr")
    seller_id, _ = create_user("prodavac@test.hr", role="salesperson")
    foreign_active = make_vehicle(db, owner_id, status="active")
    own_draft = make_vehicle(db, seller_id, status="draft", model_name="Drugi")
    foreign_id, own_id = foreign_active.id, own_draft.id
    login_as(client, seller_id)
    token = get_csrf(client, "/admin/vozila")
    response = client.post(f"/admin/vozila/{foreign_id}/obrisi", data={"csrf_token": token})
    assert response.status_code == 403
    response = client.post(
        f"/admin/vozila/{own_id}/obrisi", data={"csrf_token": token}, follow_redirects=False
    )
    assert response.status_code == 303
    db.expire_all()
    assert db.get(Vehicle, foreign_id) is not None
    assert db.get(Vehicle, own_id) is None


def test_vehicle_list_search_and_filters(client, db):
    user_id, _ = create_user("vlasnik@test.hr")
    make_vehicle(db, user_id, make_name="BMW", model_name="X5", vehicle_type="car")
    make_vehicle(
        db, user_id, make_name="Iveco", model_name="Daily", vehicle_type="van", status="draft"
    )
    login_as(client, user_id)
    html = client.get("/admin/vozila?q=Daily").text
    assert "Iveco Daily" in html and "BMW X5" not in html
    html = client.get("/admin/vozila?status=active").text
    assert "BMW X5" in html and "Iveco Daily" not in html
    html = client.get("/admin/vozila?tip=van").text
    assert "Iveco Daily" in html and "Bez slika" in html
    assert client.get("/admin/vozila?sort=nepoznato").status_code == 200
