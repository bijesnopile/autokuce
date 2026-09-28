"""Phase 2: user management, roles, invitations, profile."""

from __future__ import annotations

from sqlalchemy import select

from app.models import AuditLog, User, UserSession
from tests.helpers import (
    PASSWORD,
    create_user,
    csrf_from,
    eml_text,
    find_link,
    get_csrf,
    login_as,
    outbox,
    read_eml,
    totp_now,
)


def test_salesperson_cannot_access_users_or_audit(client):
    user_id, _ = create_user("prodavac@test.hr", role="salesperson")
    login_as(client, user_id)
    for path in ("/admin/korisnici", "/admin/korisnici/novi", "/admin/audit"):
        response = client.get(path)
        assert response.status_code == 403
        assert "Pristup nije dopušten" in response.text


def test_salesperson_sidebar_hides_restricted_items(client):
    user_id, _ = create_user("prodavac@test.hr", role="salesperson")
    login_as(client, user_id)
    html = client.get("/admin").text
    assert 'href="/admin/vozila"' in html
    assert 'href="/admin/korisnici"' not in html
    assert 'href="/admin/postavke"' not in html


def test_owner_invites_user_and_invite_flow_works(client, db):
    owner_id, _ = create_user("vlasnik@test.hr", role="owner")
    login_as(client, owner_id)
    token = get_csrf(client, "/admin/korisnici/novi")
    response = client.post(
        "/admin/korisnici/novi",
        data={
            "email": "Novi@Test.hr",
            "name": "Prodavač 1",
            "role": "salesperson",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    new_user = db.scalar(select(User).where(User.email == "novi@test.hr"))
    assert new_user and new_user.password_hash is None and new_user.role == "salesperson"

    message = read_eml(outbox()[0])
    link = find_link(eml_text(message), "http://testserver/admin/lozinka/postavi/")
    path = link.replace("http://testserver", "")
    client.cookies.clear()
    form = client.get(path)
    assert "Dobrodošli" in form.text
    pw = "Prodavac-Lozinka-2026"
    client.post(
        path, data={"password": pw, "password_confirm": pw, "csrf_token": csrf_from(form.text)}
    )
    db.expire_all()
    assert db.get(User, new_user.id).password_hash
    # First login -> forced 2FA setup.
    token = get_csrf(client)
    response = client.post(
        "/admin/prijava",
        data={"email": "novi@test.hr", "password": pw, "csrf_token": token},
        follow_redirects=False,
    )
    assert response.headers["location"] == "/admin/2fa/postavljanje"
    assert db.scalar(select(AuditLog).where(AuditLog.action == "user.invite"))


def test_owner_cannot_create_or_edit_superadmin(client, db):
    owner_id, _ = create_user("vlasnik@test.hr", role="owner")
    admin = db.scalar(select(User).where(User.role == "superadmin"))  # seeded
    login_as(client, owner_id)
    assert client.get(f"/admin/korisnici/{admin.id}").status_code == 403
    token = get_csrf(client, "/admin/korisnici/novi")
    response = client.post(
        "/admin/korisnici/novi",
        data={"email": "x@test.hr", "name": "X Y", "role": "superadmin", "csrf_token": token},
    )
    assert response.status_code == 400
    response = client.post(f"/admin/korisnici/{admin.id}/deaktiviraj", data={"csrf_token": token})
    assert response.status_code == 403


def test_nobody_can_change_own_role_or_deactivate_self(client, db):
    owner_id, _ = create_user("vlasnik@test.hr", role="owner")
    login_as(client, owner_id)
    token = get_csrf(client, f"/admin/korisnici/{owner_id}")
    client.post(
        f"/admin/korisnici/{owner_id}",
        data={"name": "Novo Ime", "role": "salesperson", "csrf_token": token},
    )
    client.post(f"/admin/korisnici/{owner_id}/deaktiviraj", data={"csrf_token": token})
    db.expire_all()
    owner = db.get(User, owner_id)
    assert owner.role == "owner" and owner.is_active and owner.name == "Novo Ime"


def test_last_superadmin_cannot_be_demoted(client, db):
    admin = db.scalar(select(User).where(User.role == "superadmin"))
    other_id, _ = create_user("drugi-admin@test.hr", role="superadmin")
    login_as(client, other_id)
    token = get_csrf(client, f"/admin/korisnici/{admin.id}")
    # With two superadmins, demoting one works.
    client.post(
        f"/admin/korisnici/{admin.id}",
        data={"name": "Administrator", "role": "owner", "csrf_token": token},
    )
    db.expire_all()
    assert db.get(User, admin.id).role == "owner"
    # Deactivating the last active superadmin (self) is blocked anyway.
    client.post(f"/admin/korisnici/{other_id}/deaktiviraj", data={"csrf_token": token})
    db.expire_all()
    assert db.get(User, other_id).is_active


def test_deactivate_user_kills_sessions(client, db):
    owner_id, _ = create_user("vlasnik@test.hr", role="owner")
    seller_id, _ = create_user("prodavac@test.hr", role="salesperson")
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as seller_client:
        login_as(seller_client, seller_id)
        assert seller_client.get("/admin").status_code == 200
        login_as(client, owner_id)
        token = get_csrf(client, f"/admin/korisnici/{seller_id}")
        client.post(f"/admin/korisnici/{seller_id}/deaktiviraj", data={"csrf_token": token})
        assert seller_client.get("/admin", follow_redirects=False).status_code == 303
    assert db.query(UserSession).filter_by(user_id=seller_id).count() == 0


def test_owner_resets_2fa_of_user(client, db):
    owner_id, _ = create_user("vlasnik@test.hr", role="owner")
    seller_id, _ = create_user("prodavac@test.hr", role="salesperson")
    login_as(client, owner_id)
    token = get_csrf(client, f"/admin/korisnici/{seller_id}")
    client.post(f"/admin/korisnici/{seller_id}/reset-2fa", data={"csrf_token": token})
    db.expire_all()
    seller = db.get(User, seller_id)
    assert not seller.totp_enabled and seller.totp_secret is None
    entry = db.scalar(select(AuditLog).where(AuditLog.action == "user.2fa_reset"))
    assert entry.user_id == owner_id and entry.entity_id == str(seller_id)


def test_profile_password_change_closes_other_sessions(client, db):
    user_id, _ = create_user("vlasnik@test.hr")
    login_as(client, user_id)  # other device
    login_as(client, user_id)  # this device
    page = client.get("/admin/profil")
    assert "Aktivne sesije" in page.text
    new = "Potpuno-Nova-Lozinka-9"
    response = client.post(
        "/admin/profil/lozinka",
        data={
            "current_password": PASSWORD,
            "new_password": new,
            "new_password_confirm": new,
            "csrf_token": csrf_from(page.text),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert db.query(UserSession).filter_by(user_id=user_id).count() == 1
    assert client.get("/admin").status_code == 200


def test_profile_2fa_resetup_requires_current_code(client, db):
    user_id, secret = create_user("vlasnik@test.hr")
    login_as(client, user_id)
    page = client.get("/admin/profil")
    bad = client.post(
        "/admin/profil/2fa", data={"code": "000000", "csrf_token": csrf_from(page.text)}
    )
    assert bad.status_code == 400
    ok = client.post(
        "/admin/profil/2fa",
        data={"code": totp_now(secret), "csrf_token": csrf_from(page.text)},
        follow_redirects=False,
    )
    assert ok.headers["location"] == "/admin/2fa/postavljanje"
    setup = client.get("/admin/2fa/postavljanje")
    assert setup.status_code == 200 and "data:image/png" in setup.text


def test_audit_page_filters(client, db):
    owner_id, _ = create_user("vlasnik@test.hr")
    login_as(client, owner_id)
    from app.services import audit

    audit.log(db, owner_id, "user.update", "user", owner_id, {"fields": ["name"]})
    audit.log(db, None, "system.maintenance")
    db.commit()
    page = client.get("/admin/audit?akcija=user.update")
    assert page.status_code == 200
    assert "Izmjena korisnika" in page.text
    assert "Održavanje" not in page.text.split("<tbody>")[1]
