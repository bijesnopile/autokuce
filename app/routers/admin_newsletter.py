"""Admin newsletter: subscribers and campaigns.

Routes (salesperson: read-only lists; everything else owner+):
    GET  /admin/newsletter/pretplatnici                 list, filters, counts
    POST /admin/newsletter/pretplatnici/novi            manual add (consent note required)
    GET  /admin/newsletter/pretplatnici/izvoz.csv       export confirmed subscribers
    POST /admin/newsletter/pretplatnici/{id}/obrisi     delete subscriber
    GET  /admin/newsletter/kampanje                     campaigns list
    GET/POST /admin/newsletter/kampanje/nova            create
    GET/POST /admin/newsletter/kampanje/{id}            edit (draft) / report (sent)
    GET  /admin/newsletter/kampanje/{id}/pregled        rendered email (shown in sandboxed iframe)
    POST /admin/newsletter/kampanje/{id}/test           test email to the logged-in user
    POST /admin/newsletter/kampanje/{id}/posalji        send to all confirmed (background)
    POST /admin/newsletter/kampanje/{id}/ponovi         retry failed deliveries
    POST /admin/newsletter/kampanje/{id}/dupliciraj     copy as draft
    POST /admin/newsletter/kampanje/{id}/obrisi         delete draft
    GET  /admin/newsletter/api/vozila?q=                vehicle cards for the editor (JSON)
"""

from __future__ import annotations

import codecs
import csv
import io
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import csrf_protect, require_permission
from app.models import (
    CAMPAIGN_DRAFT,
    CAMPAIGN_SENDING,
    CAMPAIGN_SENT,
    DELIVERY_FAILED,
    STATUS_ACTIVE,
    STATUS_RESERVED,
    SUB_CONFIRMED,
    Campaign,
    CampaignDelivery,
    Subscriber,
    User,
    Vehicle,
)
from app.pagination import paginate, parse_page
from app.permissions import can
from app.security import client_ip, email_hash
from app.services import audit
from app.services import newsletter as nl
from app.services.email import send
from app.templating import datetime_hr, flash, render

router = APIRouter(prefix="/admin/newsletter", dependencies=[Depends(csrf_protect)])


# ---------------------------------------------------------------------------
# Subscribers
# ---------------------------------------------------------------------------
def _subscriber_query(status: str, q: str):
    stmt = select(Subscriber).order_by(Subscriber.created_at.desc(), Subscriber.id.desc())
    if status in nl.STATUS_LABELS:
        stmt = stmt.where(Subscriber.status == status)
    if q:
        if "@" in q:
            # Exact match through the hash (also finds anonymised entries).
            stmt = stmt.where(Subscriber.email_hash == email_hash(q))
        else:
            stmt = stmt.where(Subscriber.email.ilike(f"{q.lower()}%"))
    return stmt


@router.get("/pretplatnici")
async def subscribers(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("newsletter.view")),
):
    params = request.query_params
    filters = {"status": params.get("status", ""), "q": params.get("q", "").strip()[:254]}
    page = paginate(
        db,
        _subscriber_query(filters["status"], filters["q"]),
        parse_page(params.get("stranica")),
        25,
    )
    counts = dict(
        db.execute(select(Subscriber.status, func.count()).group_by(Subscriber.status)).all()
    )
    return render(
        request,
        "admin/newsletter/subscribers.html",
        {
            "section": "newsletter",
            "page": page,
            "filters": filters,
            "counts": counts,
            "status_labels": nl.STATUS_LABELS,
            "sources": nl.SOURCES,
            "can_manage": can(user, "newsletter.manage"),
            "form": {},
            "errors": {},
        },
    )


@router.post("/pretplatnici/novi")
async def subscriber_add(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("newsletter.manage")),
):
    form = await request.form()
    email = str(form.get("email", ""))
    note = str(form.get("manual_consent_note", ""))
    subscriber, error = nl.add_manual(db, email, note)
    if error:
        flash(request, error, "error")
        return RedirectResponse("/admin/newsletter/pretplatnici", status_code=303)
    audit.log(
        db,
        user.id,
        "newsletter.manual_add",
        "subscriber",
        subscriber.id,
        {"email_hash": subscriber.email_hash},
        client_ip(request),
    )
    db.commit()
    flash(request, "Pretplatnik je dodan kao potvrđen (ručni unos).", "success")
    return RedirectResponse("/admin/newsletter/pretplatnici", status_code=303)


