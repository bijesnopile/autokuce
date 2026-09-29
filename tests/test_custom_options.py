"""Vlastite opcije u formi vozila ("+ Nova opcija…", nova oprema) i polja za električna vozila."""

from __future__ import annotations

from sqlalchemy import select

from app.models import AuditLog, CustomOption, Vehicle
from app.services import custom_options
from app.vehicle_schema import label, validate_common
from tests.helpers import create_user, csrf_from, get_csrf, login_as, make_catalog
from tests.test_vehicles import _form_data


def _post_new(client, db, **extra):
    make, model = make_catalog(db, "Volkswagen", "Golf")
    token = get_csrf(client, "/admin/vozila/novo")
    data = _form_data(make, model, "car", csrf_token=token, status="active", **extra)
    return client.post("/admin/vozila/novo", data=data, follow_redirects=False)


def _owner(client):
    user_id, _ = create_user("vlasnik@test.hr", role="owner")
    login_as(client, user_id)
    return user_id


def test_new_select_option_is_created_and_shown_with_the_others(client, db):
    _owner(client)
    page = client.get("/admin/vozila/novo").text
    assert 'value="__new__"' in page and 'name="color__new"' in page
    response = _post_new(client, db, color="__new__", color__new="  Mat  zelena ")
    assert response.status_code == 303, response.text[:1500]
    option = db.scalar(select(CustomOption).where(CustomOption.scope == "color"))
    assert option.label == "Mat zelena" and option.code == "mat-zelena"
    vehicle = db.scalar(select(Vehicle))
    assert vehicle.color == "mat-zelena"
    assert label("color", vehicle.color) == "Mat zelena"
    # Next form lists it next to the built-in colours; the public ad shows the label.
    assert '<option value="mat-zelena">Mat zelena</option>' in client.get("/admin/vozila/novo").text
    assert "Mat zelena" in client.get(f"/vozila/{vehicle.slug}").text
    entry = db.scalar(select(AuditLog).where(AuditLog.action == "option.create"))
    assert entry and entry.details["labels"] == ["Mat zelena"]


def test_same_label_reuses_existing_option(client, db):
    _owner(client)
    _post_new(client, db, color="__new__", color__new="Mat zelena")
    _post_new(client, db, color="__new__", color__new="MAT ZELENA")
    assert db.query(CustomOption).count() == 1
    _post_new(client, db, color="__new__", color__new="bijela")  # built-in label
    assert db.query(CustomOption).count() == 1
    assert db.scalar(select(Vehicle).order_by(Vehicle.id.desc())).color == "bijela"


def test_type_specific_option(client, db):
    _owner(client)
    response = _post_new(client, db, car__body_type="__new__", car__body_type__new="Shooting brake")
    assert response.status_code == 303
    vehicle = db.scalar(select(Vehicle))
    assert vehicle.attributes["body_type"] == "shooting-brake"
    option = db.scalar(select(CustomOption))
    assert option.scope == "car.body_type"
    assert "Shooting brake" in client.get(f"/vozila/{vehicle.slug}").text


def test_invalid_form_creates_nothing(client, db):
    _owner(client)
    response = _post_new(client, db, color="__new__", color__new="")
    assert response.status_code == 400 and "Upišite naziv nove opcije" in response.text
    response = _post_new(client, db, color="__new__", color__new="Pješčana", year="")
    assert response.status_code == 400
    assert 'value="Pješčana"' in response.text  # typed label is kept for the retry
    assert db.query(CustomOption).count() == 0 and db.query(Vehicle).count() == 0


def test_fixed_fields_cannot_be_extended(client, db):
    _owner(client)
    response = _post_new(client, db, condition="__new__", condition__new="Oldtimer")
    assert response.status_code == 400
    assert db.query(CustomOption).count() == 0


def test_new_equipment(client, db):
    _owner(client)
    response = _post_new(client, db, equipment_new__udobnost="Hladnjak, Masažna sjedala, hladnjak")
    assert response.status_code == 303
    vehicle = db.scalar(select(Vehicle))
    codes = {o.label: o.code for o in db.scalars(select(CustomOption))}
    assert set(codes) == {"Hladnjak", "Masažna sjedala"}
    assert codes["Hladnjak"] in vehicle.equipment and "abs" in vehicle.equipment
    assert "Masažna sjedala" in client.get(f"/vozila/{vehicle.slug}").text
    form = client.get("/admin/vozila/novo").text
    assert f'value="{codes["Hladnjak"]}"' in form  # offered as a checkbox from now on


