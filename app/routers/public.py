"""Public website routes (spec chapter 8).

    GET  /                          home: hero, quick search, featured, latest, contact
    GET  /vozila                    list with filters (GET params), sorting, 12 per page
    GET  /vozila/{slug}             detail (old slug -> 301, archived/expired -> 410, draft -> 404)
    GET  /kontakt                   contact page + general inquiry form
    GET  /o-nama, /usluge           CMS pages
    GET  /privatnost, /kolacici, /uvjeti   legal pages (version + date)
    GET  /zdravlje                  health check (JSON)
    GET  /media/{key}               locally stored images
Form handlers (POST /upit, newsletter) live in routers added in phases 5 and 6.
"""

from __future__ import annotations

from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.deps import csrf_protect
from app.models import (
    STATUS_ACTIVE,
    STATUS_DRAFT,
    STATUS_RESERVED,
    Make,
    Page,
    Vehicle,
    VehicleModel,
    VehicleSlugHistory,
)
from app.pagination import paginate, parse_page
from app.services import seo
from app.services import vehicles as vs
from app.services.site import get_site
from app.services.storage import LocalStorage, get_storage, is_safe_key
from app.templating import flash, format_number, query_url, render
from app.vehicle_schema import (
    FUELS,
    TRANSMISSIONS,
    VEHICLE_TYPES,
    equipment_grouped,
    type_label,
)

router = APIRouter(dependencies=[Depends(csrf_protect)])
settings = get_settings()

PRICE_STEPS = [5000, 10000, 15000, 20000, 30000, 40000, 50000, 75000, 100000]


def safe_back(request: Request, default: str = "/") -> str:
    """Same-site Referer path (for redirects after form posts), else `default`."""
    referer = request.headers.get("referer", "")
    parsed = urlparse(referer)
    if parsed.netloc and parsed.netloc == request.url.netloc and parsed.path.startswith("/"):
        return parsed.path + (f"?{parsed.query}" if parsed.query else "")
    return default


# ---------------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------------
@router.get("/")
async def home(request: Request, db: Session = Depends(get_db)):
    site = get_site()
    available = vs.public_query().where(Vehicle.status.in_((STATUS_ACTIVE, STATUS_RESERVED)))
    featured = list(
        db.scalars(
            available.where(Vehicle.featured)
            .order_by(Vehicle.published_at.desc(), Vehicle.id.desc())
            .limit(8)
        )
    )
    latest = list(
        db.scalars(available.order_by(Vehicle.published_at.desc(), Vehicle.id.desc()).limit(8))
    )
    meta = seo.page_meta(
        f"{site['company_name']} — rabljena i nova vozila",
        site["hero_subtitle"],
        "/",
    )
    return render(
        request,
        "public/home.html",
        {
            "meta": meta,
            "featured": featured,
            "latest": latest,
            "options": vs.filter_options(db),
            "price_steps": PRICE_STEPS,
            "jsonld": [seo.organization_jsonld(site)],
        },
    )


# ---------------------------------------------------------------------------
# Vehicle list
# ---------------------------------------------------------------------------
def _chips(db: Session, filters: dict, sort: str) -> list[dict]:
    """Active filters as removable chips: [{label, url}]."""
    params = dict(filters)
    if sort != "najnovije":
        params["sort"] = sort
    labels = {
        "tip": lambda v: type_label(v),
        "marka": lambda v: db.get(Make, v).name if db.get(Make, v) else str(v),
        "model": lambda v: db.get(VehicleModel, v).name if db.get(VehicleModel, v) else str(v),
        "cijena_od": lambda v: f"od {format_number(v)} €",
        "cijena_do": lambda v: f"do {format_number(v)} €",
        "godina_od": lambda v: f"od {v}. god.",
        "godina_do": lambda v: f"do {v}. god.",
        "km_do": lambda v: f"do {format_number(v)} km",
        "gorivo": lambda v: dict(FUELS).get(v, v),
        "mjenjac": lambda v: dict(TRANSMISSIONS).get(v, v),
        "stanje": lambda v: "Novo" if v == "novo" else "Rabljeno",
    }
    chips = []
    for key, value in filters.items():
        remaining = {k: v for k, v in params.items() if k != key}
        if key == "marka":
            remaining.pop("model", None)
        chips.append({"label": labels[key](value), "url": query_url("/vozila", remaining)})
    return chips


