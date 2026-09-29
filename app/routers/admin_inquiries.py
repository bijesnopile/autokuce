"""Admin mini-CRM for customer inquiries.

Routes:
    GET  /admin/upiti                              inbox (filters, search, sort, 25/page)
    GET  /admin/upiti/izvoz.csv                    CSV of the current filter (owner+)
    GET  /admin/upiti/{id}                         detail
    POST /admin/upiti/{id}/status                  new / contacted / closed
    POST /admin/upiti/{id}/dodjela                 assign to a user (or nobody)
    POST /admin/upiti/{id}/biljeske                add internal note
    POST /admin/upiti/{id}/biljeske/{note}/obrisi  delete own note (within 15 min)
    POST /admin/upiti/{id}/obrisi                  delete inquiry (owner+)
Audit details never contain customer data — only IDs.
"""

from __future__ import annotations

from datetime import date, timedelta
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db, utcnow
from app.deps import csrf_protect, require_feature, require_permission
from app.models import INQUIRY_NEW, Inquiry, InquiryNote, User, Vehicle
from app.pagination import paginate, parse_page
from app.permissions import can
from app.security import client_ip, mask_ip
from app.services import audit
from app.services import inquiries as inquiry_service
from app.services.site import get_site
from app.templating import flash, render
from app.utils import local_day_start_utc

router = APIRouter(prefix="/admin", dependencies=[Depends(csrf_protect)])

NOTE_DELETE_MINUTES = 15


def _parse_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def _filters(request: Request) -> dict:
    params = request.query_params
    return {
        "status": params.get("status", "")
        if params.get("status") in inquiry_service.INQUIRY_STATUS_LABELS
        else "",
        "tip": params.get("tip", "")
        if params.get("tip") in inquiry_service.INQUIRY_TYPE_LABELS
        else "",
        "dodijeljeno": params.get("dodijeljeno", ""),
        "vozilo": params.get("vozilo", "") if params.get("vozilo", "").isdigit() else "",
        "od": params.get("od", ""),
        "do": params.get("do", ""),
        "q": params.get("q", "").strip()[:100],
        "sort": "staro" if params.get("sort") == "staro" else "",
    }


def _filtered_query(filters: dict, user: User):
    stmt = select(Inquiry).options(
        selectinload(Inquiry.vehicle), selectinload(Inquiry.assignee), selectinload(Inquiry.notes)
    )
    if filters["status"]:
        stmt = stmt.where(Inquiry.status == filters["status"])
    if filters["tip"]:
        stmt = stmt.where(Inquiry.type == filters["tip"])
    assigned = filters["dodijeljeno"]
    if assigned == "moji":
        stmt = stmt.where(Inquiry.assigned_to == user.id)
    elif assigned == "nitko":
        stmt = stmt.where(Inquiry.assigned_to.is_(None))
    elif assigned.isdigit():
        stmt = stmt.where(Inquiry.assigned_to == int(assigned))
    if filters["vozilo"]:
        stmt = stmt.where(Inquiry.vehicle_id == int(filters["vozilo"]))
    date_from, date_to = _parse_date(filters["od"]), _parse_date(filters["do"])
    if date_from:
        stmt = stmt.where(Inquiry.created_at >= local_day_start_utc(date_from))
    if date_to:
        stmt = stmt.where(Inquiry.created_at < local_day_start_utc(date_to + timedelta(days=1)))
    if filters["q"]:
        like = f"%{filters['q']}%"
        stmt = stmt.where(
            or_(Inquiry.name.ilike(like), Inquiry.email.ilike(like), Inquiry.phone.ilike(like))
        )
    order = Inquiry.created_at.asc() if filters["sort"] == "staro" else Inquiry.created_at.desc()
    return stmt.order_by(order, Inquiry.id.desc())


def _active_users(db: Session) -> list[User]:
    return list(db.scalars(select(User).where(User.is_active).order_by(User.name, User.email)))


