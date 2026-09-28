"""SEO routes: /sitemap.xml and /robots.txt."""

from __future__ import annotations

from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import STATUS_ACTIVE, STATUS_RESERVED, Page, Vehicle

router = APIRouter()
settings = get_settings()

STATIC_PATHS = ["/", "/vozila", "/kontakt"]


@router.get("/robots.txt")
async def robots():
    lines = [
        "User-agent: *",
        "Disallow: /admin",
        "Disallow: /api",
        "Disallow: /media/private",
        "Disallow: /newsletter/",
        "",
        f"Sitemap: {settings.base_url}/sitemap.xml",
        "",
    ]
    return PlainTextResponse("\n".join(lines))


@router.get("/sitemap.xml")
async def sitemap(db: Session = Depends(get_db)):
    """Static pages + published CMS pages + active/reserved vehicles (never sold/archived)."""
    base = settings.base_url
    entries: list[tuple[str, str | None]] = [(base + path, None) for path in STATIC_PATHS]
    for slug, updated in db.execute(
        select(Page.slug, Page.updated_at).where(Page.is_published).order_by(Page.slug)
    ):
        entries.append((f"{base}/{slug}", updated.date().isoformat() if updated else None))
    for slug, updated in db.execute(
        select(Vehicle.slug, Vehicle.updated_at)
        .where(Vehicle.status.in_((STATUS_ACTIVE, STATUS_RESERVED)))
        .order_by(Vehicle.published_at.desc(), Vehicle.id.desc())
    ):
        entries.append((f"{base}/vozila/{slug}", updated.date().isoformat() if updated else None))

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for loc, lastmod in entries:
        parts.append("  <url>")
        parts.append(f"    <loc>{escape(loc)}</loc>")
        if lastmod:
            parts.append(f"    <lastmod>{lastmod}</lastmod>")
        parts.append("  </url>")
    parts.append("</urlset>")
    return Response("\n".join(parts) + "\n", media_type="application/xml")
