"""Company data comes only from settings (spec chapter 3): nothing hardcoded in templates."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.site import DEFAULTS
from tests.helpers import make_vehicle

APP = Path(__file__).resolve().parent.parent / "app"
TEMPLATES = APP / "templates"

# Format hints inside input placeholder="" attributes are allowed ("+385 ...", "ime@primjer.hr").
PLACEHOLDER_ATTR_RE = re.compile(r'placeholder="[^"]*"')
EXAMPLE_DOMAINS = ("primjer.hr", "example.com", "domena.com")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+\.[A-Za-z.]{2,})")
FORBIDDEN = [
    (re.compile(r"\+385\s*[\dX]"), "telefonski broj"),
    (re.compile(r"\bd\.\s?o\.\s?o\.", re.I), "d.o.o."),
    (re.compile(r"\bj\.\s?d\.\s?o\.\s?o\.", re.I), "j.d.o.o."),
    (re.compile(r"(?<![\w#])\d{11}(?!\w)"), "OIB"),
    (re.compile(r"IME PODUZE", re.I), "naziv tvrtke"),
    (re.compile(r"Ulica i broj"), "adresa"),
    (re.compile(r"\b(IBAN|HR\d{19})\b"), "IBAN"),
]


def template_files():
    return sorted(p for p in TEMPLATES.rglob("*") if p.suffix in {".html", ".txt"} and p.is_file())


@pytest.mark.parametrize("path", template_files(), ids=lambda p: str(p.relative_to(TEMPLATES)))
def test_template_has_no_hardcoded_company_data(path):
    text = PLACEHOLDER_ATTR_RE.sub("", path.read_text(encoding="utf-8"))
    # Help texts that describe the OIB placeholder format are fine.
    text = text.replace("XXXXXXXXXXX", "")
    problems = [label for pattern, label in FORBIDDEN if pattern.search(text)]
    for domain in EMAIL_RE.findall(text):
        if not domain.endswith(EXAMPLE_DOMAINS):
            problems.append(f"email @{domain}")
    assert problems == []


def test_static_js_has_no_company_data():
    for path in (APP / "static" / "js").glob("*.js"):
        text = path.read_text(encoding="utf-8")
        assert not EMAIL_RE.search(text), path.name
        assert "+385" not in text, path.name


COMPANY = {
    "company_name": "Autokuća Testić",
    "company_address": "Testna ulica 5, 21000 Split",
    "company_oib": "12345678903",
    "company_email": "info@testic.hr",
    "company_phone": "+385 21 555 666",
    "company_web": "www.testic.hr",
    "working_hours": "Pon–Sub 07:00–15:00",
    "inquiry_notify_email": "upiti@testic.hr",
    "newsletter_sender_name": "Testić Newsletter",
    "facebook_url": "https://facebook.com/testic",
    "instagram_url": "https://instagram.com/testic",
    "maps_url": "https://maps.google.com/?q=Testna+ulica+5+Split",
}


def test_changed_settings_replace_every_placeholder(client, db):
    """With real company data set, no default placeholder may remain on public pages."""
    from app.services.site import set_values

    vehicle = make_vehicle(db)
    set_values(db, COMPANY)
    db.commit()
    defaults = [DEFAULTS[key] for key in COMPANY if DEFAULTS.get(key)]
    for path in ("/", "/vozila", f"/vozila/{vehicle.slug}", "/kontakt", "/ne-postoji"):
        html = client.get(path).text
        assert "Autokuća Testić" in html, path
        leftovers = [value for value in defaults if value in html]
        assert leftovers == [], (path, leftovers)
    contact = client.get("/kontakt").text
    for key in ("company_address", "company_email", "working_hours"):
        assert COMPANY[key] in contact, key
    assert "12345678903" in client.get("/").text  # impressum in the footer (ZEK)


def test_changed_settings_appear_in_emails(db):
    from app.services.email import render_email
    from app.services.site import set_values

    set_values(db, COMPANY)
    db.commit()
    html, text = render_email("newsletter_confirm", {"url": "http://testserver/x"})
    for body in (html, text):
        assert "Autokuća Testić" in body and "12345678903" in body
        assert DEFAULTS["company_name"] not in body
