"""Admin: vehicles (list, dynamic form per type, status, duplicate, delete) and images.

Routes:
    GET       /admin/vozila                               list (search, filters, sort, 25/page)
    GET/POST  /admin/vozila/novo                          create
    GET/POST  /admin/vozila/{id}                          edit
    POST      /admin/vozila/{id}/status                   status change (allowed transitions)
    POST      /admin/vozila/{id}/istaknuto                featured on/off
    POST      /admin/vozila/{id}/dupliciraj               copy as draft (without images)
    POST      /admin/vozila/{id}/obrisi                   delete (+ image files)
    GET       /admin/vozila/{id}/slike                    images page
    POST      /admin/vozila/{id}/slike                    upload (JSON for JS, redirect without JS)
    POST      /admin/vozila/{id}/slike/redoslijed         JSON {"order": [ids]} (X-CSRF-Token)
    POST      /admin/vozila/{id}/slike/alt                save alt texts
    POST      /admin/vozila/{id}/slike/{img}/glavna       set main image
    POST      /admin/vozila/{id}/slike/{img}/obrisi       delete image
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.database import get_db
from app.deps import csrf_protect, require_permission
from app.models import (
    STATUS_ACTIVE,
    STATUS_DRAFT,
    Make,
    User,
    Vehicle,
    VehicleImage,
    VehicleModel,
)
from app.pagination import paginate, parse_page
from app.security import client_ip
from app.services import audit
from app.services import vehicles as vehicle_service
from app.services.images import ImageError, delete_variants, save_vehicle_image
from app.services.site import get_site
from app.templating import flash, media_url, render
from app.vehicle_schema import (
    EQUIPMENT,
    EQUIPMENT_CATEGORIES,
    SECTIONS,
    STATUSES,
    TYPE_CODES,
    VEHICLE_TYPES,
    allowed_transitions,
    schema_for,
    status_label,
)

router = APIRouter(prefix="/admin", dependencies=[Depends(csrf_protect)])
settings = get_settings()

SORTS = {
    "azurirano": Vehicle.updated_at.desc(),
    "novo": Vehicle.created_at.desc(),
    "cijena": Vehicle.price_eur.asc(),
    "-cijena": Vehicle.price_eur.desc(),
    "godina": Vehicle.year.desc(),
    "km": Vehicle.mileage_km.asc(),
    "pregledi": Vehicle.views_total.desc(),
}


def _get_vehicle(db: Session, vehicle_id: int) -> Vehicle:
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise HTTPException(status_code=404)
    return vehicle


def _safe_back(url: str | None, default: str = "/admin/vozila") -> str:
    if url and url.startswith("/admin/vozila") and not url.startswith("//"):
        return url
    return default


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------
@router.get("/vozila")
async def vehicles_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("vehicles")),
):
    params = request.query_params
    filters = {
        "q": params.get("q", "").strip()[:100],
        "status": params.get("status", ""),
        "tip": params.get("tip", ""),
        "marka": params.get("marka", ""),
        "sort": params.get("sort", "azurirano"),
    }
    stmt = select(Vehicle).options(
        selectinload(Vehicle.images), selectinload(Vehicle.make), selectinload(Vehicle.model)
    )
    if filters["q"]:
        q = filters["q"]
        conditions = [Vehicle.title.ilike(f"%{q}%"), Vehicle.vin.ilike(f"%{q}%")]
        if q.isdigit():
            conditions.append(Vehicle.id == int(q))
        stmt = stmt.where(or_(*conditions))
    if filters["status"] in STATUSES:
        stmt = stmt.where(Vehicle.status == filters["status"])
    if filters["tip"] in VEHICLE_TYPES:
        stmt = stmt.where(Vehicle.vehicle_type == filters["tip"])
    if filters["marka"].isdigit():
        stmt = stmt.where(Vehicle.make_id == int(filters["marka"]))
    order = SORTS.get(filters["sort"], SORTS["azurirano"])
    stmt = stmt.order_by(order, Vehicle.id.desc())

    page = paginate(db, stmt, parse_page(params.get("stranica")), 25)
    counts = dict(db.execute(select(Vehicle.status, func.count()).group_by(Vehicle.status)).all())
    makes = list(
        db.scalars(select(Make).where(Make.id.in_(select(Vehicle.make_id))).order_by(Make.name))
    )
    return render(
        request,
        "admin/vehicles/list.html",
        {
            "section": "vozila",
            "page": page,
            "filters": filters,
            "counts": counts,
            "makes": makes,
            "statuses": STATUSES,
            "types": VEHICLE_TYPES,
            "allowed_transitions": allowed_transitions,
            "status_label": status_label,
            "can_delete": lambda v: vehicle_service.can_delete(user, v),
        },
    )


# ---------------------------------------------------------------------------
# Create / edit form
# ---------------------------------------------------------------------------
def _form_context(
    db: Session, vehicle: Vehicle | None, raw: dict, errors: dict, vehicle_type: str
) -> dict:
    makes = list(db.scalars(select(Make).order_by(Make.name)))
    make_id = raw.get("make_id") or (vehicle.make_id if vehicle else None)
    try:
        make_id = int(make_id) if make_id else None
    except ValueError:
        make_id = None
    models = []
    if make_id:
        models = list(
            db.scalars(
                select(VehicleModel)
                .where(VehicleModel.make_id == make_id)
                .order_by(VehicleModel.name)
            )
        )
    current_status = vehicle.status if vehicle else STATUS_DRAFT
    status_choices = [current_status] + allowed_transitions(current_status)
    if vehicle is None:
        status_choices = [STATUS_DRAFT, STATUS_ACTIVE]
    return {
        "section": "vozila",
        "vehicle": vehicle,
        "raw": raw,
        "errors": errors,
        "vehicle_type": vehicle_type,
        "types": VEHICLE_TYPES,
        "schemas": {code: schema_for(code) for code in TYPE_CODES},
        "sections": SECTIONS,
        "makes": makes,
        "models": models,
        "make_id": make_id,
        "status_choices": status_choices,
        "status_label": status_label,
        "equipment_items": EQUIPMENT,
        "equipment_categories": EQUIPMENT_CATEGORIES,
    }


def _raw_from_vehicle(vehicle: Vehicle) -> dict:
    """Current values as form strings (for the edit form)."""
    raw: dict = {}
    for column in Vehicle.__table__.columns.keys():
        value = getattr(vehicle, column)
        if value is None:
            raw[column] = ""
        elif isinstance(value, bool):
            raw[column] = "1" if value else ""
        elif column in ("first_registration", "registered_until"):
            raw[column] = value.strftime("%Y-%m")
        elif isinstance(value, float):
            raw[column] = f"{value:g}"
        else:
            raw[column] = value
    for key, value in (vehicle.attributes or {}).items():
        raw[f"{vehicle.vehicle_type}__{key}"] = (
            "1" if value is True else ("" if value is False else value)
        )
    raw["equipment"] = list(vehicle.equipment or [])
    raw["status"] = vehicle.status
    return raw


@router.get("/vozila/novo")
async def vehicle_new(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("vehicles")),
):
    vehicle_type = request.query_params.get("tip", "car")
    if vehicle_type not in VEHICLE_TYPES:
        vehicle_type = "car"
    raw = {
        "vehicle_type": vehicle_type,
        "condition": "used",
        "tax_type": "marza",
        "status": STATUS_DRAFT,
        "equipment": [],
    }
    return render(
        request, "admin/vehicles/form.html", _form_context(db, None, raw, {}, vehicle_type)
    )


@router.post("/vozila/novo")
async def vehicle_create(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("vehicles")),
):
    form = await request.form()
    values, raw, errors = vehicle_service.parse_vehicle_form(db, form)
    requested_status = str(form.get("status", STATUS_DRAFT))
    if errors:
        context = _form_context(db, None, raw, errors, raw.get("vehicle_type") or "car")
        return render(request, "admin/vehicles/form.html", context, status_code=400)
    values["status"] = STATUS_DRAFT
    vehicle = vehicle_service.create_vehicle(db, values, user)
    if requested_status == STATUS_ACTIVE:
        vehicle_service.change_status(vehicle, STATUS_ACTIVE)
    audit.log(
        db,
        user.id,
        "vehicle.create",
        "vehicle",
        vehicle.id,
        {"type": vehicle.vehicle_type, "status": vehicle.status},
        client_ip(request),
    )
    db.commit()
    flash(request, "Vozilo je spremljeno. Dodajte fotografije.", "success")
    return RedirectResponse(f"/admin/vozila/{vehicle.id}/slike", status_code=303)


@router.get("/vozila/{vehicle_id}")
async def vehicle_edit(
    request: Request,
    vehicle_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("vehicles")),
):
    vehicle = _get_vehicle(db, vehicle_id)
    context = _form_context(db, vehicle, _raw_from_vehicle(vehicle), {}, vehicle.vehicle_type)
    context["can_delete"] = vehicle_service.can_delete(user, vehicle)
    return render(request, "admin/vehicles/form.html", context)


@router.post("/vozila/{vehicle_id}")
async def vehicle_update(
    request: Request,
    vehicle_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("vehicles")),
):
    vehicle = _get_vehicle(db, vehicle_id)
    form = await request.form()
    values, raw, errors = vehicle_service.parse_vehicle_form(db, form, current=vehicle)
    new_status = str(form.get("status", vehicle.status))
    if (
        not errors
        and new_status != vehicle.status
        and new_status not in allowed_transitions(vehicle.status)
    ):
        errors["status"] = "Ta promjena statusa nije dopuštena."
    if errors:
        context = _form_context(db, vehicle, raw, errors, raw.get("vehicle_type") or "car")
        context["can_delete"] = vehicle_service.can_delete(user, vehicle)
        return render(request, "admin/vehicles/form.html", context, status_code=400)

    changed = []
    for key, value in values.items():
        if getattr(vehicle, key) != value:
            setattr(vehicle, key, value)
            changed.append(key)
    if new_status != vehicle.status:
        vehicle_service.change_status(vehicle, new_status)
        changed.append("status")
    vehicle_service.refresh_title_and_slug(db, vehicle)
    if changed:
        audit.log(
            db,
            user.id,
            "vehicle.update",
            "vehicle",
            vehicle.id,
            {"fields": sorted(changed)},
            client_ip(request),
        )
    db.commit()
    flash(request, "Promjene su spremljene.", "success")
    return RedirectResponse(f"/admin/vozila/{vehicle.id}", status_code=303)


# ---------------------------------------------------------------------------
# Quick actions
# ---------------------------------------------------------------------------
@router.post("/vozila/{vehicle_id}/status")
async def vehicle_status(
    request: Request,
    vehicle_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("vehicles")),
):
    vehicle = _get_vehicle(db, vehicle_id)
    form = await request.form()
    new_status = str(form.get("status", ""))
    old_status = vehicle.status
    error = vehicle_service.change_status(vehicle, new_status)
    if error:
        flash(request, error, "error")
    elif old_status != vehicle.status:
        audit.log(
            db,
            user.id,
            "vehicle.status",
            "vehicle",
            vehicle.id,
            {"from": old_status, "to": vehicle.status},
            client_ip(request),
        )
        db.commit()
        flash(request, f"{vehicle.title}: status „{status_label(vehicle.status)}”.", "success")
    return RedirectResponse(_safe_back(str(form.get("next", ""))), status_code=303)


@router.post("/vozila/{vehicle_id}/istaknuto")
async def vehicle_feature(
    request: Request,
    vehicle_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("vehicles")),
):
    vehicle = _get_vehicle(db, vehicle_id)
    form = await request.form()
    vehicle.featured = not vehicle.featured
    audit.log(
        db,
        user.id,
        "vehicle.feature",
        "vehicle",
        vehicle.id,
        {"featured": vehicle.featured},
        client_ip(request),
    )
    db.commit()
    return RedirectResponse(_safe_back(str(form.get("next", ""))), status_code=303)


@router.post("/vozila/{vehicle_id}/dupliciraj")
async def vehicle_duplicate(
    request: Request,
    vehicle_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("vehicles")),
):
    vehicle = _get_vehicle(db, vehicle_id)
    copy = vehicle_service.duplicate_vehicle(db, vehicle, user)
    audit.log(
        db,
        user.id,
        "vehicle.duplicate",
        "vehicle",
        copy.id,
        {"source": vehicle.id},
        client_ip(request),
    )
    db.commit()
    flash(request, "Kopija je spremljena kao skica (bez fotografija).", "success")
    return RedirectResponse(f"/admin/vozila/{copy.id}", status_code=303)


@router.post("/vozila/{vehicle_id}/obrisi")
async def vehicle_delete(
    request: Request,
    vehicle_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("vehicles")),
):
    vehicle = _get_vehicle(db, vehicle_id)
    if not vehicle_service.can_delete(user, vehicle):
        raise HTTPException(status_code=403, detail="Možete brisati samo vlastite skice.")
    title = vehicle.title
    vehicle_service.delete_vehicle(db, vehicle)
    audit.log(
        db,
        user.id,
        "vehicle.delete",
        "vehicle",
        vehicle_id,
        {"status": vehicle.status},
        client_ip(request),
    )
    db.commit()
    flash(request, f"Vozilo „{title}” je obrisano.", "success")
    return RedirectResponse("/admin/vozila", status_code=303)


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------
def _images_context(vehicle: Vehicle) -> dict:
    return {
        "section": "vozila",
        "vehicle": vehicle,
        "images": vehicle.images,
        "max_images": settings.MAX_IMAGES_PER_VEHICLE,
        "max_mb": settings.MAX_UPLOAD_MB,
        "plates_required": get_site()["plates_reminder_enabled"],
        "status_label": status_label,
    }


@router.get("/vozila/{vehicle_id}/slike")
async def images_page(
    request: Request,
    vehicle_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("vehicles")),
):
    vehicle = _get_vehicle(db, vehicle_id)
    return render(request, "admin/vehicles/images.html", _images_context(vehicle))


def _image_json(image: VehicleImage) -> dict:
    return {
        "id": image.id,
        "thumb": media_url(image, 400),
        "alt": image.alt,
        "width": image.width,
        "height": image.height,
    }


def _renumber(images: list[VehicleImage]) -> None:
    for index, image in enumerate(images):
        image.sort_order = index


@router.post("/vozila/{vehicle_id}/slike")
async def images_upload(
    request: Request,
    vehicle_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("vehicles")),
):
    vehicle = _get_vehicle(db, vehicle_id)
    wants_json = "application/json" in request.headers.get("accept", "")
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024

    def fail(message: str, status: int = 400):
        if wants_json:
            return JSONResponse({"ok": False, "errors": [message]}, status_code=status)
        flash(request, message, "error")
        return RedirectResponse(f"/admin/vozila/{vehicle.id}/slike", status_code=303)

    content_length = int(request.headers.get("content-length") or 0)
    if content_length > max_bytes * 10 + 1024 * 1024:
        return fail("Zahtjev je prevelik. Učitajte manje slika odjednom.", 413)
    form = await request.form()
    if get_site()["plates_reminder_enabled"] and form.get("plates_confirmed") != "1":
        return fail("Potvrdite da su registarske tablice zamagljene ili prekrivene.")
    uploads = [
        f for f in form.getlist("files") if hasattr(f, "read") and getattr(f, "filename", "")
    ]
    if not uploads:
        return fail("Odaberite barem jednu sliku.")
    existing = len(vehicle.images)
    if existing + len(uploads) > settings.MAX_IMAGES_PER_VEHICLE:
        return fail(
            f"Najviše {settings.MAX_IMAGES_PER_VEHICLE} slika po vozilu (trenutno {existing})."
        )

    created: list[VehicleImage] = []
    errors: list[str] = []
    next_order = max((image.sort_order for image in vehicle.images), default=-1) + 1
    for upload in uploads:
        data = await upload.read(max_bytes + 1)
        try:
            key, processed = await run_in_threadpool(save_vehicle_image, vehicle.id, data)
        except ImageError as exc:
            errors.append(f"{upload.filename}: {exc}")
            continue
        image = VehicleImage(
            vehicle_id=vehicle.id,
            file_key=key,
            sort_order=next_order,
            width=processed.width,
            height=processed.height,
        )
        next_order += 1
        db.add(image)
        created.append(image)
    if created:
        audit.log(
            db,
            user.id,
            "vehicle.images",
            "vehicle",
            vehicle.id,
            {"added": len(created)},
            client_ip(request),
        )
        db.commit()
    if wants_json:
        return JSONResponse(
            {"ok": not errors, "images": [_image_json(i) for i in created], "errors": errors},
            status_code=200 if created or not errors else 400,
        )
    if created:
        flash(request, f"Učitano slika: {len(created)}.", "success")
    for message in errors:
        flash(request, message, "error")
    return RedirectResponse(f"/admin/vozila/{vehicle.id}/slike", status_code=303)


@router.post("/vozila/{vehicle_id}/slike/redoslijed")
async def images_reorder(
    request: Request,
    vehicle_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("vehicles")),
):
    vehicle = _get_vehicle(db, vehicle_id)
    try:
        payload = json.loads(await request.body() or b"{}")
        order = [int(x) for x in payload.get("order", [])]
    except (ValueError, TypeError, AttributeError):
        return JSONResponse({"ok": False, "error": "Neispravan zahtjev."}, status_code=400)
    by_id = {image.id: image for image in vehicle.images}
    if sorted(order) != sorted(by_id):
        return JSONResponse({"ok": False, "error": "Popis slika ne odgovara."}, status_code=400)
    _renumber([by_id[image_id] for image_id in order])
    audit.log(
        db,
        user.id,
        "vehicle.images",
        "vehicle",
        vehicle.id,
        {"reordered": True},
        client_ip(request),
    )
    db.commit()
    return JSONResponse({"ok": True})


@router.post("/vozila/{vehicle_id}/slike/alt")
async def images_alt(
    request: Request,
    vehicle_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("vehicles")),
):
    vehicle = _get_vehicle(db, vehicle_id)
    form = await request.form()
    for image in vehicle.images:
        value = form.get(f"alt_{image.id}")
        if value is not None:
            image.alt = str(value).strip()[:250]
    db.commit()
    flash(request, "Opisi slika su spremljeni.", "success")
    return RedirectResponse(f"/admin/vozila/{vehicle.id}/slike", status_code=303)


def _get_image(vehicle: Vehicle, image_id: int) -> VehicleImage:
    image = next((i for i in vehicle.images if i.id == image_id), None)
    if image is None:
        raise HTTPException(status_code=404)
    return image


@router.post("/vozila/{vehicle_id}/slike/{image_id}/glavna")
async def image_set_main(
    request: Request,
    vehicle_id: int,
    image_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("vehicles")),
):
    vehicle = _get_vehicle(db, vehicle_id)
    image = _get_image(vehicle, image_id)
    ordered = [image] + [i for i in vehicle.images if i.id != image.id]
    _renumber(ordered)
    audit.log(
        db, user.id, "vehicle.images", "vehicle", vehicle.id, {"main": image.id}, client_ip(request)
    )
    db.commit()
    flash(request, "Glavna slika je postavljena.", "success")
    return RedirectResponse(f"/admin/vozila/{vehicle.id}/slike", status_code=303)


@router.post("/vozila/{vehicle_id}/slike/{image_id}/obrisi")
async def image_delete(
    request: Request,
    vehicle_id: int,
    image_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("vehicles")),
):
    vehicle = _get_vehicle(db, vehicle_id)
    image = _get_image(vehicle, image_id)
    delete_variants(image.file_key)
    vehicle.images.remove(image)
    db.delete(image)
    _renumber(list(vehicle.images))
    audit.log(
        db,
        user.id,
        "vehicle.images",
        "vehicle",
        vehicle.id,
        {"deleted": image_id},
        client_ip(request),
    )
    db.commit()
    flash(request, "Slika je obrisana.", "success")
    return RedirectResponse(f"/admin/vozila/{vehicle.id}/slike", status_code=303)