@router.get("/pretplatnici/izvoz.csv")
async def subscribers_export(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("newsletter.manage")),
):
    rows = list(
        db.scalars(
            select(Subscriber)
            .where(Subscriber.status == SUB_CONFIRMED, Subscriber.email.is_not(None))
            .order_by(Subscriber.email)
        )
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(
        [
            "Email",
            "Izvor",
            "Privola (vrijeme)",
            "Verzija politike",
            "Potvrđeno",
            "Napomena o privoli",
        ]
    )
    for sub in rows:
        writer.writerow(
            [
                sub.email,
                nl.SOURCES.get(sub.source or "", sub.source or ""),
                datetime_hr(sub.consent_at),
                sub.consent_policy_version or "",
                datetime_hr(sub.confirmed_at),
                sub.manual_consent_note or "",
            ]
        )
    audit.log(
        db,
        user.id,
        "newsletter.export",
        "subscriber",
        None,
        {"count": len(rows)},
        client_ip(request),
    )
    db.commit()
    filename = f"pretplatnici-{date.today().isoformat()}.csv"
    return Response(
        codecs.BOM_UTF8 + buffer.getvalue().encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/pretplatnici/{subscriber_id:int}/obrisi")
async def subscriber_delete(
    request: Request,
    subscriber_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("newsletter.manage")),
):
    subscriber = db.get(Subscriber, subscriber_id)
    if subscriber is None:
        raise HTTPException(status_code=404)
    digest = subscriber.email_hash
    db.delete(subscriber)
    audit.log(
        db,
        user.id,
        "newsletter.delete",
        "subscriber",
        subscriber_id,
        {"email_hash": digest},
        client_ip(request),
    )
    db.commit()
    flash(request, "Pretplatnik je obrisan.", "success")
    return RedirectResponse("/admin/newsletter/pretplatnici", status_code=303)


# ---------------------------------------------------------------------------
# Campaigns
# ---------------------------------------------------------------------------
@router.get("/kampanje")
async def campaigns(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("newsletter.view")),
):
    items = list(db.scalars(select(Campaign).order_by(Campaign.created_at.desc())))
    stats = {c.id: nl.delivery_stats(db, c.id) for c in items}
    return render(
        request,
        "admin/newsletter/campaigns.html",
        {
            "section": "newsletter",
            "campaigns": items,
            "stats": stats,
            "status_labels": nl.CAMPAIGN_STATUS_LABELS,
            "can_manage": can(user, "newsletter.manage"),
            "confirmed": nl.confirmed_count(db),
        },
    )


def _get_campaign(db: Session, campaign_id: int) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404)
    return campaign


def _validate_campaign(form) -> tuple[dict, dict]:
    subject = " ".join(str(form.get("subject", "")).split())
    body = nl.clean_campaign_html(str(form.get("body_html", ""))[:100_000])
    errors = {}
    if not 3 <= len(subject) <= 120:
        errors["subject"] = "Naslov mora imati 3–120 znakova."
    if len(nl.html_to_text(body)) < 10:
        errors["body_html"] = "Sadržaj je prekratak."
    return {"subject": subject[:120], "body_html": body}, errors


def _campaign_context(
    db: Session, campaign: Campaign | None, form: dict, errors: dict, user: User
) -> dict:
    context = {
        "section": "newsletter",
        "campaign": campaign,
        "form": form,
        "errors": errors,
        "status_labels": nl.CAMPAIGN_STATUS_LABELS,
        "confirmed": nl.confirmed_count(db),
        "can_manage": can(user, "newsletter.manage"),
    }
    if campaign is not None:
        context["preview_html"] = nl.render_campaign(campaign)[0]
        context["stats"] = nl.delivery_stats(db, campaign.id)
        context["failures"] = list(
            db.scalars(
                select(CampaignDelivery)
                .where(
                    CampaignDelivery.campaign_id == campaign.id,
                    CampaignDelivery.status == DELIVERY_FAILED,
                )
                .limit(50)
            )
        )
    return context


