"""Faza 10 D: dijeljenje (interni /podijeli/ redirect) i QR kod."""

from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlparse

from app.services import share
from tests.helpers import external_urls, make_vehicle


def test_share_block_on_detail(client, db):
    vehicle = make_vehicle(db, make_name="Volkswagen", model_name="Golf", price_eur=18500)
    html = client.get(f"/vozila/{vehicle.slug}").text
    path = f"/vozila/{vehicle.slug}"
    assert f'href="/podijeli/whatsapp?u=/vozila/{vehicle.slug}"' in html or (
        f'href="/podijeli/whatsapp?u=%2Fvozila%2F{vehicle.slug}"' in html
    )
    assert f'data-share-url="http://testserver{path}"' in html
    assert f'data-copy-link="http://testserver{path}"' in html
    assert "mailto:?subject=" in html
    assert html.count('src="data:image/png;base64,') >= 2  # popover + aside card
    assert external_urls(html) == []  # nothing external on the page itself


def test_share_redirects(client, db):
    vehicle = make_vehicle(db, make_name="Volkswagen", model_name="Golf", price_eur=18500)
    path = f"/vozila/{vehicle.slug}"
    response = client.get(f"/podijeli/whatsapp?u={path}", follow_redirects=False)
    assert response.status_code == 302 and response.headers["cache-control"] == "no-store"
    location = response.headers["location"]
    assert location.startswith("https://wa.me/?text=")
    text = unquote(location.split("text=", 1)[1])
    assert text == f"{vehicle.title} – 18.500 € http://testserver{path}"
    facebook = client.get(f"/podijeli/facebook?u={path}", follow_redirects=False)
    query = parse_qs(urlparse(facebook.headers["location"]).query)
    assert facebook.headers["location"].startswith("https://www.facebook.com/sharer/sharer.php?")
    assert query["u"] == [f"http://testserver{path}"]
    viber = client.get("/podijeli/viber?u=/usporedba?v=1,2", follow_redirects=False)
    assert viber.headers["location"].startswith("viber://forward?text=")


def test_share_redirect_rejects_foreign_urls(client):
    for bad in ("https://evil.example/", "//evil.example", "/admin", "/vozila/../admin", ""):
        assert client.get(f"/podijeli/whatsapp?u={bad}", follow_redirects=False).status_code == 404
    assert client.get("/podijeli/twitter?u=/favoriti", follow_redirects=False).status_code == 404


def test_share_on_favorites_and_compare(client, db):
    vehicle = make_vehicle(db)
    for page in (f"/favoriti?v={vehicle.id}", f"/usporedba?v={vehicle.id}"):
        html = client.get(page).text
        assert "data-share" in html and "/podijeli/facebook?u=" in html
        assert external_urls(html) == []


def test_qr_is_cached():
    share.qr.cache_clear()
    first = share.qr("http://testserver/vozila/a")
    assert first.startswith("data:image/png;base64,")
    assert share.qr("http://testserver/vozila/a") is first
    assert share.qr.cache_info().hits == 1


def test_browser_copy_link_shows_toast(live_server, page, db):
    vehicle = make_vehicle(db)
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    page.goto(f"{live_server}/vozila/{vehicle.slug}")
    page.click(".vehicle-price .share > summary")
    page.click(".vehicle-price [data-copy-link]")
    page.wait_for_selector("[data-toast].is-visible")
    assert "Link kopiran" in page.inner_text("[data-toast]")
    assert page.errors == []
