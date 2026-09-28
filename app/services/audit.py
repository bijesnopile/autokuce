"""Audit log helper. Every admin action should call `log()`.

`details` must never contain customer personal data (names, emails, phones,
messages). Use IDs, counts, changed field names or email hashes instead.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AuditLog


def log(
    db: Session,
    user_id: int | None,
    action: str,
    entity_type: str | None = None,
    entity_id: int | str | None = None,
    details: dict | None = None,
    ip: str | None = None,
) -> AuditLog:
    """Add an audit entry to the session (the caller commits)."""
    entry = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        details=details or None,
        ip=ip,
    )
    db.add(entry)
    return entry