@router.get("/kampanje/nova")
async def campaign_new(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("newsletter.manage")),
):
    form = {"subject": "", "body_html": ""}
    return render(
        request, "admin/newsletter/campaign.html", _campaign_context(db, None, form, {}, user)
    )


@router.post("/kampanje/nova")
async def campaign_create(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("newsletter.manage")),
):
    values, errors = _validate_campaign(await request.form())
    if errors:
        return render(
            request,
            "admin/newsletter/campaign.html",
            _campaign_context(db, None, values, errors, user),
            status_code=400,
        )
    campaign = Campaign(
        subject=values["subject"],
        body_html=values["body_html"],
        status=CAMPAIGN_DRAFT,
        created_by=user.id,
    )
    db.add(campaign)
    db.flush()
    audit.log(db, user.id, "campaign.create", "campaign", campaign.id, None, client_ip(request))
    db.commit()
    flash(request, "Kampanja je spremljena kao skica.", "success")
    return RedirectResponse(f"/admin/newsletter/kampanje/{campaign.id}", status_code=303)


@router.get("/kampanje/{campaign_id:int}")
async def campaign_edit(
    request: Request,
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("newsletter.view")),
):
    campaign = _get_campaign(db, campaign_id)
    form = {"subject": campaign.subject, "body_html": campaign.body_html}
    return render(
        request, "admin/newsletter/campaign.html", _campaign_context(db, campaign, form, {}, user)
    )


@router.post("/kampanje/{campaign_id:int}")
async def campaign_update(
    request: Request,
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("newsletter.manage")),
):
    campaign = _get_campaign(db, campaign_id)
    if campaign.status != CAMPAIGN_DRAFT:
        flash(request, "Poslana kampanja se ne može mijenjati — duplicirajte je.", "error")
        return RedirectResponse(f"/admin/newsletter/kampanje/{campaign.id}", status_code=303)
    values, errors = _validate_campaign(await request.form())
    if errors:
        return render(
            request,
            "admin/newsletter/campaign.html",
            _campaign_context(db, campaign, values, errors, user),
            status_code=400,
        )
    campaign.subject, campaign.body_html = values["subject"], values["body_html"]
    audit.log(db, user.id, "campaign.update", "campaign", campaign.id, None, client_ip(request))
    db.commit()
    flash(request, "Kampanja je spremljena.", "success")
    return RedirectResponse(f"/admin/newsletter/kampanje/{campaign.id}", status_code=303)


@router.get("/kampanje/{campaign_id:int}/pregled")
async def campaign_preview(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("newsletter.view")),
):
    html, _text = nl.render_campaign(_get_campaign(db, campaign_id))
    return HTMLResponse(
        html,
        headers={
            "Content-Security-Policy": "default-src 'none'; "
            "img-src 'self' data: https: http:; style-src 'unsafe-inline'"
        },
    )


@router.post("/kampanje/{campaign_id:int}/test")
async def campaign_test(
    request: Request,
    campaign_id: int,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("newsletter.manage")),
):
    campaign = _get_campaign(db, campaign_id)
    html, text = nl.render_campaign(campaign)
    background.add_task(
        send, user.email, f"[TEST] {campaign.subject}", text, html, "newsletter_test"
    )
    flash(request, f"Testni email je poslan na {user.email}.", "success")
    return RedirectResponse(f"/admin/newsletter/kampanje/{campaign.id}", status_code=303)


