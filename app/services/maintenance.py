"""Daily maintenance: data retention (GDPR) and housekeeping.

    python -m app.cli maintenance [--dry-run]     (cron, e.g. 04:00 — deploy/crontab.example)

or, with MAINTENANCE_IN_APP=true, a background thread in the app runs `run_all`
once a day at 04:00 (Europe/Zagreb). With several workers only one run per day
happens: the date of the last run is claimed atomically in `settings`
(`maintenance_last_run`).

Retention rules (docs/GDPR.md):
    inquiries + notes ........ INQUIRY_RETENTION_DAYS (365) from created_at
    pending subscribers ...... 7 days after the last confirmation email
    unsubscribed (hash only).. 3 years
    sold vehicles ............ archived SOLD_VISIBLE_DAYS (30) after sale (kept, no personal data)
    sessions / auth tokens ... deleted after expiry (tokens also 7 days after use)
    email_log ................ 90 days
    audit_log ................ 2 years
    vehicle_views ............ 400 days
"""

from __future__ import annotations

import logging
import threading
import time as time_module
from datetime import timedelta

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal, utcnow
from app.models import (
    STATUS_ARCHIVED,
    STATUS_SOLD,
    AuditLog,
    AuthToken,
    EmailLog,
    Inquiry,
    InquiryNote,
    Setting,
    UserSession,
    Vehicle,
    VehicleView,
)
from app.utils import local_now, local_today

log = logging.getLogger(__name__)

EMAIL_LOG_DAYS = 90
AUDIT_DAYS = 2 * 365
VIEWS_DAYS = 400
LAST_RUN_KEY = "maintenance_last_run"
RUN_HOUR = 4


def _count(db: Session, model, condition) -> int:
    return int(db.scalar(select(func.count()).select_from(model).where(condition)) or 0)


def purge_old_inquiries(db: Session, dry_run: bool = False) -> int:
    """Delete inquiries (and their notes) older than INQUIRY_RETENTION_DAYS.

    Open and closed inquiries are treated the same (retention runs from `created_at`).
    """
    cutoff = utcnow() - timedelta(days=get_settings().INQUIRY_RETENTION_DAYS)
    condition = Inquiry.created_at < cutoff
    count = _count(db, Inquiry, condition)
    if count and not dry_run:
        old_ids = select(Inquiry.id).where(condition)
        db.execute(delete(InquiryNote).where(InquiryNote.inquiry_id.in_(old_ids)))
        db.execute(delete(Inquiry).where(condition))
    return count


def purge_pending_subscribers(db: Session, dry_run: bool = False) -> int:
    """Newsletter signups not confirmed within 7 days."""
    from app.services.newsletter import purge_pending_subscribers as purge

    return purge(db, dry_run)


def purge_old_unsubscribed(db: Session, dry_run: bool = False) -> int:
    """Anonymised (hash-only) unsubscribed entries older than 3 years."""
    from app.services.newsletter import purge_old_unsubscribed as purge

    return purge(db, dry_run)


def archive_sold_vehicles(db: Session, dry_run: bool = False) -> int:
    """`sold` vehicles older than SOLD_VISIBLE_DAYS become `archived` (410 on the website)."""
    cutoff = utcnow() - timedelta(days=get_settings().SOLD_VISIBLE_DAYS)
    condition = (Vehicle.status == STATUS_SOLD) & (Vehicle.sold_at < cutoff)
    count = _count(db, Vehicle, condition)
    if count and not dry_run:
        db.execute(
            update(Vehicle)
            .where(condition)
            .values(status=STATUS_ARCHIVED, featured=False, updated_at=Vehicle.updated_at)
        )
    return count


def purge_expired_sessions_and_tokens(db: Session, dry_run: bool = False) -> int:
    now = utcnow()
    session_condition = UserSession.expires_at < now
    token_condition = or_(
        AuthToken.expires_at < now,
        AuthToken.used_at < now - timedelta(days=7),
    )
    count = _count(db, UserSession, session_condition) + _count(db, AuthToken, token_condition)
    if count and not dry_run:
        db.execute(delete(UserSession).where(session_condition))
        db.execute(delete(AuthToken).where(token_condition))
    return count


def purge_old_email_log(db: Session, dry_run: bool = False) -> int:
    condition = EmailLog.created_at < utcnow() - timedelta(days=EMAIL_LOG_DAYS)
    count = _count(db, EmailLog, condition)
    if count and not dry_run:
        db.execute(delete(EmailLog).where(condition))
    return count


