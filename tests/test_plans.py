"""Paketi (Osnovni/Standard/Premium): has_feature, require_feature, badges, limits, override."""

from __future__ import annotations

import pytest

from app import plans
from app.config import get_settings
from app.services.site import invalidate_site_cache, set_values
from tests.helpers import create_user, csrf_from, login_as


@pytest.fixture
def plan(monkeypatch):
    """Set the PLAN env value for a test (no override)."""

    def _set(value: str):
        monkeypatch.setattr(get_settings(), "PLAN", value)
        invalidate_site_cache()

    return _set


def test_has_feature_per_plan():
    assert not plans.has_feature("whatsapp", "osnovni")
    assert plans.has_feature("whatsapp", "standard")
    assert plans.has_feature("feed_portali", "premium")
    assert not plans.has_feature("ugovor_pdf", "premium")  # planned only
    assert not plans.has_feature("does-not-exist", "premium")
    for code in (
        "whatsapp",
        "izlog_kartica",
        "ponuda_pdf",
        "auto_odgovor",
        "kalendar_termin",
        "kalkulator_rate",
        "upit_financiranje",
        "feed_portali",
        "korisnici_5",
    ):
        assert code in plans.FEATURES and plans.required_plan(code) == "standard"


def test_invalid_plan_value_is_rejected():
    from pydantic import ValidationError

    from app.config import Settings

    with pytest.raises(ValidationError):
        Settings(_env_file=None, PLAN="gold")
    assert Settings(_env_file=None, PLAN=" Standard ").PLAN == "standard"


def test_default_plan_is_osnovni_and_override_wins(db, plan):
    plan("osnovni")
    assert plans.current_plan() == "osnovni"
    set_values(db, {"plan_override": "premium"})
    db.commit()
    invalidate_site_cache()
    assert plans.current_plan() == "premium" and plans.plan_override() == "premium"
    set_values(db, {"plan_override": "nonsense"})
    db.commit()
    invalidate_site_cache()
    assert plans.current_plan() == "osnovni"  # invalid override is ignored


def test_locked_admin_route_shows_plan_page(client, plan):
    plan("osnovni")
    owner_id, _ = create_user("vlasnik@test.hr", role="owner")
    login_as(client, owner_id)
    response = client.get("/admin/feed")
    assert response.status_code == 403
    assert "Dostupno u paketu Standard" in response.text
    assert "Feed prema portalima" in response.text  # feature label + description
    plan("standard")
    assert client.get("/admin/feed").status_code == 200


def test_sidebar_badge_only_when_locked(client, plan):
    owner_id, _ = create_user("vlasnik@test.hr", role="owner")
    login_as(client, owner_id)
    plan("osnovni")
    html = client.get("/admin").text
    assert 'href="/admin/feed"' in html  # locked items stay visible
    assert 'class="plan-badge"' in html.split('href="/admin/feed"')[1].split("</li>")[0]
    plan("standard")
    html = client.get("/admin").text
    assert 'class="plan-badge"' not in html.split('href="/admin/feed"')[1].split("</li>")[0]


def test_public_feature_dependency_returns_404(plan):
    import asyncio

    from fastapi import HTTPException

    from app.deps import public_feature

    plan("osnovni")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(public_feature("whatsapp")())
    assert exc.value.status_code == 404
    plan("standard")
    assert asyncio.run(public_feature("whatsapp")()) is None


def test_user_limit_enforced_on_invite_and_activation(client, db, plan):
    plan("osnovni")  # 2 users (superadmins do not count)
    owner_id, _ = create_user("vlasnik@test.hr", role="owner")
    create_user("prodavac@test.hr", role="salesperson")
    login_as(client, owner_id)
    page = client.get("/admin/korisnici/novi")
    response = client.post(
        "/admin/korisnici/novi",
        data={
            "email": "novi@test.hr",
            "name": "Novi Prodavač",
            "role": "salesperson",
            "csrf_token": csrf_from(page.text),
        },
    )
    assert response.status_code == 400 and "najviše 2 aktivnih korisnika" in response.text
    assert "paket Standard" in response.text
    listing = client.get("/admin/korisnici").text
    assert "2</strong> / 2" in listing and 'class="plan-badge"' in listing

    plan("standard")  # 5 users
    response = client.post(
        "/admin/korisnici/novi",
        data={
            "email": "novi@test.hr",
            "name": "Novi Prodavač",
            "role": "salesperson",
            "csrf_token": csrf_from(page.text),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    # Deactivated user cannot be re-activated past the limit.
    from app.models import User

    novi = db.query(User).filter_by(email="novi@test.hr").one()
    novi.is_active = False
    db.commit()
    plan("osnovni")
    page = client.get(f"/admin/korisnici/{novi.id}")
    client.post(f"/admin/korisnici/{novi.id}/aktiviraj", data={"csrf_token": csrf_from(page.text)})
    db.expire_all()
    assert db.get(User, novi.id).is_active is False


def test_plan_override_only_superadmin(client, db, plan):
    plan("osnovni")
    owner_id, _ = create_user("vlasnik@test.hr", role="owner")
    login_as(client, owner_id)
    token = csrf_from(client.get("/admin").text)
    assert (
        client.post(
            "/admin/sustav/paket", data={"plan": "premium", "csrf_token": token}
        ).status_code
        == 403
    )

    admin_id, _ = create_user("super@test.hr", role="superadmin")
    client.cookies.clear()
    login_as(client, admin_id)
    page = client.get("/admin/sustav")
    assert page.status_code == 200 and "Paket: Osnovni" in page.text
    response = client.post(
        "/admin/sustav/paket",
        data={"plan": "standard", "csrf_token": csrf_from(page.text)},
        follow_redirects=False,
    )
    assert response.status_code == 303
    invalidate_site_cache()
    assert plans.current_plan() == "standard"
    page = client.get("/admin/sustav").text
    assert "Nadjačavanje je aktivno." in page and "Paket: Standard" in page
    assert "uključeno" in page and "planirano" in page
    client.post("/admin/sustav/paket", data={"plan": "", "csrf_token": csrf_from(page)})
    invalidate_site_cache()
    assert plans.current_plan() == "osnovni"