@router.post("/kampanje/{campaign_id:int}/posalji")
async def campaign_send(
    request: Request,
    campaign_id: int,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("newsletter.manage")),
):
    campaign = _get_campaign(db, campaign_id)
    if campaign.status != CAMPAIGN_DRAFT:
        flash(request, "Kampanja je već poslana ili se šalje.", "error")
        return RedirectResponse(f"/admin/newsletter/kampanje/{campaign.id}", status_code=303)
    recipients = nl.confirmed_count(db)
    if recipients == 0:
        flash(request, "Nema potvrđenih pretplatnika.", "error")
        return RedirectResponse(f"/admin/newsletter/kampanje/{campaign.id}", status_code=303)
    campaign.status = CAMPAIGN_SENDING
    campaign.recipients_count = recipients
    audit.log(
        db,
        user.id,
        "campaign.send",
        "campaign",
        campaign.id,
        {"recipients": recipients},
        client_ip(request),
    )
    db.commit()
    background.add_task(nl.start_sending, campaign.id)
    flash(
        request,
        f"Slanje je pokrenuto ({recipients} primatelja). Izvještaj se osvježava na ovoj stranici.",
        "success",
    )
    return RedirectResponse(f"/admin/newsletter/kampanje/{campaign.id}", status_code=303)


@router.post("/kampanje/{campaign_id:int}/ponovi")
async def campaign_retry(
    request: Request,
    campaign_id: int,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("newsletter.manage")),
):
    campaign = _get_campaign(db, campaign_id)
    failed = nl.delivery_stats(db, campaign.id)[DELIVERY_FAILED]
    if campaign.status != CAMPAIGN_SENT or not failed:
        flash(request, "Nema neuspjelih isporuka za ponovno slanje.", "info")
    else:
        audit.log(
            db,
            user.id,
            "campaign.send",
            "campaign",
            campaign.id,
            {"retry_failed": failed},
            client_ip(request),
        )
        db.commit()
        background.add_task(nl.start_sending, campaign.id, True)
        flash(request, f"Ponovno slanje {failed} neuspjelih isporuka je pokrenuto.", "success")
    return RedirectResponse(f"/admin/newsletter/kampanje/{campaign.id}", status_code=303)


@router.post("/kampanje/{campaign_id:int}/dupliciraj")
async def campaign_duplicate(
    request: Request,
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("newsletter.manage")),
):
    source = _get_campaign(db, campaign_id)
    copy = Campaign(
        subject=source.subject,
        body_html=source.body_html,
        status=CAMPAIGN_DRAFT,
        created_by=user.id,
    )
    db.add(copy)
    db.flush()
    audit.log(
        db,
        user.id,
        "campaign.create",
        "campaign",
        copy.id,
        {"source": source.id},
        client_ip(request),
    )
    db.commit()
    flash(request, "Kopija kampanje je spremljena kao skica.", "success")
    return RedirectResponse(f"/admin/newsletter/kampanje/{copy.id}", status_code=303)


@router.post("/kampanje/{campaign_id:int}/obrisi")
async def campaign_delete(
    request: Request,
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("newsletter.manage")),
):
    campaign = _get_campaign(db, campaign_id)
    if campaign.status != CAMPAIGN_DRAFT:
        flash(request, "Brisati se mogu samo skice.", "error")
        return RedirectResponse(f"/admin/newsletter/kampanje/{campaign.id}", status_code=303)
    db.delete(campaign)
    audit.log(db, user.id, "campaign.delete", "campaign", campaign_id, None, client_ip(request))
    db.commit()
    flash(request, "Skica kampanje je obrisana.", "success")
    return RedirectResponse("/admin/newsletter/kampanje", status_code=303)


@router.get("/api/vozila")
async def editor_vehicles(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("newsletter.manage")),
):
    q = request.query_params.get("q", "").strip()[:100]
    stmt = select(Vehicle).where(Vehicle.status.in_((STATUS_ACTIVE, STATUS_RESERVED)))
    if q.isdigit():
        stmt = stmt.where(or_(Vehicle.id == int(q), Vehicle.title.ilike(f"%{q}%")))
    elif q:
        stmt = stmt.where(Vehicle.title.ilike(f"%{q}%"))
    items = list(db.scalars(stmt.order_by(Vehicle.published_at.desc()).limit(10)))
    return JSONResponse(
        [{"id": v.id, "title": v.title, "html": nl.vehicle_card_html(v)} for v in items]
    )
