"""WhatsApp / Viber gumbi (paket Standard, funkcija `whatsapp`)."""

from __future__ import annotations

from urllib.parse import unquote

from app.models import ContactClick
from app.services.site import invalidate_site_cache, set_values
from tests.helpers import create_user, csrf_from, external_urls, login_as, make_vehicle

NUMBER = "+385911234567"


def set_numbers(db, whatsapp=NUMBER, viber=""):
    set_values(db, {"whatsapp_number": whatsapp, "viber_number": viber})
    db.commit()
    invalidate_site_cache()


def test_buttons_render_only_with_number_and_plan(client, db, set_plan):
    vehicle = make_vehicle(db)
    detail = f"/vozila/{vehicle.slug}"

    set_plan("osnovni")
    set_numbers(db)
    assert "/idi/whatsapp" not in client.get(detail).text  # locked: not rendered at all

    set_plan("standard")
    set_numbers(db, whatsapp="", viber="")
    assert "/idi/" not in client.get(detail).text  # no number: no button

    set_numbers(db, whatsapp=NUMBER, viber=NUMBER)
    html = client.get(detail).text
    assert html.count(f'href="/idi/whatsapp/{vehicle.id}"') == 2  # aside + mobile bar
    assert f'href="/idi/viber/{vehicle.id}"' in html
    assert "sticky-cta no-print has-chat" in html
    contact = client.get("/kontakt").text
    assert 'href="/idi/whatsapp"' in contact and 'href="/idi/viber"' in contact
    assert external_urls(html) == [] and external_urls(contact) == []  # links stay internal


def test_redirect_counts_and_builds_the_message(client, db, set_plan):
    set_plan("standard")
    set_numbers(db, viber=NUMBER)
    vehicle = make_vehicle(db)
    response = client.get(f"/idi/whatsapp/{vehicle.id}", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["cache-control"] == "no-store"
    location = response.headers["location"]
    assert location.startswith("https://wa.me/385911234567?text=")
    text = unquote(location.split("text=", 1)[1])
    assert text == f"Pozdrav, zanima me {vehicle.title} (http://testserver/vozila/{vehicle.slug})"

    client.get(f"/idi/whatsapp/{vehicle.id}", follow_redirects=False)
    client.get(
        f"/idi/whatsapp/{vehicle.id}",
        headers={"User-Agent": "Googlebot/2.1"},
        follow_redirects=False,
    )
    rows = db.query(ContactClick).filter_by(vehicle_id=vehicle.id, channel="whatsapp").all()
    assert len(rows) == 1 and rows[0].count == 2  # one daily row, bot not counted

    viber = client.get(f"/idi/viber/{vehicle.id}", follow_redirects=False)
    assert viber.headers["location"] == "viber://chat?number=%2B385911234567"
    general = client.get("/idi/whatsapp", follow_redirects=False)
    assert "vozilima" in unquote(general.headers["location"])
    assert db.query(ContactClick).filter(ContactClick.vehicle_id.is_(None)).count() == 1


def test_redirect_404_when_locked_unconfigured_or_not_public(client, db, set_plan):
    vehicle = make_vehicle(db)
    draft = make_vehicle(db, status="draft")
    set_numbers(db)
    set_plan("osnovni")
    assert client.get(f"/idi/whatsapp/{vehicle.id}", follow_redirects=False).status_code == 404
    set_plan("standard")
    assert client.get(f"/idi/whatsapp/{draft.id}", follow_redirects=False).status_code == 404
    assert client.get("/idi/viber", follow_redirects=False).status_code == 404  # no viber number
    assert client.get("/idi/telegram", follow_redirects=False).status_code == 404
    assert "Disallow: /idi/" in client.get("/robots.txt").text


def test_statistics_show_contacts_per_vehicle(client, db, set_plan):
    set_plan("standard")
    set_numbers(db)
    vehicle = make_vehicle(db)
    for _ in range(3):
        client.get(f"/idi/whatsapp/{vehicle.id}", follow_redirects=False)
    owner_id, _ = create_user("vlasnik@test.hr", role="owner")
    login_as(client, owner_id)
    html = client.get("/admin/statistika?sort=kontakti").text
    assert ">Kontakti" in html
    assert '<td class="num" data-label="Kontakti">3</td>' in html
    csv_text = client.get("/admin/statistika/izvoz.csv?tablica=vozila").content.decode("utf-8-sig")
    assert "Kontakti (WhatsApp/Viber)" in csv_text.splitlines()[0]


def _settings_post(client, **changes):
    from app.services.site import get_site

    page = client.get("/admin/postavke")
    site = get_site()
    data = {"csrf_token": csrf_from(page.text)}
    for key in ("company_name", "company_address", "company_oib", "company_email",
                "company_phone", "company_web", "working_hours", "inquiry_notify_email",
                "newsletter_sender_name", "facebook_url", "instagram_url", "maps_url",
                "primary_color", "accent_color", "hero_title", "hero_subtitle", "footer_text",
                "why_us", "privacy_policy_version"):  # fmt: skip
        data[key] = site[key]
    data.update(changes)
    return client.post("/admin/postavke", data=data, follow_redirects=False), page.text


def test_settings_validate_and_lock_numbers(client, db, set_plan):
    from app.services.site import get_site

    owner_id, _ = create_user("vlasnik@test.hr", role="owner")
    login_as(client, owner_id)
    set_plan("standard")
    response, _ = _settings_post(client, whatsapp_number="0911234567")
    assert response.status_code == 400 and "Međunarodni format" in response.text
    response, _ = _settings_post(client, whatsapp_number="+385 91 234-5678", viber_number="")
    assert response.status_code == 303
    invalidate_site_cache()
    assert get_site()["whatsapp_number"] == "+385912345678"
    response, _ = _settings_post(client, whatsapp_number="+385XXXXXXXXXX")  # demo placeholder
    assert response.status_code == 303

    set_plan("osnovni")
    response, page = _settings_post(client, whatsapp_number="")  # disabled field: not sent/used
    assert (
        'id="s-whatsapp_number"' in page
        and "disabled" in page.split('id="s-whatsapp_number"')[1].split(">")[0]
    )
    assert "/admin/postavke/paket/whatsapp" in page
    invalidate_site_cache()
    assert get_site()["whatsapp_number"] == "+385XXXXXXXXXX"  # locked value kept
    locked = client.get("/admin/postavke/paket/whatsapp")
    assert locked.status_code == 403 and "Dostupno u paketu Standard" in locked.text
