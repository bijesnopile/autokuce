"""Presentation helpers for editable marketing content (CMS pages, "why us" items).

Content stays editable in the admin as plain rich text; these helpers only change how it is
laid out on the public site:

- `split_sections(html)` turns "intro + <h3> blocks (+ <h2> outro)" into cards (Usluge page);
- `why_us_items(text)` parses the "Zašto kupiti kod nas" setting ("Naslov | opis" per line);
- `pick_icon(text, index)` chooses a fitting icon from keywords in a title.
"""

from __future__ import annotations

import re
from html import unescape

from markupsafe import Markup
from sqlalchemy import func, select
from sqlalchemy.orm import Session

H3_RE = re.compile(r"<h3[^>]*>(.*?)</h3>", re.S | re.I)
H2_RE = re.compile(r"<h2[^>]*>", re.I)
TAG_RE = re.compile(r"<[^>]+>")

# (keywords, icon) — first match wins; titles are compared in lower case.
ICON_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("financ", "leasing", "kredit", "rat"), "tag"),
    (("zamjen", "otkup"), "refresh"),
    (("registr", "dokument", "vlasništv"), "file"),
    (("servis", "održav", "priprem"), "wrench"),
    (("jamstv", "garanc", "provjer", "sigurn"), "shield-check"),
    (("probn", "vožnj", "pregled"), "key"),
    (("dostav", "prijevoz", "gospodar"), "truck"),
    (("prodaj", "vozil", "ponud"), "car"),
    (("tvrtk", "pravn", "obrt", "r1"), "users"),
]
FALLBACK_ICONS = ("award", "handshake", "star", "heart", "check-circle", "layers")


def pick_icon(text: str, index: int = 0) -> str:
    lowered = text.lower()
    for keywords, icon in ICON_KEYWORDS:
        if any(word in lowered for word in keywords):
            return icon
    return FALLBACK_ICONS[index % len(FALLBACK_ICONS)]


def plain_text(html: str) -> str:
    """Tags removed, entities decoded, whitespace collapsed."""
    return re.sub(r"\s+", " ", unescape(TAG_RE.sub(" ", html or ""))).strip()


def first_paragraph_text(html: str, limit: int = 160) -> str:
    """Plain text of the first paragraph (meta description), shortened on a word boundary."""
    match = re.search(r"<p[^>]*>(.*?)</p>", html or "", re.S | re.I)
    text = plain_text(match.group(1) if match else html)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0].rstrip(",.;:") + "…"


def split_sections(html: str) -> dict:
    """Split sanitized page HTML into intro, cards (one per <h3>) and outro (from the first
    <h2> after the cards). Without any <h3> everything is the intro."""
    html = html or ""
    matches = list(H3_RE.finditer(html))
    if not matches:
        return {"intro": Markup(html), "cards": [], "outro": Markup("")}
    intro = html[: matches[0].start()]
    cards = []
    outro = ""
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(html)
        body = html[match.end() : end]
        if index + 1 == len(matches):
            h2 = H2_RE.search(body)
            if h2:
                body, outro = body[: h2.start()], body[h2.start() :]
        title = plain_text(match.group(1))
        cards.append(
            {"title": title, "body": Markup(body.strip()), "icon": pick_icon(title, index)}
        )
    return {"intro": Markup(intro.strip()), "cards": cards, "outro": Markup(outro.strip())}


def split_lead(html: str) -> tuple[Markup, Markup]:
    """(first paragraph, everything after it) — the lead is shown under the page title."""
    html = html or ""
    match = re.match(r"\s*(<p[^>]*>.*?</p>)", html, re.S | re.I)
    if not match:
        return Markup(""), Markup(html)
    return Markup(match.group(1)), Markup(html[match.end() :].strip())


def why_us_items(text: str, limit: int = 8) -> list[dict]:
    """'Naslov | kratki opis' per line -> [{title, text, icon}] (empty lines ignored)."""
    items = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        title, _, body = line.partition("|")
        title = title.strip()
        if not title:
            continue
        items.append({"title": title, "text": body.strip(), "icon": pick_icon(title, len(items))})
        if len(items) >= limit:
            break
    return items


def about_stats(db: Session) -> list[dict]:
    """Live numbers for the "O nama" page — only facts the database can back up."""
    from datetime import timedelta

    from app.database import utcnow
    from app.models import STATUS_ACTIVE, STATUS_RESERVED, Vehicle

    public = Vehicle.status.in_((STATUS_ACTIVE, STATUS_RESERVED))  # currently for sale
    offered = db.scalar(select(func.count()).select_from(Vehicle).where(public)) or 0
    makes = db.scalar(select(func.count(func.distinct(Vehicle.make_id))).where(public)) or 0
    types = db.scalar(select(func.count(func.distinct(Vehicle.vehicle_type))).where(public)) or 0
    recent = (
        db.scalar(
            select(func.count())
            .select_from(Vehicle)
            .where(public, Vehicle.published_at >= utcnow() - timedelta(days=30))
        )
        or 0
    )
    return [
        {"value": offered, "label": "vozila u ponudi", "icon": "car"},
        {"value": makes, "label": "marki vozila", "icon": "tag"},
        {"value": types, "label": "vrsta vozila", "icon": "layers"},
        {"value": recent, "label": "novih oglasa u 30 dana", "icon": "star"},
    ]


def page_template(slug: str) -> str:
    """`public/pages/<slug>.html` when it exists (also in overrides/), else `public/page.html`."""
    from jinja2 import TemplateNotFound

    from app.templating import env

    name = f"public/pages/{slug}.html"
    try:
        env.get_template(name)
    except TemplateNotFound:
        return "public/page.html"
    return name


def page_extras(db: Session, slug: str, body_html: str) -> dict:
    """Extra context for pages that have their own layout (public/pages/<slug>.html)."""
    lead, rest = split_lead(body_html)
    extras: dict = {"sections": split_sections(body_html), "lead": lead, "rest": rest}
    if slug == "o-nama":
        extras["stats"] = about_stats(db)
    return extras
