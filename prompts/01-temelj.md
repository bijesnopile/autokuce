# FAZA 1/8 — Temelj projekta

## Kontekst

Gradimo MVP template web-platforme za autokuće u Hrvatskoj (FastAPI + Jinja2 SSR + vlastiti HTML/CSS/JS, PostgreSQL u Dockeru / SQLite lokalno, jedna instanca po klijentu). Ovo je faza 1 od 8. Mapa projekta je `C:\Users\matej\Documents\projekti\autokuce` — projekt se gradi u njezinom korijenu, a promptovi su u `prompts/` (ostaju u repozitoriju). Cijela specifikacija je u `prompts/SPECIFIKACIJA.md` — **prvo je kopiraj u `docs/SPECIFIKACIJA.md`** (ako već nije tamo) i **pročitaj je cijelu prije početka** (posebno poglavlja 2 — uključujući "Razvojno okruženje", 3, 4, 5, 6, 9, 13, 16, 17). Odluke u njoj su konačne. Ako nešto nije definirano, odaberi razumnu opciju i zabilježi je u `docs/PRETPOSTAVKE.md`. Ne postavljaj pitanja — radi do kraja faze.

Radiš na Windows računalu (PowerShell ili WSL — provjeri u kojoj si ljusci). Prije početka provjeri `python --version` (3.11+), `git --version`, `docker --version` (može nedostajati) i kreiraj `.venv`.

Ako u repozitoriju već postoji dio ovoga (prekinuta sesija), provjeri stanje i nastavi gdje je stalo; ne radi ispočetka.

## Cilj faze

Kostur aplikacije koji se diže na SQLite-u i PostgreSQL-u, s kompletnim modelom podataka, migracijama, templating sustavom, sigurnosnim headerima i temeljem dizajna. Bez funkcionalnosti (auth, vozila) — one dolaze u sljedećim fazama.

## Zadaci

1. **Inicijalizacija**
   - `git init`, `.gitignore` (data/, .env, __pycache__, .venv, node_modules; screenshotove u `docs/screenshots/` commitaj), `.gitattributes` (`* text=auto`; `*.sh`, `*.py`, `Dockerfile`, `Caddyfile`, `*.yml` s `eol=lf` — repozitorij se commita s Windowsa, a shell/Docker datoteke idu na Linux VPS), `requirements.txt` s pinanim verzijama (fastapi, uvicorn[standard], jinja2, sqlalchemy>=2, alembic, pydantic-settings, psycopg[binary], argon2-cffi, pyotp, qrcode[pil], itsdangerous, nh3, pillow, boto3, httpx, python-multipart) i `requirements-dev.txt` (pytest, ruff, pip-audit, playwright — Chromium instaliraj s `python -m playwright install chromium`; dev alati ne idu u Docker sliku).
   - `run.py`: lokalni razvoj — učita `.env`, pokrene `alembic upgrade head`, `seed --minimal` ako je baza prazna, uvicorn s reloadom na portu 8000.
   - `.env.example` sa **svim** varijablama iz specifikacije (poglavlja 5, 12, 13, 18) i komentarom za svaku: `APP_ENV`, `SECRET_KEY`, `DATABASE_URL`, `BASE_URL`, `HTTPS`, `TRUST_PROXY`, `LANGUAGE`, `STORAGE_BACKEND`, `S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_REGION`, `MEDIA_URL`, `EMAIL_BACKEND`, `EMAIL_FROM`, `BREVO_API_KEY`, `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY`, `UMAMI_SCRIPT_URL`, `UMAMI_WEBSITE_ID`, `INQUIRY_RETENTION_DAYS=365`, `SOLD_VISIBLE_DAYS=30`, `SESSION_HOURS=12`, `MAX_IMAGES_PER_VEHICLE=30`, `MAX_UPLOAD_MB=10`, `ADMIN_IP_ALLOWLIST`, `MAINTENANCE_IN_APP=true`, `SEED_PASSWORD`.
   - `CLAUDE.md` odmah sada (poglavlje 22 specifikacije) — to je memorija projekta za sve sljedeće faze i sesije. Uključi: stack, kako pokrenuti/testirati, strukturu, pravila (podaci tvrtke samo iz postavki; bez CDN-ova i inline skripti; svaki POST ima CSRF; svaki upload kroz `images.py`; svaka admin akcija u audit log; svaki UI string kroz `_()`; migracije Alembicom; `scripts/check.py` prije završetka), popis faza i koja je trenutno gotova.

