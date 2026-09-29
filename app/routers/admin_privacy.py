"""Data subject rights tool (/admin/gdpr, owner+): find, export and erase all data of a person.

Search by email (inquiries by address, subscriber by hash) and optionally phone.
Export: JSON download with every inquiry, note and the newsletter subscription.
Erase: deletes inquiries + notes, anonymises the subscriber (hash stays as suppression
entry), deletes email_log rows for that address. Audit entries contain only the
email hash and counts — never the address.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db, utcnow
from app.deps import csrf_protect, require_permission
from app.models import EmailLog, Inquiry, InquiryNote, Subscriber, User
from app.security import client_ip, email_hash, mask_ip, normalize_email
from app.services import audit
from app.services.inquiries import INQUIRY_STATUS_LABELS, INQUIRY_TYPE_LABELS, normalize_phone
from app.services.newsletter import STATUS_LABELS, anonymise
from app.templating import flash, render

router = APIRouter(prefix="/admin", dependencies=[Depends(csrf_protect)])
CONFIRM_WORD = "OBRIŠI"


def find_person(db: Session, email: str, phone: str = "") -> dict:
    email = normalize_email(email)
    digest = email_hash(email)
    conditions = [func.lower(Inquiry.email) == email]
    normalized_phone, _error = normalize_phone(phone) if phone else (None, None)
    if normalized_phone:
        conditions.append(Inquiry.phone == normalized_phone)
    inquiries = list(
        db.scalars(
            select(Inquiry)
            .options(selectinload(Inquiry.notes), selectinload(Inquiry.vehicle))
            .where(or_(*conditions))
            .order_by(Inquiry.created_at)
        )
    )
    subscriber = db.scalar(select(Subscriber).where(Subscriber.email_hash == digest))
    email_logs = db.scalar(select(func.count(EmailLog.id)).where(EmailLog.to_hash == digest)) or 0
    return {
        "email": email,
        "phone": normalized_phone,
        "hash": digest,
        "inquiries": inquiries,
        "notes": sum(len(i.notes) for i in inquiries),
        "subscriber": subscriber,
        "email_logs": email_logs,
    }


def export_data(found: dict) -> dict:
    def ts(value):
        return value.isoformat() + "Z" if value else None

    subscriber = found["subscriber"]
    return {
        "zahtjev": {"email": found["email"], "telefon": found["phone"], "generirano": ts(utcnow())},
        "upiti": [
            {
                "id": i.id,
                "vrsta": INQUIRY_TYPE_LABELS.get(i.type, i.type),
                "status": INQUIRY_STATUS_LABELS.get(i.status, i.status),
                "ime": i.name,
                "email": i.email,
                "telefon": i.phone,
                "poruka": i.message,
                "zeljeni_termin": ts(i.preferred_date),
                "potvrdeni_termin": ts(i.scheduled_at),
                "financiranje": (i.extra or {}).get("financing"),
                "vozilo": i.vehicle.title if i.vehicle else None,
                "primljeno": ts(i.created_at),
                "izvor": i.source_url,
                "privola": {
                    "vrijeme": ts(i.consent_at),
                    "ip": i.consent_ip,
                    "preglednik": i.consent_user_agent,
                    "verzija_politike": i.consent_policy_version,
                },
                "biljeske": [{"tekst": n.body, "vrijeme": ts(n.created_at)} for n in i.notes],
            }
            for i in found["inquiries"]
        ],
        "newsletter": None
        if subscriber is None
        else {
            "email": subscriber.email,
            "status": STATUS_LABELS.get(subscriber.status, subscriber.status),
            "izvor": subscriber.source,
            "privola": {
                "vrijeme": ts(subscriber.consent_at),
                "ip": subscriber.consent_ip,
                "preglednik": subscriber.consent_user_agent,
                "verzija_politike": subscriber.consent_policy_version,
                "napomena_rucni_unos": subscriber.manual_consent_note,
            },
            "potvrdeno": ts(subscriber.confirmed_at),
            "odjavljeno": ts(subscriber.unsubscribed_at),
        },
        "zapisi_o_slanju_emaila": found["email_logs"],
    }


def _render_tool(request: Request, email: str = "", phone: str = "", found=None):
    return render(
        request,
        "admin/privacy.html",
        {
            "section": "gdpr",
            "email": email,
            "phone": phone,
            "found": found,
            "type_labels": INQUIRY_TYPE_LABELS,
            "status_labels": INQUIRY_STATUS_LABELS,
            "sub_labels": STATUS_LABELS,
            "mask_ip": mask_ip,
            "confirm_word": CONFIRM_WORD,
        },
    )


# Search, export and erase use POST so that email addresses never appear in URLs
# (browser history, proxy and access logs).
@router.get("/gdpr")
async def privacy_tool(request: Request, user: User = Depends(require_permission("gdpr"))):
    return _render_tool(request)


@router.post("/gdpr")
async def privacy_search(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("gdpr")),
):
    form = await request.form()
    email = str(form.get("email", "")).strip()[:254]
    phone = str(form.get("telefon", "")).strip()[:40]
    if "@" not in email:
        flash(request, "Upišite email adresu osobe.", "error")
        return _render_tool(request, email, phone)
    return _render_tool(request, email, phone, find_person(db, email, phone))


@router.post("/gdpr/izvoz")
async def privacy_export(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("gdpr")),
):
    form = await request.form()
    found = find_person(db, str(form.get("email", "")), str(form.get("telefon", "")))
    audit.log(
        db,
        user.id,
        "privacy.export",
        "person",
        None,
        {"email_hash": found["hash"], "inquiries": len(found["inquiries"])},
        client_ip(request),
    )
    db.commit()
    payload = json.dumps(export_data(found), ensure_ascii=False, indent=2)
    return Response(
        payload.encode("utf-8"),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="podaci-ispitanika.json"'},
    )


@router.post("/gdpr/obrisi")
async def privacy_delete(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("gdpr")),
):
    form = await request.form()
    email = str(form.get("email", ""))
    phone = str(form.get("telefon", ""))
    if str(form.get("confirm", "")).strip() != CONFIRM_WORD:
        flash(request, f"Za brisanje upišite riječ {CONFIRM_WORD}.", "error")
        return _render_tool(request, email, phone, find_person(db, email, phone))
    found = find_person(db, email, phone)
    inquiry_ids = [i.id for i in found["inquiries"]]
    counts = {
        "inquiries": len(inquiry_ids),
        "notes": found["notes"],
        "subscriber": 0,
        "email_logs": found["email_logs"],
    }
    if inquiry_ids:
        db.execute(delete(InquiryNote).where(InquiryNote.inquiry_id.in_(inquiry_ids)))
        db.execute(delete(Inquiry).where(Inquiry.id.in_(inquiry_ids)))
    if found["subscriber"] is not None and found["subscriber"].email is not None:
        anonymise(found["subscriber"])
        counts["subscriber"] = 1
    db.execute(delete(EmailLog).where(EmailLog.to_hash == found["hash"]))
    audit.log(
        db,
        user.id,
        "privacy.delete",
        "person",
        None,
        {"email_hash": found["hash"], **counts},
        client_ip(request),
    )
    db.commit()
    flash(
        request,
        f"Podaci su obrisani: upita {counts['inquiries']}, bilješki {counts['notes']}, "
        f"pretplata anonimizirana: {'da' if counts['subscriber'] else 'ne'}, "
        f"zapisa o emailovima {counts['email_logs']}.",
        "success",
    )
    return RedirectResponse("/admin/gdpr", status_code=303)