def test_management_rename_and_delete(client, db):
    _owner(client)
    _post_new(client, db, color="__new__", color__new="Mat zelena")
    option = db.scalar(select(CustomOption))
    page = client.get("/admin/katalog/opcije")
    assert "Mat zelena" in page.text and "u upotrebi" in page.text
    token = csrf_from(page.text)
    client.post(
        f"/admin/katalog/opcije/{option.id}", data={"csrf_token": token, "label": "Zelena mat"}
    )
    db.expire_all()
    assert db.get(CustomOption, option.id).label == "Zelena mat"
    client.post(f"/admin/katalog/opcije/{option.id}/obrisi", data={"csrf_token": token})
    assert db.get(CustomOption, option.id) is not None  # still used by a vehicle
    db.query(Vehicle).delete()
    db.commit()
    client.post(f"/admin/katalog/opcije/{option.id}/obrisi", data={"csrf_token": token})
    db.expunge_all()
    assert db.query(CustomOption).count() == 0
    actions = set(db.scalars(select(AuditLog.action)))
    assert {"option.create", "option.update", "option.delete"} <= actions


def test_salesperson_can_add_and_manage_like_the_catalog(client, db):
    user_id, _ = create_user("prodavac@test.hr", role="salesperson")
    login_as(client, user_id)
    assert _post_new(client, db, color="__new__", color__new="Mat zelena").status_code == 303
    assert client.get("/admin/katalog/opcije").status_code == 200  # catalog: all roles


def test_cache_sees_options_from_other_workers(db):
    custom_options.refresh()
    db.add(CustomOption(scope="color", code="petrolej", label="Petrolej"))
    db.commit()
    custom_options.refresh()  # the vehicle form refreshes before validating
    assert ("petrolej", "Petrolej") in custom_options.extra_options("color")


# ---------------------------------------------------------------------------
# Electric vehicles: kWh/100 km instead of l/100 km
# ---------------------------------------------------------------------------
NEW_CAR = {
    "condition": "new",
    "year": "2026",
    "mileage_km": "10",
    "price_eur": "45000",
    "tax_type": "pdv",
    "transmission": "automatski",
}


def test_electric_needs_kwh_not_litres():
    _, errors = validate_common("car", dict(NEW_CAR, fuel="elektricni"))
    assert "energy_consumption_kwh100" in errors
    assert "fuel_consumption_l100" not in errors and "co2_g_km" not in errors
    clean, errors = validate_common(
        "car",
        dict(
            NEW_CAR,
            fuel="elektricni",
            energy_consumption_kwh100="16,8",
            electric_range_km="480",
            battery_kwh="77",
            fuel_consumption_l100="23",  # left in a hidden field: ignored
        ),
    )
    assert errors == {}
    assert clean["energy_consumption_kwh100"] == 16.8 and clean["fuel_consumption_l100"] is None
    assert clean["electric_range_km"] == 480 and clean["battery_kwh"] == 77


def test_petrol_ignores_electric_fields_and_plugin_needs_both():
    clean, errors = validate_common(
        "car",
        dict(
            NEW_CAR,
            fuel="benzin",
            fuel_consumption_l100="6,1",
            co2_g_km="139",
            energy_consumption_kwh100="15",
        ),
    )
    assert errors == {} and clean["energy_consumption_kwh100"] is None
    _, errors = validate_common("car", dict(NEW_CAR, fuel="plugin_hibrid"))
    assert {"fuel_consumption_l100", "co2_g_km", "energy_consumption_kwh100"} <= set(errors)


def test_form_marks_fields_by_fuel(client, db):
    _owner(client)
    html = client.get("/admin/vozila/novo").text
    assert ' data-hide-fuels="elektricni"' in html  # separate attribute (not glued to another)
    assert 'data-fuels="elektricni plugin_hibrid"' in html
    assert "kWh/100 km" in html and "data-fuel-select" in html
