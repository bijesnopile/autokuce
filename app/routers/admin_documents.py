"""Ispisni dokumenti za vozilo (paket Standard).

GET  /admin/vozila/{id}/izlog[?slika=0][&format=a5]   kartica za izlog (A4 ili A5 pejzažno)
GET  /admin/vozila/{id}/ponuda[?upit={id}]            obrazac ponude (predispunjen iz upita)
POST /admin/vozila/{id}/ponuda                         ponuda kao A4 dokument za ispis/PDF
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import csrf_protect, require_feature, require_permission
from app.models import Inquiry, User, Vehicle
from app.security import client_ip
from app.services import audit, documents
from app.templating import render
from app.utils import local_today

router = APIRouter(prefix="/admin", dependencies=[Depends(csrf_protect)])


def _vehicle(db: Session, vehicle_id: int) -> Vehicle:
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise HTTPException(status_code=404)
    return vehicle


@router.get("/vozila/{vehicle_id}/izlog")
async def window_card(
    request: Request,
    vehicle_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("vehicles")),
    _feature: None = Depends(require_feature("izlog_kartica")),
):
    vehicle = _vehicle(db, vehicle_id)
    size = "a5" if request.query_params.get("format") == "a5" else "a4"
    show_image = request.query_params.get("slika") != "0" and bool(vehicle.images)
    return render(
        request,
        "admin/print/window_card.html",
        {
            "vehicle": vehicle,
            "size": size,
            "show_image": show_image,
            "facts": documents.card_facts(vehicle),
            "equipment": documents.equipment_labels(vehicle, 12 if size == "a4" else 6),
            "qr": documents.vehicle_qr(vehicle),
            "public_url": documents.public_url(vehicle),
        },
    )


@router.get("/vozila/{vehicle_id}/ponuda")
async def offer_form(
    request: Request,
    vehicle_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("vehicles")),
    _feature: None = Depends(require_feature("ponuda_pdf")),
):
    vehicle = _vehicle(db, vehicle_id)
    form = {"valid_until": documents.default_valid_until().isoformat()}
    inquiry_id = request.query_params.get("upit", "")
    if inquiry_id.isdigit():
        inquiry = db.get(Inquiry, int(inquiry_id))
        if inquiry is not None:
            form.update(customer_name=inquiry.name, customer_email=inquiry.email or "")
    return render(
        request,
        "admin/vehicles/offer_form.html",
        {"section": "vozila", "vehicle": vehicle, "form": form, "errors": {}},
    )


@router.post("/vozila/{vehicle_id}/ponuda")
async def offer_document(
    request: Request,
    vehicle_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("vehicles")),
    _feature: None = Depends(require_feature("ponuda_pdf")),
):
    vehicle = _vehicle(db, vehicle_id)
    data, errors = documents.parse_offer_form(await request.form(), vehicle)
    if errors:
        return render(
            request,
            "admin/vehicles/offer_form.html",
            {"section": "vozila", "vehicle": vehicle, "form": data, "errors": errors},
            status_code=400,
        )
    # Not stored (MVP); the audit entry gives the offer a unique, traceable number.
    entry = audit.log(
        db,
        user.id,
        "offer.print",
        "vehicle",
        vehicle.id,
        {"final_eur": data["final_eur"]},
        client_ip(request),
    )
    db.flush()
    today = local_today()
    db.commit()
    return render(
        request,
        "admin/print/offer.html",
        {
            "vehicle": vehicle,
            "offer": data,
            "number": f"{today.year}-{entry.id}",
            "issued": today,
            "seller": user,
            "facts": documents.card_facts(vehicle),
            "equipment": documents.equipment_labels(vehicle),
            "public_url": documents.public_url(vehicle),
        },
    )
