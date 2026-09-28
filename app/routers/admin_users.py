"""Admin users (invite, edit, deactivate, reset 2FA) and the personal profile page.

Rules (spec chapter 10 + phase 2):
- only superadmin and owner manage users; salesperson gets 403
- owner cannot modify or create a superadmin
- nobody can change their own role or deactivate themselves
- at least one active superadmin must always exist
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import csrf_protect, get_current_user, require_permission
from app.models import (
    ROLE_OWNER,
    ROLE_SALESPERSON,
    ROLE_SUPERADMIN,
    ROLES,
    TOKEN_INVITE,
    User,
    UserSession,
)
from app.permissions import ROLE_LABELS
from app.security import (
    client_ip,
    decrypt_secret,
    hash_password,
    mask_ip,
    normalize_email,
    validate_password_strength,
    verify_password,
    verify_totp,
)
from app.services import audit
from app.services import auth as auth_service
from app.services.email import absolute_url, send_template
from app.templating import flash, render

router = APIRouter(prefix="/admin", dependencies=[Depends(csrf_protect)])


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------
def assignable_roles(actor: User) -> list[str]:
    if actor.role == ROLE_SUPERADMIN:
        return list(ROLES)
    return [ROLE_OWNER, ROLE_SALESPERSON]


def can_manage(actor: User, target: User) -> bool:
    """Owner cannot touch a superadmin; superadmin can manage everyone."""
    if target.role == ROLE_SUPERADMIN and actor.role != ROLE_SUPERADMIN:
        return False
    return True


def active_superadmins(db: Session) -> int:
    return (
        db.scalar(select(func.count(User.id)).where(User.role == ROLE_SUPERADMIN, User.is_active))
        or 0
    )


def _get_target(db: Session, actor: User, user_id: int) -> User:
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404)
    if not can_manage(actor, target):
        raise HTTPException(status_code=403, detail="Ne možete mijenjati ovog korisnika.")
    return target


def _send_invite(background: BackgroundTasks, db: Session, target: User, request: Request):
    raw = auth_service.create_auth_token(db, target, TOKEN_INVITE, auth_service.INVITE_HOURS)
    link = absolute_url(f"/admin/lozinka/postavi/{raw}")
    background.add_task(
        send_template,
        target.email,
        "user_invite",
        "Pozivnica u administraciju",
        {
            "name": target.name or target.email,
            "role_label": ROLE_LABELS.get(target.role, target.role),
            "link": link,
        },
    )


# ---------------------------------------------------------------------------
# Users list / create
# ---------------------------------------------------------------------------
@router.get("/korisnici")
async def users_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("users")),
):
    users = list(db.scalars(select(User).order_by(User.is_active.desc(), User.name, User.email)))
    return render(
        request,
        "admin/users/list.html",
        {"section": "korisnici", "users": users, "can_manage": can_manage},
    )


@router.get("/korisnici/novi")
async def user_new_form(request: Request, user: User = Depends(require_permission("users"))):
    return render(
        request,
        "admin/users/new.html",
        {"section": "korisnici", "roles": assignable_roles(user), "form": {}, "errors": {}},
    )


@router.post("/korisnici/novi")
async def user_new_submit(
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("users")),
):
    form = await request.form()
    data = {
        "email": normalize_email(str(form.get("email", "")))[:254],
        "name": str(form.get("name", "")).strip()[:100],
        "role": str(form.get("role", ROLE_SALESPERSON)),
    }
    errors = {}
    if "@" not in data["email"] or "." not in data["email"].split("@")[-1]:
        errors["email"] = "Upišite ispravnu email adresu."
    elif auth_service.get_user_by_email(db, data["email"]):
        errors["email"] = "Korisnik s ovom adresom već postoji."
    if len(data["name"]) < 2:
        errors["name"] = "Upišite ime i prezime."
    if data["role"] not in assignable_roles(user):
        errors["role"] = "Odaberite dopuštenu ulogu."
    if errors:
        return render(
            request,
            "admin/users/new.html",
            {
                "section": "korisnici",
                "roles": assignable_roles(user),
                "form": data,
                "errors": errors,
            },
            status_code=400,
        )
    target = User(email=data["email"], name=data["name"], role=data["role"], is_active=True)
    db.add(target)
    db.flush()
    _send_invite(background, db, target, request)
    audit.log(
        db, user.id, "user.invite", "user", target.id, {"role": target.role}, client_ip(request)
    )
    db.commit()
    flash(request, f"Pozivnica je poslana na {target.email}.", "success")
    return RedirectResponse("/admin/korisnici", status_code=303)


# ---------------------------------------------------------------------------
# Edit / actions
# ---------------------------------------------------------------------------
@router.get("/korisnici/{user_id}")
async def user_edit_form(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("users")),
):
    target = _get_target(db, user, user_id)
    return render(
        request,
        "admin/users/edit.html",
        {
            "section": "korisnici",
            "target": target,
            "roles": assignable_roles(user),
            "errors": {},
            "is_self": target.id == user.id,
        },
    )


@router.post("/korisnici/{user_id}")
async def user_edit_submit(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("users")),
):
    target = _get_target(db, user, user_id)
    form = await request.form()
    is_self = target.id == user.id
    name = str(form.get("name", "")).strip()[:100]
    role = str(form.get("role", target.role))
    errors = {}
    if len(name) < 2:
        errors["name"] = "Upišite ime i prezime."
    if not is_self and role not in assignable_roles(user):
        errors["role"] = "Odaberite dopuštenu ulogu."
    if (
        not is_self
        and target.role == ROLE_SUPERADMIN
        and role != ROLE_SUPERADMIN
        and target.is_active
        and active_superadmins(db) <= 1
    ):
        errors["role"] = "Mora postojati barem jedan aktivni superadmin."
    if errors:
        return render(
            request,
            "admin/users/edit.html",
            {
                "section": "korisnici",
                "target": target,
                "roles": assignable_roles(user),
                "errors": errors,
                "is_self": is_self,
            },
            status_code=400,
        )
    changed = []
    if name != target.name:
        target.name = name
        changed.append("name")
    if not is_self and role != target.role:
        target.role = role
        changed.append("role")
    if changed:
        audit.log(
            db, user.id, "user.update", "user", target.id, {"fields": changed}, client_ip(request)
        )
    db.commit()
    flash(request, "Korisnik je spremljen.", "success")
    return RedirectResponse(f"/admin/korisnici/{target.id}", status_code=303)


@router.post("/korisnici/{user_id}/deaktiviraj")
async def user_deactivate(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("users")),
):
    target = _get_target(db, user, user_id)
    if target.id == user.id:
        flash(request, "Ne možete deaktivirati vlastiti račun.", "error")
    elif target.role == ROLE_SUPERADMIN and active_superadmins(db) <= 1:
        flash(request, "Mora postojati barem jedan aktivni superadmin.", "error")
    else:
        target.is_active = False
        count = auth_service.delete_user_sessions(db, target.id)
        audit.log(
            db,
            user.id,
            "user.deactivate",
            "user",
            target.id,
            {"sessions": count},
            client_ip(request),
        )
        db.commit()
        flash(request, "Korisnik je deaktiviran i odjavljen sa svih uređaja.", "success")
    return RedirectResponse(f"/admin/korisnici/{target.id}", status_code=303)


@router.post("/korisnici/{user_id}/aktiviraj")
async def user_activate(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("users")),
):
    target = _get_target(db, user, user_id)
    target.is_active = True
    auth_service.reset_failures(target)
    audit.log(
        db, user.id, "user.update", "user", target.id, {"fields": ["is_active"]}, client_ip(request)
    )
    db.commit()
    flash(request, "Korisnik je ponovno aktivan.", "success")
    return RedirectResponse(f"/admin/korisnici/{target.id}", status_code=303)


@router.post("/korisnici/{user_id}/reset-2fa")
async def user_reset_2fa(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("users")),
):
    target = _get_target(db, user, user_id)
    if target.id == user.id:
        flash(request, "Vlastitu 2FA ponovno postavljate u profilu.", "info")
        return RedirectResponse("/admin/profil", status_code=303)
    target.totp_enabled = False
    target.totp_secret = None
    target.totp_last_step = None
    target.recovery_codes = []
    count = auth_service.delete_user_sessions(db, target.id)
    audit.log(
        db, user.id, "user.2fa_reset", "user", target.id, {"sessions": count}, client_ip(request)
    )
    db.commit()
    flash(
        request,
        "2FA je poništena. Korisnik je odjavljen i pri sljedećoj prijavi "
        "mora ponovno postaviti 2FA.",
        "success",
    )
    return RedirectResponse(f"/admin/korisnici/{target.id}", status_code=303)


@router.post("/korisnici/{user_id}/pozivnica")
async def user_resend_invite(
    request: Request,
    user_id: int,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("users")),
):
    target = _get_target(db, user, user_id)
    if target.password_hash:
        flash(request, "Korisnik je već postavio lozinku.", "info")
    else:
        _send_invite(background, db, target, request)
        audit.log(
            db, user.id, "user.invite", "user", target.id, {"resend": True}, client_ip(request)
        )
        db.commit()
        flash(request, f"Pozivnica je ponovno poslana na {target.email}.", "success")
    return RedirectResponse(f"/admin/korisnici/{target.id}", status_code=303)


# ---------------------------------------------------------------------------
# Profile (every logged-in user)
# ---------------------------------------------------------------------------
def _profile_context(request: Request, db: Session, user: User, **extra) -> dict:
    sessions = list(
        db.scalars(
            select(UserSession)
            .where(UserSession.user_id == user.id)
            .order_by(UserSession.last_seen_at.desc())
        )
    )
    context = {
        "section": "profil",
        "sessions": sessions,
        "current_session_id": getattr(request.state, "session_id", None),
        "describe_ua": auth_service.describe_user_agent,
        "mask_ip": mask_ip,
        "recovery_left": len(user.recovery_codes or []),
        "errors": {},
    }
    context.update(extra)
    return context


@router.get("/profil")
async def profile(
    request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    return render(request, "admin/users/profile.html", _profile_context(request, db, user))


@router.post("/profil/lozinka")
async def profile_password(
    request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    form = await request.form()
    current = str(form.get("current_password", ""))
    new = str(form.get("new_password", ""))
    confirm = str(form.get("new_password_confirm", ""))
    errors = {}
    if not verify_password(user.password_hash, current):
        errors["current_password"] = "Trenutna lozinka nije ispravna."
    else:
        strength = validate_password_strength(new)
        if strength:
            errors["new_password"] = strength
        elif new != confirm:
            errors["new_password_confirm"] = "Lozinke se ne podudaraju."
        elif new == current:
            errors["new_password"] = "Nova lozinka mora biti drugačija od trenutne."
    if errors:
        context = _profile_context(request, db, user, errors=errors)
        return render(request, "admin/users/profile.html", context, status_code=400)
    user.password_hash = hash_password(new)
    count = auth_service.delete_user_sessions(db, user.id, request.state.session_id)
    audit.log(
        db,
        user.id,
        "user.password_change",
        "user",
        user.id,
        {"other_sessions_closed": count},
        client_ip(request),
    )
    db.commit()
    flash(request, "Lozinka je promijenjena. Ostali uređaji su odjavljeni.", "success")
    return RedirectResponse("/admin/profil", status_code=303)


@router.post("/profil/2fa")
async def profile_reset_2fa(
    request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    """Re-setup own 2FA: requires the current TOTP code, then the setup screen."""
    form = await request.form()
    secret = decrypt_secret(user.totp_secret)
    step = verify_totp(secret, str(form.get("code", "")), user.totp_last_step) if secret else None
    if step is None:
        context = _profile_context(
            request, db, user, errors={"code": "Kod nije ispravan. Upišite trenutni kod."}
        )
        return render(request, "admin/users/profile.html", context, status_code=400)
    user.totp_enabled = False
    user.totp_secret = None
    user.totp_last_step = step
    user.recovery_codes = []
    audit.log(db, user.id, "user.2fa_reset", "user", user.id, {"self": True}, client_ip(request))
    db.commit()
    return RedirectResponse("/admin/2fa/postavljanje", status_code=303)
