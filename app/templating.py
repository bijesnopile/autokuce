"""Jinja2 environment, filters, globals and the `render()` helper.

Template lookup order (per-client customisation, spec chapter 17):
    1. overrides/templates/   (mounted volume per client)
    2. app/templates/

Every template receives: `request`, `site` (company settings), `_` (i18n),
`config` (safe config values), `csrf_token()`, `flash_messages()`,
`current_user`, `static_url()`, `now()`.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from urllib.parse import urlencode

from fastapi import Request
from fastapi.responses import HTMLResponse
from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

from app import plans as _plans
from app.config import APP_DIR, get_settings
from app.i18n import gettext
from app.security import form_timestamp, get_csrf_token
from app.services.site import get_site
from app.utils import LOCAL_TZ

settings = get_settings()
STATIC_DIR = APP_DIR / "static"
OVERRIDE_STATIC_DIR = settings.OVERRIDES_DIR / "static"

env = Environment(
    loader=ChoiceLoader(
        [
            FileSystemLoader(str(settings.OVERRIDES_DIR / "templates")),
            FileSystemLoader(str(APP_DIR / "templates")),
        ]
    ),
    autoescape=select_autoescape(enabled_extensions=("html", "xml"), default_for_string=True),
    trim_blocks=True,
    lstrip_blocks=True,
)


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
def format_number(value, decimals: int = 0) -> str:
    """Croatian number format: 12.500 / 5,6."""
    if value is None or value == "":
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    text = f"{number:,.{decimals}f}"  # 12,500.00
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def money(value) -> str:
    if value is None or value == "":
        return ""
    return f"{format_number(value)} €"


def km(value) -> str:
    if value is None or value == "":
        return ""
    return f"{format_number(value)} km"


def to_local(value: datetime) -> datetime:
    """Naive UTC (DB) -> Europe/Zagreb aware datetime."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(LOCAL_TZ)


def date_hr(value) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        value = to_local(value)
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value[:10])
        except ValueError:
            return value
    return value.strftime("%d.%m.%Y.")


def datetime_hr(value) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        return to_local(value).strftime("%d.%m.%Y. %H:%M")
    return date_hr(value)


def month_year(value) -> str:
    if not value:
        return ""
    return value.strftime("%m/%Y")


def nl2br(value) -> Markup:
    if value is None:
        return Markup("")
    return Markup("<br>\n").join(escape(value).split("\n"))


def media_url(image, size: int = 1000) -> str:
    """URL of an image variant. `image` is a VehicleImage or a base file key."""
    from app.services.storage import get_storage

    if image is None:
        return ""
    key = image if isinstance(image, str) else image.file_key
    return get_storage().url(f"{key}_{size}.webp")


def srcset(image, sizes=(400, 1000, 1600)) -> str:
    return ", ".join(f"{media_url(image, s)} {s}w" for s in sizes)


env.filters.update(
    {
        "number": format_number,
        "money": money,
        "km": km,
        "date_hr": date_hr,
        "datetime_hr": datetime_hr,
        "month_year": month_year,
        "nl2br": nl2br,
        "media_url": media_url,
        "srcset": srcset,
    }
)


# ---------------------------------------------------------------------------
# Static files: cache-busting version + optional per-client custom.css
# ---------------------------------------------------------------------------
_static_cache: dict = {}


def _compute_static_info() -> dict:
    digest = hashlib.sha256()
    for folder in (STATIC_DIR, OVERRIDE_STATIC_DIR):
        if not folder.exists():
            continue
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                stat = path.stat()
                digest.update(f"{path.name}:{stat.st_size}:{stat.st_mtime_ns}".encode())
    return {
        "version": digest.hexdigest()[:10],
        "has_custom_css": (OVERRIDE_STATIC_DIR / "custom.css").is_file(),
    }


def static_info() -> dict:
    """Recomputed on every call in development (CSS edits), once otherwise."""
    if settings.is_development or not _static_cache:
        _static_cache.update(_compute_static_info())
    return _static_cache


def static_url(path: str) -> str:
    return f"/static/{path}?v={static_info()['version']}"


def custom_css_url() -> str | None:
    info = static_info()
    return f"/static/custom/custom.css?v={info['version']}" if info["has_custom_css"] else None


def now_local() -> datetime:
    return datetime.now(LOCAL_TZ)