def purge_old_audit(db: Session, dry_run: bool = False) -> int:
    condition = AuditLog.created_at < utcnow() - timedelta(days=AUDIT_DAYS)
    count = _count(db, AuditLog, condition)
    if count and not dry_run:
        db.execute(delete(AuditLog).where(condition))
    return count


def purge_old_vehicle_views(db: Session, dry_run: bool = False) -> int:
    condition = VehicleView.date < local_today() - timedelta(days=VIEWS_DAYS)
    count = _count(db, VehicleView, condition)
    if count and not dry_run:
        db.execute(delete(VehicleView).where(condition))
    return count


STEPS = [
    ("old_inquiries", purge_old_inquiries),
    ("pending_subscribers", purge_pending_subscribers),
    ("old_unsubscribed", purge_old_unsubscribed),
    ("archived_sold_vehicles", archive_sold_vehicles),
    ("expired_sessions_tokens", purge_expired_sessions_and_tokens),
    ("old_email_log", purge_old_email_log),
    ("old_audit", purge_old_audit),
    ("old_vehicle_views", purge_old_vehicle_views),
]


def step_labels() -> dict[str, str]:
    """Human-readable (Croatian) description of each step, with the configured periods."""
    cfg = get_settings()
    return {
        "old_inquiries": f"Upiti i bilješke stariji od {cfg.INQUIRY_RETENTION_DAYS} dana",
        "pending_subscribers": "Nepotvrđene prijave na newsletter (7 dana)",
        "old_unsubscribed": "Odjavljeni pretplatnici — hash stariji od 3 godine",
        "archived_sold_vehicles": f"Prodana vozila za arhivu (nakon {cfg.SOLD_VISIBLE_DAYS} dana)",
        "expired_sessions_tokens": "Istekle sesije i tokeni",
        "old_email_log": f"Zapisi o poslanim emailovima stariji od {EMAIL_LOG_DAYS} dana",
        "old_audit": "Audit log stariji od 2 godine",
        "old_vehicle_views": f"Dnevni pregledi oglasa stariji od {VIEWS_DAYS} dana",
    }


def run_all(db: Session, dry_run: bool = False) -> dict:
    """Run every step; returns {step: affected rows}. The caller commits (or rolls back)."""
    result = {}
    for name, step in STEPS:
        result[name] = step(db, dry_run=dry_run)
        log.info("maintenance %s%s: %s", "[dry-run] " if dry_run else "", name, result[name])
    if not dry_run:
        from app.services import audit

        audit.log(db, None, "system.maintenance", details=result)
    return result


# ---------------------------------------------------------------------------
# Once-a-day guard (safe with several workers / processes)
# ---------------------------------------------------------------------------
def claim_daily_run(db: Session, today: str) -> bool:
    """Atomically claim today's run. Returns True for exactly one caller per day."""
    row = db.get(Setting, LAST_RUN_KEY)
    if row is None:
        try:
            db.add(Setting(key=LAST_RUN_KEY, value=today))
            db.commit()
            return True
        except Exception:  # noqa: BLE001 - another worker inserted it first
            db.rollback()
    claimed = db.execute(
        update(Setting)
        .where(Setting.key == LAST_RUN_KEY, Setting.value != today)
        .values(value=today)
    ).rowcount
    db.commit()
    return bool(claimed)


def run_daily_if_due(now=None) -> dict | None:
    """Run maintenance if it is past 04:00 local time and it has not run today."""
    now = now or local_now()
    if now.hour < RUN_HOUR:
        return None
    db = SessionLocal()
    try:
        if not claim_daily_run(db, now.date().isoformat()):
            return None
        result = run_all(db)
        db.commit()
        from app.services.site import invalidate_site_cache

        invalidate_site_cache()
        return result
    except Exception:  # noqa: BLE001 - never kill the worker thread
        log.exception("Daily maintenance failed")
        db.rollback()
        return None
    finally:
        db.close()


_thread_started = False


def start_background_thread(check_every_s: int = 600) -> None:
    """Daemon thread that checks every 10 minutes whether the daily run is due."""
    global _thread_started
    if _thread_started:
        return
    _thread_started = True

    def loop() -> None:
        while True:
            run_daily_if_due()
            time_module.sleep(check_every_s)

    threading.Thread(target=loop, name="maintenance", daemon=True).start()
    log.info("In-app maintenance thread started (daily at %02d:00)", RUN_HOUR)
