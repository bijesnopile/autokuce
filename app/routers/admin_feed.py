"""Feed prema portalima (paket Standard, funkcija `feed_portali`).

Javno (s tokenom):
GET  /feed/{portal}.{xml|csv}?token=...   feed vozila; krivi/nepostojeći token ili zaključano -> 404

Admin (vlasnik+):
GET  /admin/feed                          URL-ovi, zadnja preuzimanja, validacija, upute
GET  /admin/feed/pregled/{portal}.{fmt}   pregled feeda (bez tokena, za prijavljene)
POST /admin/feed/token                    novi token (stari URL-ovi prestaju raditi)
POST /admin/feed/postavke                 izvoz VIN-a da/ne
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import csrf_protect, require_feature, require_permission
from app.models import User
from app.plans import has_feature
from app.security import client_ip, rate_limit
from app.services import audit, feeds
from app.services import feed_formats as formats
from app.services.site import get_site, set_values
from app.templating import flash, render

router = APIRouter(prefix="/admin", dependencies=[Depends(csrf_protect)])
public_router = APIRouter(dependencies=[Depends(rate_limit("feed", 30, 60))])

MEDIA_TYPES = {"xml": "application/xml; charset=utf-8", "csv": "text/csv; charset=utf-8"}


def _split(name: str) -> tuple[str, str]:
    portal, _, fmt = name.rpartition(".")
    if portal not in formats.PORTALS or fmt not in formats.PORTALS[portal]["formats"]:
        raise HTTPException(status_code=404)
    return portal, fmt


def _feed_response(request: Request, body: bytes, fmt: str, filename: str) -> Response:
    headers = {
        "Cache-Control": f"private, max-age={feeds.CACHE_SECONDS}",
        "X-Robots-Tag": "noindex, nofollow",
        "Vary": "Accept-Encoding",
        "Content-Disposition": f'inline; filename="{filename}"',
    }
    if "gzip" in request.headers.get("accept-encoding", "").lower():
        headers["Content-Encoding"] = "gzip"
        body = feeds.gzip_body(body)
    return Response(body, media_type=MEDIA_TYPES[fmt], headers=headers)


@public_router.get("/feed/{name}")
async def feed(request: Request, name: str, db: Session = Depends(get_db)):
    """The token is the only authorization; every failure looks the same (404)."""
    if not has_feature("feed_portali"):
        raise HTTPException(status_code=404)
    portal, fmt = _split(name)
    if not feeds.token_valid(db, request.query_params.get("token", "")):
        raise HTTPException(status_code=404)
    body = feeds.cached_body(db, portal, fmt)
    feeds.record_access(db, portal, fmt)
    return _feed_response(request, body, fmt, f"{portal}.{fmt}")


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------
@router.get("/feed")
async def feed_admin(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("feed")),
    _feature: None = Depends(require_feature("feed_portali")),
):
    token = feeds.get_token(db, create=True)  # generated on the first visit
    base = feeds.absolute("/feed/")
    portals = []
    for code, meta in formats.PORTALS.items():
        portals.append(
            meta
            | {
                "code": code,
                "urls": [(fmt, f"{base}{code}.{fmt}?token={token}") for fmt in meta["formats"]],
            }
        )
    return render(
        request,
        "admin/feed.html",
        {
            "section": "feed",
            "portals": portals,
            "access": feeds.access_by_portal(db),
            "problems": formats.validate(db),
            "vehicle_count": len(feeds.feed_vehicles(db)),
            "site_values": get_site(),
            "site_problems": formats.meta_site_problems(get_site()),
            "cache_minutes": feeds.CACHE_SECONDS // 60,
        },
    )


@router.get("/feed/pregled/{name}")
async def feed_preview(
    request: Request,
    name: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("feed")),
    _feature: None = Depends(require_feature("feed_portali")),
):
    """Fresh (uncached) feed for the logged-in owner; not counted as a portal download."""
    portal, fmt = _split(name)
    body = formats.build(db, portal, fmt)
    return Response(
        body,
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"},
    )


@router.post("/feed/token")
async def feed_token(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("feed")),
    _feature: None = Depends(require_feature("feed_portali")),
):
    feeds.regenerate_token(db)
    audit.log(db, user.id, "feed.token", "setting", None, None, client_ip(request))
    db.commit()
    flash(
        request,
        "Novi token je izrađen. Stari URL-ovi više ne rade — upišite nove kod svakog portala.",
        "warning",
    )
    return RedirectResponse("/admin/feed", status_code=303)


@router.post("/feed/postavke")
async def feed_settings(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("feed")),
    _feature: None = Depends(require_feature("feed_portali")),
):
    form = await request.form()
    values, error = formats.parse_feed_settings(form)
    if error:
        flash(request, error, "error")
        return RedirectResponse("/admin/feed#postavke", status_code=303)
    changed = set_values(db, values)
    if changed:
        audit.log(
            db, user.id, "feed.settings", "setting", None, {"changed": changed}, client_ip(request)
        )
    db.commit()
    feeds.clear_cache()
    flash(request, "Postavke feeda su spremljene.", "success")
    return RedirectResponse("/admin/feed", status_code=303)