2. **Konfiguracija i baza**
   - `app/config.py`: `Settings` (pydantic-settings). U `APP_ENV=production` aplikacija odbija start bez `SECRET_KEY` (min 32 znaka) i s `DATABASE_URL` na SQLite.
   - `app/database.py`: engine (SQLite default `sqlite:///./data/app.db` s `check_same_thread=False` i WAL; Postgres iz `DATABASE_URL`), `SessionLocal`, `Base`, `get_db`.
   - `app/models.py`: **svi modeli iz poglavlja 6** (users, sessions, auth_tokens, makes, vehicle_models, vehicles, vehicle_slug_history, vehicle_images, vehicle_views, inquiries, inquiry_notes, subscribers, campaigns, campaign_deliveries, settings, pages, audit_log, email_log) s indeksima (slug, status, make_id, email_hash, created_at…), `created_at/updated_at` defaultima i enumima kao string konstantama (ne DB enum tip — lakše migracije).
   - Alembic: `alembic.ini`, `migrations/env.py` (čita URL iz Settings), inicijalna migracija generirana autogenerateom i **provjerena da radi na SQLite-u i Postgresu** (Postgres: ako je Docker dostupan, podigni `postgres:16` kontejner privremeno; ako nije, zabilježi u PRETPOSTAVKE.md).

3. **Templating i i18n**
   - `app/templating.py`: Jinja `Environment` s `ChoiceLoader([FileSystemLoader("overrides/templates"), FileSystemLoader("app/templates")])`, autoescape uključen, `trim_blocks/lstrip_blocks`.
   - Globali: `site` (dict svih postavki iz tablice `settings` s defaultima iz poglavlja 3, učitan jednom po requestu i keširan 60 s), `_` (i18n), `now`, `config` (samo bezopasne vrijednosti: BASE_URL, UMAMI_*, TURNSTILE_SITE_KEY, LANGUAGE), `csrf_token()`, `flash_messages()`, `static_version` (cache-busting hash).
   - Filteri: `money` (`12.500 €`), `km` (`145.000 km`), `date_hr` (`28.09.2026.`), `datetime_hr`, `nl2br`, `media_url(image, size)`.
   - `app/i18n/__init__.py`: `_(text, **kwargs)` — ključ je hrvatski izvorni tekst; učitava `app/i18n/{LANGUAGE}.json`; nepostojeći ključ vraća tekst. `hr.json` = `{}`, `en.json` s ~30 primjera. `scripts/extract_strings.py` skuplja `_()` pozive iz `.py` i `.html` u JSON (spaja s postojećim).

4. **Aplikacija i middleware** (`app/main.py`)
   - `create_app()`; `SessionMiddleware`-stil potpisani kolačić samo za CSRF token i flash poruke (auth sesije dolaze u fazi 2, na serveru).
   - Middleware za sigurnosne headere točno prema poglavlju 13 (CSP dinamički uključuje Turnstile/Umami/MEDIA_URL host samo kad su konfigurirani; HSTS samo kad `HTTPS=true`).
   - Middleware za pravi IP klijenta (`CF-Connecting-IP`, zatim `X-Forwarded-For`) samo kad `TRUST_PROXY=true`; inače `request.client.host`.
   - Statika na `/static` (cache headeri 1 god. uz `static_version`), media ruta `/media/{path}` za lokalni storage (samo `.webp` iz `data/media`, bez path traversala), `/zdravlje` (JSON `{"status":"ok","db":"ok"}`, bez detalja o verzijama).
   - Handleri 404 i 500 s templateima u dizajnu stranice (500 bez stack tracea; u `APP_ENV=development` može više detalja).
   - Startup: kreiraj `data/media`, `data/outbox`, `data/backups`.

