"""Phase 1: application skeleton, templating, security headers, migrations."""

from __future__ import annotations

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from app.config import Settings
from app.database import Base
from app.migrate import alembic_config


def test_home_contains_placeholders(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.text
    for placeholder in ("IME PODUZEĆA", "mailpoduzeca@domena.com", "+385XXXXXXXXXX", "LOGO"):
        assert placeholder in html
    assert "Ulica i broj 1, 10000 Grad" in html
    assert "XXXXXXXXXXX" in html  # OIB in the impressum


def test_health(client):
    response = client.get("/zdravlje")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok"}


@pytest.mark.parametrize(
    "path",
    ["/media/../secret", "/media/%2e%2e/%2e%2e/app.db", "/media/..%2fapp.db", "/media/x.png"],
)
def test_media_path_traversal_rejected(client, path):
    response = client.get(path)
    assert response.status_code == 404


def test_media_serves_webp(client):
    from app.services.storage import get_storage

    get_storage().save("test/abc_400.webp", b"RIFFxxxxWEBP")
    response = client.get("/media/test/abc_400.webp")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    assert "max-age=31536000" in response.headers["cache-control"]


def test_unknown_route_renders_404_template(client):
    response = client.get("/ova-stranica-ne-postoji")
    assert response.status_code == 404
    assert "Stranica nije pronađena" in response.text
    assert "IME PODUZEĆA" in response.text  # rendered inside the site design
    assert response.headers.get("x-robots-tag") == "noindex"


def test_static_files_are_cached(client):
    response = client.get("/static/css/public.css")
    assert response.status_code == 200
    assert "immutable" in response.headers["cache-control"]


def test_production_requires_secret_and_postgres():
    bad = Settings(_env_file=None, APP_ENV="production", SECRET_KEY="short", DATABASE_URL="")
    with pytest.raises(RuntimeError):
        bad.validate_for_startup()
    good = Settings(
        _env_file=None,
        APP_ENV="production",
        SECRET_KEY="x" * 40,
        DATABASE_URL="postgresql://u:p@db:5432/app",
    )
    good.validate_for_startup()
    assert good.database_url.startswith("postgresql+psycopg://")


def test_migrations_match_models(tmp_path):
    """`alembic upgrade head` on an empty DB yields exactly the model schema."""
    engine = create_engine(f"sqlite:///{(tmp_path / 'm.db').as_posix()}")
    cfg = alembic_config()
    cfg.attributes["configure_logger"] = False
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        diff = compare_metadata(context, Base.metadata)
    engine.dispose()
    assert diff == []


def test_i18n_returns_source_text_and_translates():
    from app.i18n import gettext, load_translations

    assert gettext("Vozila") == "Vozila"  # hr: identity
    assert load_translations("en")["Vozila"] == "Vehicles"
    assert gettext("Prikazano {n}", n=5) == "Prikazano 5"


def test_template_filters():
    from datetime import date

    from app.templating import date_hr, km, money

    assert money(12500) == "12.500 €"
    assert km(145000) == "145.000 km"
    assert date_hr(date(2026, 9, 28)) == "28.09.2026."
