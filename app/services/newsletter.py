"""Newsletter: double opt-in, one-click unsubscribe with anonymisation, campaigns.

Consent flow: the signup stores consent metadata (time, IP, user agent, policy
version, source) and sends a confirmation link (7 days). Only `confirmed`
subscribers receive campaigns. Unsubscribing sets the email to NULL and keeps
only the SHA-256 hash (suppression list); re-subscribing needs a new opt-in.

Tokens: the confirmation token is random (only its hash is stored). The
unsubscribe token is an HMAC of the subscriber's id/hash/confirmation time with
SECRET_KEY — it can be regenerated for every campaign email while the DB still
stores only its hash; unsubscribing clears the hash, so old links stop working.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import threading
import time
from datetime import timedelta
from html.parser import HTMLParser

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal, utcnow
from app.models import (
    CAMPAIGN_DRAFT,
    CAMPAIGN_SENDING,
    CAMPAIGN_SENT,
    DELIVERY_FAILED,
    DELIVERY_SENT,
    SUB_CONFIRMED,
    SUB_PENDING,
    SUB_UNSUBSCRIBED,
    Campaign,
    CampaignDelivery,
    Subscriber,
)
from app.security import clean_html, email_hash, generate_token, hash_token, normalize_email

log = logging.getLogger(__name__)
settings = get_settings()

CONFIRM_DAYS = 7
RESEND_MINUTES = 10
UNSUBSCRIBED_KEEP_DAYS = 3 * 365
BATCH_SIZE = 50
BATCH_PAUSE_S = 0.0 if settings.APP_ENV == "test" else 1.0
NEUTRAL_MESSAGE = "Ako adresa još nije potvrđena, poslali smo vam email s linkom za potvrdu."
SOURCES = {
    "footer": "Podnožje",
    "home": "Naslovnica",
    "vehicle": "Stranica vozila",
    "manual": "Ručni unos",
}
STATUS_LABELS = {
    SUB_PENDING: "Na čekanju",
    SUB_CONFIRMED: "Potvrđen",
    SUB_UNSUBSCRIBED: "Odjavljen",
}
CAMPAIGN_STATUS_LABELS = {
    CAMPAIGN_DRAFT: "Skica",
    CAMPAIGN_SENDING: "Šalje se",
    CAMPAIGN_SENT: "Poslano",
}

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[A-Za-z]{2,}$")


def valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email)) and len(email) <= 254


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------
def unsubscribe_token(subscriber: Subscriber) -> str:
    """Stable per-subscription token (HMAC with SECRET_KEY)."""
    stamp = subscriber.confirmed_at.isoformat() if subscriber.confirmed_at else ""
    message = f"unsubscribe:{subscriber.id}:{subscriber.email_hash}:{stamp}".encode()
    return hmac.new(settings.secret_key.encode(), message, hashlib.sha256).hexdigest()


def _activate(subscriber: Subscriber) -> None:
    """Mark as confirmed and create the permanent unsubscribe token (hash stored)."""
    subscriber.status = SUB_CONFIRMED
    subscriber.confirmed_at = utcnow()
    subscriber.confirm_token_hash = None
    subscriber.unsubscribed_at = None
    subscriber.unsubscribe_token_hash = hash_token(unsubscribe_token(subscriber))


# ---------------------------------------------------------------------------
# Subscribe / confirm / unsubscribe
# ---------------------------------------------------------------------------
def subscribe(db: Session, email: str, meta: dict) -> str | None:
    """Register a signup. Returns the raw confirmation token if an email must be sent.

    confirmed -> nothing; pending -> resend at most once per 10 min; unsubscribed
    (anonymised) -> treated as a brand-new signup; unknown -> create pending.
    The caller always shows the same neutral message.
    """
    email = normalize_email(email)
    digest = email_hash(email)
    subscriber = db.scalar(select(Subscriber).where(Subscriber.email_hash == digest))
    now = utcnow()
    if subscriber is not None and subscriber.status == SUB_CONFIRMED:
        return None
    if subscriber is not None and subscriber.status == SUB_PENDING:
        if subscriber.confirm_sent_at and subscriber.confirm_sent_at > now - timedelta(
            minutes=RESEND_MINUTES
        ):
            return None
    if subscriber is None:
        subscriber = Subscriber(email_hash=digest)
        db.add(subscriber)
    raw = generate_token(32)
    subscriber.email = email
    subscriber.status = SUB_PENDING
    subscriber.confirm_token_hash = hash_token(raw)
    subscriber.unsubscribe_token_hash = None
    subscriber.confirm_sent_at = now
    subscriber.confirmed_at = None
    subscriber.unsubscribed_at = None
    subscriber.consent_at = now
    subscriber.consent_ip = meta.get("ip")
    subscriber.consent_user_agent = (meta.get("user_agent") or "")[:300]
    subscriber.consent_policy_version = meta.get("policy_version")
    subscriber.source = meta.get("source") if meta.get("source") in SOURCES else "footer"
    subscriber.manual_consent_note = None
    db.flush()
    return raw


def confirm(db: Session, raw_token: str) -> Subscriber | None:
    """Confirm a pending signup (token valid 7 days, single use)."""
    subscriber = db.scalar(
        select(Subscriber).where(Subscriber.confirm_token_hash == hash_token(raw_token or ""))
    )
    if subscriber is None or subscriber.status != SUB_PENDING:
        return None
    sent = subscriber.confirm_sent_at or subscriber.created_at
    if sent < utcnow() - timedelta(days=CONFIRM_DAYS):
        return None
    _activate(subscriber)
    return subscriber


def find_by_unsubscribe_token(db: Session, raw_token: str) -> Subscriber | None:
    return db.scalar(
        select(Subscriber).where(
            Subscriber.unsubscribe_token_hash == hash_token(raw_token or ""),
            Subscriber.status == SUB_CONFIRMED,
        )
    )


def anonymise(subscriber: Subscriber) -> None:
    """Unsubscribe: drop the address, keep only the hash (suppression list), kill tokens."""
    subscriber.status = SUB_UNSUBSCRIBED
    subscriber.unsubscribed_at = utcnow()
    subscriber.email = None
    subscriber.confirm_token_hash = None
    subscriber.unsubscribe_token_hash = None


def unsubscribe(db: Session, raw_token: str) -> bool:
    subscriber = find_by_unsubscribe_token(db, raw_token)
    if subscriber is None:
        return False
    anonymise(subscriber)
    return True


def add_manual(db: Session, email: str, note: str) -> tuple[Subscriber | None, str | None]:
    """Owner adds a subscriber whose consent was collected outside the system."""
    email = normalize_email(email)
    if not valid_email(email):
        return None, "Upišite ispravnu email adresu."
    if len(note.strip()) < 5:
        return None, "Upišite kako je prikupljena privola (npr. papirnati obrazac u salonu, datum)."
    digest = email_hash(email)
    subscriber = db.scalar(select(Subscriber).where(Subscriber.email_hash == digest))
    if subscriber is not None and subscriber.status == SUB_CONFIRMED:
        return None, "Ova adresa je već potvrđeni pretplatnik."
    if subscriber is None:
        subscriber = Subscriber(email_hash=digest)
        db.add(subscriber)
    now = utcnow()
    subscriber.email = email
    subscriber.source = "manual"
    subscriber.manual_consent_note = note.strip()[:300]
    subscriber.consent_at = now
    subscriber.consent_ip = None
    subscriber.consent_user_agent = None
    db.flush()
    _activate(subscriber)
    return subscriber, None


def send_confirmation(email: str, raw_token: str) -> None:
    """Background task: double opt-in email."""
    from app.services.email import absolute_url, send_template

    link = absolute_url(f"/newsletter/potvrda/{raw_token}")
    send_template(
        email,
        "newsletter_confirm",
        "Potvrdite prijavu na newsletter",
        {"link": link, "days": CONFIRM_DAYS},
    )


# ---------------------------------------------------------------------------
# Campaign content
# ---------------------------------------------------------------------------
def _allowed_image(src: str) -> bool:
    base = settings.base_url
    prefixes = ["/media/", f"{base}/media/"]
    if settings.MEDIA_URL:
        prefixes.append(settings.MEDIA_URL.rstrip("/") + "/")
    return any(src.startswith(prefix) for prefix in prefixes)


_UNSAFE_STYLE = re.compile(r"url\s*\(|expression|@import|javascript:", re.I)


def _campaign_attribute_filter(tag: str, attribute: str, value: str) -> str | None:
    if tag == "img" and attribute == "src":
        return value if _allowed_image(value) else None
    if attribute == "style" and _UNSAFE_STYLE.search(value):
        return None
    return value


def clean_campaign_html(html: str) -> str:
    """Campaign allowlist: basic formatting + tables (vehicle cards) + images from own media."""
    return clean_html(
        html,
        extra_tags={"img", "table", "tbody", "tr", "td", "span", "div"},
        extra_attributes={
            "img": {"src", "alt", "width", "height", "style"},
            "table": {"width", "cellpadding", "cellspacing", "border", "role", "style"},
            "td": {"width", "align", "valign", "style"},
            "a": {"style"},
            "p": {"style"},
            "span": {"style"},
            "div": {"style"},
        },
        attribute_filter=_campaign_attribute_filter,
    )


class _TextExtractor(HTMLParser):
    BLOCKS = {"p", "div", "h1", "h2", "h3", "li", "tr", "br", "table"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "li":
            self.parts.append("\n- ")
        elif tag in self.BLOCKS:
            self.parts.append("\n")
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)

    def handle_endtag(self, tag):
        if tag == "a" and self.links:
            self.parts.append(f" ({self.links.pop()})")
        if tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html or "")
    text = "".join(parser.parts)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n\s*\n+", "\n\n", text).strip()


def absolutize(html: str) -> str:
    """Relative /media/ and / links -> absolute (emails are read outside the site)."""
    base = settings.base_url
    html = re.sub(r'(src|href)="/(?!/)', rf'\1="{base}/', html)
    return html


def vehicle_card_html(vehicle) -> str:
    """Email-safe vehicle card (table, inline styles) inserted by the campaign editor."""
    from app.services.email import render_email_fragment

    return render_email_fragment("emails/_vehicle_card.html", {"v": vehicle})


def render_campaign(campaign: Campaign, subscriber: Subscriber | None = None) -> tuple[str, str]:
    """(html, text) of a campaign; personalised when a subscriber is given (unsubscribe link)."""
    from app.services.email import absolute_url, render_email
    from app.templating import date_hr

    if subscriber is not None:
        unsubscribe_url = absolute_url(
            f"/newsletter/odjava/{unsubscribe_token(subscriber)}?potvrdi=1"
        )
        subscribed_on = date_hr(subscriber.confirmed_at or subscriber.created_at)
    else:
        unsubscribe_url = absolute_url("/newsletter/odjava/PRIMJER")
        subscribed_on = date_hr(utcnow())
    body = absolutize(campaign.body_html or "")
    context = {
        "subject": campaign.subject,
        "body_html": body,
        "body_text": html_to_text(body),
        "unsubscribe_url": unsubscribe_url,
        "subscribed_on": subscribed_on,
        "domain": settings.base_url.split("://", 1)[-1],
    }
    return render_email("newsletter_campaign", context)


def list_headers(unsubscribe_url: str) -> dict:
    return {
        "List-Unsubscribe": f"<{unsubscribe_url}>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------
def confirmed_count(db: Session) -> int:
    return (
        db.scalar(
            select(func.count(Subscriber.id)).where(
                Subscriber.status == SUB_CONFIRMED, Subscriber.email.is_not(None)
            )
        )
        or 0
    )


def send_campaign(campaign_id: int, only_failed: bool = False) -> dict:
    """Send a campaign to all confirmed subscribers in batches (own DB session).

    Idempotent: subscribers with a `sent` delivery are skipped, so a restart after a
    crash continues where it stopped. `only_failed=True` retries failed deliveries.
    """
    from app.services.email import send

    db = SessionLocal()
    result = {"sent": 0, "failed": 0, "skipped": 0}
    try:
        campaign = db.get(Campaign, campaign_id)
        if campaign is None:
            return result
        campaign.status = CAMPAIGN_SENDING
        db.commit()
        deliveries = {
            d.subscriber_id: d
            for d in db.scalars(
                select(CampaignDelivery).where(CampaignDelivery.campaign_id == campaign.id)
            )
        }
        subscribers = list(
            db.scalars(
                select(Subscriber)
                .where(Subscriber.status == SUB_CONFIRMED, Subscriber.email.is_not(None))
                .order_by(Subscriber.id)
            )
        )
        site_name = None
        for start in range(0, len(subscribers), BATCH_SIZE):
            batch = subscribers[start : start + BATCH_SIZE]
            for subscriber in batch:
                existing = deliveries.get(subscriber.id)
                if existing is not None and existing.status == DELIVERY_SENT:
                    result["skipped"] += 1
                    continue
                if only_failed and existing is None:
                    result["skipped"] += 1
                    continue
                html, text = render_campaign(campaign, subscriber)
                unsubscribe_url = (
                    f"{settings.base_url}/newsletter/odjava/{unsubscribe_token(subscriber)}"
                    "?potvrdi=1"
                )
                if site_name is None:
                    from app.services.site import get_site

                    site_name = get_site().get("newsletter_sender_name") or None
                outcome = send(
                    subscriber.email,
                    campaign.subject,
                    text,
                    html,
                    template="newsletter_campaign",
                    headers=list_headers(unsubscribe_url),
                    from_name=site_name,
                )
                status = DELIVERY_SENT if outcome.ok else DELIVERY_FAILED
                if existing is None:
                    existing = CampaignDelivery(
                        campaign_id=campaign.id, subscriber_id=subscriber.id
                    )
                    db.add(existing)
                    deliveries[subscriber.id] = existing
                existing.status = status
                existing.error = (outcome.error or "")[:500] or None
                existing.created_at = utcnow()
                result["sent" if outcome.ok else "failed"] += 1
            db.commit()
            if start + BATCH_SIZE < len(subscribers) and BATCH_PAUSE_S:
                time.sleep(BATCH_PAUSE_S)
        campaign.status = CAMPAIGN_SENT
        campaign.sent_at = campaign.sent_at or utcnow()
        campaign.recipients_count = sum(
            1 for d in deliveries.values() if d.status in (DELIVERY_SENT, DELIVERY_FAILED)
        )
        db.commit()
        log.info("Campaign %s: %s", campaign_id, result)
        return result
    except Exception:
        log.exception("Campaign %s sending failed", campaign_id)
        db.rollback()
        raise
    finally:
        db.close()


def start_sending(campaign_id: int, only_failed: bool = False) -> None:
    """Run send_campaign in its own thread (tests run it inline for determinism)."""
    if settings.APP_ENV == "test":
        send_campaign(campaign_id, only_failed)
        return
    thread = threading.Thread(
        target=send_campaign,
        args=(campaign_id, only_failed),
        daemon=True,
        name=f"campaign-{campaign_id}",
    )
    thread.start()


def delivery_stats(db: Session, campaign_id: int) -> dict:
    rows = db.execute(
        select(CampaignDelivery.status, func.count())
        .where(CampaignDelivery.campaign_id == campaign_id)
        .group_by(CampaignDelivery.status)
    ).all()
    stats = {DELIVERY_SENT: 0, DELIVERY_FAILED: 0}
    stats.update(dict(rows))
    return stats


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------
def purge_pending_subscribers(db: Session, dry_run: bool = False) -> int:
    """Unconfirmed signups older than 7 days are deleted."""
    cutoff = utcnow() - timedelta(days=CONFIRM_DAYS)
    condition = (Subscriber.status == SUB_PENDING) & (
        func.coalesce(Subscriber.confirm_sent_at, Subscriber.created_at) < cutoff
    )
    count = db.scalar(select(func.count(Subscriber.id)).where(condition)) or 0
    if count and not dry_run:
        db.execute(delete(Subscriber).where(condition))
    return count


def purge_old_unsubscribed(db: Session, dry_run: bool = False) -> int:
    """Anonymised (unsubscribed) hash-only entries are kept 3 years, then deleted."""
    cutoff = utcnow() - timedelta(days=UNSUBSCRIBED_KEEP_DAYS)
    condition = (Subscriber.status == SUB_UNSUBSCRIBED) & or_(
        Subscriber.unsubscribed_at < cutoff,
        Subscriber.unsubscribed_at.is_(None) & (Subscriber.created_at < cutoff),
    )
    count = db.scalar(select(func.count(Subscriber.id)).where(condition)) or 0
    if count and not dry_run:
        db.execute(delete(Subscriber).where(condition))
    return count
