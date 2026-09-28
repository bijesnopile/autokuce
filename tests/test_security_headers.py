"""Security headers, CSP, cookies and the "no inline scripts" rule (spec chapter 13)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.helpers import PASSWORD, create_user, get_csrf, login_via_ui, make_vehicle

TEMPLATES = Path(__file__).resolve().parent.parent / "app" / "templates"
SCRIPT_TAG_RE = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.S | re.I)


def csp_directives(response) -> dict[str, list[str]]:
    policy = response.headers["content-security-policy"]
    directives = {}
    for part in policy.split(";"):
        tokens = part.split()
        if tokens:
            directives[tokens[0]] = tokens[1:]
    return directives


@pytest.fixture
def vehicle(db):
    return make_vehicle(db)


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/vozila",
        "/kontakt",
        "/privatnost",
        "/admin/prijava",
        "/zdravlje",
        "/sitemap.xml",
        "/robots.txt",
        "/static/css/public.css",
        "/ne-postoji",
    ],
)
def test_headers_on_every_response(client, path):
    response = client.get(path)
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "camera=()" in response.headers["permissions-policy"]
    assert "content-security-policy" in response.headers
    # HTTPS=false in tests -> no HSTS (it would break plain-HTTP local development)
    assert "strict-transport-security" not in response.headers


def test_csp_matches_spec(client):
    d = csp_directives(client.get("/"))
    assert d["default-src"] == ["'self'"]
    assert "'unsafe-inline'" not in d["script-src"] and "'unsafe-eval'" not in d["script-src"]
    assert d["script-src"] == ["'self'"]  # nothing external unless Turnstile/Umami are set
    assert d["style-src"] == ["'self'", "'unsafe-inline'"]
    assert d["img-src"][:2] == ["'self'", "data:"]
    assert d["frame-src"] == ["https://www.youtube-nocookie.com"]
    assert d["frame-ancestors"] == ["'none'"]
    assert d["object-src"] == ["'none'"]
    assert d["base-uri"] == ["'self'"] and d["form-action"] == ["'self'"]


def test_csp_adds_configured_hosts_only():
    from types import SimpleNamespace

    from app.main import build_csp

    cfg = SimpleNamespace(
        TURNSTILE_SITE_KEY="0x4AAA",
        umami_enabled=True,
        UMAMI_SCRIPT_URL="https://analytics.primjer.hr/script.js",
        MEDIA_URL="https://media.primjer.hr",
        STORAGE_BACKEND="s3",
        S3_ENDPOINT="https://x.r2.cloudflarestorage.com",
    )
    csp = build_csp(cfg)
    assert "script-src 'self' https://challenges.cloudflare.com https://analytics.primjer.hr" in csp
    assert "img-src 'self' data: https://media.primjer.hr" in csp
    assert "frame-src https://challenges.cloudflare.com https://www.youtube-nocookie.com" in csp
    assert "unsafe-inline" not in csp.split("style-src")[0]


def test_hsts_and_secure_cookies_only_with_https(monkeypatch):
    from app.config import get_settings
    from app.main import create_app

    monkeypatch.setattr(get_settings(), "HTTPS", True)
    create_user("hsts@test.hr", role="owner")
    with TestClient(create_app(), base_url="https://testserver") as client:
        response = client.get("/")
        assert response.headers["strict-transport-security"].startswith("max-age=31536000")
        token = get_csrf(client)
        response = client.post(
            "/admin/prijava",
            data={"email": "hsts@test.hr", "password": PASSWORD, "csrf_token": token},
            follow_redirects=False,
        )
        cookie = response.headers["set-cookie"].lower()
        assert "secure" in cookie and "httponly" in cookie
        assert "samesite=lax" in cookie and "path=/admin" in cookie


def test_admin_session_cookie_flags(client):
    user_id, secret = create_user("kolacic@test.hr", role="owner")
    response = login_via_ui(client, "kolacic@test.hr", PASSWORD, secret)
    cookies = response.headers.get_list("set-cookie")
    session = next(c for c in cookies if c.startswith("session="))
    lowered = session.lower()
    assert "httponly" in lowered and "samesite=lax" in lowered and "path=/admin" in lowered
    assert "max-age=43200" in lowered  # 12 h
    assert "secure" not in lowered  # HTTPS=false in tests


def test_admin_pages_are_noindex_and_not_cached(client):
    response = client.get("/admin/prijava")
    assert response.headers["x-robots-tag"] == "noindex, nofollow"
    assert response.headers["cache-control"] == "no-store"
    assert '<meta name="robots" content="noindex' in response.text


@pytest.mark.parametrize("path", ["/", "/vozila", "/kontakt", "/o-nama", "/admin/prijava"])
def test_no_inline_scripts_in_rendered_pages(client, vehicle, path):
    for attrs, body in SCRIPT_TAG_RE.findall(client.get(path).text):
        if "src=" in attrs:
            assert not body.strip()
        else:
            # Only data blocks are allowed inline (JSON-LD, consent placeholders).
            assert re.search(r'type="(application/ld\+json|text/plain)"', attrs), attrs


def test_no_inline_scripts_on_vehicle_detail(client, vehicle):
    html = client.get(f"/vozila/{vehicle.slug}").text
    tags = SCRIPT_TAG_RE.findall(html)
    assert any("application/ld+json" in attrs for attrs, _ in tags)
    for attrs, _body in tags:
        assert "src=" in attrs or "application/ld+json" in attrs


def test_templates_have_no_inline_event_handlers_or_javascript_urls():
    offenders = []
    for path in TEMPLATES.rglob("*.html"):
        if path.parts[-2] == "emails":
            continue  # emails never run scripts; checked separately for external resources
        text = path.read_text(encoding="utf-8")
        if re.search(r"\son[a-z]+\s*=", text) or "javascript:" in text.lower():
            offenders.append(str(path.relative_to(TEMPLATES)))
    assert offenders == []


def test_health_endpoint_reveals_nothing(client):
    response = client.get("/zdravlje")
    assert response.status_code == 200
    body = response.text.lower()
    for secret in ("python", "fastapi", "sqlite", "postgres", "version", "secret"):
        assert secret not in body
