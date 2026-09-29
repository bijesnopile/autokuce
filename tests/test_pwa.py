"""Faza 10 E: administracija kao aplikacija na telefonu (PWA)."""

from __future__ import annotations

import io
import json
import re
from types import SimpleNamespace

from PIL import Image

from app.services import pwa
from app.services.auth import SESSION_COOKIE
from app.services.images import save_logo
from app.services.site import invalidate_site_cache, set_values
from tests.helpers import create_user, image_bytes, login_as


def test_manifest_from_settings(client, db):
    set_values(db, {"company_name": "Auto Horvat Zagreb", "primary_color": "#0f766e"})
    db.commit()
    invalidate_site_cache()
    response = client.get("/admin/manifest.webmanifest")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/manifest+json")
    data = json.loads(response.text)
    assert data["name"] == "Auto Horvat Zagreb – Admin"
    assert len(data["short_name"]) <= 12 and data["short_name"] == "Auto Horvat"
    assert data["start_url"] == "/admin/" and data["scope"] == "/admin/"
    assert data["display"] == "standalone" and data["lang"] == "hr"
    assert data["theme_color"] == "#0f766e" and data["background_color"] == "#ffffff"
    sizes = {(i["sizes"], i.get("purpose", "any")) for i in data["icons"]}
    assert {("192x192", "any"), ("512x512", "any"), ("512x512", "maskable")} <= sizes


def test_icons_have_right_size_and_follow_the_logo(client, db):
    for size in (180, 192, 512):
        response = client.get(f"/admin/pwa-icon-{size}.png")
        assert response.status_code == 200 and response.headers["content-type"] == "image/png"
        assert Image.open(io.BytesIO(response.content)).size == (size, size)
    assert client.get("/admin/pwa-icon-64.png").status_code == 404
    letter_icon = client.get("/admin/pwa-icon-192.png").content

    key = save_logo(image_bytes("PNG", size=(600, 200), color=(20, 20, 20)))
    set_values(db, {"logo_key": key})
    db.commit()
    invalidate_site_cache()
    logo_icon = client.get("/admin/pwa-icon-192.png").content
    assert logo_icon != letter_icon

    set_values(db, {"primary_color": "#b91c1c"})
    db.commit()
    invalidate_site_cache()
    assert client.get("/admin/pwa-icon-192.png").content != logo_icon  # colour change
    image = Image.open(io.BytesIO(client.get("/admin/pwa-icon-512.png").content)).convert("RGB")
    assert image.getpixel((5, 5)) == (185, 28, 28)  # brand background (maskable safe margin)


def test_letter_icon():
    assert pwa._letter("IME PODUZEĆA") == "L"  # placeholder -> like the LOGO placeholder
    assert pwa._letter("Auto Horvat") == "A"
    assert pwa.short_name("IME PODUZEĆA") == "IME PODUZEĆA"


def test_service_worker_never_caches_admin_pages(client):
    response = client.get("/admin/sw.js")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/javascript")
    assert response.headers["service-worker-allowed"] == "/admin/"
    code = response.text
    # Static analysis: the only cache writes are guarded by the /static/ check.
    assert code.count("cache.put(") == 1
    assert 'url.pathname.startsWith("/static/")' in code
    assert "/admin" not in re.sub(r"/\*.*?\*/", "", code, flags=re.S).replace("/admin/", "")
    assert "event.respondWith(fetch(request))" in code
    assert "push" not in code.lower()


def test_admin_pages_link_the_manifest(client, db):
    user_id, _ = create_user("vlasnik@test.hr", role="owner")
    login_as(client, user_id)
    html = client.get("/admin/profil").text
    assert '<link rel="manifest" href="/admin/manifest.webmanifest">' in html
    assert 'rel="apple-touch-icon" href="/admin/pwa-icon-180.png"' in html
    assert 'name="apple-mobile-web-app-capable" content="yes"' in html
    assert "Aplikacija na telefonu" in html and "data-pwa-install" in html
    public = client.get("/").text
    assert "manifest" not in public and 'name="theme-color"' in public  # no PWA publicly
    csp = client.get("/").headers["content-security-policy"]
    assert "worker-src 'self'" in csp


def test_browser_service_worker_registers(live_server, page, db):
    user_id, _ = create_user("vlasnik@test.hr", role="owner")
    token = login_as(SimpleNamespace(cookies=SimpleNamespace(set=lambda *a, **k: None)), user_id)
    page.context.add_cookies(
        [{"name": SESSION_COOKIE, "value": token, "url": f"{live_server}/admin/profil"}]
    )
    page.goto(f"{live_server}/admin/profil")
    assert "Aplikacija na telefonu" in page.content()
    scope = page.evaluate("async () => (await navigator.serviceWorker.ready).scope")
    assert scope == f"{live_server}/admin/"
    page.reload()  # controlled page still loads (network-only for admin pages)
    assert "Aplikacija na telefonu" in page.content()
    assert page.errors == []
