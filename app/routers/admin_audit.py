"""Audit log viewer (/admin/audit) — owner and superadmin, read only."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import csrf_protect, require_permission
from app.models import AuditLog, User
from app.pagination import paginate, parse_page
from app.security import mask_ip
from app.templating import render
from app.utils import local_day_start_utc

router = APIRouter(prefix="/admin", dependencies=[Depends(csrf_protect)])

# Human readable labels for audit actions (unknown actions are shown as codes).
ACTION_LABELS = {
    "user.login": "Prijava",
    "user.login_failed": "Neuspjela prijava",
    "user.logout": "Odjava",
    "user.logout_all": "Odjava sa svih uređaja",
    "user.2fa_setup": "Postavljena 2FA",
    "user.2fa_reset": "Poništena 2FA",
    "user.recovery_code_used": "Iskorišten kod za oporavak",
    "user.password_change": "Promjena lozinke",
    "user.password_reset": "Nova lozinka (reset)",
    "user.password_reset_request": "Zahtjev za novu lozinku",
    "user.password_set": "Postavljena lozinka (pozivnica)",
    "user.invite": "Pozivnica",
    "user.update": "Izmjena korisnika",
    "user.deactivate": "Deaktivacija korisnika",
    "vehicle.create": "Novo vozilo",
    "vehicle.update": "Izmjena vozila",
    "vehicle.status": "Promjena statusa vozila",
    "vehicle.feature": "Istaknuto vozilo",
    "vehicle.duplicate": "Dupliciranje vozila",
    "vehicle.delete": "Brisanje vozila",
    "vehicle.images": "Slike vozila",
    "catalog.make": "Katalog: marka",
    "catalog.model": "Katalog: model",
    "catalog.import": "Katalog: uvoz CSV",
    "inquiry.status": "Upit: status",
    "inquiry.assign": "Upit: dodjela",
    "inquiry.note": "Upit: bilješka",
    "inquiry.delete": "Upit: brisanje",
    "inquiry.export": "Upiti: izvoz",
    "newsletter.manual_add": "Newsletter: ručni unos",
    "newsletter.delete": "Newsletter: brisanje",
    "newsletter.export": "Newsletter: izvoz",
    "campaign.create": "Kampanja: nova",
    "campaign.update": "Kampanja: izmjena",
    "campaign.send": "Kampanja: slanje",
    "campaign.delete": "Kampanja: brisanje",
    "settings.update": "Postavke",
    "page.update": "Stranica",
    "privacy.export": "GDPR: izvoz podataka",
    "privacy.delete": "GDPR: brisanje podataka",
    "stats.export": "Statistika: izvoz",
    "system.maintenance": "Održavanje (automatski)",
    "system.plan_override": "Paket (nadjačavanje)",
    "offer.print": "Ponuda kupcu (ispis)",
}


def _parse_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


@router.get("/audit")
async def audit_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("audit")),
):
    params = request.query_params
    user_filter = params.get("korisnik", "")
    action_filter = params.get("akcija", "")
    date_from = _parse_date(params.get("od"))
    date_to = _parse_date(params.get("do"))

    stmt = select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    if user_filter == "sustav":
        stmt = stmt.where(AuditLog.user_id.is_(None))
    elif user_filter.isdigit():
        stmt = stmt.where(AuditLog.user_id == int(user_filter))
    if action_filter:
        stmt = stmt.where(AuditLog.action == action_filter)
    if date_from:
        stmt = stmt.where(AuditLog.created_at >= local_day_start_utc(date_from))
    if date_to:
        stmt = stmt.where(AuditLog.created_at < local_day_start_utc(date_to + timedelta(days=1)))

    page = paginate(db, stmt, parse_page(params.get("stranica")), 50)
    actions = sorted(set(db.scalars(select(AuditLog.action).distinct())))
    users = list(db.scalars(select(User).order_by(User.name)))
    return render(
        request,
        "admin/audit.html",
        {
            "section": "audit",
            "page": page,
            "actions": actions,
            "users": users,
            "labels": ACTION_LABELS,
            "mask_ip": mask_ip,
            "filters": {
                "korisnik": user_filter,
                "akcija": action_filter,
                "od": params.get("od", ""),
                "do": params.get("do", ""),
            },
        },
    )
