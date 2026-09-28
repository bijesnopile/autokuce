"""Admin dashboard and placeholder pages for sections that are not built yet."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import csrf_protect, require_permission
from app.models import (
    INQUIRY_NEW,
    STATUS_ACTIVE,
    SUB_CONFIRMED,
    Inquiry,
    Subscriber,
    User,
    Vehicle,
    VehicleView,
)
from app.templating import render
from app.utils import local_today

router = APIRouter(prefix="/admin", dependencies=[Depends(csrf_protect)])

# Sections that are still under construction -> phase in which they arrive.
UNDER_CONSTRUCTION = {
    "newsletter": 6,
    "statistika": 7,
    "postavke": 7,
    "stranice": 7,
    "gdpr": 7,
    "sustav": 7,
}


@router.get("")
async def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("dashboard")),
):
    stats = {
        "active_vehicles": db.scalar(
            select(func.count(Vehicle.id)).where(Vehicle.status == STATUS_ACTIVE)
        ),
        "new_inquiries": db.scalar(
            select(func.count(Inquiry.id)).where(Inquiry.status == INQUIRY_NEW)
        ),
        "confirmed_subscribers": db.scalar(
            select(func.count(Subscriber.id)).where(Subscriber.status == SUB_CONFIRMED)
        ),
        "views_30": db.scalar(
            select(func.coalesce(func.sum(VehicleView.count), 0)).where(
                VehicleView.date >= local_today() - timedelta(days=29)
            )
        ),
    }
    return render(request, "admin/dashboard.html", {"section": "", "stats": stats})


@router.get("/{section}")
@router.get("/{section}/{rest:path}")
async def under_construction(
    request: Request,
    section: str,
    rest: str = "",
    user: User = Depends(require_permission("dashboard")),
):
    if section not in UNDER_CONSTRUCTION:
        raise HTTPException(status_code=404)
    return render(
        request,
        "admin/u_izradi.html",
        {"section": section, "phase": UNDER_CONSTRUCTION[section]},
    )
