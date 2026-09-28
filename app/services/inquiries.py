"""Customer inquiries: validation, anti-spam checks, saving with consent metadata,
dealer notification email, status workflow and CSV export.

HOW TO ADD AN INQUIRY TYPE (e.g. "test_drive", "financing", "trade_in")
    1. Add the code + label to INQUIRY_TYPE_LABELS (and models.INQUIRY_TYPES).
    2. Add the form variant in templates/public/_inquiry_form.html (extra fields are
       stored in `inquiries.extra` JSON — no migration needed).
    3. Validate the extra fields in `validate_inquiry` below.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.database import utcnow
from app.models import (
    INQUIRY_CLOSED,
    INQUIRY_CONTACTED,
    INQUIRY_GENERAL,
    INQUIRY_NEW,
    INQUIRY_VEHICLE,
    INQUIRY_VIEWING,
    Inquiry,
    Vehicle,
)
from app.security import normalize_email
from app.utils import LOCAL_TZ, local_now

INQUIRY_TYPE_LABELS = {
    INQUIRY_VEHICLE: "Upit za vozilo",
    INQUIRY_VIEWING: "Dogovor pregleda",
    INQUIRY_GENERAL: "Opći upit",
}
INQUIRY_STATUS_LABELS = {
    INQUIRY_NEW: "Novi",
    INQUIRY_CONTACTED: "Kontaktiran",
    INQUIRY_CLOSED: "Zatvoren",
}
UNANSWERED_HOURS = 48
SUCCESS_MESSAGE = "Hvala, javit ćemo vam se u najkraćem roku."

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[A-Za-z]{2,}$")


def normalize_phone(raw: str) -> tuple[str | None, str | None]:
    """Croatian numbers (+385… or 0…) normalised to +385…; other +country numbers kept.

    Returns (phone, error). Empty input -> (None, None).
    """
    text = re.sub(r"[\s\-/().]", "", raw or "")
    if not text:
        return None, None
    if text.startswith("00"):
        text = "+" + text[2:]
    if text.startswith("0"):
        text = "+385" + text[1:]
    if not re.fullmatch(r"\+\d{8,15}", text):
        return None, "Upišite ispravan broj telefona (npr. +385 91 234 5678 ili 091 234 5678)."
    if text.startswith("+385") and not 8 <= len(text) - 4 <= 10:
        return None, "Upišite ispravan hrvatski broj telefona."
    return text, None


def parse_preferred_date(raw: str) -> tuple[datetime | None, str | None]:
    """`YYYY-MM-DDTHH:MM` in local time -> naive UTC. Must be tomorrow or later."""
    if not raw:
        return None, "Odaberite željeni termin."
    try:
        local = datetime.fromisoformat(raw.strip()).replace(tzinfo=LOCAL_TZ)
    except ValueError:
        return None, "Neispravan datum i vrijeme."
    tomorrow = (local_now() + timedelta(days=1)).date()
    if local.date() < tomorrow:
        return None, "Termin mora biti najranije sutra."
    if local.date() > tomorrow + timedelta(days=365):
        return None, "Termin može biti najviše godinu dana unaprijed."
    return local.astimezone(UTC).replace(tzinfo=None), None


def min_viewing_value() -> str:
    """`min` attribute for the datetime-local input (tomorrow 08:00 local)."""
    tomorrow = (local_now() + timedelta(days=1)).date()
    return f"{tomorrow.isoformat()}T08:00"


def validate_inquiry(form) -> tuple[dict, dict]:
    """Validate raw form values. Returns (clean, errors)."""
    errors: dict = {}
    clean: dict = {}
    kind = str(form.get("type", INQUIRY_GENERAL))
    if kind not in INQUIRY_TYPE_LABELS:
        kind = INQUIRY_GENERAL
    clean["type"] = kind

    name = " ".join(str(form.get("name", "")).split())[:100]
    if len(name) < 2:
        errors["name"] = "Upišite ime i prezime (najmanje 2 znaka)."
    clean["name"] = name

    email = normalize_email(str(form.get("email", "")))[:254]
    if not EMAIL_RE.match(email):
        errors["email"] = "Upišite ispravnu email adresu."
    clean["email"] = email

    phone, phone_error = normalize_phone(str(form.get("phone", ""))[:40])
    if phone_error:
        errors["phone"] = phone_error
    clean["phone"] = phone

    message = str(form.get("message", "")).strip()
    if len(message) < 10:
        errors["message"] = "Poruka mora imati barem 10 znakova."
    elif len(message) > 2000:
        errors["message"] = "Poruka može imati najviše 2000 znakova."
    clean["message"] = message[:2000]

    if kind == INQUIRY_VIEWING:
        preferred, date_error = parse_preferred_date(str(form.get("preferred_date", "")))
        if date_error:
            errors["preferred_date"] = date_error
        clean["preferred_date"] = preferred

    if str(form.get("consent", "")) not in ("1", "on", "true"):
        errors["consent"] = "Za slanje upita potrebna je vaša privola."
    return clean, errors


def create_inquiry(
    db: Session,
    clean: dict,
    vehicle: Vehicle | None,
    ip: str,
    user_agent: str,
    policy_version: str,
    source_url: str,
) -> Inquiry:
    inquiry = Inquiry(
        type=clean["type"],
        vehicle_id=vehicle.id if vehicle else None,
        name=clean["name"],
        email=clean["email"],
        phone=clean.get("phone"),
        message=clean["message"],
        preferred_date=clean.get("preferred_date"),
        status=INQUIRY_NEW,
        consent_at=utcnow(),
        consent_ip=ip,
        consent_user_agent=(user_agent or "")[:300],
        consent_policy_version=policy_version,
        source_url=source_url[:500],
    )
    db.add(inquiry)
    db.flush()
    return inquiry


def change_status(inquiry: Inquiry, status: str) -> bool:
    """new -> contacted -> closed (going back is allowed). Returns True if changed."""
    if status not in INQUIRY_STATUS_LABELS or status == inquiry.status:
        return False
    now = utcnow()
    inquiry.status = status
    if status == INQUIRY_CONTACTED and inquiry.contacted_at is None:
        inquiry.contacted_at = now
    if status == INQUIRY_CLOSED:
        inquiry.closed_at = now
        if inquiry.contacted_at is None:
            inquiry.contacted_at = now
    else:
        inquiry.closed_at = None
    return True


def is_unanswered(inquiry: Inquiry) -> bool:
    return inquiry.status == INQUIRY_NEW and inquiry.created_at < utcnow() - timedelta(
        hours=UNANSWERED_HOURS
    )


def export_csv(inquiries: list[Inquiry]) -> bytes:
    """CSV for Excel on Croatian Windows: UTF-8 with BOM, `;` separator."""
    from app.templating import datetime_hr

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    writer.writerow(
        [
            "ID",
            "Primljeno",
            "Tip",
            "Status",
            "Ime i prezime",
            "Email",
            "Telefon",
            "Vozilo",
            "Poruka",
            "Željeni termin",
            "Dodijeljeno",
            "Privola (vrijeme)",
            "Verzija politike",
        ]
    )
    for item in inquiries:
        writer.writerow(
            [
                item.id,
                datetime_hr(item.created_at),
                INQUIRY_TYPE_LABELS.get(item.type, item.type),
                INQUIRY_STATUS_LABELS.get(item.status, item.status),
                item.name,
                item.email,
                item.phone or "",
                item.vehicle.title if item.vehicle else "",
                item.message.replace("\r", " ").replace("\n", " "),
                datetime_hr(item.preferred_date) if item.preferred_date else "",
                (item.assignee.name or item.assignee.email) if item.assignee else "",
                datetime_hr(item.consent_at) if item.consent_at else "",
                item.consent_policy_version or "",
            ]
        )
    return "﻿".encode() + buffer.getvalue().encode("utf-8")


def send_notification(inquiry_id: int) -> None:
    """Email the dealer about a new inquiry (runs in BackgroundTasks, own DB session).

    Recipient: settings `inquiry_notify_email` (fallback `company_email`); Reply-To is the
    customer's address so the dealer can answer directly. The customer gets no email in MVP.
    """
    from app.database import SessionLocal
    from app.services.email import absolute_url, send_template
    from app.services.site import get_site
    from app.templating import datetime_hr

    db = SessionLocal()
    try:
        inquiry = db.get(Inquiry, inquiry_id)
        if inquiry is None:
            return
        site = get_site()
        recipient = site.get("inquiry_notify_email") or site.get("company_email")
        vehicle = inquiry.vehicle
        context = {
            "type_label": INQUIRY_TYPE_LABELS.get(inquiry.type, inquiry.type),
            "name": inquiry.name,
            "email": inquiry.email,
            "phone": inquiry.phone,
            "message": inquiry.message,
            "preferred_date": datetime_hr(inquiry.preferred_date) if inquiry.preferred_date else "",
            "received": datetime_hr(inquiry.created_at),
            "vehicle_title": vehicle.title if vehicle else "",
            "vehicle_url": absolute_url(f"/vozila/{vehicle.slug}") if vehicle else "",
            "admin_url": absolute_url(f"/admin/upiti/{inquiry.id}"),
        }
        subject_target = vehicle.title if vehicle else "opći upit"
        subject = f"Novi upit: {context['type_label']} – {subject_target}"
        send_template(recipient, "inquiry_notification", subject, context, reply_to=inquiry.email)
    finally:
        db.close()
