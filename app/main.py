"""Application factory: middleware, routers, error pages, startup tasks."""

from __future__ import annotations

import ipaddress
import logging
import traceback
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import APP_DIR, get_settings
from app.errors import FeatureLocked, LoginRequired, TwoFactorSetupRequired
from app.templating import render

log = logging.getLogger("app")


# ---------------------------------------------------------------------------
# Middleware (pure ASGI — no BaseHTTPMiddleware, so BackgroundTasks behave)
# ---------------------------------------------------------------------------
def _valid_ip(value: str) -> str | None:
    value = value.strip()
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


class RealIPMiddleware:
    """Replace the client address with the real visitor IP behind Cloudflare/Caddy.

    Only active when TRUST_PROXY=true — otherwise the headers could be spoofed.
    Order: CF-Connecting-IP, then the first address in X-Forwarded-For.
    """

    def __init__(self, app: ASGIApp, trust_proxy: bool) -> None:
        self.app = app
        self.trust_proxy = trust_proxy

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self.trust_proxy and scope["type"] == "http":
            headers = {
                k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]
            }
            real_ip = None
            if "cf-connecting-ip" in headers:
                real_ip = _valid_ip(headers["cf-connecting-ip"])
            if not real_ip and "x-forwarded-for" in headers:
                real_ip = _valid_ip(headers["x-forwarded-for"].split(",")[0])
            if real_ip:
                port = scope["client"][1] if scope.get("client") else 0
                scope["client"] = (real_ip, port)
        await self.app(scope, receive, send)


def build_csp(settings) -> str:
    """Content-Security-Policy per spec chapter 13; external hosts only when configured."""

    def origin(url: str) -> str:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""

    script_src = ["'self'"]
    frame_src = ["https://www.youtube-nocookie.com"]
    img_src = ["'self'", "data:"]
    connect_src = ["'self'"]
    if settings.TURNSTILE_SITE_KEY:
        script_src.append("https://challenges.cloudflare.com")
        frame_src.insert(0, "https://challenges.cloudflare.com")
    if settings.umami_enabled and origin(settings.UMAMI_SCRIPT_URL):
        script_src.append(origin(settings.UMAMI_SCRIPT_URL))
        connect_src.append(origin(settings.UMAMI_SCRIPT_URL))
    if settings.MEDIA_URL and origin(settings.MEDIA_URL):
        img_src.append(origin(settings.MEDIA_URL))
    elif settings.STORAGE_BACKEND == "s3" and origin(settings.S3_ENDPOINT):
        img_src.append(origin(settings.S3_ENDPOINT))
    return "; ".join(
        [
            "default-src 'self'",
            "script-src " + " ".join(script_src),
            "style-src 'self' 'unsafe-inline'",
            "img-src " + " ".join(img_src),
            "font-src 'self'",
            "connect-src " + " ".join(connect_src),
            "frame-src " + " ".join(frame_src),
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "object-src 'none'",
        ]
    )


class SecurityHeadersMiddleware:
    """Adds security and caching headers to every HTTP response."""

    def __init__(self, app: ASGIApp, settings) -> None:
        self.app = app
        self.csp = build_csp(settings)
        self.hsts = settings.HTTPS

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope.get("path", "")

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("Content-Security-Policy", self.csp)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("X-Frame-Options", "DENY")
                headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
                headers.setdefault(
                    "Permissions-Policy",
                    "camera=(), microphone=(), geolocation=(), payment=(), usb=(), "
                    "browsing-topics=()",
                )
                if self.hsts:
                    headers.setdefault(
                        "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
                    )
                if path.startswith("/admin"):
                    headers.setdefault("X-Robots-Tag", "noindex, nofollow")
                    headers.setdefault("Cache-Control", "no-store")
                elif path.startswith(("/static/", "/media/")) and message["status"] == 200:
                    headers["Cache-Control"] = "public, max-age=31536000, immutable"
            await send(message)

        await self.app(scope, receive, send_wrapper)


class AdminIPAllowlistMiddleware:
    """Optional: restrict /admin/* to ADMIN_IP_ALLOWLIST (IPs or CIDRs, comma separated)."""

    def __init__(self, app: ASGIApp, allowlist: str) -> None:
        self.app = app
        self.networks = []
        for item in [x.strip() for x in allowlist.split(",") if x.strip()]:
            try:
                self.networks.append(ipaddress.ip_network(item, strict=False))
            except ValueError:
                log.error("Invalid ADMIN_IP_ALLOWLIST entry: %s", item)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self.networks and scope["type"] == "http" and scope["path"].startswith("/admin"):
            host = scope["client"][0] if scope.get("client") else ""
            try:
                address = ipaddress.ip_address(host)
                allowed = any(address in net for net in self.networks)
            except ValueError:
                allowed = False
            if not allowed:
                response = PlainTextResponse("403 — pristup nije dopušten.", status_code=403)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


