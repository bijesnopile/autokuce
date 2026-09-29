"""Email sending with three backends (EMAIL_BACKEND):

- `console` — prints to the log (development only; body printed only in APP_ENV=development)
- `file`    — writes an `.eml` file into `data/outbox/` (default for local/demo)
- `brevo`   — Brevo transactional HTTP API (https://api.brevo.com/v3/smtp/email)

Every send is recorded in `email_log` with a SHA-256 hash of the recipient
(never the plain address). Call from `BackgroundTasks` in request handlers.
"""

from __future__ import annotations

import base64
import logging
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import format_datetime, formataddr, make_msgid

import httpx

from app.config import get_settings
from app.database import SessionLocal
from app.models import EmailLog
from app.security import email_hash, mask_email
from app.services.site import get_site
from app.templating import render_string
from app.utils import slugify

log = logging.getLogger(__name__)
settings = get_settings()

BREVO_URL = "https://api.brevo.com/v3/smtp/email"


@dataclass
class EmailResult:
    ok: bool
    message_id: str | None = None
    error: str | None = None


def absolute_url(path: str) -> str:
    """Links in emails must be absolute (BASE_URL + path)."""
    if path.startswith(("http://", "https://")):
        return path
    return f"{settings.base_url}{path if path.startswith('/') else '/' + path}"


def sender() -> tuple[str, str]:
    site = get_site()
    return site.get("company_name") or "", settings.EMAIL_FROM


# (filename, content, MIME type), e.g. ("pregled.ics", b"BEGIN:VCALENDAR...", "text/calendar")
Attachment = tuple[str, bytes, str]


def _build_message(
    to: str,
    subject: str,
    text: str,
    html: str | None,
    reply_to: str | None,
    headers: dict | None,
    from_name: str | None = None,
    attachments: list[Attachment] | None = None,
) -> EmailMessage:
    name, address = sender()
    message = EmailMessage()
    message["From"] = formataddr((from_name or name, address))
    message["To"] = to
    message["Subject"] = subject
    message["Date"] = format_datetime(datetime.now(UTC))
    message["Message-ID"] = make_msgid(domain=address.split("@")[-1] or "localhost")
    if reply_to:
        message["Reply-To"] = reply_to
    for key, value in (headers or {}).items():
        message[key] = value
    message.set_content(text)
    if html:
        message.add_alternative(html, subtype="html")
    for filename, content, mime in attachments or []:
        maintype, _, subtype = mime.partition("/")
        params = {"method": "PUBLISH"} if mime == "text/calendar" else {}
        message.add_attachment(
            content, maintype=maintype, subtype=subtype, filename=filename, params=params
        )
    return message


def _send_file(
    message: EmailMessage, subject: str, attachments: list[Attachment] | None = None
) -> EmailResult:
    outbox = settings.outbox_dir
    outbox.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    name = f"{stamp}_{slugify(subject, 50) or 'email'}_{secrets.token_hex(3)}.eml"
    (outbox / name).write_bytes(bytes(message))
    # Attachments also as separate files next to the .eml (easy to open while developing).
    for filename, content, _mime in attachments or []:
        (outbox / f"{name[:-4]}_{filename}").write_bytes(content)
    return EmailResult(ok=True, message_id=message["Message-ID"])


def _send_console(message: EmailMessage, to: str, subject: str) -> EmailResult:
    attached = [part.get_filename() for part in message.iter_attachments()]
    log.info(
        "EMAIL (console) to=%s subject=%r attachments=%s", mask_email(to), subject, attached or "-"
    )
    if settings.is_development:
        body = message.get_body(preferencelist=("plain",))
        print("-" * 60 + f"\nTo: {to}\nSubject: {subject}\n\n{body.get_content()}\n" + "-" * 60)
    return EmailResult(ok=True, message_id=message["Message-ID"])


