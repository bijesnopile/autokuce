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
python run.py                        # http://localhost:8000  (migracije + puni demo na praznoj bazi)
python scripts/check.py              # ruff check + ruff format --check + pytest + pip-audit (--brzo bez audita)
python -m pytest -q tests/test_x.py  # pojedini testovi
python scripts/screenshots.py        # vlastita instanca + tijekovi kao klijent + docs/screenshots/
```

PostgreSQL testovi: `TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:54329/autokuca_test pytest`
(baza se briše). SQLite ne provjerava duljine `VARCHAR` — promjene modela provjeri i na PostgreSQL-u.

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
| `app/services/auth.py` | sesije (hash tokena u bazi), lockout, `ak_pending` kolačić, invite/reset tokeni, QR |
| `app/services/email.py` | `send()`, `send_template(to, "ime", subject, ctx)` — backendi console/file/brevo, `email_log` |
| `app/deps.py` | `get_current_user`, `require_permission("x")`, `require_role(...)`, `csrf_protect` |
| `app/errors.py` | `LoginRequired`, `TwoFactorSetupRequired` |
| `app/pagination.py` | `paginate(db, stmt, page, per_page)` → `Page` |
| `app/routers/admin_auth.py` | prijava, 2FA, postavljanje 2FA, odjava, zaboravljena/nova lozinka, pozivnice |
| `app/routers/admin_users.py` | `/admin/korisnici*`, `/admin/profil*` |
| `app/routers/admin_audit.py` | `/admin/audit` (+ `ACTION_LABELS` — dodaj labelu za novu akciju) |
| `app/vehicle_schema.py` | **jedini izvor istine** za vrste vozila, polja, opcije, opremu, statuse i prijelaze |
| `app/services/vehicles.py` | naslov/slug (+ povijest slugova), statusi, dupliciranje, brisanje, parsiranje forme |
| `app/services/images.py` | `process_image`, `save_vehicle_image`, `save_logo`, `delete_variants` |
| `app/routers/admin_catalog.py` | `/admin/katalog/*`, CSV uvoz, **`GET /api/modeli`** (javno) |
| `app/routers/admin_vehicles.py` | `/admin/vozila*` i `/admin/vozila/{id}/slike*` |
| `app/seed_catalog.py` | generički katalog marki/modela za seed |
| `app/routers/public.py` | `/`, `/vozila`, `/vozila/{slug}`, `/kontakt`, CMS stranice, `/zdravlje`, `/media` |
| `app/routers/seo.py` | `/sitemap.xml`, `/robots.txt` |
| `app/services/seo.py` | `page_meta`, `vehicle_meta`, JSON-LD (`organization_jsonld`, `vehicle_jsonld`, `breadcrumbs_jsonld`) |
| `app/services/placeholder_images.py` | generirane slike vozila i OG slika (Pillow) |
| `app/services/inquiries.py` | validacija upita, telefon, spremanje s privolom, email dealeru, CSV |
| `app/services/turnstile.py` | `verify_turnstile(token, ip)` (isključeno bez ključa) |
| `app/services/maintenance.py` | retencija (`STEPS`, `run_all(db, dry_run)`, `step_labels()`), dnevna nit (`start_background_thread`), `python -m app.cli maintenance [--dry-run]` |
| `app/routers/admin_inquiries.py` | `/admin/upiti*` (inbox, detalj, status, dodjela, bilješke, CSV) |
| `app/services/newsletter.py` | prijava/double opt-in, odjava (anonimizacija), kampanje, slanje u serijama, retencija |
| `app/routers/admin_newsletter.py` | `/admin/newsletter/pretplatnici*`, `/admin/newsletter/kampanje*`, `/admin/newsletter/api/vozila` |
| `app/templates/public/_vehicle_card.html` | makro kartice vozila; `_inquiry_form.html` forma upita |
| `app/static/js/editor.js` | rich-text editor (`<textarea data-editor>`), opcija `data-editor-vehicles` |
| `app/services/stats.py` | brojke za nadzornu ploču i statistiku (`dashboard`, `views_per_day`, `vehicle_table`, `inquiry_breakdown`, `newsletter_weekly`, `top_makes`) |
| `app/services/charts.py` | inline SVG grafovi (`bar_chart`, `paired_bar_chart`) |
| `app/routers/admin_dashboard.py` | `/admin`, `/admin/statistika` (+ `/izvoz.csv`), `/admin/sustav*`; catch-all 404 — uključuje se ZADNJI |
| `app/routers/admin_settings.py` | `/admin/postavke` (`FIELDS`, `SECTIONS`, `_validate`), logo upload/uklanjanje |
| `app/routers/admin_pages.py` | `/admin/stranice*` (uređivanje, objava, pregled) |
| `app/routers/admin_privacy.py` | `/admin/gdpr` (pretraga, JSON izvoz, brisanje) — `find_person`, `export_data` |
| `app/seed_demo.py` | puni demo (`VEHICLES`, `seed_demo`, `reset_demo`), oznaka `demo_seeded` |
| `app/services/content.py` | marketinški sadržaj: `split_sections` (H3 → kartice), `split_lead`, `why_us_items`, `pick_icon`, `page_template`, `page_extras` (brojke za O nama) |
| `app/templates/public/pages/<slug>.html` | vlastiti raspored CMS stranice (`usluge`, `o-nama`); inače `public/page.html` |
| `app/templates/public/_sections.html` | makroi `page_hero`, `why_us_cards`, `cta_band` |
| `app/icons.py` + `templates/_icons.html` | inline SVG ikone (`{{ icon("phone") }}`) |
| `app/i18n/` | `_()` (ključ = hrvatski tekst), `hr.json` prazan, `en.json` primjer |
| `app/seed.py`, `app/seed_content.py` | seed (idempotentan), zadani sadržaj stranica (O nama i Usluge generički tekst, pravne lorem + `[PRAVNIK]`) |
| `app/cli.py` | `python -m app.cli <naredba>` |
| `app/utils.py` | `slugify()`, `ensure_utf8_console()` |
| `app/templates/public/`, `admin/`, `emails/` | templatei; `public/_macros.html` = forme (CSRF, honeypot, Turnstile, newsletter); `admin/_macros.html` = paginacija, greške polja; `emails/_macros.html` = gumb |
| `app/static/css/public.css` | design sustav (tokeni, komponente); admin učitava public.css + admin.css |
| `migrations/versions/` | Alembic; `0001_initial_schema.py` |
| `overrides/` | per-klijent templatei i `static/custom.css` (vidi `overrides/README.md`) |
| `Dockerfile`, `docker/entrypoint.sh` | slika (python:3.11-slim, multi-stage, korisnik `app`); entrypoint: SECRET_KEY, wait-db, migracije, `seed --if-empty` |
| `docker-compose.yml`, `Caddyfile` | jedan klijent/demo (app + postgres + caddy); `DOMAIN` prazno = `http://localhost` |
| `deploy/` | zajednički Caddy (`caddy/`), predložak klijenta, `new-client.sh`, `remove-client.sh`, `update-all.sh`, `backup.sh`, `restore.sh`, `lib.sh`, `crontab.example` |
| `scripts/check.py`, `scripts/screenshots.py` | provjera kvalitete; screenshotovi + prolaz tijekova |
| `scripts/check_wheels.py` | ima li svaki pin binarni wheel za Docker sliku (cp311, glibc 2.41) — pokreni nakon promjene pinova |
| `tests/conftest.py` | privremeni DATA_DIR + SQLite, čišćenje tablica i minimal seed prije svakog testa |

## Pravila (obavezno)

1. **Podaci tvrtke samo iz postavki** (`site.company_name`, `site.company_phone`…). Nikad hardkodirano u templateima.
2. **Nema CDN-ova ni vanjskih resursa** (fontovi = sistemski stack). **Nema inline `<script>`** (CSP). Inline `<style>` je dopušten.
3. **Svaki POST ima CSRF**: forma `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`, router `APIRouter(dependencies=[Depends(csrf_protect)])` (`app/deps.py`) — pokriva sve POST/PUT/PATCH/DELETE rute routera; iznimka je samo `unsubscribe_router` (RFC 8058 one-click, autorizacija tokenom); fetch šalje header `X-CSRF-Token` (admin: `Admin.csrf()` iz `<meta name="csrf-token">`).
4. **Svaki upload kroz `app/services/images.py`** (Pillow provjera, re-enkodiranje u WebP, bez EXIF-a).
5. **Svaka admin akcija u audit log** (`audit.log(...)`), bez osobnih podataka kupaca u `details`.
6. **Svaki UI string kroz `_()`** (Python i Jinja). Novi jezik = `app/i18n/xx.json` + `python scripts/extract_strings.py --lang xx`.
7. **Migracije Alembicom**: promjena modela → `alembic revision --autogenerate -m "..."` → pregledaj → test `test_migrations_match_models` mora proći.
8. Prije završetka: **`python scripts/check.py`** (ruff, format, pytest, pip-audit) mora proći.
9. Makroi koji koriste `csrf_token()` importaju se **`with context`**: `{% from "public/_macros.html" import x with context %}`.
   Makro vidi kontekst iz trenutka importa — vrijednosti koje se postavljaju kasnije šalji kao parametre.
   **Nikad `{% set _ = ... %}`** u templateu — `_` je i18n funkcija.
10. Datumi u bazi su **naivni UTC** (`utcnow()`); prikaz u Europe/Zagreb kroz filtere `date_hr`/`datetime_hr`.
11. Statusi/uloge/tipovi su **string konstante** u `models.py` (ne DB enum).
12. Lokalne skripte samo u Pythonu, `pathlib`, rade na Windowsu i Linuxu. `deploy/*.sh` samo za Linux VPS
    (bash, `set -Eeuo pipefail`, zajedničke funkcije u `deploy/lib.sh`; lokalni test backupa: `AK_PG_LOCAL=1`).
13. Datoteke montirane u Docker samo za čitanje (`overrides/`) aplikacija nikad ne smije pisati; pisati se
    smije samo u `DATA_DIR`.
14. Novi javni API endpoint: `dependencies=[Depends(rate_limit("api", 100, 60))]`.

## Kako raditi promjene (postupak)

1. Pročitaj ovaj dokument i relevantni dio `docs/SPECIFIKACIJA.md`; nejasno → odluči i zapiši u
   `docs/PRETPOSTAVKE.md`.
2. Model: promjena u `app/models.py` → `alembic revision --autogenerate -m "..."` → pregledaj migraciju
   (batch za SQLite) → `test_migrations_match_models`.
3. Logika u `app/services/`, tanka ruta u `app/routers/` (ovlast, CSRF preko routera, audit), template s
   `_()` i podacima iz `site`.
4. Test u `tests/` (pomoćne funkcije u `tests/helpers.py`); sigurnosno osjetljive stvari imaju test.
5. `python scripts/check.py`; za promjene izgleda `python scripts/screenshots.py` i pregledaj slike.
6. Dokumentacija: README (za korisnika/operatera), ovaj dokument (za razvoj), `docs/*` po potrebi.
7. Commit s opisnom porukom; release: tag `vX.Y.Z`, na VPS-u `deploy/update-all.sh`.

## Konvencije

- Render: `render(request, "public/x.html", {...}, status_code=200)`; flash: `flash(request, "Poruka", "success|error|info|warning")`.
- Greške: `raise HTTPException(404)` → dizajnirana 404; 403 u adminu → `admin/403.html`; neprijavljen → `raise LoginRequired(next)` (redirect na prijavu).
- `admin_dashboard` router ima catch-all 404 za `/admin/*` → uključi ga u `main.py` ZADNJI.
- Kolačići: `st` (potpisano klijentsko stanje: CSRF, flash) — nužni, bez pristanka; `session`
  (admin sesija, Path=/admin, 12 h); `ak_pending` (10 min između lozinke i 2FA koda).
- Novi admin router: `APIRouter(prefix="/admin", dependencies=[Depends(csrf_protect)])`, svaka ruta
  `user: User = Depends(require_permission("..."))`, uključi ga u `main.py` PRIJE `admin_dashboard`.
- Forme se parsiraju ručno (`form = await request.form()`), greške u dict `errors` → re-render s
  `status_code=400`; nakon uspjeha PRG: `flash(...)` + `RedirectResponse(url, 303)`.
- Emailovi: predložak `emails/<ime>.html` + `.txt` (extends `emails/base.*`), slanje u pozadini:
  `background.add_task(send_template, to, "<ime>", "Subject", {...})`.

## Rute (admin — auth)

`/admin/prijava`, `/admin/prijava/2fa`, `/admin/2fa/postavljanje`, `POST /admin/odjava`,
`POST /admin/odjava-svugdje`, `/admin/lozinka/zaboravljena`, `/admin/lozinka/nova/{token}` (1 h),
`/admin/lozinka/postavi/{token}` (pozivnica, 48 h), `/admin/korisnici`, `/admin/korisnici/novi`,
`/admin/korisnici/{id}` (+ `/deaktiviraj`, `/aktiviraj`, `/reset-2fa`, `/pozivnica`), `/admin/profil`
(+ `/lozinka`, `/2fa`), `/admin/audit`. Faza 7: `/admin`, `/admin/statistika` (+ `/izvoz.csv?tablica=`),
`/admin/postavke` (+ `/logo`, `/logo/ukloni`), `/admin/stranice/{slug}` (+ `/objava`, `/pregled`),
`/admin/gdpr` (+ `/izvoz`, `/obrisi`), `/admin/sustav` (+ `/testni-email`, `/odrzavanje`).

Demo pristup: `admin@domena.com` (superadmin), `vlasnik@domena.com` (owner), `prodavac1@domena.com`
(prodavač) / `SEED_PASSWORD` (default `Promijeni-me-2026!`), bez 2FA — prva prijava traži postavljanje.
Seed: `python -m app.seed` (puni demo, idempotentno), `--minimal`, `--reset-demo` (briše SVE podatke
o vozilima/upitima/newsletteru; u produkciji samo uz `DEMO_SEED=true` ili `--potvrdi`). CLI: `python -m app.cli create-superadmin --email .. --password ..`,
`python -m app.cli reset-2fa --email ..`, `ensure-secret-key` / `check-secret-key [--accept]` (Docker
entrypoint: ključ se generira jednom u `data/.secret_key`, promjena ključa odbija start).

## Postavke tvrtke — kako dodati novu postavku

1. Ključ i placeholder vrijednost u `DEFAULTS` (`app/services/site.py`; bool → i u `BOOL_KEYS`).
2. Polje u `FIELDS` (`app/routers/admin_settings.py`: ključ, labela, vrsta za validaciju, max duljina, sekcija).
3. Korištenje u templateu kroz `site.<ključ>` (nikad hardkodirano). Marketinške tvrdnje ("Zašto kupiti
   kod nas") također idu u postavke (`why_us`), ne u predloške. Seed dodaje nove ključeve postojećim
   instancama (`seed_settings` ne prepisuje postojeće vrijednosti).

## Upiti — kako dodati novu vrstu upita

1. Kod + labela u `INQUIRY_TYPE_LABELS` (`app/services/inquiries.py`) i `models.INQUIRY_TYPES`.
2. Varijanta forme u `templates/public/_inquiry_form.html` (parametar `kind`); dodatna polja se spremaju
   u `inquiries.extra` (JSON, bez migracije) — validacija u `validate_inquiry`.
3. Po potrebi prikaz dodatnih polja u `admin/inquiries/detail.html` i u email predlošku
   `emails/inquiry_notification.*`.
Svaka javna forma koristi `form_security()` (CSRF + honeypot + `form_ts`) i `turnstile()` iz
`public/_macros.html`; handler provjerava `check_form_timestamp`, `verify_turnstile`, `check_rate_limit`.

## Vozila — kako dodati polje/tip

Polje specifično za vrstu → `TYPE_FIELDS[tip]` u `app/vehicle_schema.py` (JSON, bez migracije); u formi
se zove `<tip>__<ključ>`. Zajedničko polje s kolonom → model + migracija + `COMMON_FIELDS`. Nova vrsta →
`VEHICLE_TYPES` + `TYPE_FIELDS` + `models.VEHICLE_TYPES`. Detalji u README-u ("Vrste vozila i polja").
Slike: `<file_key>_{400,1000,1600}.webp`; filter `img|media_url(1000)`, `img|srcset`.

## Testovi — pomoćne funkcije

`tests/helpers.py`: `create_user(email, role, totp=True)` → (id, secret), `login_as(client, id)` (brza
prijava bez UI-ja), `get_csrf(client, path)`, `login_via_ui(...)`, `totp_now(secret)`, `outbox()`,
`read_eml()`, `eml_text()`, `find_link()`, `external_urls(html)`, `make_catalog(db, marka, model, tip)`,
`make_vehicle(db, user_id, vehicle_type, status, **polja)`, `image_bytes()`, `gps_exif()`.
Playwright i CSP: stranice imaju strogi CSP, pa `page.wait_for_function` treba kontekst s `bypass_csp=True`.

## Okruženje (važno)

- Windows 11 sa **Smart App Control**: blokira nepotpisane nove `.pyd` datoteke. Zato su pinani `sqlalchemy==2.1.0` i `nh3==0.3.6` (novije verzije blokirane). Ne mijenjati bez provjere `python -c "import sqlalchemy.orm, nh3"`.
- Windows konzola je cp1252 kad je izlaz preusmjeren → ulazne točke zovu `ensure_utf8_console()`.
- Pinovi moraju imati Linux cp311 wheel (Docker `python:3.11-slim-trixie`, `--only-binary`):
  `python scripts/check_wheels.py`. Pillow 12.3 ima samo manylinux_2_28 (ne 2014) — namjerno.
- Docker nije instaliran na razvojnom računalu → `docker build`/`compose` nisu izvedeni (PRETPOSTAVKE.md →
  "Otvoreno"); backup/restore skripte su provjerene lokalno s `AK_PG_LOCAL=1` i PostgreSQL 16 binarnim datotekama.
- Alati za pisanje/uređivanje datoteka pretvaraju `\uXXXX` u stvarni znak — za escape sekvence u kodu
  koristi `chr()`/`codecs.BOM_UTF8` ili Python skriptu. Bash heredoc zna puknuti na navodnicima →
  skripte za izmjene piši u datoteku (scratchpad) i pokreni Pythonom.

## Status faza

- Faza 1: gotova — 28.09.2026.
- Faza 2: gotova — 28.09.2026.
- Faza 3: gotova — 28.09.2026.
- Faza 4: gotova — 28.09.2026.
- Faza 5: gotova — 28.09.2026.
- Faza 6: gotova — 28.09.2026.
- Faza 7: gotova — 28.09.2026.
- Faza 8: gotova — 28.09.2026.

## Trenutno

Sve faze (1–8) su gotove; verzija `v0.1.0-mvp`. Nakon toga (29.09.2026.): redizajn specifikacija i
opreme na detalju vozila, stranice Usluge i O nama s vlastitim rasporedom, postavka `why_us`, generički
demo sadržaj umjesto lorem ipsuma (PRETPOSTAVKE.md → "Demo sadržaj i podstranice"). Otvoreno (PRETPOSTAVKE.md): provjera `docker compose`
na računalu s Dockerom. Sljedeći koraci: docs/ROADMAP.md i "Što ostaje" u docs/SIGURNOST.md.
