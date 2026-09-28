# CLAUDE.md — memorija projekta (čitaj na početku svake sesije)

MVP template web-platforme za autokuće u Hrvatskoj. Jedna instanca = jedna autokuća
(vlastita domena, vlastita baza), sve instance na jednom VPS-u kao Docker kontejneri.
Izvor istine: `docs/SPECIFIKACIJA.md` (odluke su konačne). Nedefinirano → odluči i zapiši u
`docs/PRETPOSTAVKE.md`. Build se vodi promptovima u `prompts/` (00 orkestrator, 01–08 faze).

## Stack

Python 3.11+ (lokalno 3.14), FastAPI + Jinja2 SSR, SQLAlchemy 2.0 (sync), Alembic,
pydantic-settings, SQLite lokalno / PostgreSQL 16 u Dockeru, vlastiti CSS + vanilla JS
(bez frameworka i build koraka), argon2-cffi, pyotp, qrcode, itsdangerous, nh3, Pillow,
boto3, httpx. Testovi: pytest + TestClient, Playwright (Chromium) za screenshotove.

## Pokretanje i testiranje

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1          # bash/WSL: source .venv/bin/activate (Git Bash: source .venv/Scripts/activate)
pip install -r requirements-dev.txt
python -m playwright install chromium
python run.py                        # http://localhost:8000  (migracije + seed na praznoj bazi)
python -m pytest -q
ruff check . ; ruff format --check .
python scripts/check.py              # ruff + pytest + pip-audit (od faze 8)
```

Bez aktivacije: `.venv/Scripts/python.exe run.py` (Windows) / `.venv/bin/python run.py` (Linux).

## Gdje je što

| Putanja | Sadržaj |
|---|---|
| `app/main.py` | `create_app()`, middleware (RealIP, SecurityHeaders+CSP, ErrorPage 500, AdminIPAllowlist, Session `st`), error handleri, routeri |
| `app/config.py` | `Settings` (sve env varijable), `get_settings()`; produkcijska validacija |
| `app/database.py` | engine, `SessionLocal`, `Base`, `get_db`, `utcnow()` (naivni UTC) |
| `app/models.py` | SVI modeli + string konstante statusa/uloga/tipova |
| `app/security.py` | Argon2, tokeni (SHA-256 u bazi), CSRF (`verify_csrf`), rate limiter, Fernet, TOTP |
| `app/permissions.py` | matrica ovlasti (`PERMISSIONS`, `can()`), admin navigacija `ADMIN_NAV` |
| `app/templating.py` | Jinja env (ChoiceLoader overrides→app), filteri, `render()`, `flash()`, `query_url()` |
| `app/services/site.py` | postavke tvrtke: `DEFAULTS` (placeholderi), `get_site()` (keš 60 s), `set_values()` |
| `app/services/storage.py` | `LocalStorage` / `S3Storage`, `get_storage()` |
| `app/services/audit.py` | `log(db, user_id, action, ...)` |
| `app/icons.py` + `templates/_icons.html` | inline SVG ikone (`{{ icon("phone") }}`) |
| `app/i18n/` | `_()` (ključ = hrvatski tekst), `hr.json` prazan, `en.json` primjer |
| `app/seed.py`, `app/seed_content.py` | seed (idempotentan), lorem sadržaj stranica |
| `app/cli.py` | `python -m app.cli <naredba>` |
| `app/utils.py` | `slugify()`, `ensure_utf8_console()` |
| `app/templates/public/`, `admin/`, `emails/` | templatei; `public/_macros.html` = forme (CSRF, honeypot, Turnstile, newsletter) |
| `app/static/css/public.css` | design sustav (tokeni, komponente); admin učitava public.css + admin.css |
| `migrations/versions/` | Alembic; `0001_initial_schema.py` |
| `overrides/` | per-klijent templatei i `static/custom.css` (vidi `overrides/README.md`) |
| `tests/conftest.py` | privremeni DATA_DIR + SQLite, čišćenje tablica i minimal seed prije svakog testa |

## Pravila (obavezno)

1. **Podaci tvrtke samo iz postavki** (`site.company_name`, `site.company_phone`…). Nikad hardkodirano u templateima.
2. **Nema CDN-ova ni vanjskih resursa** (fontovi = sistemski stack). **Nema inline `<script>`** (CSP). Inline `<style>` je dopušten.
3. **Svaki POST ima CSRF**: forma `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`, ruta `dependencies=[Depends(verify_csrf)]`; fetch šalje header `X-CSRF-Token` (admin: `Admin.csrf()` iz `<meta name="csrf-token">`).
4. **Svaki upload kroz `app/services/images.py`** (Pillow provjera, re-enkodiranje u WebP, bez EXIF-a).
5. **Svaka admin akcija u audit log** (`audit.log(...)`), bez osobnih podataka kupaca u `details`.
6. **Svaki UI string kroz `_()`** (Python i Jinja). Novi jezik = `app/i18n/xx.json` + `python scripts/extract_strings.py --lang xx`.
7. **Migracije Alembicom**: promjena modela → `alembic revision --autogenerate -m "..."` → pregledaj → test `test_migrations_match_models` mora proći.
8. Prije završetka: `ruff check .`, `ruff format --check .`, `pytest` (od faze 8 `python scripts/check.py`).
9. Makroi koji koriste `csrf_token()` importaju se **`with context`**: `{% from "public/_macros.html" import x with context %}`.
10. Datumi u bazi su **naivni UTC** (`utcnow()`); prikaz u Europe/Zagreb kroz filtere `date_hr`/`datetime_hr`.
11. Statusi/uloge/tipovi su **string konstante** u `models.py` (ne DB enum).
12. Lokalne skripte samo u Pythonu, `pathlib`, rade na Windowsu i Linuxu. `deploy/*.sh` samo za Linux VPS.

## Konvencije

- Render: `render(request, "public/x.html", {...}, status_code=200)`; flash: `flash(request, "Poruka", "success|error|info|warning")`.
- Greške: `raise HTTPException(404)` → dizajnirana 404; 403 u adminu → `admin/403.html`; neprijavljen → `raise LoginRequired(next)` (redirect na prijavu).
- Admin sekcija još nije napravljena → `app/routers/admin_dashboard.py::UNDER_CONSTRUCTION` (ukloni ključ kad sekcija dobije pravi router; admin_dashboard router uključi ZADNJI).
- Kolačići: `st` (potpisano klijentsko stanje: CSRF, flash) — nužni, bez pristanka.

## Okruženje (važno)

- Windows 11 sa **Smart App Control**: blokira nepotpisane nove `.pyd` datoteke. Zato su pinani `sqlalchemy==2.1.0` i `nh3==0.3.6` (novije verzije blokirane). Ne mijenjati bez provjere `python -c "import sqlalchemy.orm, nh3"`.
- Windows konzola je cp1252 kad je izlaz preusmjeren → ulazne točke zovu `ensure_utf8_console()`.
- Docker nije instaliran na razvojnom računalu → Docker provjere se preskaču (zapisano u PRETPOSTAVKE.md).

## Status faza

- Faza 1: gotova — 28.09.2026.
- Faza 2: —
- Faza 3: —
- Faza 4: —
- Faza 5: —
- Faza 6: —
- Faza 7: —
- Faza 8: —

## Trenutno

Faza 2 (autentikacija, 2FA, korisnici, admin okvir), zadnji dovršeni korak: faza 1 commitana.
