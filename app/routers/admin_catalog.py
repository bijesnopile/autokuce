"""Catalog of makes and models (admin) + public JSON API for dependent model selects.

Routes:
    GET  /api/modeli?marka={id}&tip={type}         JSON [{id, name}] (public, 60/min)
    GET  /admin/katalog/marke                        makes list + add form
    POST /admin/katalog/marke                        add make
    POST /admin/katalog/marke/{id}                   rename make
    POST /admin/katalog/marke/{id}/aktivno           toggle active
    POST /admin/katalog/marke/{id}/obrisi            delete (only without vehicles)
    GET  /admin/katalog/marke/{id}/modeli            models of a make + add form
    POST /admin/katalog/marke/{id}/modeli            add model
    POST /admin/katalog/modeli/{id}                  edit model (name, type)
    POST /admin/katalog/modeli/{id}/aktivno          toggle active
    POST /admin/katalog/modeli/{id}/obrisi           delete (only without vehicles)
    GET/POST /admin/katalog/uvoz                     CSV import (preview, then confirm)
    GET  /admin/katalog/tipovi                       read-only overview of vehicle types/fields
"""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import csrf_protect, require_permission
from app.models import Make, User, Vehicle, VehicleModel
from app.security import client_ip, rate_limit
from app.services import audit
from app.templating import flash, render
from app.utils import slugify
from app.vehicle_schema import (
    COMMON_FIELDS,
    SECTION_LABELS,
    TYPE_FIELDS,
    VEHICLE_TYPES,
    equipment_for,
    type_label,
)

router = APIRouter(dependencies=[Depends(csrf_protect)])

# Accepted values for the "tip" column in CSV imports (codes and Croatian words).
TYPE_ALIASES = {
    "": None,
    "svi": None,
    "car": "car",
    "osobni": "car",
    "osobni automobil": "car",
    "automobil": "car",
    "van": "van",
    "kombi": "van",
    "dostavno": "van",
    "motorcycle": "motorcycle",
    "motocikl": "motorcycle",
    "motor": "motorcycle",
    "camper": "camper",
    "kamper": "camper",
    "truck": "truck",
    "kamion": "truck",
}


# ---------------------------------------------------------------------------
# Public JSON API
# ---------------------------------------------------------------------------
@router.get("/api/modeli", dependencies=[Depends(rate_limit("api", 100, 60))])
async def api_models(request: Request, db: Session = Depends(get_db)):
    try:
        make_id = int(request.query_params.get("marka", ""))
    except ValueError:
        return JSONResponse([])
    vehicle_type = request.query_params.get("tip") or None
    stmt = (
        select(VehicleModel.id, VehicleModel.name)
        .join(Make)
        .where(VehicleModel.make_id == make_id, VehicleModel.is_active, Make.is_active)
        .order_by(VehicleModel.name)
    )
    if vehicle_type in VEHICLE_TYPES:
        stmt = stmt.where(
            or_(VehicleModel.vehicle_type.is_(None), VehicleModel.vehicle_type == vehicle_type)
        )
    rows = db.execute(stmt).all()
    return JSONResponse(
        [{"id": row.id, "name": row.name} for row in rows],
        headers={"Cache-Control": "public, max-age=300"},
    )


# ---------------------------------------------------------------------------
# Makes
# ---------------------------------------------------------------------------
def _unique_make_slug(db: Session, name: str, exclude_id: int | None = None) -> str | None:
    slug = slugify(name)
    stmt = select(Make.id).where(Make.slug == slug)
    if exclude_id:
        stmt = stmt.where(Make.id != exclude_id)
    return None if db.scalar(stmt) else slug


@router.get("/admin/katalog/marke")
async def makes_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("catalog")),
):
    model_counts = dict(
        db.execute(select(VehicleModel.make_id, func.count()).group_by(VehicleModel.make_id)).all()
    )
    vehicle_counts = dict(
        db.execute(select(Vehicle.make_id, func.count()).group_by(Vehicle.make_id)).all()
    )
    q = request.query_params.get("q", "").strip()
    stmt = select(Make).order_by(Make.name)
    if q:
        stmt = stmt.where(Make.name.ilike(f"%{q}%"))
    makes = list(db.scalars(stmt))
    return render(
        request,
        "admin/catalog/makes.html",
        {
            "section": "katalog",
            "makes": makes,
            "model_counts": model_counts,
            "vehicle_counts": vehicle_counts,
            "q": q,
            "errors": {},
        },
    )


