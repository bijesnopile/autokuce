"""FastAPI dependencies: current admin user, role/permission checks, CSRF.

Usage in admin routers:

    router = APIRouter(prefix="/admin/...", dependencies=[Depends(csrf_protect)])

    @router.get("/x")
    async def x(request: Request, user: User = Depends(require_permission("vehicles"))):
        ...
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import FeatureLocked, LoginRequired, TwoFactorSetupRequired
from app.models import User
from app.permissions import can
from app.security import verify_csrf
from app.services.auth import SESSION_COOKIE, load_session


def _next_url(request: Request) -> str:
    url = request.url.path
    if request.url.query and request.method == "GET":
        url += "?" + request.url.query
    return url if request.method == "GET" else "/admin"


async def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Return the logged-in admin user or redirect to the login page."""
    session = load_session(db, request.cookies.get(SESSION_COOKIE))
    if session is None:
        raise LoginRequired(_next_url(request))
    user = session.user
    if not user.totp_enabled:
        # 2FA is mandatory: a session without active 2FA may only finish the setup.
        raise TwoFactorSetupRequired()
    request.state.user = user
    request.state.session_id = session.id
    request.state.nav_counts = _nav_counts(db)
    return user


def _nav_counts(db: Session) -> dict:
    """Badges in the admin sidebar (e.g. number of new inquiries)."""
    from sqlalchemy import func, select

    from app.models import INQUIRY_NEW, Inquiry

    return {"upiti": db.scalar(select(func.count(Inquiry.id)).where(Inquiry.status == INQUIRY_NEW))}


def require_permission(permission: str):
    """Dependency factory: logged-in user with `permission` (see app/permissions.py), else 403."""

    async def _dependency(user: User = Depends(get_current_user)) -> User:
        if not can(user, permission):
            raise HTTPException(status_code=403, detail="Nemate ovlasti za ovu radnju.")
        return user

    return _dependency


def require_feature(code: str):
    """Dependency factory: the active plan must include `code` (app/plans.py).

    Admin routes: FeatureLocked → 403 page in the admin design ("Dostupno u paketu Standard").
    Public routes should use `public_feature(code)` (404, the feature simply does not exist).
    """

    async def _dependency() -> None:
        from app.plans import has_feature

        if not has_feature(code):
            raise FeatureLocked(code)

    return _dependency


def public_feature(code: str):
    """Public routes: 404 when the feature is not in the active plan."""

    async def _dependency() -> None:
        from app.plans import has_feature

        if not has_feature(code):
            raise HTTPException(status_code=404)

    return _dependency


def require_role(*roles: str):
    """Dependency factory: logged-in user whose role is one of `roles`, else 403."""

    async def _dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Nemate ovlasti za ovu radnju.")
        return user

    return _dependency


async def csrf_protect(request: Request) -> None:
    """Router-level dependency: every state-changing request must carry a CSRF token."""
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        await verify_csrf(request)