@router.get("/vozila")
async def vehicle_list(request: Request, db: Session = Depends(get_db)):
    site = get_site()
    params = request.query_params
    filters = vs.parse_filters(params)
    sort = params.get("sort") if params.get("sort") in vs.PUBLIC_SORTS else "najnovije"
    stmt = vs.apply_sort(vs.apply_filters(vs.public_query(), filters), sort)
    page = paginate(db, stmt, parse_page(params.get("stranica")), vs.PER_PAGE)

    models = []
    if "marka" in filters:
        model_stmt = (
            select(VehicleModel)
            .where(VehicleModel.make_id == filters["marka"], VehicleModel.is_active)
            .order_by(VehicleModel.name)
        )
        models = list(db.scalars(model_stmt))

    base_params = dict(filters)
    if sort != "najnovije":
        base_params["sort"] = sort
    canonical_params = dict(base_params)
    if page.page > 1:
        canonical_params["stranica"] = page.page
    prev_url = next_url = None
    if page.has_prev:
        prev_url = query_url("/vozila", dict(base_params, stranica=page.page - 1 or ""))
        if page.page - 1 == 1:
            prev_url = query_url("/vozila", base_params)
    if page.has_next:
        next_url = query_url("/vozila", dict(base_params, stranica=page.page + 1))

    title = "Vozila u ponudi"
    if "tip" in filters:
        title = VEHICLE_TYPES[filters["tip"]]["plural"]
    heading = title
    if page.page > 1:
        title += f" — stranica {page.page}"
    meta = seo.page_meta(
        f"{title} – {site['company_name']}",
        f"{heading}: {page.total} vozila u ponudi. "
        f"{site['company_name']}, {site['company_address']}.",
        query_url("/vozila", canonical_params),
    )
    breadcrumbs = [("Naslovnica", "/"), ("Vozila", "/vozila")]
    return render(
        request,
        "public/vehicles.html",
        {
            "meta": meta,
            "heading": heading,
            "page": page,
            "filters": filters,
            "sort": sort,
            "sorts": vs.PUBLIC_SORTS,
            "options": vs.filter_options(db),
            "models": models,
            "chips": _chips(db, filters, sort),
            "base_params": base_params,
            "prev_url": prev_url,
            "next_url": next_url,
            "price_steps": PRICE_STEPS,
            "fuels": FUELS,
            "transmissions": TRANSMISSIONS,
            "jsonld": [seo.breadcrumbs_jsonld(breadcrumbs)],
        },
    )


# ---------------------------------------------------------------------------
# Vehicle detail
# ---------------------------------------------------------------------------
def _gone(request: Request):
    return render(
        request,
        "public/error.html",
        {
            "status_code": 410,
            "message": "Ovo vozilo je prodano ili uklonjeno iz ponude. Pogledajte ostala vozila.",
        },
        status_code=410,
        headers={"X-Robots-Tag": "noindex"},
    )


@router.get("/vozila/{slug}")
async def vehicle_detail(request: Request, slug: str, db: Session = Depends(get_db)):
    site = get_site()
    vehicle = db.scalar(select(Vehicle).where(Vehicle.slug == slug))
    if vehicle is None:
        history = db.scalar(select(VehicleSlugHistory).where(VehicleSlugHistory.old_slug == slug))
        if history is not None:
            current = db.get(Vehicle, history.vehicle_id)
            if current is not None:
                return RedirectResponse(f"/vozila/{current.slug}", status_code=301)
        raise HTTPException(status_code=404)
    if vehicle.status == STATUS_DRAFT:
        raise HTTPException(status_code=404)
    if not vs.is_publicly_visible(vehicle):
        return _gone(request)

    vs.count_view(db, vehicle, request)
    breadcrumbs = [
        ("Naslovnica", "/"),
        ("Vozila", "/vozila"),
        (VEHICLE_TYPES[vehicle.vehicle_type]["plural"], f"/vozila?tip={vehicle.vehicle_type}"),
        (vehicle.title, f"/vozila/{vehicle.slug}"),
    ]
    return render(
        request,
        "public/vehicle.html",
        {
            "meta": seo.vehicle_meta(vehicle, site),
            "vehicle": vehicle,
            "facts": vs.key_facts(vehicle),
            "specs": vs.spec_sections(vehicle),
            "equipment": equipment_grouped(vehicle.equipment, vehicle.vehicle_type),
            "youtube_id": vs.youtube_id(vehicle.video_url),
            "similar": vs.similar_vehicles(db, vehicle),
            "breadcrumbs": breadcrumbs,
            "jsonld": [seo.vehicle_jsonld(vehicle, site), seo.breadcrumbs_jsonld(breadcrumbs)],
        },
    )