@router.post("/admin/katalog/marke")
async def make_create(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("catalog")),
):
    form = await request.form()
    name = str(form.get("name", "")).strip()[:80]
    slug = _unique_make_slug(db, name) if len(name) >= 2 else None
    if not slug:
        flash(request, "Upišite naziv marke (marka s tim nazivom možda već postoji).", "error")
        return RedirectResponse("/admin/katalog/marke", status_code=303)
    make = Make(name=name, slug=slug, is_active=True)
    db.add(make)
    db.flush()
    audit.log(db, user.id, "catalog.make", "make", make.id, {"op": "create"}, client_ip(request))
    db.commit()
    flash(request, f"Marka {name} je dodana. Sada dodajte modele.", "success")
    return RedirectResponse(f"/admin/katalog/marke/{make.id}/modeli", status_code=303)


def _get_make(db: Session, make_id: int) -> Make:
    make = db.get(Make, make_id)
    if make is None:
        raise HTTPException(status_code=404)
    return make


@router.post("/admin/katalog/marke/{make_id}")
async def make_update(
    request: Request,
    make_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("catalog")),
):
    make = _get_make(db, make_id)
    form = await request.form()
    name = str(form.get("name", "")).strip()[:80]
    slug = _unique_make_slug(db, name, exclude_id=make.id) if len(name) >= 2 else None
    if not slug:
        flash(request, "Neispravan ili zauzet naziv marke.", "error")
    else:
        make.name, make.slug = name, slug
        audit.log(
            db, user.id, "catalog.make", "make", make.id, {"op": "rename"}, client_ip(request)
        )
        db.commit()
        flash(request, "Marka je spremljena.", "success")
    return RedirectResponse(f"/admin/katalog/marke/{make.id}/modeli", status_code=303)


@router.post("/admin/katalog/marke/{make_id}/aktivno")
async def make_toggle(
    request: Request,
    make_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("catalog")),
):
    make = _get_make(db, make_id)
    make.is_active = not make.is_active
    audit.log(
        db,
        user.id,
        "catalog.make",
        "make",
        make.id,
        {"op": "activate" if make.is_active else "deactivate"},
        client_ip(request),
    )
    db.commit()
    state = "aktivirana" if make.is_active else "deaktivirana"
    flash(request, f"Marka {make.name} je {state}.", "success")
    return RedirectResponse("/admin/katalog/marke", status_code=303)


@router.post("/admin/katalog/marke/{make_id}/obrisi")
async def make_delete(
    request: Request,
    make_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("catalog")),
):
    make = _get_make(db, make_id)
    if db.scalar(select(func.count(Vehicle.id)).where(Vehicle.make_id == make.id)):
        flash(request, "Marka ima vozila i ne može se obrisati — deaktivirajte je.", "error")
        return RedirectResponse("/admin/katalog/marke", status_code=303)
    for model in list(make.models):
        db.delete(model)
    db.delete(make)
    audit.log(db, user.id, "catalog.make", "make", make_id, {"op": "delete"}, client_ip(request))
    db.commit()
    flash(request, "Marka je obrisana.", "success")
    return RedirectResponse("/admin/katalog/marke", status_code=303)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
def _model_slug_taken(db: Session, make_id: int, slug: str, exclude_id: int | None = None) -> bool:
    stmt = select(VehicleModel.id).where(VehicleModel.make_id == make_id, VehicleModel.slug == slug)
    if exclude_id:
        stmt = stmt.where(VehicleModel.id != exclude_id)
    return bool(db.scalar(stmt))


@router.get("/admin/katalog/marke/{make_id}/modeli")
async def models_list(
    request: Request,
    make_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("catalog")),
):
    make = _get_make(db, make_id)
    vehicle_counts = dict(
        db.execute(
            select(Vehicle.model_id, func.count())
            .where(Vehicle.make_id == make.id)
            .group_by(Vehicle.model_id)
        ).all()
    )
    return render(
        request,
        "admin/catalog/models.html",
        {
            "section": "katalog",
            "make": make,
            "models": make.models,
            "vehicle_counts": vehicle_counts,
            "types": VEHICLE_TYPES,
        },
    )


def _parse_model_type(value) -> tuple[str | None, bool]:
    value = str(value or "")
    if value in ("", "svi"):
        return None, True
    return (value, True) if value in VEHICLE_TYPES else (None, False)


