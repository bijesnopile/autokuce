"""Daily maintenance: data retention (GDPR) and housekeeping.

Run with `python -m app.cli maintenance [--dry-run]` (cron 04:00) or the
in-app daily thread when MAINTENANCE_IN_APP=true (phase 7 adds `run_all`).
Every step returns the number of affected rows; nothing personal is logged.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import utcnow
from app.models import Inquiry, InquiryNote

log = logging.getLogger(__name__)


def purge_old_inquiries(db: Session, dry_run: bool = False) -> int:
    """Delete inquiries (and their notes) older than INQUIRY_RETENTION_DAYS.

    Open and closed inquiries are treated the same (retention runs from `created_at`).
    """
    cutoff = utcnow() - timedelta(days=get_settings().INQUIRY_RETENTION_DAYS)
    old_ids = select(Inquiry.id).where(Inquiry.created_at < cutoff)
    count = db.scalar(select(func.count()).select_from(old_ids.subquery())) or 0
    if count and not dry_run:
        db.execute(delete(InquiryNote).where(InquiryNote.inquiry_id.in_(old_ids)))
        db.execute(delete(Inquiry).where(Inquiry.created_at < cutoff))
    return count