# ---------------------------------------------------------------------------
# Inbox
# ---------------------------------------------------------------------------
@router.get("/upiti")
async def inquiry_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("inquiries")),
):
    filters = _filters(request)
    page = paginate(
        db, _filtered_query(filters, user), parse_page(request.query_params.get("stranica")), 25
    )
    counts = dict(db.execute(select(Inquiry.status, func.count()).group_by(Inquiry.status)).all())
    vehicles = list(
        db.scalars(
            select(Vehicle)
            .where(Vehicle.id.in_(select(Inquiry.vehicle_id)))
            .order_by(Vehicle.title)
        )
    )
    return render(
        request,
        "admin/inquiries/list.html",
        {
            "section": "upiti",
            "page": page,
            "filters": filters,
            "counts": counts,
            "users": _active_users(db),
            "vehicles": vehicles,
            "type_labels": inquiry_service.INQUIRY_TYPE_LABELS,
            "status_labels": inquiry_service.INQUIRY_STATUS_LABELS,
            "is_unanswered": inquiry_service.is_unanswered,
            "can_export": can(user, "inquiries.export"),
        },
    )


@router.get("/upiti/izvoz.csv")
async def inquiry_export(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("inquiries.export")),
):
    filters = _filters(request)
    items = list(db.scalars(_filtered_query(filters, user)))
    audit.log(
        db, user.id, "inquiry.export", "inquiry", None, {"count": len(items)}, client_ip(request)
    )
    db.commit()
    filename = f"upiti-{date.today().isoformat()}.csv"
    return Response(
        inquiry_service.export_csv(items),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Detail and actions
# ---------------------------------------------------------------------------
def _get(db: Session, inquiry_id: int) -> Inquiry:
    inquiry = db.get(Inquiry, inquiry_id)
    if inquiry is None:
        raise HTTPException(status_code=404)
    return inquiry


@router.get("/upiti/{inquiry_id:int}")
async def inquiry_detail(
    request: Request,
    inquiry_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("inquiries")),
):
    inquiry = _get(db, inquiry_id)
    site = get_site()
    target = inquiry.vehicle.title if inquiry.vehicle else None
    subject = " – ".join(p for p in ("Vaš upit", target, site["company_name"]) if p)
    newer = db.scalar(
        select(Inquiry.id).where(Inquiry.id > inquiry.id).order_by(Inquiry.id.asc()).limit(1)
    )
    older = db.scalar(
        select(Inquiry.id).where(Inquiry.id < inquiry.id).order_by(Inquiry.id.desc()).limit(1)
    )
    return render(
        request,
        "admin/inquiries/detail.html",
        {
            "section": "upiti",
            "inquiry": inquiry,
            "users": _active_users(db),
            "type_labels": inquiry_service.INQUIRY_TYPE_LABELS,
            "status_labels": inquiry_service.INQUIRY_STATUS_LABELS,
            "mailto": f"mailto:{inquiry.email}?subject={quote(subject)}",
            "mask_ip": mask_ip,
            "newer_id": newer,
            "older_id": older,
            "unanswered": inquiry_service.is_unanswered(inquiry),
            "can_delete": can(user, "inquiries.delete"),
            "schedule_value": inquiry_service.local_input_value(
                inquiry.scheduled_at or inquiry.preferred_date
            ),
            "note_deletable": lambda n: (
                n.user_id == user.id
                and n.created_at > utcnow() - timedelta(minutes=NOTE_DELETE_MINUTES)
            ),
        },
    )


@router.post("/upiti/{inquiry_id:int}/status")
async def inquiry_status(
    request: Request,
    inquiry_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("inquiries")),
):
    inquiry = _get(db, inquiry_id)
    form = await request.form()
    old = inquiry.status
    if inquiry_service.change_status(inquiry, str(form.get("status", ""))):
        audit.log(
            db,
            user.id,
            "inquiry.status",
            "inquiry",
            inquiry.id,
            {"from": old, "to": inquiry.status},
            client_ip(request),
        )
        db.commit()
        label = inquiry_service.INQUIRY_STATUS_LABELS[inquiry.status]
        flash(request, f"Status je promijenjen u „{label}”.", "success")
    back = str(form.get("next", ""))
    target = back if back.startswith("/admin/upiti") else f"/admin/upiti/{inquiry.id}"
    return RedirectResponse(target, status_code=303)


