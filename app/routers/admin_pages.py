"""CMS pages (/admin/stranice, owner+): O nama, Usluge, Politika privatnosti, Kolačići, Uvjeti.

Edited with the simple editor (editor.js); saved HTML is sanitised with nh3;
every change increases `version` (shown on the legal pages).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db, utcnow
from app.deps import csrf_protect, require_permission
from app.models import PAGE_SLUGS, Page, User
from app.security import clean_html, client_ip
from app.services import audit, content
from app.templating import flash, render

router = APIRouter(prefix="/admin", dependencies=[Depends(csrf_protect)])
LEGAL = {"privatnost", "kolacici", "uvjeti"}


def _get(db: Session, slug: str) -> Page:
    page = db.scalar(select(Page).where(Page.slug == slug))
    if page is None or slug not in PAGE_SLUGS:
        raise HTTPException(status_code=404)
    return page


@router.get("/stranice")
async def pages_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("pages")),
):
    pages = sorted(
        db.scalars(select(Page)),
        key=lambda p: PAGE_SLUGS.index(p.slug) if p.slug in PAGE_SLUGS else 99,
    )
    return render(
        request, "admin/pages/list.html", {"section": "stranice", "pages": pages, "legal": LEGAL}
    )


@router.get("/stranice/{slug}")
async def page_edit(
    request: Request,
    slug: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("pages")),
):
    page = _get(db, slug)
    return render(
        request,
        "admin/pages/edit.html",
        {
            "section": "stranice",
            "page": page,
            "errors": {},
            "legal": LEGAL,
            "form": {"title": page.title, "body_html": page.body_html},
        },
    )


@router.post("/stranice/{slug}")
async def page_save(
    request: Request,
    slug: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("pages")),
):
    page = _get(db, slug)
    form = await request.form()
    title = " ".join(str(form.get("title", "")).split())[:200]
    body = clean_html(str(form.get("body_html", ""))[:200_000])
    if len(title) < 2:
        return render(
            request,
            "admin/pages/edit.html",
            {
                "section": "stranice",
                "page": page,
                "legal": LEGAL,
                "errors": {"title": "Upišite naslov."},
                "form": {"title": title, "body_html": body},
            },
            status_code=400,
        )
    if title != page.title or body != page.body_html:
        page.title = title
        page.body_html = body
        page.version = (page.version or 0) + 1
        page.updated_by = user.id
        page.updated_at = utcnow()
        audit.log(
            db,
            user.id,
            "page.update",
            "page",
            page.slug,
            {"version": page.version},
            client_ip(request),
        )
        db.commit()
        flash(request, f"Stranica je spremljena (verzija {page.version}).", "success")
    else:
        flash(request, "Nema promjena.", "info")
    return RedirectResponse(f"/admin/stranice/{page.slug}", status_code=303)


@router.post("/stranice/{slug}/objava")
async def page_toggle_publish(
    request: Request,
    slug: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("pages")),
):
    page = _get(db, slug)
    page.is_published = not page.is_published
    audit.log(
        db,
        user.id,
        "page.update",
        "page",
        page.slug,
        {"is_published": page.is_published},
        client_ip(request),
    )
    db.commit()
    state = "objavljena" if page.is_published else "skrivena (javno vraća 404)"
    flash(request, f"Stranica je {state}.", "success")
    return RedirectResponse(f"/admin/stranice/{page.slug}", status_code=303)


@router.get("/stranice/{slug}/pregled")
async def page_preview(
    request: Request,
    slug: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("pages")),
):
    """Admin preview in the public design (also for unpublished pages)."""
    page = _get(db, slug)
    request.state.user = None  # render the public layout without admin context
    return render(
        request,
        content.page_template(slug),
        {
            "page": page,
            "is_legal": slug in LEGAL,
            "preview": True,
            "breadcrumbs": [("Naslovnica", "/"), (page.title, f"/{slug}")],
            **content.page_extras(db, slug, page.body_html),
        },
        headers={"X-Robots-Tag": "noindex"},
    )
