"""Admin dashboard and placeholder pages for sections that are not built yet."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.templating import render

router = APIRouter(prefix="/admin")

# Sections that are still under construction -> phase in which they arrive.
UNDER_CONSTRUCTION = {
    "vozila": 3,
    "katalog": 3,
    "upiti": 5,
    "newsletter": 6,
    "statistika": 7,
    "korisnici": 2,
    "postavke": 7,
    "stranice": 7,
    "gdpr": 7,
    "audit": 2,
    "sustav": 7,
    "profil": 2,
}


@router.get("")
async def dashboard(request: Request):
    return render(request, "admin/dashboard.html", {"section": ""})


@router.get("/{section}")
@router.get("/{section}/{rest:path}")
async def under_construction(request: Request, section: str, rest: str = ""):
    if section not in UNDER_CONSTRUCTION:
        raise HTTPException(status_code=404)
    return render(
        request,
        "admin/u_izradi.html",
        {"section": section, "phase": UNDER_CONSTRUCTION[section]},
    )
