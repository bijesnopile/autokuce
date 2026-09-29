"""Feed prema portalima — admin stranica (paket Standard, funkcija `feed_portali`).

GET  /admin/feed          URL-ovi feedova, zadnja preuzimanja, validacija, upute
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import csrf_protect, require_feature, require_permission
from app.models import User
from app.templating import render

router = APIRouter(prefix="/admin", dependencies=[Depends(csrf_protect)])


@router.get("/feed")
async def feed_admin(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("feed")),
    _feature: None = Depends(require_feature("feed_portali")),
):
    return render(request, "admin/feed.html", {"section": "feed"})
