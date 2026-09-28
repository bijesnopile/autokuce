"""Admin dashboard (/admin), statistics (/admin/statistika) and system diagnostics
(/admin/sustav, superadmin only)."""

from __future__ import annotations

import codecs
import csv
import io
import platform
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.deps import csrf_protect, require_permission
from app.models import AuditLog, EmailLog, User
from app.permissions import can
from app.security import client_ip
from app.services import audit, charts, stats
from app.services.inquiries import INQUIRY_STATUS_LABELS, INQUIRY_TYPE_LABELS
from app.services.site import get_site
from app.templating import flash, render

router = APIRouter(prefix="/admin", dependencies=[Depends(csrf_protect)])
settings = get_settings()


@router.get("")
async def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("dashboard")),
):
    data = stats.dashboard(db)
    chart = charts.bar_chart(data["chart_points"], "Pregledi oglasa po danu (zadnjih 30 dana)")
    return render(
        request,
        "admin/dashboard.html",
        {
            "section": "",
            "data": data,
            "chart": chart,
            "type_labels": INQUIRY_TYPE_LABELS,
            "status_labels": INQUIRY_STATUS_LABELS,
        },
    )


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
SORT_KEYS = {"pregledi": "views", "upiti": "inquiries", "konverzija": "conversion"}


def _period(request: Request) -> int:
    try:
        days = int(request.query_params.get("razdoblje", "30"))
    except ValueError:
        days = 30
    return days if days in stats.PERIODS else 30


@router.get("/statistika")
async def statistics(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("stats")),
):
    days = _period(request)
    sort = request.query_params.get("sort", "pregledi")
    sort_key = SORT_KEYS.get(sort, "views")
    rows = stats.vehicle_table(db, days)
    rows.sort(key=lambda r: (r[sort_key] is None, -(r[sort_key] or 0)))
    points = stats.views_per_day(db, days)
    weekly = stats.newsletter_weekly(db, days)
    return render(
        request,
        "admin/statistics.html",
        {
            "section": "statistika",
            "days": days,
            "periods": stats.PERIODS,
            "sort": sort if sort in SORT_KEYS else "pregledi",
            "views_chart": charts.bar_chart(points, f"Pregledi po danu (zadnjih {days} dana)"),
            "views_total": sum(v for _, v in points),
            "vehicle_rows": rows,
            "inquiries": stats.inquiry_breakdown(db, days),
            "newsletter_chart": charts.paired_bar_chart(weekly, "Newsletter po tjednu"),
            "newsletter_totals": (sum(a for _, a, _ in weekly), sum(b for _, _, b in weekly)),
            "top_makes": stats.top_makes(db, days),
            "type_labels": INQUIRY_TYPE_LABELS,
            "status_labels": INQUIRY_STATUS_LABELS,
            "can_export": can(user, "stats.export"),
        },
    )