class ErrorPageMiddleware:
    """Render the designed 500 page for unhandled exceptions (inside the header middleware,
    so error pages also get security headers). Stack traces only in development."""

    def __init__(self, app: ASGIApp, debug: bool) -> None:
        self.app = app
        self.debug = debug

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            log.exception("Unhandled error on %s %s", scope.get("method"), scope.get("path"))
            if started:
                raise
            request = Request(scope)
            detail = traceback.format_exc() if self.debug else None
            try:
                response = render(request, "public/500.html", {"detail": detail}, status_code=500)
            except Exception:  # template itself broken -> plain fallback
                response = HTMLResponse("<h1>500 — Došlo je do greške</h1>", status_code=500)
            await response(scope, receive, send)


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------
def _wants_json(request: Request) -> bool:
    return request.url.path.startswith("/api/") or "application/json" in request.headers.get(
        "accept", ""
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    headers = dict(exc.headers or {})
    if _wants_json(request):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=headers)
    is_admin = request.url.path.startswith("/admin")
    if exc.status_code == 404:
        headers["X-Robots-Tag"] = "noindex"
        return render(request, "public/404.html", status_code=404, headers=headers)
    if exc.status_code == 403 and is_admin and getattr(request.state, "user", None):
        return render(request, "admin/403.html", {"detail": exc.detail}, 403, headers)
    headers.setdefault("X-Robots-Tag", "noindex")
    message = exc.detail if isinstance(exc.detail, str) else None
    return render(
        request,
        "public/error.html",
        {"status_code": exc.status_code, "message": message},
        status_code=exc.status_code,
        headers=headers,
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    if _wants_json(request):
        return JSONResponse({"detail": "Neispravan zahtjev."}, status_code=422)
    return render(
        request,
        "public/error.html",
        {"status_code": 400, "message": "Neispravan zahtjev. Provjerite unesene podatke."},
        status_code=400,
    )


async def feature_locked_handler(request: Request, exc: FeatureLocked):
    """Locked feature: admin page with the plan that unlocks it; elsewhere a plain 404."""
    from app.plans import FEATURES, PLANS, required_plan

    if not request.url.path.startswith("/admin") or not getattr(request.state, "user", None):
        return render(request, "public/404.html", status_code=404)
    feature = FEATURES.get(exc.code, {"label": exc.code, "description": ""})
    plan = PLANS[required_plan(exc.code)] if exc.code in FEATURES else PLANS["standard"]
    return render(
        request,
        "admin/plan_locked.html",
        {"feature": feature, "plan": plan},
        status_code=403,
    )


async def twofa_setup_handler(request: Request, exc: TwoFactorSetupRequired):
    return RedirectResponse("/admin/2fa/postavljanje", status_code=303)


async def login_required_handler(request: Request, exc: LoginRequired):
    from app.templating import query_url

    return RedirectResponse(query_url("/admin/prijava", {"next": exc.next_url}), status_code=303)


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    for folder in (settings.media_dir, settings.outbox_dir, settings.backups_dir):
        folder.mkdir(parents=True, exist_ok=True)
    if not settings.turnstile_enabled:
        log.warning("Turnstile isključen (TURNSTILE_SITE_KEY/SECRET_KEY nisu postavljeni).")
    if settings.MAINTENANCE_IN_APP and settings.APP_ENV != "test":
        from app.services.maintenance import start_background_thread

        start_background_thread()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    settings.validate_for_startup()
    logging.basicConfig(
        level=settings.LOG_LEVEL,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    app = FastAPI(
        title="Autokuća",
        docs_url=None,  # no public API docs
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    # Middleware: the LAST added is the OUTERMOST.
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="st",  # signed client state: CSRF token, flash messages
        max_age=None,  # browser-session cookie
        same_site="lax",
        https_only=settings.HTTPS,
    )
    app.add_middleware(AdminIPAllowlistMiddleware, allowlist=settings.ADMIN_IP_ALLOWLIST)
    app.add_middleware(ErrorPageMiddleware, debug=settings.is_development)
    app.add_middleware(SecurityHeadersMiddleware, settings=settings)
    app.add_middleware(RealIPMiddleware, trust_proxy=settings.TRUST_PROXY)

    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(LoginRequired, login_required_handler)
    app.add_exception_handler(TwoFactorSetupRequired, twofa_setup_handler)
    app.add_exception_handler(FeatureLocked, feature_locked_handler)

    # Static files. Per-client overrides/static is mounted first under /static/custom.
    # In Docker the overrides volume is read-only: never fail if the folder cannot be created.
    overrides_static = settings.OVERRIDES_DIR / "static"
    try:
        overrides_static.mkdir(parents=True, exist_ok=True)
    except OSError:
        log.info("overrides/static ne postoji i ne može se kreirati — /static/custom isključen")
    if overrides_static.is_dir():
        app.mount("/static/custom", StaticFiles(directory=overrides_static), name="custom_static")
    app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")

    from app.routers import (
        admin_audit,
        admin_auth,
        admin_catalog,
        admin_dashboard,
        admin_documents,
        admin_feed,
        admin_inquiries,
        admin_newsletter,
        admin_pages,
        admin_privacy,
        admin_settings,
        admin_users,
        admin_vehicles,
        public,
        seo,
    )

    app.include_router(public.router)
    app.include_router(public.unsubscribe_router)  # one-click unsubscribe (no CSRF by design)
    app.include_router(seo.router)
    app.include_router(admin_feed.public_router)  # /feed/{portal}.{fmt}?token=
    app.include_router(admin_auth.router)
    app.include_router(admin_users.router)
    app.include_router(admin_audit.router)
    app.include_router(admin_catalog.router)
    app.include_router(admin_vehicles.router)
    app.include_router(admin_inquiries.router)
    app.include_router(admin_newsletter.router)
    app.include_router(admin_settings.router)
    app.include_router(admin_pages.router)
    app.include_router(admin_privacy.router)
    app.include_router(admin_feed.router)
    app.include_router(admin_documents.router)
    # Must stay LAST: contains the catch-all "under construction" route.
    app.include_router(admin_dashboard.router)
    return app


app = create_app()
