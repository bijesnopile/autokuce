"""CMS pages editing and publishing (phase 7)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import (
    AuditLog,
    Page,
)
from tests.helpers import create_user, csrf_from, get_csrf, login_as


@pytest.fixture
def owner(client):
    user_id, _ = create_user("vlasnik@test.hr", role="owner")
    login_as(client, user_id)
    return user_id


def test_page_edit_increments_version_and_sanitizes(client, db, owner):
    page = client.get("/admin/stranice/o-nama")
    assert page.status_code == 200
    response = client.post(
        "/admin/stranice/o-nama",
        data={
            "csrf_token": csrf_from(page.text),
            "title": "O nama",
            "body_html": "<h2>Tko smo</h2><p>Tekst <script>alert(1)</script><em>kurziv</em></p>",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    db.expire_all()
    stored = db.scalar(select(Page).where(Page.slug == "o-nama"))
    assert stored.version == 2
    assert "<script" not in stored.body_html and "<em>kurziv</em>" in stored.body_html
    assert "Tko smo" in client.get("/o-nama").text
    assert db.scalar(select(AuditLog).where(AuditLog.action == "page.update"))


def test_unpublished_page_404_publicly_but_previewable(client, db, owner):
    token = get_csrf(client, "/admin/stranice/usluge")
    client.post("/admin/stranice/usluge/objava", data={"csrf_token": token})
    db.expire_all()
    assert not db.scalar(select(Page).where(Page.slug == "usluge")).is_published
    public = client.get("/usluge")
    assert public.status_code == 404
    preview = client.get("/admin/stranice/usluge/pregled")
    assert preview.status_code == 200 and "Pregled iz administracije" in preview.text