5. **Servisi (temelj)**
   - `app/security.py`: hashiranje lozinki (Argon2id), generiranje/hashiranje tokena (SHA-256 u bazi, sirovi token samo u linku), CSRF (token u potpisanom kolačiću, `verify_csrf` dependency koji uspoređuje s `csrf_token` poljem forme; 403 bez njega), in-memory rate limiter `rate_limit(scope, limit, window_s)` po IP-u s napomenom o Redisu, Fernet šifriranje izvedeno iz `SECRET_KEY` (za TOTP tajne).
   - `app/services/storage.py`: `LocalStorage` (data/media) i `S3Storage` (boto3, S3-kompatibilan endpoint) iza istog sučelja (`save(key, bytes, content_type)`, `delete(key)`, `url(key)`); izbor po `STORAGE_BACKEND`.
   - `app/services/audit.py`: `log(db, user_id, action, entity_type, entity_id, details=None, ip=None)` — details nikad ne sadrže osobne podatke kupaca.
   - `app/seed.py` s `--minimal`: postavke s placeholderima iz poglavlja 3 (idempotentno — ne pregazi postojeće vrijednosti) i pet stranica (`o-nama`, `usluge`, `privatnost`, `kolacici`, `uvjeti`) s lorem ipsum strukturom i oznakama `[PRAVNIK: dopuniti]` prema poglavlju 14. Puni demo seed dolazi u fazi 7.

6. **Temelj dizajna**
   - `app/static/css/public.css`: CSS varijable (`--color-primary`, `--color-accent`, neutrali, razmaci, radijusi, sjene, tipografska skala), reset, sistemski font stack, tipografija, layout (container, grid), gumbi (primarni/sekundarni/ghost), forme (input, select, checkbox, greške), kartice, badge, alert/flash, tablica, header/nav (s mobilnim izbornikom, vanilla JS), footer. Mobile-first, 360–1440 px, vidljiv focus, kontrast AA.
   - `app/static/css/admin.css`: isti design tokens, sidebar layout (sklopiv na mobitelu), tablice, forme, kartice, flash.
   - `app/static/js/public.js` i `admin.js`: zasad mobilni izbornik, zatvaranje flash poruka, potvrda prije brisanja (`data-confirm`).
   - `app/templates/public/base.html`: `<head>` s meta/OG blokovima (`{% block meta %}`), `<style>` s bojama iz `site` (inline stilovi dopušteni, skripte ne), link na `public.css` + `overrides/static/custom.css` ako postoji (mount `/static/custom`), Umami skripta samo ako je konfigurirana; header (tekst `LOGO` u okviru ili `<img>` ako `site.logo_key`; nav: Vozila, Usluge, O nama, Kontakt; telefon `tel:`), `{% block content %}`, footer s impressumom (naziv, adresa, OIB, email, telefon iz `site`), linkovima na pravne stranice, društvenim mrežama i copyright `© {godina} {site.company_name}`.
   - `app/templates/admin/base.html`: kostur sa sidebarom (sve stavke navigacije iz poglavlja 10; nepostojeće rute zasad vode na stranicu "U izradi") — bez zaštite prijavom do faze 2.
   - `app/templates/public/home.html` privremeno: hero s `site.hero_title`/`hero_subtitle` i tekstom lorem — pravi sadržaj u fazi 4. `404.html`, `500.html`.
   - `overrides/README.md` s objašnjenjem mehanizma i primjerom overridea (poglavlje 17), `overrides/templates/.gitkeep`, `overrides/static/.gitkeep`.

7. **Dokumentacija i provjera**
   - `README.md` kostur: što je ovo, brzi start lokalno, env varijable, struktura (dopunjava se u kasnijim fazama).
   - `docs/PRETPOSTAVKE.md` s prvim zapisima.
   - `tests/conftest.py` (test app na privremenom SQLite-u, TestClient) i `tests/test_temelj.py`: `/` vraća 200 i sadrži `IME PODUZEĆA`, `mailpoduzeca@domena.com`, `+385XXXXXXXXXX`, `LOGO`; `/zdravlje` 200; sigurnosni headeri prisutni; `/media/../secret` odbijen; nepoznata ruta → 404 template.

## Provjera prije završetka

- `python run.py` se digne bez ručnih koraka; `http://localhost:8000/` prikazuje header/footer s placeholderima; `/zdravlje` vraća 200.
- Migracije prolaze na SQLite-u i (ako je moguće) Postgresu.
- `ruff check .` i `pytest` prolaze.
- Nema vanjskih URL-ova u HTML-u naslovnice (curl + grep za `http` u `src=`/`href=` osim vlastitih).
- Git commit: `Faza 1: temelj projekta`.

## Ne raditi u ovoj fazi

Prijavu, korisnike, vozila, upite, newsletter, Docker (osim privremenog Postgresa za test migracija).

## Završni izvještaj faze

Kratko: što je napravljeno (popis datoteka po mapama), kako pokrenuti, što je zabilježeno u PRETPOSTAVKE.md, poznati nedostaci, potvrda da testovi prolaze.
