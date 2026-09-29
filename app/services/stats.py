"""Numbers for the admin dashboard and statistics pages (plain SQL aggregates)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.database import utcnow
from app.models import (
    CAMPAIGN_DRAFT,
    INQUIRY_NEW,
    STATUS_ACTIVE,
    STATUS_DRAFT,
    STATUS_RESERVED,
    SUB_CONFIRMED,
    Campaign,
    Inquiry,
    Make,
    Subscriber,
    Vehicle,
    VehicleImage,
    VehicleView,
)
from app.services.inquiries import UNANSWERED_HOURS
from app.utils import local_day_start_utc, local_today, to_local_date

PERIODS = (30, 90, 365)


def period_start(days: int) -> date:
    return local_today() - timedelta(days=days - 1)


def views_per_day(db: Session, days: int) -> list[tuple[date, int]]:
    start = period_start(days)
    rows = dict(
        db.execute(
            select(VehicleView.date, func.sum(VehicleView.count))
            .where(VehicleView.date >= start)
            .group_by(VehicleView.date)
        ).all()
    )
    return [
        (start + timedelta(days=i), int(rows.get(start + timedelta(days=i), 0) or 0))
        for i in range(days)
    ]


def views_between(db: Session, start: date, end: date) -> int:
    return int(
        db.scalar(
            select(func.coalesce(func.sum(VehicleView.count), 0)).where(
                VehicleView.date >= start, VehicleView.date <= end
            )
        )
        or 0
    )


def _count(db: Session, stmt) -> int:
    return int(db.scalar(stmt) or 0)


def dashboard(db: Session) -> dict:
    today = local_today()
    status_counts = dict(
        db.execute(select(Vehicle.status, func.count()).group_by(Vehicle.status)).all()
    )
    unanswered_cutoff = utcnow() - timedelta(hours=UNANSWERED_HOURS)
    month_start = local_day_start_utc(today.replace(day=1))
    views_30 = views_between(db, today - timedelta(days=29), today)
    views_prev = views_between(db, today - timedelta(days=59), today - timedelta(days=30))
    change = None
    if views_prev:
        change = round((views_30 - views_prev) / views_prev * 100)

    cards = {
        "active": status_counts.get(STATUS_ACTIVE, 0),
        "reserved": status_counts.get(STATUS_RESERVED, 0),
        "drafts": status_counts.get(STATUS_DRAFT, 0),
        "new_inquiries": _count(
            db, select(func.count(Inquiry.id)).where(Inquiry.status == INQUIRY_NEW)
        ),
        "unanswered": _count(
            db,
            select(func.count(Inquiry.id)).where(
                Inquiry.status == INQUIRY_NEW, Inquiry.created_at < unanswered_cutoff
            ),
        ),
        "subscribers": _count(
            db, select(func.count(Subscriber.id)).where(Subscriber.status == SUB_CONFIRMED)
        ),
        "subscribers_month": _count(
            db,
            select(func.count(Subscriber.id)).where(
                Subscriber.status == SUB_CONFIRMED, Subscriber.confirmed_at >= month_start
            ),
        ),
        "views_30": views_30,
        "views_change": change,
    }

    recent = list(
        db.scalars(
            select(Inquiry)
            .options(selectinload(Inquiry.vehicle))
            .order_by(Inquiry.created_at.desc())
            .limit(10)
        )
    )
    top = top_vehicles(db, 30, limit=5)

    has_images = select(VehicleImage.vehicle_id)
    reminders = {
        "drafts_without_images": list(
            db.scalars(
                select(Vehicle)
                .where(Vehicle.status == STATUS_DRAFT, ~Vehicle.id.in_(has_images))
                .limit(10)
            )
        ),
        "active_without_images": list(
            db.scalars(
                select(Vehicle)
                .where(
                    Vehicle.status.in_((STATUS_ACTIVE, STATUS_RESERVED)),
                    ~Vehicle.id.in_(has_images),
                )
                .limit(10)
            )
        ),
        "unanswered": list(
            db.scalars(
                select(Inquiry)
                .where(Inquiry.status == INQUIRY_NEW, Inquiry.created_at < unanswered_cutoff)
                .order_by(Inquiry.created_at)
                .limit(10)
            )
        ),
        "old_campaign_drafts": list(
            db.scalars(
                select(Campaign)
                .where(
                    Campaign.status == CAMPAIGN_DRAFT,
                    Campaign.created_at < utcnow() - timedelta(days=7),
                )
                .limit(5)
            )
        ),
    }
    return {
        "cards": cards,
        "chart_points": views_per_day(db, 30),
        "recent": recent,
        "top": top,
        "reminders": reminders,
        "reminder_count": sum(len(v) for v in reminders.values()),
    }


def top_vehicles(db: Session, days: int, limit: int = 5) -> list[tuple[Vehicle, int]]:
    start = period_start(days)
    rows = db.execute(
        select(VehicleView.vehicle_id, func.sum(VehicleView.count).label("views"))
        .where(VehicleView.date >= start)
        .group_by(VehicleView.vehicle_id)
        .order_by(func.sum(VehicleView.count).desc())
        .limit(limit)
    ).all()
    vehicles = {
        v.id: v
        for v in db.scalars(
            select(Vehicle)
            .options(selectinload(Vehicle.images))
            .where(Vehicle.id.in_([r[0] for r in rows]))
        )
    }
    return [(vehicles[r[0]], int(r[1])) for r in rows if r[0] in vehicles]


def vehicle_table(db: Session, days: int) -> list[dict]:
    """Views and inquiries per vehicle in the period, with conversion (inquiries / views)."""
    start = period_start(days)
    start_utc = local_day_start_utc(start)
    views = dict(
        db.execute(
            select(VehicleView.vehicle_id, func.sum(VehicleView.count))
            .where(VehicleView.date >= start)
            .group_by(VehicleView.vehicle_id)
        ).all()
    )
    inquiries = dict(
        db.execute(
            select(Inquiry.vehicle_id, func.count(Inquiry.id))
            .where(Inquiry.created_at >= start_utc, Inquiry.vehicle_id.is_not(None))
            .group_by(Inquiry.vehicle_id)
        ).all()
    )
    from app.services.messaging import clicks_by_vehicle

    contacts = clicks_by_vehicle(db, start)
    ids = set(views) | set(inquiries) | set(contacts)
    rows = []
    for vehicle in db.scalars(select(Vehicle).where(Vehicle.id.in_(ids))):
        v_count = int(views.get(vehicle.id, 0) or 0)
        i_count = int(inquiries.get(vehicle.id, 0) or 0)
        rows.append(
            {
                "vehicle": vehicle,
                "views": v_count,
                "inquiries": i_count,
                "contacts": int(contacts.get(vehicle.id, 0) or 0),
                "conversion": round(i_count / v_count * 100, 1) if v_count else None,
            }
        )
    return rows


def inquiry_breakdown(db: Session, days: int) -> dict:
    start_utc = local_day_start_utc(period_start(days))
    by_type = dict(
        db.execute(
            select(Inquiry.type, func.count())
            .where(Inquiry.created_at >= start_utc)
            .group_by(Inquiry.type)
        ).all()
    )
    by_status = dict(
        db.execute(
            select(Inquiry.status, func.count())
            .where(Inquiry.created_at >= start_utc)
            .group_by(Inquiry.status)
        ).all()
    )
    contacted = db.execute(
        select(Inquiry.created_at, Inquiry.contacted_at).where(
            Inquiry.created_at >= start_utc, Inquiry.contacted_at.is_not(None)
        )
    ).all()
    hours = [(c - a).total_seconds() / 3600 for a, c in contacted if c >= a]
    return {
        "by_type": by_type,
        "by_status": by_status,
        "total": sum(by_type.values()),
        "avg_first_contact_hours": round(sum(hours) / len(hours), 1) if hours else None,
    }


def newsletter_weekly(db: Session, days: int) -> list[tuple[str, int, int]]:
    """Signups (confirmed) and unsubscribes per ISO week."""
    start = period_start(days)
    start_utc = local_day_start_utc(start)
    weeks: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    first_monday = start - timedelta(days=start.weekday())
    day = first_monday
    while day <= local_today():
        weeks[day.strftime("%d.%m.")] = [0, 0]
        day += timedelta(days=7)

    def week_key(value) -> str:
        local = to_local_date(value)
        return (local - timedelta(days=local.weekday())).strftime("%d.%m.")

    for (confirmed_at,) in db.execute(
        select(Subscriber.confirmed_at).where(Subscriber.confirmed_at >= start_utc)
    ):
        weeks[week_key(confirmed_at)][0] += 1
    for (unsubscribed_at,) in db.execute(
        select(Subscriber.unsubscribed_at).where(Subscriber.unsubscribed_at >= start_utc)
    ):
        weeks[week_key(unsubscribed_at)][1] += 1
    return [(label, a, b) for label, (a, b) in weeks.items()]


def top_makes(db: Session, days: int, limit: int = 10) -> list[tuple[str, int]]:
    start = period_start(days)
    rows = db.execute(
        select(Make.name, func.sum(VehicleView.count))
        .join(Vehicle, Vehicle.make_id == Make.id)
        .join(VehicleView, VehicleView.vehicle_id == Vehicle.id)
        .where(VehicleView.date >= start)
        .group_by(Make.name)
        .order_by(func.sum(VehicleView.count).desc())
        .limit(limit)
    ).all()
    return [(name, int(total)) for name, total in rows]
