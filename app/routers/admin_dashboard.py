"""Admin dashboard and placeholder pages for sections that are not built yet."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.deps import csrf_protect, require_permission
from app.models import User
from app.templating import render

router = APIRouter(prefix="/admin", dependencies=[Depends(csrf_protect)])

# Sections that are still under construction -> phase in which they arrive.
UNDER_CONSTRUCTION = {
    "upiti": 5,
    "newsletter": 6,
    "statistika": 7,
    "postavke": 7,
    "stranice": 7,
    "gdpr": 7,
    "sustav": 7,
}


@router.get("")
async def dashboard(request: Request, user: User = Depends(require_permission("dashboard"))):
    return render(request, "admin/dashboard.html", {"section": ""})


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
