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

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.deps import csrf_protect, public_feature
from app.models import (
    INQUIRY_FINANCING,
    INQUIRY_GENERAL,
    INQUIRY_VIEWING,
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
from app.security import check_form_timestamp, check_rate_limit, client_ip, email_hash
from app.services import content, seo
from app.services import inquiries as inquiry_service
from app.services import newsletter as newsletter_service
from app.services import vehicles as vs
from app.services.site import get_site
from app.services.storage import LocalStorage, get_storage, is_safe_key
from app.services.turnstile import TOKEN_FIELD, verify_turnstile
from app.templating import flash, format_number, query_url, render
from app.vehicle_schema import (
    VEHICLE_TYPES,
    equipment_grouped,
    field_options,
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
        "gorivo": lambda v: dict(field_options("fuel")).get(v, v),
        "mjenjac": lambda v: dict(field_options("transmission")).get(v, v),
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
            "fuels": field_options("fuel"),
            "transmissions": field_options("transmission"),
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
    return render(request, "public/vehicle.html", _vehicle_context(db, vehicle))


# ---------------------------------------------------------------------------
# WhatsApp / Viber (paket Standard): count the click, then hand over to the app
# ---------------------------------------------------------------------------
@router.get("/idi/{channel}", dependencies=[Depends(public_feature("whatsapp"))])
@router.get("/idi/{channel}/{vehicle_id:int}", dependencies=[Depends(public_feature("whatsapp"))])
async def chat_redirect(
    request: Request, channel: str, vehicle_id: int | None = None, db: Session = Depends(get_db)
):
    from app.services import messaging

    meta = messaging.CHANNELS.get(channel)
    number = (get_site().get(meta["setting"]) or "").strip() if meta else ""
    if not number:
        raise HTTPException(status_code=404)
    vehicle = None
    if vehicle_id is not None:
        vehicle = db.get(Vehicle, vehicle_id)
        if vehicle is None or not vs.is_publicly_visible(vehicle):
            raise HTTPException(status_code=404)
    if not vs.is_bot(request.headers.get("user-agent")):
        messaging.record_click(db, channel, vehicle.id if vehicle else None)
    vehicle_url = f"{settings.base_url}/vozila/{vehicle.slug}" if vehicle else None
    target = messaging.channel_url(channel, number, messaging.message_text(vehicle, vehicle_url))
    return RedirectResponse(
        target, status_code=302, headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"}
    )


def _vehicle_context(db: Session, vehicle: Vehicle) -> dict:
    site = get_site()
    breadcrumbs = [
        ("Naslovnica", "/"),
        ("Vozila", "/vozila"),
        (VEHICLE_TYPES[vehicle.vehicle_type]["plural"], f"/vozila?tip={vehicle.vehicle_type}"),
        (vehicle.title, f"/vozila/{vehicle.slug}"),
    ]
    specs = vs.spec_sections(vehicle)
    equipment = equipment_grouped(vehicle.equipment, vehicle.vehicle_type)
    from app.plans import has_feature
    from app.services import financing

    show_financing = financing.calculator_enabled(site) and financing.financeable(vehicle)
    return {
        "financing": financing.example(vehicle) if show_financing else None,
        "financing_cfg": financing.config(site) if show_financing else None,
        "financing_form": show_financing and has_feature("upit_financiranje"),
        "meta": seo.vehicle_meta(vehicle, site),
        "vehicle": vehicle,
        "facts": vs.key_facts(vehicle),
        "energy": vs.energy_metrics(vehicle),
        "specs": specs,
        "spec_columns": vs.spec_columns(specs),
        "highlights": vs.highlights(vehicle),
        "equipment": equipment,
        "equipment_columns": vs.equipment_columns(equipment),
        "youtube_id": vs.youtube_id(vehicle.video_url),
        "similar": vs.similar_vehicles(db, vehicle),
        "breadcrumbs": breadcrumbs,
        "min_viewing_date": inquiry_service.min_viewing_value(),
        "jsonld": [seo.vehicle_jsonld(vehicle, site), seo.breadcrumbs_jsonld(breadcrumbs)],
    }


# ---------------------------------------------------------------------------
# Contact and CMS pages
# ---------------------------------------------------------------------------
def _contact_context() -> dict:
    site = get_site()
    meta = seo.page_meta(
        f"Kontakt – {site['company_name']}",
        f"{site['company_name']}, {site['company_address']}. Telefon {site['company_phone']}, "
        f"radno vrijeme: {site['working_hours']}.",
        "/kontakt",
    )
    return {"meta": meta, "jsonld": [seo.organization_jsonld(site)]}


@router.get("/kontakt")
async def contact(request: Request):
    return render(request, "public/contact.html", _contact_context())


# ---------------------------------------------------------------------------
# Favourites and comparison (state in the browser, IDs in the URL -> shareable)
# ---------------------------------------------------------------------------
@router.get("/favoriti")
async def favorites(request: Request, db: Session = Depends(get_db)):
    from app.services import compare

    site = get_site()
    vehicles = compare.load_public(
        db, compare.parse_ids(request.query_params.get("v"), compare.MAX_FAVORITES)
    )
    path = "/favoriti" + (f"?v={compare.ids_param(vehicles)}" if vehicles else "")
    return render(
        request,
        "public/favorites.html",
        {
            "meta": seo.page_meta(
                f"Favoriti – {site['company_name']}",
                "Vozila koja ste spremili u favorite.",
                path,
                noindex=True,
            ),
            "vehicles": vehicles,
            "share_url": seo.absolute(path),
            "breadcrumbs": [("Naslovnica", "/"), ("Favoriti", "/favoriti")],
        },
    )


@router.get("/usporedba")
async def comparison(request: Request, db: Session = Depends(get_db)):
    from app.services import compare

    site = get_site()
    vehicles = compare.load_public(
        db, compare.parse_ids(request.query_params.get("v"), compare.MAX_COMPARE)
    )
    path = "/usporedba" + (f"?v={compare.ids_param(vehicles)}" if vehicles else "")
    remove_urls = {
        v.id: "/usporedba?v=" + ",".join(str(o.id) for o in vehicles if o.id != v.id)
        for v in vehicles
    }
    return render(
        request,
        "public/compare.html",
        {
            "meta": seo.page_meta(
                f"Usporedba vozila – {site['company_name']}",
                " · ".join(v.title for v in vehicles) or "Usporedba vozila.",
                path,
                noindex=True,  # combinatorial pages
            ),
            "vehicles": vehicles,
            "sections": compare.comparison(vehicles) if vehicles else [],
            "remove_urls": remove_urls,
            "share_url": seo.absolute(path),
            "max_compare": compare.MAX_COMPARE,
            "breadcrumbs": [("Naslovnica", "/"), ("Usporedba", "/usporedba")],
        },
    )


LEGAL_PAGES = {"privatnost", "kolacici", "uvjeti"}


def _cms_page(request: Request, db: Session, slug: str):
    page = db.scalar(select(Page).where(Page.slug == slug))
    if page is None or not page.is_published:
        raise HTTPException(status_code=404)
    site = get_site()
    intro = content.first_paragraph_text(page.body_html)
    meta = seo.page_meta(
        f"{page.title} – {site['company_name']}",
        intro or f"{page.title} — {site['company_name']}.",
        f"/{slug}",
    )
    return render(
        request,
        content.page_template(slug),
        {
            "meta": meta,
            "page": page,
            "is_legal": slug in LEGAL_PAGES,
            "breadcrumbs": [("Naslovnica", "/"), (page.title, f"/{slug}")],
            **content.page_extras(db, slug, page.body_html),
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
async def inquiry_submit(
    request: Request, background: BackgroundTasks, db: Session = Depends(get_db)
):
    """Inquiry form (vehicle / viewing / general). Anti-spam: honeypot, timing check,
    Turnstile (if configured), rate limits (5 / 10 min per IP, 3 / h per email)."""
    form = await request.form()
    site = get_site()
    kind = str(form.get("type", INQUIRY_GENERAL))
    vehicle = None
    if kind == INQUIRY_FINANCING:
        from app.plans import has_feature

        if not has_feature("upit_financiranje"):
            raise HTTPException(status_code=404)  # locked features do not exist publicly
    if kind in inquiry_service.VEHICLE_INQUIRY_TYPES:
        try:
            vehicle = db.get(Vehicle, int(str(form.get("vehicle_id", ""))))
        except ValueError:
            vehicle = None
        from app.services.financing import financeable

        unavailable = vehicle is None or not vs.is_publicly_visible(vehicle)
        if unavailable or (kind == INQUIRY_FINANCING and not financeable(vehicle)):
            return render(
                request,
                "public/error.html",
                {"status_code": 400, "message": "Vozilo za koje šaljete upit nije dostupno."},
                status_code=400,
            )
    back_url = f"/vozila/{vehicle.slug}" if vehicle else "/kontakt"

    # Honeypot: pretend success, store nothing.
    if str(form.get("website", "")).strip():
        flash(request, inquiry_service.SUCCESS_MESSAGE, "success")
        return RedirectResponse(back_url, status_code=303)

    values = {
        key: str(form.get(key, ""))
        for key in (
            "name",
            "email",
            "phone",
            "message",
            "preferred_date",
            "consent",
            "down_payment",
            "months",
        )
    }

    def rerender(errors: dict, status_code: int):
        if vehicle is None:
            context = _contact_context() | {"inquiry_values": values, "inquiry_errors": errors}
            return render(request, "public/contact.html", context, status_code=status_code)
        context = _vehicle_context(db, vehicle)
        if kind == INQUIRY_VIEWING:
            context |= {"viewing_values": values, "viewing_errors": errors, "viewing_open": True}
        elif kind == INQUIRY_FINANCING:
            context |= {
                "financing_values": values,
                "financing_errors": errors,
                "financing_open": True,
            }
        else:
            context |= {"inquiry_values": values, "inquiry_errors": errors}
        return render(request, "public/vehicle.html", context, status_code=status_code)

    if not check_rate_limit(request, "inquiry-ip", 5, 600):
        message = (
            "Poslali ste previše upita u kratkom vremenu. "
            "Pokušajte ponovno za nekoliko minuta ili nas nazovite."
        )
        return rerender({"form": message}, 429)

    clean, errors = inquiry_service.validate_inquiry(form, vehicle)
    timing = check_form_timestamp(str(form.get("form_ts", "")))
    if timing == "fast":
        errors["form"] = (
            "Obrazac je poslan prebrzo. Pričekajte nekoliko sekundi i pošaljite ponovno."
        )
    elif timing == "invalid":
        errors["form"] = "Obrazac je istekao. Osvježite stranicu i pošaljite ponovno."
    if not errors and not verify_turnstile(str(form.get(TOKEN_FIELD, "")), client_ip(request)):
        errors["form"] = "Provjera protiv neželjenih poruka nije uspjela. Pokušajte ponovno."
    if errors:
        return rerender(errors, 400)
    if not check_rate_limit(request, "inquiry-email", 3, 3600, key=email_hash(clean["email"])):
        message = "S ove email adrese već smo primili više upita. Javit ćemo vam se uskoro."
        return rerender({"form": message}, 429)

    inquiry = inquiry_service.create_inquiry(
        db,
        clean,
        vehicle,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
        policy_version=site["privacy_policy_version"],
        source_url=safe_back(request, back_url),
    )
    db.commit()
    background.add_task(inquiry_service.send_notification, inquiry.id)
    background.add_task(inquiry_service.send_auto_reply, inquiry.id)  # checks plan + setting
    flash(request, inquiry_service.SUCCESS_MESSAGE, "success")
    return RedirectResponse(back_url, status_code=303)


@router.post("/newsletter/prijava")
async def newsletter_subscribe(
    request: Request, background: BackgroundTasks, db: Session = Depends(get_db)
):
    """Newsletter signup (footer, home, vehicle page) with double opt-in.

    Always answers with the same neutral message (never reveals whether an address exists).
    """
    form = await request.form()
    back = safe_back(request)
    if str(form.get("website", "")).strip():  # honeypot
        flash(request, newsletter_service.NEUTRAL_MESSAGE, "success")
        return RedirectResponse(back, status_code=303)
    if not check_rate_limit(request, "newsletter-ip", 5, 600):
        flash(request, "Previše pokušaja prijave. Pokušajte ponovno za nekoliko minuta.", "error")
        return RedirectResponse(back, status_code=303)
    email = str(form.get("email", ""))
    if not newsletter_service.valid_email(email.strip().lower()):
        flash(request, "Upišite ispravnu email adresu za prijavu na newsletter.", "error")
        return RedirectResponse(back, status_code=303)
    if str(form.get("consent", "")) not in ("1", "on", "true"):
        flash(request, "Za prijavu na newsletter potrebna je vaša privola.", "error")
        return RedirectResponse(back, status_code=303)
    if check_form_timestamp(str(form.get("form_ts", ""))) is not None:
        flash(request, "Obrazac je poslan prebrzo ili je istekao. Pokušajte ponovno.", "error")
        return RedirectResponse(back, status_code=303)
    if not verify_turnstile(str(form.get(TOKEN_FIELD, "")), client_ip(request)):
        flash(request, "Provjera protiv neželjenih poruka nije uspjela.", "error")
        return RedirectResponse(back, status_code=303)
    raw = newsletter_service.subscribe(
        db,
        email,
        {
            "ip": client_ip(request),
            "user_agent": request.headers.get("user-agent", ""),
            "policy_version": get_site()["privacy_policy_version"],
            "source": str(form.get("source", "footer")),
        },
    )
    db.commit()
    if raw:
        background.add_task(newsletter_service.send_confirmation, email.strip().lower(), raw)
    flash(request, newsletter_service.NEUTRAL_MESSAGE, "success")
    return RedirectResponse(back, status_code=303)


@router.get("/newsletter/potvrda/{token}")
async def newsletter_confirm(request: Request, token: str, db: Session = Depends(get_db)):
    subscriber = newsletter_service.confirm(db, token)
    if subscriber is None:
        return render(
            request, "public/newsletter_result.html", {"state": "invalid"}, status_code=400
        )
    db.commit()
    return render(request, "public/newsletter_result.html", {"state": "confirmed"})


@router.get("/newsletter/odjava/{token}")
async def newsletter_unsubscribe_page(request: Request, token: str, db: Session = Depends(get_db)):
    """Shows a confirmation button; `?potvrdi=1` (link in emails) unsubscribes immediately."""
    if newsletter_service.find_by_unsubscribe_token(db, token) is None:
        return render(
            request, "public/newsletter_result.html", {"state": "invalid"}, status_code=400
        )
    if request.query_params.get("potvrdi") == "1":
        newsletter_service.unsubscribe(db, token)
        db.commit()
        return render(request, "public/newsletter_result.html", {"state": "unsubscribed"})
    return render(request, "public/newsletter_result.html", {"state": "unsubscribe_confirm"})


# One-click unsubscribe (RFC 8058): mail clients POST "List-Unsubscribe=One-Click" without a
# CSRF token. The unguessable token in the URL is the authorisation, so this single route is
# registered on a router WITHOUT the CSRF dependency.
unsubscribe_router = APIRouter()


@unsubscribe_router.post("/newsletter/odjava/{token}")
async def newsletter_unsubscribe(request: Request, token: str, db: Session = Depends(get_db)):
    if not newsletter_service.unsubscribe(db, token):
        return render(
            request, "public/newsletter_result.html", {"state": "invalid"}, status_code=400
        )
    db.commit()
    return render(request, "public/newsletter_result.html", {"state": "unsubscribed"})


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
