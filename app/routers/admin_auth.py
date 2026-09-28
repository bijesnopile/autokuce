"""Admin login, mandatory 2FA (TOTP), logout, password reset and invitations.

Routes (all POSTs require CSRF):
    GET/POST /admin/prijava                 email + password
    GET/POST /admin/prijava/2fa             TOTP or recovery code
    GET/POST /admin/2fa/postavljanje        forced 2FA setup (QR + manual key + confirm)
    POST     /admin/odjava                  logout (this device)
    POST     /admin/odjava-svugdje          logout from all devices
    GET/POST /admin/lozinka/zaboravljena    request reset email (always the same message)
    GET/POST /admin/lozinka/nova/{token}    set new password (reset, 1 h)
    GET/POST /admin/lozinka/postavi/{token} set first password (invitation, 48 h)
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db, utcnow
from app.deps import csrf_protect
from app.models import TOKEN_INVITE, TOKEN_RESET, User
from app.security import (
    burn_password_check,
    check_rate_limit,
    client_ip,
    decrypt_secret,
    email_hash,
    encrypt_secret,
    generate_recovery_codes,
    hash_password,
    hash_recovery_code,
    match_recovery_code,
    new_totp_secret,
    normalize_email,
    password_needs_rehash,
    rotate_csrf_token,
    totp_uri,
    validate_password_strength,
    verify_password,
    verify_totp,
)
from app.services import audit
from app.services import auth as auth_service
from app.services.email import absolute_url, send_template
from app.services.site import get_site
from app.templating import flash, render

router = APIRouter(prefix="/admin", dependencies=[Depends(csrf_protect)])
settings = get_settings()

# Small fixed delay on failed login attempts (slows brute force; disabled in tests).
FAIL_DELAY_S = 0.0 if settings.APP_ENV == "test" else 0.6
LOGIN_ERROR = (
    "Prijava nije uspjela. Provjerite email i lozinku. Nakon 5 neuspjelih pokušaja "
    "račun se zaključava na 15 minuta."
)
CODE_ERROR = "Kod nije ispravan ili je istekao. Pokušajte ponovno."


def _current_session_user(request: Request, db: Session) -> User | None:
    session = auth_service.load_session(db, request.cookies.get(auth_service.SESSION_COOKIE))
    return session.user if session else None


async def _fail_delay() -> None:
    if FAIL_DELAY_S:
        await asyncio.sleep(FAIL_DELAY_S)


def _finish_login(request: Request, db: Session, user: User, next_url: str, response):
    """Create the server-side session after successful 2FA and attach cookies."""
    token = auth_service.create_session(db, user, request)
    auth_service.reset_failures(user)
    user.last_login_at = utcnow()
    audit.log(db, user.id, "user.login", "user", user.id, ip=client_ip(request))
    db.commit()
    rotate_csrf_token(request)  # new CSRF token bound to the new session
    auth_service.set_session_cookie(response, token)
    auth_service.clear_pending_cookie(response)
    return response


# ---------------------------------------------------------------------------
# Login: step 1 (password)
# ---------------------------------------------------------------------------
@router.get("/prijava")
async def login_form(request: Request, db: Session = Depends(get_db)):
    if _current_session_user(request, db):
        return RedirectResponse("/admin", status_code=303)
    next_url = auth_service.safe_next(request.query_params.get("next"))
    return render(request, "admin/auth/login.html", {"next": next_url, "email": ""})


@router.post("/prijava")
async def login_submit(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    email = normalize_email(str(form.get("email", "")))[:254]
    password = str(form.get("password", ""))[:256]
    next_url = auth_service.safe_next(str(form.get("next", "")))
    context = {"next": next_url, "email": email}

    if not check_rate_limit(request, "login", 10, 60):
        context["error"] = "Previše pokušaja prijave. Pričekajte minutu pa pokušajte ponovno."
        return render(request, "admin/auth/login.html", context, status_code=429)

    user = auth_service.get_user_by_email(db, email) if email else None
    if user is None or not user.is_active or not user.password_hash:
        burn_password_check(password)  # same timing as a real check
        audit.log(
            db,
            None,
            "user.login_failed",
            details={"email_hash": email_hash(email)},
            ip=client_ip(request),
        )
        db.commit()
        await _fail_delay()
        context["error"] = LOGIN_ERROR
        return render(request, "admin/auth/login.html", context, status_code=400)

    if auth_service.is_locked(user) or not verify_password(user.password_hash, password):
        if not auth_service.is_locked(user):
            auth_service.register_failure(user)
        audit.log(
            db,
            user.id,
            "user.login_failed",
            "user",
            user.id,
            details={"email_hash": email_hash(email)},
            ip=client_ip(request),
        )
        db.commit()
        await _fail_delay()
        context["error"] = LOGIN_ERROR
        return render(request, "admin/auth/login.html", context, status_code=400)

    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        db.commit()

    target = "/admin/prijava/2fa" if user.totp_enabled else "/admin/2fa/postavljanje"
    response = RedirectResponse(target, status_code=303)
    auth_service.set_pending_cookie(response, user.id, next_url)
    return response


# ---------------------------------------------------------------------------
# Login: step 2 (TOTP or recovery code)
# ---------------------------------------------------------------------------
def _pending_user(request: Request, db: Session) -> tuple[User | None, str]:
    pending = auth_service.read_pending(request)
    if not pending:
        return None, "/admin"
    user = db.get(User, pending["uid"])
    if user is None or not user.is_active:
        return None, "/admin"
    return user, auth_service.safe_next(pending.get("next"))


def _expired_login(request: Request) -> RedirectResponse:
    flash(request, "Prijava je istekla. Prijavite se ponovno.", "warning")
    response = RedirectResponse("/admin/prijava", status_code=303)
    auth_service.clear_pending_cookie(response)
    return response


@router.get("/prijava/2fa")
async def twofa_form(request: Request, db: Session = Depends(get_db)):
    user, _next = _pending_user(request, db)
    if user is None:
        return _expired_login(request)
    if not user.totp_enabled:
        return RedirectResponse("/admin/2fa/postavljanje", status_code=303)
    return render(request, "admin/auth/twofa.html", {})


@router.post("/prijava/2fa")
async def twofa_submit(request: Request, db: Session = Depends(get_db)):
    user, next_url = _pending_user(request, db)
    if user is None:
        return _expired_login(request)
    if not user.totp_enabled:
        return RedirectResponse("/admin/2fa/postavljanje", status_code=303)
    if not check_rate_limit(request, "login", 10, 60):
        return render(
            request,
            "admin/auth/twofa.html",
            {"error": "Previše pokušaja. Pričekajte minutu pa pokušajte ponovno."},
            status_code=429,
        )

    form = await request.form()
    code = str(form.get("code", "")).strip()[:40]
    ok = False
    used_recovery = False
    if not auth_service.is_locked(user):
        secret = decrypt_secret(user.totp_secret)
        step = verify_totp(secret, code, user.totp_last_step) if secret else None
        if step is not None:
            user.totp_last_step = step
            ok = True
        elif len(code) > 6:
            index = match_recovery_code(user.recovery_codes or [], code)
            if index is not None:
                codes = list(user.recovery_codes)
                codes.pop(index)  # each recovery code works exactly once
                user.recovery_codes = codes
                ok = True
                used_recovery = True

    if not ok:
        if not auth_service.is_locked(user):
            auth_service.register_failure(user)
        audit.log(
            db,
            user.id,
            "user.login_failed",
            "user",
            user.id,
            details={"stage": "2fa"},
            ip=client_ip(request),
        )
        db.commit()
        await _fail_delay()
        return render(request, "admin/auth/twofa.html", {"error": CODE_ERROR}, status_code=400)

    if used_recovery:
        audit.log(
            db,
            user.id,
            "user.recovery_code_used",
            "user",
            user.id,
            details={"remaining": len(user.recovery_codes)},
            ip=client_ip(request),
        )
        flash(
            request,
            f"Iskoristili ste kod za oporavak. Preostalo kodova: {len(user.recovery_codes)}. "
            "Ako ste izgubili mobitel, ponovno postavite 2FA u profilu.",
            "warning",
        )
    response = RedirectResponse(next_url, status_code=303)
    return _finish_login(request, db, user, next_url, response)


# ---------------------------------------------------------------------------
# Forced 2FA setup (first login, after admin reset, or re-setup from profile)
# ---------------------------------------------------------------------------
def _setup_user(request: Request, db: Session) -> tuple[User | None, bool, str]:
    """Return (user, via_login_flow, next_url). Logged-in users may re-setup 2FA."""
    user, next_url = _pending_user(request, db)
    if user is not None:
        return user, True, next_url
    session_user = _current_session_user(request, db)
    if session_user is not None and not session_user.totp_enabled:
        request.state.user = session_user
        return session_user, False, "/admin/profil"
    return None, False, "/admin"


def _setup_context(user: User) -> dict:
    secret = decrypt_secret(user.totp_secret)
    site = get_site()
    uri = totp_uri(secret, user.email, site.get("company_name") or "Autokuca")
    return {
        "qr": auth_service.qr_data_uri(uri),
        "secret": auth_service.format_secret(secret),
        "account": user.email,
    }


@router.get("/2fa/postavljanje")
async def setup_form(request: Request, db: Session = Depends(get_db)):
    user, via_login, _next = _setup_user(request, db)
    if user is None:
        if _current_session_user(request, db):
            return RedirectResponse("/admin", status_code=303)
        return _expired_login(request)
    if user.totp_enabled:
        return RedirectResponse("/admin/prijava/2fa" if via_login else "/admin", status_code=303)
    if not user.totp_secret or decrypt_secret(user.totp_secret) is None:
        user.totp_secret = encrypt_secret(new_totp_secret())
        db.commit()
    return render(request, "admin/auth/setup.html", _setup_context(user))


@router.post("/2fa/postavljanje")
async def setup_submit(request: Request, db: Session = Depends(get_db)):
    user, via_login, next_url = _setup_user(request, db)
    if user is None:
        return _expired_login(request)
    if user.totp_enabled:
        return RedirectResponse("/admin", status_code=303)
    if not check_rate_limit(request, "login", 10, 60):
        context = _setup_context(user) | {"error": "Previše pokušaja. Pričekajte minutu."}
        return render(request, "admin/auth/setup.html", context, status_code=429)

    form = await request.form()
    secret = decrypt_secret(user.totp_secret)
    step = verify_totp(secret, str(form.get("code", "")), None) if secret else None
    if step is None:
        context = _setup_context(user) | {"error": CODE_ERROR}
        return render(request, "admin/auth/setup.html", context, status_code=400)

    codes = generate_recovery_codes(10)
    user.totp_enabled = True
    user.totp_last_step = step
    user.recovery_codes = [hash_recovery_code(code) for code in codes]
    audit.log(db, user.id, "user.2fa_setup", "user", user.id, ip=client_ip(request))
    db.commit()

    context = {"codes": codes, "continue_url": next_url}
    if via_login:
        response = render(request, "admin/auth/recovery_codes.html", context)
        return _finish_login(request, db, user, next_url, response)
    request.state.user = user
    return render(request, "admin/auth/recovery_codes.html", context)


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------
@router.post("/odjava")
async def logout(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get(auth_service.SESSION_COOKIE)
    session = auth_service.load_session(db, token)
    if session:
        audit.log(
            db, session.user_id, "user.logout", "user", session.user_id, ip=client_ip(request)
        )
        auth_service.delete_session(db, token)
        db.commit()
    flash(request, "Odjavljeni ste.", "success")
    response = RedirectResponse("/admin/prijava", status_code=303)
    auth_service.clear_session_cookie(response)
    return response


@router.post("/odjava-svugdje")
async def logout_everywhere(request: Request, db: Session = Depends(get_db)):
    session = auth_service.load_session(db, request.cookies.get(auth_service.SESSION_COOKIE))
    if session:
        user_id = session.user_id
        count = auth_service.delete_user_sessions(db, user_id)
        audit.log(
            db,
            user_id,
            "user.logout_all",
            "user",
            user_id,
            details={"sessions": count},
            ip=client_ip(request),
        )
        db.commit()
    flash(request, "Odjavljeni ste sa svih uređaja.", "success")
    response = RedirectResponse("/admin/prijava", status_code=303)
    auth_service.clear_session_cookie(response)
    return response


# ---------------------------------------------------------------------------
# Forgotten password
# ---------------------------------------------------------------------------
FORGOT_MESSAGE = (
    "Ako račun s tom adresom postoji, poslali smo email s poveznicom za novu lozinku. "
    "Poveznica vrijedi 1 sat."
)


@router.get("/lozinka/zaboravljena")
async def forgot_form(request: Request):
    return render(request, "admin/auth/forgot.html", {})


@router.post("/lozinka/zaboravljena")
async def forgot_submit(
    request: Request, background: BackgroundTasks, db: Session = Depends(get_db)
):
    form = await request.form()
    email = normalize_email(str(form.get("email", "")))[:254]
    allowed_ip = check_rate_limit(request, "forgot-ip", 3, 900)
    allowed_email = check_rate_limit(request, "forgot-email", 3, 900, key=email_hash(email))
    if not (allowed_ip and allowed_email):
        return render(
            request,
            "admin/auth/forgot.html",
            {"error": "Previše zahtjeva. Pokušajte ponovno za 15 minuta."},
            status_code=429,
        )
    user = auth_service.get_user_by_email(db, email) if "@" in email else None
    if user is not None and user.is_active and user.password_hash:
        raw = auth_service.create_auth_token(db, user, TOKEN_RESET, auth_service.RESET_HOURS)
        audit.log(
            db, user.id, "user.password_reset_request", "user", user.id, ip=client_ip(request)
        )
        db.commit()
        link = absolute_url(f"/admin/lozinka/nova/{raw}")
        background.add_task(
            send_template,
            user.email,
            "password_reset",
            "Postavljanje nove lozinke",
            {"link": link},
        )
    else:
        await _fail_delay()
    return render(request, "admin/auth/forgot.html", {"sent": True, "message": FORGOT_MESSAGE})


# ---------------------------------------------------------------------------
# Set password (reset or invitation) — same screen
# ---------------------------------------------------------------------------
def _password_page(request: Request, db: Session, raw: str, purpose: str):
    token = auth_service.get_valid_token(db, raw, purpose)
    if token is None:
        return None, render(
            request,
            "admin/auth/set_password.html",
            {"invalid": True, "purpose": purpose},
            status_code=400,
        )
    return token, None


@router.get("/lozinka/nova/{raw}")
async def reset_form(request: Request, raw: str, db: Session = Depends(get_db)):
    return _set_password_get(request, db, raw, TOKEN_RESET)


@router.get("/lozinka/postavi/{raw}")
async def invite_form(request: Request, raw: str, db: Session = Depends(get_db)):
    return _set_password_get(request, db, raw, TOKEN_INVITE)


def _set_password_get(request: Request, db: Session, raw: str, purpose: str):
    token, error_response = _password_page(request, db, raw, purpose)
    if error_response:
        return error_response
    return render(
        request,
        "admin/auth/set_password.html",
        {"purpose": purpose, "email": token.user.email},
    )


@router.post("/lozinka/nova/{raw}")
async def reset_submit(request: Request, raw: str, db: Session = Depends(get_db)):
    return await _set_password_post(request, db, raw, TOKEN_RESET)


@router.post("/lozinka/postavi/{raw}")
async def invite_submit(request: Request, raw: str, db: Session = Depends(get_db)):
    return await _set_password_post(request, db, raw, TOKEN_INVITE)


async def _set_password_post(request: Request, db: Session, raw: str, purpose: str):
    if not check_rate_limit(request, "set-password", 10, 600):
        raise HTTPException(status_code=429)
    token, error_response = _password_page(request, db, raw, purpose)
    if error_response:
        return error_response
    form = await request.form()
    password = str(form.get("password", ""))
    confirm = str(form.get("password_confirm", ""))
    error = validate_password_strength(password)
    if not error and password != confirm:
        error = "Lozinke se ne podudaraju."
    if error:
        context = {"purpose": purpose, "email": token.user.email, "error": error}
        return render(request, "admin/auth/set_password.html", context, status_code=400)

    user = token.user
    user.password_hash = hash_password(password)
    auth_service.reset_failures(user)
    token.used_at = utcnow()
    auth_service.delete_user_sessions(db, user.id)
    action = "user.password_reset" if purpose == TOKEN_RESET else "user.password_set"
    audit.log(db, user.id, action, "user", user.id, ip=client_ip(request))
    db.commit()
    flash(request, "Lozinka je postavljena. Sada se možete prijaviti.", "success")
    response = RedirectResponse("/admin/prijava", status_code=303)
    auth_service.clear_session_cookie(response)
    return response
