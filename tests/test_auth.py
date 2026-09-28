"""Phase 2: login, lockout, mandatory 2FA, recovery codes, sessions, password reset."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.database import utcnow
from app.models import AuditLog, EmailLog, User, UserSession
from app.security import decrypt_secret, email_hash
from tests.helpers import (
    PASSWORD,
    create_user,
    csrf_from,
    eml_text,
    find_link,
    get_csrf,
    login_as,
    login_via_ui,
    outbox,
    read_eml,
    totp_now,
)


def _post_login(client, email, password):
    token = get_csrf(client)
    return client.post(
        "/admin/prijava",
        data={"email": email, "password": password, "csrf_token": token},
        follow_redirects=False,
    )


def test_admin_requires_login(client):
    for path in ("/admin", "/admin/vozila", "/admin/korisnici", "/admin/profil"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"].startswith("/admin/prijava?next=")


def test_login_page_renders_with_noindex(client):
    response = client.get("/admin/prijava")
    assert response.status_code == 200
    assert "Prijava u administraciju" in response.text
    assert 'name="robots" content="noindex' in response.text
    assert response.headers["x-robots-tag"].startswith("noindex")


def test_wrong_password_same_message_as_unknown_email(client):
    create_user("vlasnik@test.hr")
    wrong_password = _post_login(client, "vlasnik@test.hr", "kriva-lozinka-123")
    unknown_email = _post_login(client, "nepostoji@test.hr", "kriva-lozinka-123")
    assert wrong_password.status_code == unknown_email.status_code == 400

    def error_text(html):
        return html.split('class="alert alert-error"')[1].split("</div>")[0]

    assert error_text(wrong_password.text) == error_text(unknown_email.text)


def test_lockout_after_five_failed_attempts(client, db):
    user_id, _secret = create_user("vlasnik@test.hr")
    for _ in range(5):
        assert _post_login(client, "vlasnik@test.hr", "kriva-lozinka-123").status_code == 400
    user = db.get(User, user_id)
    assert user.locked_until is not None and user.locked_until > utcnow()
    # Even the correct password is rejected while locked.
    response = _post_login(client, "vlasnik@test.hr", PASSWORD)
    assert response.status_code == 400
    # After the lock expires, login works again.
    user.locked_until = utcnow() - timedelta(seconds=1)
    db.commit()
    assert _post_login(client, "vlasnik@test.hr", PASSWORD).status_code == 303


def test_login_rate_limit(client):
    create_user("vlasnik@test.hr")
    statuses = [
        _post_login(client, "x@test.hr", "kriva-lozinka-123").status_code for _ in range(11)
    ]
    assert statuses[-1] == 429


def test_login_without_2fa_redirects_to_forced_setup(client):
    create_user("novi@test.hr", totp=False)
    response = _post_login(client, "novi@test.hr", PASSWORD)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/2fa/postavljanje"
    page = client.get("/admin/2fa/postavljanje")
    assert page.status_code == 200
    assert "data:image/png;base64," in page.text  # QR code
    assert "Ključ za ručni unos" in page.text
    # No session yet — the dashboard still requires login.
    assert client.get("/admin", follow_redirects=False).status_code == 303


def test_full_2fa_setup_flow_reaches_dashboard(client, db):
    user_id, _ = create_user("novi@test.hr", totp=False)
    _post_login(client, "novi@test.hr", PASSWORD)
    page = client.get("/admin/2fa/postavljanje")
    secret = decrypt_secret(db.get(User, user_id).totp_secret)
    response = client.post(
        "/admin/2fa/postavljanje",
        data={"code": totp_now(secret), "csrf_token": csrf_from(page.text)},
    )
    assert response.status_code == 200
    assert "Kodovi se prikazuju samo sada" in response.text
    assert response.text.count("<li>") >= 10
    db.expire_all()
    user = db.get(User, user_id)
    assert user.totp_enabled and len(user.recovery_codes) == 10
    assert all(code.startswith("$argon2") for code in user.recovery_codes)
    dashboard = client.get("/admin")
    assert dashboard.status_code == 200
    assert "Nadzorna ploča" in dashboard.text


def test_wrong_setup_code_is_rejected(client):
    create_user("novi@test.hr", totp=False)
    _post_login(client, "novi@test.hr", PASSWORD)
    page = client.get("/admin/2fa/postavljanje")
    response = client.post(
        "/admin/2fa/postavljanje", data={"code": "000000", "csrf_token": csrf_from(page.text)}
    )
    assert response.status_code == 400
    assert "Kod nije ispravan" in response.text


def test_totp_login_and_replay_protection(client):
    _, secret = create_user("vlasnik@test.hr")
    response = login_via_ui(client, "vlasnik@test.hr", PASSWORD, secret)
    assert response.status_code == 303 and response.headers["location"] == "/admin"
    assert client.get("/admin").status_code == 200
    # Log out and try the very same code again -> rejected (replay).
    client.post("/admin/odjava", data={"csrf_token": get_csrf(client, "/admin")})
    replay = login_via_ui(client, "vlasnik@test.hr", PASSWORD, secret)
    assert replay.status_code == 400


def test_recovery_code_works_only_once(client, db):
    codes = ["abcd-efgh-jkmn", "pqrs-tuvw-xyz2"]
    user_id, _ = create_user("vlasnik@test.hr", recovery_codes=codes)

    def login_with_code(code):
        _post_login(client, "vlasnik@test.hr", PASSWORD)
        token = get_csrf(client, "/admin/prijava/2fa")
        return client.post(
            "/admin/prijava/2fa", data={"code": code, "csrf_token": token}, follow_redirects=False
        )

    assert login_with_code(codes[0]).status_code == 303
    client.cookies.clear()
    assert login_with_code(codes[0]).status_code == 400
    db.expire_all()
    assert len(db.get(User, user_id).recovery_codes) == 1


def test_twofa_page_without_pending_cookie_redirects(client):
    response = client.get("/admin/prijava/2fa", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/prijava"


def test_post_without_csrf_is_forbidden(client):
    create_user("vlasnik@test.hr")
    response = client.post(
        "/admin/prijava", data={"email": "vlasnik@test.hr", "password": PASSWORD}
    )
    assert response.status_code == 403
    user_id, _ = create_user("drugi@test.hr")
    login_as(client, user_id)
    assert client.post("/admin/odjava-svugdje", data={}).status_code == 403
    assert client.post("/admin/odjava-svugdje", data={"csrf_token": "krivi"}).status_code == 403


def test_logout_everywhere_invalidates_other_sessions(client, db):
    user_id, _ = create_user("vlasnik@test.hr")
    login_as(client, user_id)  # "other device"
    login_as(client, user_id)  # this device (cookie overwritten)
    assert db.query(UserSession).filter_by(user_id=user_id).count() == 2
    response = client.post(
        "/admin/odjava-svugdje",
        data={"csrf_token": get_csrf(client, "/admin/profil")},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert db.query(UserSession).filter_by(user_id=user_id).count() == 0
    assert client.get("/admin", follow_redirects=False).status_code == 303


def test_expired_session_redirects_to_login(client, db):
    user_id, _ = create_user("vlasnik@test.hr")
    login_as(client, user_id)
    session = db.scalar(select(UserSession).where(UserSession.user_id == user_id))
    session.expires_at = utcnow() - timedelta(minutes=1)
    db.commit()
    assert client.get("/admin", follow_redirects=False).status_code == 303


def test_session_without_2fa_is_forced_to_setup(client, db):
    user_id, _ = create_user("vlasnik@test.hr")
    login_as(client, user_id)
    user = db.get(User, user_id)
    user.totp_enabled = False
    db.commit()
    response = client.get("/admin", follow_redirects=False)
    assert response.headers["location"] == "/admin/2fa/postavljanje"


def test_password_reset_flow_via_outbox(client, db):
    user_id, secret = create_user("vlasnik@test.hr")
    token = get_csrf(client, "/admin/lozinka/zaboravljena")
    response = client.post(
        "/admin/lozinka/zaboravljena", data={"email": "vlasnik@test.hr", "csrf_token": token}
    )
    assert "Ako račun s tom adresom postoji" in response.text
    files = outbox()
    assert len(files) == 1
    message = read_eml(files[0])
    assert message["To"] == "vlasnik@test.hr"
    link = find_link(eml_text(message), "http://testserver/admin/lozinka/nova/")
    path = link.replace("http://testserver", "")

    form = client.get(path)
    assert form.status_code == 200
    new_password = "Nova-Sigurna-Lozinka-77"
    response = client.post(
        path,
        data={
            "password": new_password,
            "password_confirm": new_password,
            "csrf_token": csrf_from(form.text),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    # Token is single use.
    assert client.get(path).status_code == 400
    # Login with the new password works (2FA still required).
    assert _post_login(client, "vlasnik@test.hr", new_password).status_code == 303
    # email_log stores only the hash of the recipient.
    log_entry = db.scalar(select(EmailLog))
    assert log_entry.to_hash == email_hash("vlasnik@test.hr")
    assert "vlasnik@test.hr" not in (log_entry.error or "")


def test_forgot_password_unknown_email_same_message_no_email(client):
    token = get_csrf(client, "/admin/lozinka/zaboravljena")
    response = client.post(
        "/admin/lozinka/zaboravljena", data={"email": "nepostoji@test.hr", "csrf_token": token}
    )
    assert "Ako račun s tom adresom postoji" in response.text
    assert outbox() == []


def test_weak_password_rejected_on_reset(client, db):
    from app.services.auth import create_auth_token

    user_id, _ = create_user("vlasnik@test.hr")
    raw = create_auth_token(db, db.get(User, user_id), "reset", 1)
    db.commit()
    form = client.get(f"/admin/lozinka/nova/{raw}")
    for weak in ("kratka", "password1234"):
        response = client.post(
            f"/admin/lozinka/nova/{raw}",
            data={"password": weak, "password_confirm": weak, "csrf_token": csrf_from(form.text)},
        )
        assert response.status_code == 400


def test_audit_entries_are_created(client, db):
    _, secret = create_user("vlasnik@test.hr")
    _post_login(client, "vlasnik@test.hr", "kriva-lozinka-123")
    login_via_ui(client, "vlasnik@test.hr", PASSWORD, secret)
    client.post("/admin/odjava", data={"csrf_token": get_csrf(client, "/admin")})
    actions = [a.action for a in db.scalars(select(AuditLog).order_by(AuditLog.id))]
    assert "user.login_failed" in actions
    assert "user.login" in actions
    assert "user.logout" in actions
    failed = db.scalar(select(AuditLog).where(AuditLog.action == "user.login_failed"))
    assert "vlasnik@test.hr" not in str(failed.details)
    assert failed.details["email_hash"] == email_hash("vlasnik@test.hr")


def test_open_redirect_is_blocked(client):
    _, secret = create_user("vlasnik@test.hr")
    token = get_csrf(client, "/admin/prijava?next=https://zlo.example")
    client.post(
        "/admin/prijava",
        data={
            "email": "vlasnik@test.hr",
            "password": PASSWORD,
            "csrf_token": token,
            "next": "//zlo.example",
        },
    )
    token = get_csrf(client, "/admin/prijava/2fa")
    response = client.post(
        "/admin/prijava/2fa",
        data={"code": totp_now(secret), "csrf_token": token},
        follow_redirects=False,
    )
    assert response.headers["location"] == "/admin"


def test_admin_ip_allowlist_middleware():
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route
    from starlette.testclient import TestClient

    from app.main import AdminIPAllowlistMiddleware

    inner = Starlette(routes=[Route("/admin", lambda r: PlainTextResponse("ok"))])
    blocked = TestClient(AdminIPAllowlistMiddleware(inner, "10.0.0.0/8"))
    assert blocked.get("/admin").status_code == 403  # testclient host is not in 10/8
    allowed = TestClient(AdminIPAllowlistMiddleware(inner, "10.0.0.0/8, testclient"))
    assert allowed.get("/admin").status_code == 403  # invalid entry ignored, still blocked
    open_app = TestClient(AdminIPAllowlistMiddleware(inner, ""))
    assert open_app.get("/admin").status_code == 200


def test_totp_secret_is_encrypted_at_rest(client, db):
    user_id, secret = create_user("tajna@test.hr")
    stored = db.get(User, user_id).totp_secret
    assert secret not in stored and len(stored) > len(secret)
    assert decrypt_secret(stored) == secret