@router.post("/admin/katalog/marke/{make_id}/modeli")
async def model_create(
    request: Request,
    make_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("catalog")),
):
    make = _get_make(db, make_id)
    form = await request.form()
    name = str(form.get("name", "")).strip()[:80]
    vehicle_type, ok = _parse_model_type(form.get("vehicle_type"))
    slug = slugify(name)
    if len(name) < 1 or not slug or not ok:
        flash(request, "Upišite naziv modela.", "error")
    elif _model_slug_taken(db, make.id, slug):
        flash(request, f"Model {name} već postoji.", "error")
    else:
        model = VehicleModel(make_id=make.id, name=name, slug=slug, vehicle_type=vehicle_type)
        db.add(model)
        db.flush()
        audit.log(
            db, user.id, "catalog.model", "model", model.id, {"op": "create"}, client_ip(request)
        )
        db.commit()
        flash(request, f"Model {name} je dodan.", "success")
    return RedirectResponse(f"/admin/katalog/marke/{make.id}/modeli", status_code=303)


def _get_model(db: Session, model_id: int) -> VehicleModel:
    model = db.get(VehicleModel, model_id)
    if model is None:
        raise HTTPException(status_code=404)
    return model


@router.post("/admin/katalog/modeli/{model_id}")
async def model_update(
    request: Request,
    model_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("catalog")),
):
    model = _get_model(db, model_id)
    form = await request.form()
    name = str(form.get("name", "")).strip()[:80]
    vehicle_type, ok = _parse_model_type(form.get("vehicle_type"))
    slug = slugify(name)
    if not slug or not ok or _model_slug_taken(db, model.make_id, slug, exclude_id=model.id):
        flash(request, "Neispravan ili zauzet naziv modela.", "error")
    else:
        model.name, model.slug, model.vehicle_type = name, slug, vehicle_type
        audit.log(
            db, user.id, "catalog.model", "model", model.id, {"op": "update"}, client_ip(request)
        )
        db.commit()
        flash(request, "Model je spremljen.", "success")
    return RedirectResponse(f"/admin/katalog/marke/{model.make_id}/modeli", status_code=303)


@router.post("/admin/katalog/modeli/{model_id}/aktivno")
async def model_toggle(
    request: Request,
    model_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("catalog")),
):
    model = _get_model(db, model_id)
    model.is_active = not model.is_active
    audit.log(
        db,
        user.id,
        "catalog.model",
        "model",
        model.id,
        {"op": "activate" if model.is_active else "deactivate"},
        client_ip(request),
    )
    db.commit()
    return RedirectResponse(f"/admin/katalog/marke/{model.make_id}/modeli", status_code=303)


@router.post("/admin/katalog/modeli/{model_id}/obrisi")
async def model_delete(
    request: Request,
    model_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("catalog")),
):
    model = _get_model(db, model_id)
    make_id = model.make_id
    if db.scalar(select(func.count(Vehicle.id)).where(Vehicle.model_id == model.id)):
        flash(request, "Model ima vozila i ne može se obrisati — deaktivirajte ga.", "error")
    else:
        db.delete(model)
        audit.log(
            db, user.id, "catalog.model", "model", model_id, {"op": "delete"}, client_ip(request)
        )
        db.commit()
        flash(request, "Model je obrisan.", "success")
    return RedirectResponse(f"/admin/katalog/marke/{make_id}/modeli", status_code=303)


