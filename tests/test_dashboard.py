"""Dashboard and statistics (phase 7)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.database import utcnow
from app.models import (
    Inquiry,
    VehicleView,
)
from app.services.newsletter import add_manual
from app.utils import local_today
from tests.helpers import create_user, login_as, make_vehicle


@pytest.fixture
def owner(client):
    user_id, _ = create_user("vlasnik@test.hr", role="owner")
    login_as(client, user_id)
    return user_id


def test_dashboard_numbers(client, db, owner):
    active = make_vehicle(db, model_name="A1")
    make_vehicle(db, model_name="A2", status="reserved")
    make_vehicle(db, model_name="A3", status="draft")
    db.add_all(
        [
            VehicleView(vehicle_id=active.id, date=local_today(), count=7),
            VehicleView(vehicle_id=active.id, date=local_today() - timedelta(days=3), count=5),
            VehicleView(vehicle_id=active.id, date=local_today() - timedelta(days=40), count=4),
            Inquiry(
                type="general",
                name="Ime Prezime",
                email="a@primjer.hr",
                message="x" * 20,
                status="new",
                created_at=utcnow() - timedelta(days=3),
            ),
            Inquiry(
                type="general",
                name="Ime Prezime",
                email="b@primjer.hr",
                message="x" * 20,
                status="closed",
            ),
        ]
    )
    add_manual(db, "c@primjer.hr", "obrazac u salonu")
    db.commit()
    html = client.get("/admin").text
    assert '<div class="stat-value">1</div>' in html  # active vehicles, new inquiries...
    assert "1 rezervirano · 1 skica" in html
    assert "1 bez odgovora &gt; 48 h" in html
    assert '<div class="stat-value">12</div>' in html  # views last 30 days (7 + 5)
    assert "<svg" in html and "chart-bar" in html
    assert "Skice bez fotografija" in html and "Aktivna vozila bez fotografija" in html


def test_statistics_page_and_csv(client, db, owner):
    vehicle = make_vehicle(db)
    db.add(VehicleView(vehicle_id=vehicle.id, date=local_today(), count=20))
    db.add(
        Inquiry(
            type="vehicle",
            vehicle_id=vehicle.id,
            name="Ime Prezime",
            email="a@primjer.hr",
            message="x" * 20,
            status="contacted",
            created_at=utcnow() - timedelta(hours=5),
            contacted_at=utcnow() - timedelta(hours=3),
        )
    )
    db.commit()
    for days in (30, 90, 365):
        html = client.get(f"/admin/statistika?razdoblje={days}").text
        assert "Pregledi po danu" in html and vehicle.title in html
    html = client.get("/admin/statistika").text
    assert "5,0 %" in html  # conversion 1 inquiry / 20 views
    assert "2,0 h" in html  # average time to first contact
    response = client.get("/admin/statistika/izvoz.csv?tablica=vozila")
    assert response.content.startswith(b"\xef\xbb\xbf")
    text = response.content.decode("utf-8-sig")
    assert text.splitlines()[0] == (
        "ID;Vozilo;Status;Pregledi;Upiti;Kontakti (WhatsApp/Viber);Konverzija (%)"
    )
    assert f"{vehicle.id};{vehicle.title};active;20;1;0;5,0" in text
    seller_id, _ = create_user("prodavac@test.hr", role="salesperson")
    login_as(client, seller_id)
    assert client.get("/admin/statistika").status_code == 200
    assert client.get("/admin/statistika/izvoz.csv").status_code == 403


def test_chart_ticks_are_whole_numbers():
    import re

    from app.services.charts import _divisions, paired_bar_chart

    for max_value in (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000):
        assert max_value % _divisions(max_value) == 0
    svg = str(paired_bar_chart([("06.07.", 2, 0), ("13.07.", 1, 1)], "Newsletter"))
    labels = re.findall(r'text-anchor="end">([^<]+)<', svg)
    assert labels == ["0", "1", "2"]