def safe_config() -> dict:
    """Only harmless configuration values are exposed to templates."""
    return {
        "BASE_URL": settings.base_url,
        "LANGUAGE": settings.LANGUAGE,
        "TURNSTILE_SITE_KEY": settings.TURNSTILE_SITE_KEY if settings.turnstile_enabled else "",
        "UMAMI_SCRIPT_URL": settings.UMAMI_SCRIPT_URL if settings.umami_enabled else "",
        "UMAMI_WEBSITE_ID": settings.UMAMI_WEBSITE_ID if settings.umami_enabled else "",
        "APP_ENV": settings.APP_ENV,
        "MAX_UPLOAD_MB": settings.MAX_UPLOAD_MB,
        "MAX_IMAGES_PER_VEHICLE": settings.MAX_IMAGES_PER_VEHICLE,
    }


env.globals.update(
    {
        "_": gettext,
        "config": safe_config(),
        "static_url": static_url,
        "custom_css_url": custom_css_url,
        "has_feature": _plans.has_feature,
        "lock_badge": _plans.lock_badge,
        "current_plan": _plans.current_plan,
        "plan_label": _plans.plan_label,
        "now": now_local,
        "form_ts": form_timestamp,
    }
)


# ---------------------------------------------------------------------------
# Flash messages (stored in the signed client-state cookie)
# ---------------------------------------------------------------------------
def flash(request: Request, message: str, category: str = "success") -> None:
    """Queue a message for the next rendered page. category: success|error|info|warning."""
    messages = list(request.session.get("flash", []))
    messages.append({"message": message, "category": category})
    request.session["flash"] = messages[-5:]


def pop_flashes(request: Request) -> list[dict]:
    messages = request.session.pop("flash", [])
    return messages or []


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------
def query_url(path: str, params: dict) -> str:
    """Build `path?query` dropping empty values (clean, shareable URLs)."""
    clean = {k: v for k, v in params.items() if v not in (None, "", [], False)}
    return f"{path}?{urlencode(clean, doseq=True)}" if clean else path


env.globals["query_url"] = query_url


def _financing_from(vehicle):
    from app.services.financing import card_from

    return card_from(vehicle)


def _eur2(value) -> str:
    from app.services.financing import format_eur

    return format_eur(float(value or 0))


env.globals["financing_from"] = _financing_from


def _card_badges(vehicle):
    from app.services.pricing import card_badges

    return card_badges(vehicle)


env.globals["card_badges"] = _card_badges


def _pwa_short_name(company):
    from app.services.pwa import short_name

    return short_name(company)


env.globals["pwa_short_name"] = _pwa_short_name
env.filters["eur2"] = _eur2

# Role helpers for admin templates + inline SVG icon paths.
from app.icons import ICONS  # noqa: E402
from app.permissions import ROLE_LABELS, can, nav_for  # noqa: E402

env.globals.update({"can": can, "nav_for": nav_for, "ROLE_LABELS": ROLE_LABELS, "ICONS": ICONS})


def css_color(value, default: str = "#1e40af") -> str:
    """Only allow #rrggbb colours inside the inline <style> block (no CSS injection)."""
    value = str(value or "").strip()
    if (
        len(value) == 7
        and value[0] == "#"
        and all(c in "0123456789abcdefABCDEF" for c in value[1:])
    ):
        return value
    return default


env.filters["css_color"] = css_color


def jsonld(data) -> Markup:
    """Serialize JSON-LD for embedding in HTML (a data block, never executed; no `</script>`)."""
    import json

    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    text = text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return Markup(f'<script type="application/ld+json">{text}</script>')


env.filters["jsonld"] = jsonld

# Vehicle schema helpers for templates (labels of stored codes, type info).
from app import vehicle_schema as _vehicle_schema  # noqa: E402

env.globals.update(
    {
        "vlabel": _vehicle_schema.label,
        "type_label": _vehicle_schema.type_label,
        "status_label": _vehicle_schema.status_label,
        "vehicle_types": _vehicle_schema.VEHICLE_TYPES,
    }
)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def render(
    request: Request,
    template_name: str,
    context: dict | None = None,
    status_code: int = 200,
    headers: dict | None = None,
) -> HTMLResponse:
    ctx = {
        "request": request,
        "site": get_site(),
        "csrf_token": lambda: get_csrf_token(request),
        "flash_messages": lambda: pop_flashes(request),
        "current_user": getattr(request.state, "user", None),
        "nav_counts": getattr(request.state, "nav_counts", {}),
        "current_path": request.url.path,
    }
    if context:
        ctx.update(context)
    html = env.get_template(template_name).render(ctx)
    return HTMLResponse(html, status_code=status_code, headers=headers)


def render_string(template_name: str, context: dict | None = None) -> str:
    """Render a template outside of a request (emails)."""
    ctx = {"site": get_site()}
    if context:
        ctx.update(context)
    return env.get_template(template_name).render(ctx)
