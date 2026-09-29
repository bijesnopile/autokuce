"""Administracija kao aplikacija na telefonu (PWA) — manifest, ikone, service worker.

GET /admin/manifest.webmanifest     manifest iz postavki (naziv, primarna boja)
GET /admin/pwa-icon-{180|192|512}.png   ikone (logotip ili početno slovo), keš na disku
GET /admin/sw.js                    minimalan service worker (admin stranice se ne keširaju)

Rute su javne: preglednik manifest i ikone dohvaća bez kolačića, a sadrže samo naziv tvrtke
i boju (isto kao javna stranica).
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.deps import csrf_protect
from app.services import pwa
from app.services.site import get_site

router = APIRouter(prefix="/admin", dependencies=[Depends(csrf_protect)])


@router.get("/manifest.webmanifest")
async def manifest():
    body = json.dumps(pwa.manifest(get_site()), ensure_ascii=False, indent=2)
    return Response(
        body,
        media_type="application/manifest+json",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/pwa-icon-{size:int}.png")
async def icon(size: int):
    if size not in pwa.ICON_SIZES:
        raise HTTPException(status_code=404)
    return Response(
        pwa.icon_png(size, get_site()),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/sw.js")
async def service_worker():
    return Response(
        pwa.SERVICE_WORKER,
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/admin/", "Cache-Control": "no-cache"},
    )
