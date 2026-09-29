"""No external resources: public pages, static CSS/JS and every email template (spec 13/14).

Allowed: the site's own URLs (relative or BASE_URL), mailto:/tel:/data:, the company's own
links from settings (social networks, Maps) and — only when configured — Turnstile/Umami
(covered in test_public.py::test_turnstile_and_umami_only_when_configured).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.models import VehicleImage
from tests.helpers import external_urls, image_bytes, make_vehicle

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"


@pytest.fixture
def vehicles(db):
    """One public vehicle of every type; the car has photos (gallery, srcset, OG image)."""
    from app.services.images import save_vehicle_image

    created = {}
    for vehicle_type in ("car", "van", "motorcycle", "camper", "truck"):
        created[vehicle_type] = make_vehicle(db, vehicle_type=vehicle_type)
    car = created["car"]
    for position in range(3):
        key, processed = save_vehicle_image(car.id, image_bytes(color=(40 * position, 90, 160)))
        db.add(
            VehicleImage(
                vehicle_id=car.id,
                file_key=key,
                sort_order=position,
                width=processed.width,
                height=processed.height,
            )
        )
    db.commit()
    return created


PUBLIC_PATHS = [
    "/",
    "/vozila",
    "/vozila?vrsta=car",
    "/vozila?stranica=99",
    "/kontakt",
    "/usluge",
    "/o-nama",
    "/privatnost",
    "/kolacici",
    "/uvjeti",
    "/newsletter/potvrda/nevaljan-token",
    "/newsletter/odjava/nevaljan-token",
    "/ne-postoji",
]


@pytest.mark.parametrize("path", PUBLIC_PATHS)
def test_public_pages_have_no_external_resources(client, vehicles, path):
    response = client.get(path)
    assert response.status_code in (200, 400, 404, 410), path
    assert external_urls(response.text) == [], path


def test_vehicle_detail_pages_have_no_external_resources(client, vehicles):
    for vehicle in vehicles.values():
        html = client.get(f"/vozila/{vehicle.slug}").text
        assert external_urls(html) == [], vehicle.vehicle_type
    html = client.get(f"/vozila/{vehicles['car'].slug}").text
    assert "srcset=" in html  # the gallery was actually rendered and checked


def test_youtube_only_via_nocookie_and_on_click(client, db, vehicles):
    car = vehicles["car"]
    car.video_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    db.commit()
    html = client.get(f"/vozila/{car.slug}").text
    assert "<iframe" not in html  # nothing loads until the visitor clicks
    assert "youtube.com/embed" not in html
    js = (STATIC / "js" / "public.js").read_text(encoding="utf-8")
    assert "https://www.youtube-nocookie.com/embed/" in js
    assert "https://www.youtube.com/embed" not in js


def test_static_css_and_js_load_nothing_external():
    url_re = re.compile(r"""url\(\s*['"]?(https?:)?//""", re.I)
    for path in list(STATIC.rglob("*.css")):
        text = path.read_text(encoding="utf-8")
        assert "@import" not in text, path.name
        assert not url_re.search(text), path.name
    for path in STATIC.rglob("*.js"):
        text = path.read_text(encoding="utf-8")
        for url in re.findall(r"https?://[A-Za-z0-9.-]*", text):
            # Only the click-to-load YouTube embed and editor examples are allowed.
            assert url in ("https://www.youtube-nocookie.com", "https://"), (
                path.name,
                url,
            )
        assert "fetch('http" not in text and 'fetch("http' not in text, path.name
        assert "document.createElement('script')" not in text, path.name


def _email_contexts(vehicle) -> dict[str, dict]:
    from app.services.newsletter import vehicle_card_html

    card = vehicle_card_html(vehicle)
    return {
        "user_invite": {"url": "http://testserver/admin/lozinka/postavi/abc", "name": "Ana"},
        "password_reset": {"url": "http://testserver/admin/lozinka/nova/abc", "name": "Ana"},
        "inquiry_notification": {
            "name": "Ime Prezime",
            "email": "kupac@primjer.hr",
            "phone": "+385911234567",
            "message": "Poruka",
            "type_label": "Upit za vozilo",
            "vehicle_title": vehicle.title,
            "vehicle_url": f"http://testserver/vozila/{vehicle.slug}",
            "url": "http://testserver/admin/upiti/1",
            "received": "28.09.2026. 10:00",
        },
        "inquiry_auto_reply": {
            "body": "Poštovani Ime,\n\nprimili smo Vaš upit.",
            "type_label": "Rezervacija termina pregleda",
            "vehicle_title": vehicle.title,
            "vehicle_url": f"http://testserver/vozila/{vehicle.slug}",
            "preferred_date": "02.10.2026. 10:00",
            "has_ics": True,
        },
        "viewing_confirmed": {
            "name": "Ime Prezime",
            "when": "02.10.2026. 10:00",
            "vehicle_title": vehicle.title,
            "vehicle_url": f"http://testserver/vozila/{vehicle.slug}",
        },
        "newsletter_confirm": {"url": "http://testserver/newsletter/potvrda/abc"},
        "newsletter_campaign": {
            "subject": "Nova vozila",
            "body_html": "<p>Lorem ipsum</p>" + card,
            "body_text": "Lorem ipsum",
            "unsubscribe_url": "http://testserver/newsletter/odjava/abc?potvrdi=1",
            "signup_date": "28.09.2026.",
        },
    }


def test_email_templates_have_no_external_resources(db, vehicles):
    from app.services.email import render_email

    templates_dir = Path(__file__).resolve().parent.parent / "app" / "templates" / "emails"
    names = {p.stem for p in templates_dir.glob("*.html") if not p.stem.startswith("_")}
    names.discard("base")
    contexts = _email_contexts(vehicles["car"])
    assert names == set(contexts), "new email template? add a context here"
    for name, context in contexts.items():
        html, text = render_email(name, context)
        assert html.strip() and text.strip(), name
        assert external_urls(html) == [], name
        # Remote images/fonts/styles would be tracking pixels or third-party requests.
        assert "<link" not in html and "@import" not in html, name
        for src in re.findall(r'<img[^>]+src="([^"]+)"', html):
            assert src.startswith("http://testserver/"), (name, src)


def test_vehicle_card_in_email_uses_own_media(db, vehicles):
    from app.services.newsletter import vehicle_card_html

    html = vehicle_card_html(vehicles["car"])
    images = re.findall(r'<img[^>]+src="([^"]+)"', html)
    assert images and all(src.startswith("http://testserver/media/") for src in images)
