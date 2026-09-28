# Izvještaj — Faza 1: Temelj projekta

Datum: 28.09.2026.

## Što je napravljeno

**Korijen:** `.gitignore`, `.gitattributes` (LF za `*.sh`, `*.py`, `Dockerfile`, `Caddyfile`, `*.yml`…),
`requirements.txt` (pinano), `requirements-dev.txt`, `pyproject.toml` (ruff, pytest), `run.py`,
`.env.example` (sve varijable s komentarima), `alembic.ini`, `README.md` (kostur), `CLAUDE.md`.

**app/**
- `config.py` — `Settings` (pydantic-settings), produkcijska validacija (SECRET_KEY ≥ 32, bez SQLite-a),
  dev `SECRET_KEY` generiran u `data/.dev_secret_key`.
- `database.py` — engine (SQLite WAL + foreign keys / Postgres pool), `SessionLocal`, `Base` s
  konvencijom imenovanja, `get_db`, `utcnow()`.
- `models.py` — svih 18 tablica iz poglavlja 6 s indeksima i string konstantama.
- `security.py` — Argon2id, lista čestih lozinki, tokeni (SHA-256), kodovi za oporavak, Fernet,
  TOTP s anti-replay, CSRF (`verify_csrf`), in-memory rate limiter.
- `templating.py` — Jinja `ChoiceLoader` (overrides → app), filteri (`money`, `km`, `date_hr`,
  `datetime_hr`, `month_year`, `nl2br`, `media_url`, `srcset`, `css_color`), globali (`site`, `_`,
  `config`, `csrf_token()`, `flash_messages()`, `static_url()` s cache-bustingom), `render()`, `flash()`.
- `permissions.py` — matrica ovlasti iz poglavlja 10 + admin navigacija.
- `i18n/` — `_()`, `hr.json` (prazan), `en.json` (33 primjera).
- `services/site.py` (postavke s placeholderima, keš 60 s), `services/storage.py` (Local + S3),
  `services/audit.py`.
- `routers/public.py` (`/`, `/zdravlje`, `/media/{key}`), `routers/admin_dashboard.py`
  (`/admin` + stranice "U izradi").
- `main.py` — čisti ASGI middleware: pravi IP (samo uz `TRUST_PROXY`), sigurnosni headeri + CSP
  (dinamički Turnstile/Umami/MEDIA_URL), HSTS uz `HTTPS=true`, 500 stranica, admin IP allowlist,
  potpisani kolačić `st`; handleri 404/403/4xx/422.
- `seed.py` + `seed_content.py` (`--minimal`: postavke + 5 stranica s pravnom strukturom i
  `[PRAVNIK: dopuniti]`), `cli.py`, `migrate.py`, `utils.py`, `icons.py`.
- `templates/` — `public/base.html` (header, mobilni izbornik, footer s impressumom, newsletter
  forma), `home.html` (privremeno), `404.html`, `500.html`, `error.html`, `_macros.html`,
  `_icons.html`; `admin/base.html` (sidebar, topbar), `dashboard.html`, `u_izradi.html`, `403.html`.
- `static/` — `css/public.css` (design sustav), `css/admin.css`, `js/public.js`, `js/admin.js`,
  `img/favicon.svg` (slovo L).

**migrations/** — `env.py` (URL iz Settings, batch mode), `0001_initial_schema.py` (autogenerate).
**overrides/** — `README.md` s primjerima, `templates/`, `static/`.
**scripts/** — `extract_strings.py`.
**tests/** — `conftest.py` (privremeni DATA_DIR/SQLite ili `TEST_DATABASE_URL`), `test_temelj.py`.

## Kako pokrenuti

```powershell
python -m venv .venv; .venv\Scripts\Activate.ps1; pip install -r requirements-dev.txt; python run.py
```

## Provjera

- `python run.py` diže aplikaciju bez ručnih koraka (migracije + seed); naslovnica prikazuje
  header/footer s placeholderima; `/zdravlje` → `{"status":"ok","db":"ok"}`.
- Migracije: SQLite ✔, **PostgreSQL 16.2** ✔ (prijenosne binarne datoteke, bez Dockera; usporedba
  shema = bez razlike). Cijela suita prolazi i na Postgresu.
- Vanjski URL-ovi na naslovnici: samo linkovi društvenih mreža iz postavki.
- Screenshotovi (pregledani, u scratchpadu): naslovnica desktop/mobile, admin kostur — bez
  horizontalnog skrola i grešaka u konzoli.
- `ruff check .` ✔, `ruff format --check .` ✔, `pytest`: **15 passed**.

## Zabilježeno u PRETPOSTAVKE.md

Python 3.14 lokalno; Smart App Control → pinani `sqlalchemy==2.1.0` i `nh3==0.3.6`; Postgres bez
Dockera; UTF-8 konzola na Windowsu; kolačić `st` za CSRF/flash; CSRF rotacija pri prijavi; dodatne
kolone izvan poglavlja 6; zadane boje; `DATA_DIR`/`OVERRIDES_DIR`.

## Poznati nedostaci

- `docker compose` nije testiran (Docker nije instaliran) — faza 8.
- Naslovnica je privremena (pravi sadržaj u fazi 4); admin nije zaštićen prijavom (faza 2).
