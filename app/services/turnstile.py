"""Cloudflare Turnstile verification (optional anti-spam for public forms).

Disabled (always passes) when TURNSTILE_SECRET_KEY is not set — a warning is
logged once at startup (app/main.py). The widget script is only rendered when
TURNSTILE_SITE_KEY is set (templates, CSP).
"""

from __future__ import annotations

import logging

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)
settings = get_settings()

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TOKEN_FIELD = "cf-turnstile-response"


def verify_turnstile(token: str | None, ip: str | None) -> bool:
    """Return True if the Turnstile token is valid (or Turnstile is disabled).

    Network errors/timeouts fail OPEN (the form still has honeypot, timing check and rate
    limits) so that a Cloudflare outage does not block customer inquiries; an explicit
    "success: false" from Cloudflare fails closed.
    """
    if not settings.TURNSTILE_SECRET_KEY:
        return True
    if not token:
        return False
    data = {"secret": settings.TURNSTILE_SECRET_KEY, "response": token}
    if ip:
        data["remoteip"] = ip
    try:
        response = httpx.post(VERIFY_URL, data=data, timeout=5)
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        log.error("Turnstile verification unavailable — accepting the form (fail-open)")
        return True
    return bool(payload.get("success"))
