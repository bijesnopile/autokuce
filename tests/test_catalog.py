"""Phase 3: catalog of makes/models, CSV import, public models API, schema definitions."""

from __future__ import annotations

from sqlalchemy import select

from app.models import AuditLog, Make, VehicleModel
from app.routers.admin_catalog import analyse_csv, decode_csv
from app.utils import slugify
from tests.helpers import create_user, get_csrf, login_as, make_catalog, make_vehicle


def test_slugify_croatian_and_foreign_letters():
    assert slugify("Škoda Octavia 2.0 TDI") == "skoda-octavia-2-0-tdi"
    assert slugify("Citroën Č Ć Đ Ž") == "citroen-c-c-d-z"
    assert slugify("Mercedes-Benz") == "mercedes-benz"


def test_api_models_filters_by_make_type_and_active(client, db):
    make, octavia = make_catalog(db, "Škoda", "Octavia", "car")
    _, transit = make_catalog(db, "Škoda", "Transit X", "van")
    _, generic = make_catalog(db, "Škoda", "Univerzal")  # all types
    _, hidden = make_catalog(db, "Škoda", "Stari")
    hidden.is_active = False
    db.commit()

    names = [m["name"] for m in client.get(f"/api/modeli?marka={make.id}").json()]
    assert names == ["Octavia", "Transit X", "Univerzal"]
    names = [m["name"] for m in client.get(f"/api/modeli?marka={make.id}&tip=van").json()]
    assert names == ["Transit X", "Univerzal"]
    assert client.get("/api/modeli?marka=abc").json() == []


def test_admin_creates_make_and_model(client, db):
    user_id, _ = create_user("prodavac@test.hr", role="salesperson")  # catalog: all roles
    login_as(client, user_id)
    token = get_csrf(client, "/admin/katalog/marke")
    response = client.post(
        "/admin/katalog/marke",
        data={"name": "Citroën", "csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code == 303
    make = db.scalar(select(Make).where(Make.slug == "citroen"))
    assert make and make.name == "Citroën"
    client.post(
        f"/admin/katalog/marke/{make.id}/modeli",
        data={"name": "C5 Aircross", "vehicle_type": "car", "csrf_token": token},
    )
    model = db.scalar(select(VehicleModel).where(VehicleModel.make_id == make.id))
    assert model.slug == "c5-aircross" and model.vehicle_type == "car"
    # Duplicate model name is rejected.
    client.post(
        f"/admin/katalog/marke/{make.id}/modeli", data={"name": "C5 Aircross", "csrf_token": token}
    )
    assert db.query(VehicleModel).filter_by(make_id=make.id).count() == 1
    assert db.scalar(select(AuditLog).where(AuditLog.action == "catalog.make"))


def test_make_with_vehicles_cannot_be_deleted(client, db):
    user_id, _ = create_user("vlasnik@test.hr")
    vehicle = make_vehicle(db, user_id)
    login_as(client, user_id)
    token = get_csrf(client, "/admin/katalog/marke")
    client.post(f"/admin/katalog/marke/{vehicle.make_id}/obrisi", data={"csrf_token": token})
    db.expire_all()
    assert db.get(Make, vehicle.make_id) is not None


def test_csv_analysis_and_import(client, db):
    make_catalog(db, "Škoda", "Octavia", "car")
    text = (
        "marka;model;tip\nŠkoda;Octavia;osobni\nŠkoda;Fabia;osobni\nFord;Transit;kombi\n"
        "Ford;Transit;kombi\nYamaha;MT-07;motocikl\nX;;\nKTM;Duke;svemirski\n"
    )
    rows = analyse_csv(db, text)
    statuses = [(r["make"], r["model"], r["status"]) for r in rows]
    assert ("Škoda", "Octavia", "duplicate") in statuses
    assert ("Škoda", "Fabia", "new") in statuses
    assert statuses.count(("Ford", "Transit", "new")) == 1
    assert ("Ford", "Transit", "duplicate") in statuses
    assert sum(1 for r in rows if r["status"] == "error") == 2

    user_id, _ = create_user("vlasnik@test.hr")
    login_as(client, user_id)
    token = get_csrf(client, "/admin/katalog/uvoz")
    preview = client.post("/admin/katalog/uvoz", data={"csv_text": text, "csrf_token": token})
    assert preview.status_code == 200 and "Pregled" in preview.text
    client.post("/admin/katalog/uvoz", data={"csv_text": text, "confirm": "1", "csrf_token": token})
    assert db.scalar(select(Make).where(Make.slug == "yamaha"))
    transit = db.scalar(select(VehicleModel).where(VehicleModel.slug == "transit"))
    assert transit.vehicle_type == "van"
    assert db.query(VehicleModel).filter_by(slug="octavia").count() == 1


def test_csv_decoding_cp1250():
    data = "Škoda;Octavia;osobni".encode("cp1250")
    assert decode_csv(data).startswith("Škoda")
    assert decode_csv("Škoda".encode("utf-8-sig")) == "Škoda"


def test_types_overview_page(client):
    user_id, _ = create_user("vlasnik@test.hr")
    login_as(client, user_id)
    html = client.get("/admin/katalog/tipovi").text
    for label in (
        "Osobni automobil",
        "Kombi",
        "Motocikl",
        "Kamper",
        "Kamion",
        "Karoserija",
        "Tahograf",
        "Prikladan za A2",
    ):
        assert label in html