# ---------------------------------------------------------------------------
# CSV import: "marka;model;tip"
# ---------------------------------------------------------------------------
def decode_csv(data: bytes) -> str:
    """Excel on Croatian Windows saves CSV as cp1250; try UTF-8 first."""
    for encoding in ("utf-8-sig", "cp1250"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def analyse_csv(db: Session, text: str) -> list[dict]:
    """Parse rows and classify them: new make/model, duplicate or error."""
    existing_makes = {m.slug: m for m in db.scalars(select(Make))}
    existing_models = {
        (row.make_id, row.slug)
        for row in db.execute(select(VehicleModel.make_id, VehicleModel.slug))
    }
    seen: set[tuple[str, str]] = set()
    rows = []
    delimiter = ";" if text.count(";") >= text.count(",") else ","
    for number, parts in enumerate(csv.reader(io.StringIO(text), delimiter=delimiter), start=1):
        if not parts or all(not p.strip() for p in parts):
            continue
        make_name = parts[0].strip()[:80]
        model_name = (parts[1] if len(parts) > 1 else "").strip()[:80]
        type_raw = (parts[2] if len(parts) > 2 else "").strip().lower()
        if number == 1 and make_name.lower() in ("marka", "make"):
            continue  # header row
        row = {"line": number, "make": make_name, "model": model_name, "type": None}
        make_slug, model_slug = slugify(make_name), slugify(model_name)
        if not make_slug or not model_slug:
            row["status"], row["note"] = "error", "Nedostaje marka ili model."
        elif type_raw not in TYPE_ALIASES:
            row["status"], row["note"] = "error", f"Nepoznat tip „{type_raw}”."
        else:
            row["type"] = TYPE_ALIASES[type_raw]
            make = existing_makes.get(make_slug)
            if (make_slug, model_slug) in seen or (
                make and (make.id, model_slug) in existing_models
            ):
                row["status"], row["note"] = "duplicate", "Već postoji — preskače se."
            else:
                row["status"] = "new"
                row["note"] = "Nova marka i model" if make is None else "Novi model"
            seen.add((make_slug, model_slug))
        rows.append(row)
    return rows


def import_rows(db: Session, rows: list[dict]) -> tuple[int, int]:
    makes = {m.slug: m for m in db.scalars(select(Make))}
    added_makes = added_models = 0
    for row in rows:
        if row["status"] != "new":
            continue
        make_slug = slugify(row["make"])
        make = makes.get(make_slug)
        if make is None:
            make = Make(name=row["make"], slug=make_slug, is_active=True)
            db.add(make)
            db.flush()
            makes[make_slug] = make
            added_makes += 1
        model_slug = slugify(row["model"])
        if not _model_slug_taken(db, make.id, model_slug):
            db.add(
                VehicleModel(
                    make_id=make.id, name=row["model"], slug=model_slug, vehicle_type=row["type"]
                )
            )
            db.flush()
            added_models += 1
    return added_makes, added_models


@router.get("/admin/katalog/uvoz")
async def import_form(request: Request, user: User = Depends(require_permission("catalog"))):
    return render(request, "admin/catalog/import.html", {"section": "katalog", "rows": None})


@router.post("/admin/katalog/uvoz")
async def import_submit(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("catalog")),
):
    form = await request.form()
    if form.get("confirm") == "1":
        text = str(form.get("csv_text", ""))[:500_000]
        rows = analyse_csv(db, text)
        added_makes, added_models = import_rows(db, rows)
        audit.log(
            db,
            user.id,
            "catalog.import",
            details={"makes": added_makes, "models": added_models},
            ip=client_ip(request),
        )
        db.commit()
        flash(request, f"Uvezeno: {added_makes} marki i {added_models} modela.", "success")
        return RedirectResponse("/admin/katalog/marke", status_code=303)

    upload = form.get("file")
    text = ""
    if upload is not None and hasattr(upload, "read"):
        data = await upload.read(500_001)
        if len(data) > 500_000:
            flash(request, "CSV datoteka je prevelika (najviše 500 kB).", "error")
            return RedirectResponse("/admin/katalog/uvoz", status_code=303)
        text = decode_csv(data)
    text = text or str(form.get("csv_text", ""))[:500_000]
    if not text.strip():
        flash(request, "Odaberite CSV datoteku ili zalijepite sadržaj.", "error")
        return RedirectResponse("/admin/katalog/uvoz", status_code=303)
    rows = analyse_csv(db, text)
    summary = {
        "new": sum(1 for r in rows if r["status"] == "new"),
        "duplicate": sum(1 for r in rows if r["status"] == "duplicate"),
        "error": sum(1 for r in rows if r["status"] == "error"),
    }
    return render(
        request,
        "admin/catalog/import.html",
        {
            "section": "katalog",
            "rows": rows,
            "summary": summary,
            "csv_text": text,
            "type_label": type_label,
        },
    )


# ---------------------------------------------------------------------------
# Vehicle types overview (read only, generated from app/vehicle_schema.py)
# ---------------------------------------------------------------------------
@router.get("/admin/katalog/tipovi")
async def types_overview(request: Request, user: User = Depends(require_permission("catalog"))):
    types = []
    for code, info in VEHICLE_TYPES.items():
        common = [f for f in COMMON_FIELDS if f.get("types") is None or code in f["types"]]
        types.append(
            {
                "code": code,
                **info,
                "common": common,
                "specific": TYPE_FIELDS.get(code, []),
                "equipment": equipment_for(code),
            }
        )
    return render(
        request,
        "admin/catalog/types.html",
        {"section": "katalog", "types": types, "section_labels": SECTION_LABELS},
    )