# ---------------------------------------------------------------------------
# Contact and CMS pages
# ---------------------------------------------------------------------------
@router.get("/kontakt")
async def contact(request: Request):
    site = get_site()
    meta = seo.page_meta(
        f"Kontakt – {site['company_name']}",
        f"{site['company_name']}, {site['company_address']}. Telefon {site['company_phone']}, "
        f"radno vrijeme: {site['working_hours']}.",
        "/kontakt",
    )
    return render(
        request,
        "public/contact.html",
        {"meta": meta, "jsonld": [seo.organization_jsonld(site)]},
    )


LEGAL_PAGES = {"privatnost", "kolacici", "uvjeti"}


def _cms_page(request: Request, db: Session, slug: str):
    page = db.scalar(select(Page).where(Page.slug == slug))
    if page is None or not page.is_published:
        raise HTTPException(status_code=404)
    site = get_site()
    meta = seo.page_meta(
        f"{page.title} – {site['company_name']}",
        f"{page.title} — {site['company_name']}.",
        f"/{slug}",
    )
    return render(
        request,
        "public/page.html",
        {
            "meta": meta,
            "page": page,
            "is_legal": slug in LEGAL_PAGES,
            "breadcrumbs": [("Naslovnica", "/"), (page.title, f"/{slug}")],
        },
    )


@router.get("/o-nama")
async def page_about(request: Request, db: Session = Depends(get_db)):
    return _cms_page(request, db, "o-nama")


@router.get("/usluge")
async def page_services(request: Request, db: Session = Depends(get_db)):
    return _cms_page(request, db, "usluge")


@router.get("/privatnost")
async def page_privacy(request: Request, db: Session = Depends(get_db)):
    return _cms_page(request, db, "privatnost")


@router.get("/kolacici")
async def page_cookies(request: Request, db: Session = Depends(get_db)):
    return _cms_page(request, db, "kolacici")


@router.get("/uvjeti")
async def page_terms(request: Request, db: Session = Depends(get_db)):
    return _cms_page(request, db, "uvjeti")


# ---------------------------------------------------------------------------
# Forms (temporary placeholders — real handlers arrive in phases 5 and 6)
# ---------------------------------------------------------------------------
@router.post("/upit")
async def inquiry_submit(request: Request):
    flash(request, "Slanje upita bit će dostupno uskoro.", "info")
    return RedirectResponse(safe_back(request), status_code=303)


@router.post("/newsletter/prijava")
async def newsletter_subscribe(request: Request):
    flash(request, "Prijava na newsletter bit će dostupna uskoro.", "info")
    return RedirectResponse(safe_back(request), status_code=303)


@router.get("/newsletter/potvrda/{token}")
async def newsletter_confirm(request: Request, token: str):
    return render(request, "public/newsletter_result.html", {"state": "soon"})


@router.get("/newsletter/odjava/{token}")
async def newsletter_unsubscribe(request: Request, token: str):
    return render(request, "public/newsletter_result.html", {"state": "soon"})


# ---------------------------------------------------------------------------
# Technical routes
# ---------------------------------------------------------------------------
@router.get("/zdravlje")
async def health(db: Session = Depends(get_db)):
    """Health check for Docker/monitoring. Deliberately reveals no versions or details."""
    try:
        db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - any DB error means unhealthy
        return JSONResponse({"status": "error", "db": "error"}, status_code=503)
    return {"status": "ok", "db": "ok"}


@router.get("/media/{key:path}")
async def media(key: str):
    """Serve locally stored media. Only generated `.webp` files, no path traversal."""
    storage = get_storage()
    if not isinstance(storage, LocalStorage) or not key.endswith(".webp") or not is_safe_key(key):
        raise HTTPException(status_code=404)
    try:
        path = storage._path(key)
    except ValueError as exc:
        raise HTTPException(status_code=404) from exc
    if not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type="image/webp")
