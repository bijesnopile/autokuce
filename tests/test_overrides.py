"""Per-client overrides (spec chapter 17): templates and custom.css without touching the image."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import templating
from app.config import get_settings


def _clear_caches() -> None:
    templating.env.cache.clear()
    templating._static_cache.clear()


def test_override_template_and_custom_css(client):
    root = get_settings().OVERRIDES_DIR
    template = root / "templates" / "public" / "home.html"
    css = root / "static" / "custom.css"
    template.parent.mkdir(parents=True, exist_ok=True)
    css.parent.mkdir(parents=True, exist_ok=True)
    template.write_text(
        '{% extends "public/base.html" %}{% block content %}<section class="section">'
        "<h2>Posebna ponuda ovog mjeseca</h2><p>{{ site.company_name }}</p></section>"
        "{% endblock %}",
        encoding="utf-8",
    )
    css.write_text(":root { --color-primary: #0b3d2e; }", encoding="utf-8")
    _clear_caches()
    try:
        html = client.get("/").text
        assert "Posebna ponuda ovog mjeseca" in html
        assert "IME PODUZEĆA" in html  # company data still comes from settings
        assert html.index("/static/css/public.css") < html.index("/static/custom/custom.css")
        response = client.get("/static/custom/custom.css")
        assert response.status_code == 200 and "#0b3d2e" in response.text
        assert "Posebna ponuda" not in client.get("/kontakt").text  # only that template
    finally:
        template.unlink()
        css.unlink()
        _clear_caches()
    assert "Posebna ponuda" not in client.get("/").text


def test_read_only_or_missing_overrides_do_not_break_startup(monkeypatch, tmp_path):
    """Docker mounts overrides read-only; a missing overrides/static must not crash the app."""
    from app.main import create_app

    blocker = tmp_path / "not-a-directory"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setattr(get_settings(), "OVERRIDES_DIR", blocker / "overrides")
    with TestClient(create_app()) as client:
        assert client.get("/zdravlje").status_code == 200
        assert client.get("/static/custom/custom.css").status_code == 404