@router.post("/upiti/{inquiry_id:int}/termin")
async def inquiry_schedule(
    request: Request,
    inquiry_id: int,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("inquiries")),
    _feature: None = Depends(require_feature("kalendar_termin")),
):
    """Confirm a viewing: store the time, email the customer a CONFIRMED .ics (same UID)."""
    inquiry = _get(db, inquiry_id)
    if inquiry.type != "viewing":
        raise HTTPException(status_code=404)
    form = await request.form()
    when, error = inquiry_service.parse_confirmed_time(str(form.get("scheduled_at", "")))
    if error:
        flash(request, error, "error")
        return RedirectResponse(f"/admin/upiti/{inquiry.id}#termin", status_code=303)
    old_status = inquiry.status
    sequence = inquiry_service.confirm_viewing(inquiry, when)
    audit.log(
        db,
        user.id,
        "inquiry.schedule",
        "inquiry",
        inquiry.id,
        {"at": when.isoformat(timespec="minutes"), "sequence": sequence, "from": old_status},
        client_ip(request),
    )
    db.commit()
    if inquiry.email:
        background.add_task(inquiry_service.send_viewing_confirmation, inquiry.id)
        flash(
            request,
            "Termin je potvrđen, kupcu je poslan email s kalendarskim događajem.",
            "success",
        )
    else:
        flash(request, "Termin je potvrđen (kupac nema email adresu).", "success")
    return RedirectResponse(f"/admin/upiti/{inquiry.id}", status_code=303)


@router.post("/upiti/{inquiry_id:int}/dodjela")
async def inquiry_assign(
    request: Request,
    inquiry_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("inquiries")),
):
    inquiry = _get(db, inquiry_id)
    form = await request.form()
    raw = str(form.get("assigned_to", ""))
    new_value = None
    if raw.isdigit():
        assignee = db.get(User, int(raw))
        if assignee is None or not assignee.is_active:
            flash(request, "Odabrani korisnik nije aktivan.", "error")
            return RedirectResponse(f"/admin/upiti/{inquiry.id}", status_code=303)
        new_value = assignee.id
    if new_value != inquiry.assigned_to:
        inquiry.assigned_to = new_value
        audit.log(
            db,
            user.id,
            "inquiry.assign",
            "inquiry",
            inquiry.id,
            {"assigned_to": new_value},
            client_ip(request),
        )
        db.commit()
        flash(request, "Dodjela je spremljena.", "success")
    return RedirectResponse(f"/admin/upiti/{inquiry.id}", status_code=303)


@router.post("/upiti/{inquiry_id:int}/biljeske")
async def inquiry_note_add(
    request: Request,
    inquiry_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("inquiries")),
):
    inquiry = _get(db, inquiry_id)
    form = await request.form()
    body = str(form.get("body", "")).strip()[:5000]
    if not body:
        flash(request, "Bilješka je prazna.", "error")
    else:
        note = InquiryNote(inquiry_id=inquiry.id, user_id=user.id, body=body)
        db.add(note)
        db.flush()
        audit.log(
            db,
            user.id,
            "inquiry.note",
            "inquiry",
            inquiry.id,
            {"note_id": note.id},
            client_ip(request),
        )
        db.commit()
        flash(request, "Bilješka je dodana.", "success")
    return RedirectResponse(f"/admin/upiti/{inquiry.id}#biljeske", status_code=303)


@router.post("/upiti/{inquiry_id:int}/biljeske/{note_id:int}/obrisi")
async def inquiry_note_delete(
    request: Request,
    inquiry_id: int,
    note_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("inquiries")),
):
    note = db.get(InquiryNote, note_id)
    if note is None or note.inquiry_id != inquiry_id:
        raise HTTPException(status_code=404)
    too_old = note.created_at <= utcnow() - timedelta(minutes=NOTE_DELETE_MINUTES)
    if note.user_id != user.id or too_old:
        raise HTTPException(
            status_code=403,
            detail=f"Možete obrisati samo vlastitu bilješku unutar {NOTE_DELETE_MINUTES} minuta.",
        )
    db.delete(note)
    audit.log(
        db,
        user.id,
        "inquiry.note",
        "inquiry",
        inquiry_id,
        {"note_id": note_id, "deleted": True},
        client_ip(request),
    )
    db.commit()
    flash(request, "Bilješka je obrisana.", "success")
    return RedirectResponse(f"/admin/upiti/{inquiry_id}#biljeske", status_code=303)


@router.post("/upiti/{inquiry_id:int}/obrisi")
async def inquiry_delete(
    request: Request,
    inquiry_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("inquiries.delete")),
):
    inquiry = _get(db, inquiry_id)
    db.delete(inquiry)
    audit.log(db, user.id, "inquiry.delete", "inquiry", inquiry_id, None, client_ip(request))
    db.commit()
    flash(request, "Upit je obrisan.", "success")
    return RedirectResponse("/admin/upiti", status_code=303)


def count_new(db: Session) -> int:
    return db.scalar(select(func.count(Inquiry.id)).where(Inquiry.status == INQUIRY_NEW)) or 0