def _send_brevo(
    to: str,
    subject: str,
    text: str,
    html: str | None,
    reply_to: str | None,
    headers: dict | None,
    from_name: str | None,
    attachments: list[Attachment] | None = None,
) -> EmailResult:
    if not settings.BREVO_API_KEY:
        return EmailResult(ok=False, error="BREVO_API_KEY nije postavljen")
    name, address = sender()
    payload: dict = {
        "sender": {"name": from_name or name, "email": address},
        "to": [{"email": to}],
        "subject": subject,
        "textContent": text,
    }
    if html:
        payload["htmlContent"] = html
    if reply_to:
        payload["replyTo"] = {"email": reply_to}
    if headers:
        payload["headers"] = headers
    if attachments:
        payload["attachment"] = [
            {"name": filename, "content": base64.b64encode(content).decode("ascii")}
            for filename, content, _mime in attachments
        ]
    request_headers = {
        "api-key": settings.BREVO_API_KEY,
        "accept": "application/json",
        "content-type": "application/json",
    }
    last_error = None
    for attempt in range(2):  # one retry on network errors / 5xx
        try:
            response = httpx.post(BREVO_URL, json=payload, headers=request_headers, timeout=10)
            if response.status_code in (200, 201, 202):
                return EmailResult(ok=True, message_id=response.json().get("messageId"))
            last_error = f"Brevo HTTP {response.status_code}: {response.text[:300]}"
            if response.status_code < 500:
                break
        except httpx.HTTPError as exc:
            last_error = f"Brevo greška: {exc.__class__.__name__}"
        if attempt == 0:
            time.sleep(1)
    return EmailResult(ok=False, error=last_error)


def _record(to: str, template: str | None, result: EmailResult) -> None:
    db = SessionLocal()
    try:
        db.add(
            EmailLog(
                to_hash=email_hash(to),
                template=template,
                status="sent" if result.ok else "failed",
                provider_message_id=(result.message_id or "")[:200] or None,
                error=(result.error or "")[:500] or None,
            )
        )
        db.commit()
    except Exception:  # noqa: BLE001 - logging must never break sending
        log.exception("Could not write email_log")
    finally:
        db.close()


def send(
    to: str,
    subject: str,
    text: str,
    html: str | None = None,
    template: str | None = None,
    reply_to: str | None = None,
    headers: dict | None = None,
    from_name: str | None = None,
    attachments: list[Attachment] | None = None,
) -> EmailResult:
    """Send one email through the configured backend and record it in email_log."""
    backend = settings.EMAIL_BACKEND
    try:
        if backend == "brevo":
            result = _send_brevo(to, subject, text, html, reply_to, headers, from_name, attachments)
        else:
            message = _build_message(
                to, subject, text, html, reply_to, headers, from_name, attachments
            )
            if backend == "console":
                result = _send_console(message, to, subject)
            else:
                result = _send_file(message, subject, attachments)
    except Exception as exc:  # noqa: BLE001 - report as failed delivery
        log.exception("Email sending failed")
        result = EmailResult(ok=False, error=str(exc)[:300])
    if not result.ok:
        log.warning("Email to %s failed: %s", mask_email(to), result.error)
    _record(to, template, result)
    return result


def render_email(template: str, context: dict | None = None) -> tuple[str, str]:
    """Render `emails/<template>.html` and `.txt` -> (html, text)."""
    ctx = {"absolute_url": absolute_url, "base_url": settings.base_url}
    site = get_site()
    logo = site.get("logo_url") or ""
    ctx["logo_abs_url"] = absolute_url(logo) if logo else ""
    if context:
        ctx.update(context)
    html = render_string(f"emails/{template}.html", ctx)
    text = render_string(f"emails/{template}.txt", ctx)
    return html, text


def render_email_fragment(template_name: str, context: dict | None = None) -> str:
    """Render an email partial (e.g. the vehicle card) with the email helpers available."""
    ctx = {"absolute_url": absolute_url, "base_url": settings.base_url}
    if context:
        ctx.update(context)
    return render_string(template_name, ctx)


def send_template(
    to: str,
    template: str,
    subject: str,
    context: dict | None = None,
    reply_to: str | None = None,
    headers: dict | None = None,
    from_name: str | None = None,
    attachments: list[Attachment] | None = None,
) -> EmailResult:
    ctx = {"subject": subject}
    if context:
        ctx.update(context)
    html, text = render_email(template, ctx)
    return send(to, subject, text, html, template, reply_to, headers, from_name, attachments)