@router.get("/statistika/izvoz.csv")
async def statistics_export(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("stats.export")),
):
    days = _period(request)
    table = request.query_params.get("tablica", "vozila")
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    if table == "marke":
        writer.writerow(["Marka", f"Pregledi ({days} dana)"])
        for name, total in stats.top_makes(db, days, limit=1000):
            writer.writerow([name, total])
    elif table == "dani":
        writer.writerow(["Datum", "Pregledi"])
        for day, value in stats.views_per_day(db, days):
            writer.writerow([day.strftime("%d.%m.%Y."), value])
    else:
        table = "vozila"
        writer.writerow(["ID", "Vozilo", "Status", "Pregledi", "Upiti", "Konverzija (%)"])
        for row in stats.vehicle_table(db, days):
            conversion = "" if row["conversion"] is None else str(row["conversion"])
            writer.writerow(
                [
                    row["vehicle"].id,
                    row["vehicle"].title,
                    row["vehicle"].status,
                    row["views"],
                    row["inquiries"],
                    conversion.replace(".", ","),
                ]
            )
    audit.log(
        db, user.id, "stats.export", None, None, {"table": table, "days": days}, client_ip(request)
    )
    db.commit()
    filename = f"statistika-{table}-{date.today().isoformat()}.csv"
    return Response(
        codecs.BOM_UTF8 + buffer.getvalue().encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# System diagnostics (superadmin)
# ---------------------------------------------------------------------------
@router.get("/sustav")
async def system_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("system")),
):
    import fastapi
    import sqlalchemy

    from app.services.maintenance import run_all, step_labels

    preview = run_all(db, dry_run=True)
    db.rollback()
    email_stats = dict(
        db.execute(select(EmailLog.status, func.count()).group_by(EmailLog.status)).all()
    )
    last_errors = list(
        db.scalars(
            select(EmailLog)
            .where(EmailLog.status == "failed")
            .order_by(EmailLog.created_at.desc())
            .limit(5)
        )
    )
    info = [
        ("Okruženje (APP_ENV)", settings.APP_ENV),
        ("Baza", "SQLite" if settings.is_sqlite else "PostgreSQL"),
        (
            "Pohrana slika",
            settings.STORAGE_BACKEND + (f" · {settings.MEDIA_URL}" if settings.MEDIA_URL else ""),
        ),
        (
            "Email",
            settings.EMAIL_BACKEND + (" (API ključ postavljen)" if settings.BREVO_API_KEY else ""),
        ),
        ("Pošiljatelj", settings.EMAIL_FROM),
        ("Javni URL", settings.base_url),
        (
            "HTTPS / iza proxyja",
            f"{'da' if settings.HTTPS else 'ne'} / {'da' if settings.TRUST_PROXY else 'ne'}",
        ),
        ("Turnstile", "uključen" if settings.turnstile_enabled else "isključen"),
        ("Umami", "uključen" if settings.umami_enabled else "isključen"),
        ("Admin IP allowlist", settings.ADMIN_IP_ALLOWLIST or "—"),
        ("Održavanje u aplikaciji", "da" if settings.MAINTENANCE_IN_APP else "ne (cron)"),
        ("Zadnje održavanje", get_site().get("maintenance_last_run") or "—"),
        (
            "Verzije",
            f"Python {platform.python_version()} · FastAPI {fastapi.__version__} · "
            f"SQLAlchemy {sqlalchemy.__version__}",
        ),
    ]
    return render(
        request,
        "admin/system.html",
        {
            "section": "sustav",
            "info": info,
            "preview": preview,
            "step_labels": step_labels(),
            "email_stats": email_stats,
            "last_errors": last_errors,
            "audit_count": db.scalar(select(func.count(AuditLog.id))),
        },
    )


@router.post("/sustav/testni-email")
async def system_test_email(
    request: Request,
    background: BackgroundTasks,
    user: User = Depends(require_permission("system")),
):
    from app.services.email import send

    background.add_task(
        send,
        user.email,
        "Testni email — administracija",
        "Ovo je testna poruka iz administracije. Ako je vidite, slanje emaila radi.",
        None,
        "system_test",
    )
    flash(request, f"Testni email je poslan na {user.email} ({settings.EMAIL_BACKEND}).", "success")
    return RedirectResponse("/admin/sustav", status_code=303)


@router.post("/sustav/odrzavanje")
async def system_run_maintenance(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("system")),
):
    from app.services.maintenance import run_all

    result = run_all(db, dry_run=False)
    db.commit()
    summary = ", ".join(f"{k}: {v}" for k, v in result.items())
    flash(request, f"Održavanje je izvršeno — {summary}.", "success")
    return RedirectResponse("/admin/sustav", status_code=303)


@router.get("/{section}")
@router.get("/{section}/{rest:path}")
async def unknown_section(
    request: Request,
    section: str,
    rest: str = "",
    user: User = Depends(require_permission("dashboard")),
):
    """Unknown admin URLs: 404 inside the admin (after login check)."""
    raise HTTPException(status_code=404)
