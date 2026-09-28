# Autokuća — MVP template web-platforme za autokuće

Kompletan, pokretljiv predložak web-stranice i administracije za autokuće u Hrvatskoj:
oglasi vozila sa slikama i specifikacijama, upiti kupaca s mini-CRM-om, newsletter s
double opt-inom, admin panel s obaveznom 2FA, statistikom i audit logom. Jedna instalacija =
jedna autokuća na vlastitoj domeni; sve instalacije rade kao Docker kontejneri na jednom VPS-u.

Svi podaci su placeholderi (`IME PODUZEĆA`, `LOGO`, lorem ipsum, generirane slike vozila) —
klijent unese svoje podatke u **Admin → Postavke** i cijela stranica se promijeni bez diranja koda.

> Status: u izradi (faze 1–8). Dokument se dopunjava u svakoj fazi.

## Brzi start lokalno (Windows / Linux, bez Dockera)

Potrebno: Python 3.11+ i Git.

```powershell
# 1. virtualno okruženje
python -m venv .venv
.venv\Scripts\Activate.ps1           # PowerShell
# source .venv/Scripts/activate      # Git Bash na Windowsu
# source .venv/bin/activate          # Linux / WSL / macOS

# 2. ovisnosti
pip install -r requirements-dev.txt

# 3. pokretanje (migracije + seed na praznoj bazi, SQLite u data/app.db)
python run.py
```

Otvori <http://localhost:8000> (javna stranica) i <http://localhost:8000/admin> (administracija).
Emailovi se u razvoju ne šalju nego spremaju u `data/outbox/` (`EMAIL_BACKEND=file`).

Testovi: `python -m pytest -q` · Lint: `ruff check .` i `ruff format --check .`

### Prijava u administraciju

| Korisnik | Uloga | Lozinka |
|---|---|---|
| `admin@domena.com` | superadmin | vrijednost `SEED_PASSWORD` (default `Promijeni-me-2026!`) |

Pri **prvoj prijavi** sustav traži postavljanje dvofaktorske autentikacije (obavezno za sve korisnike):
skenirajte QR kod aplikacijom (Google/Microsoft Authenticator, 1Password…), upišite kod i spremite
10 kodova za oporavak. Ostale korisnike superadmin/vlasnik poziva emailom (Admin → Korisnici).

Korisne naredbe:

```bash
python -m app.cli create-superadmin --email ja@domena.com --password "Duga-Lozinka-2026"
python -m app.cli reset-2fa --email korisnik@domena.com   # izgubljen mobitel
```

### Email

`EMAIL_BACKEND=file` (default) sprema svaku poruku kao `.eml` u `data/outbox/` (otvara se u bilo kojem
mail klijentu). `console` ispisuje u log, `brevo` šalje preko Brevo API-ja (`BREVO_API_KEY`).

## Konfiguracija (env varijable)

Sve varijable s objašnjenjem su u [`.env.example`](.env.example). Lokalno ništa nije obavezno
(`.env` je opcionalan). U produkciji su obavezni `APP_ENV=production`, `SECRET_KEY` (min 32 znaka),
`DATABASE_URL` (PostgreSQL) i `BASE_URL`.

## Struktura projekta

```
app/
  main.py            aplikacija, middleware (sigurnosni headeri, CSP, pravi IP), error stranice
  config.py          postavke iz env-a (pydantic-settings)
  database.py        SQLAlchemy engine i sesije
  models.py          svi modeli baze
  security.py        lozinke (Argon2id), tokeni, CSRF, rate limit, TOTP, šifriranje
  permissions.py     uloge i ovlasti, admin navigacija
  templating.py      Jinja2 (overrides → app), filteri, render()
  services/          site (postavke tvrtke), storage (lokalno/S3), audit, ...
  routers/           javne i admin rute
  templates/         public/, admin/, emails/
  static/            css/, js/, img/
  i18n/              prijevodi (ključ = hrvatski tekst)
migrations/          Alembic migracije
overrides/           prilagodbe po klijentu (templatei, custom.css) — vidi overrides/README.md
scripts/             pomoćne skripte (extract_strings.py, ...)
tests/               pytest
docs/                specifikacija, pretpostavke, izvještaji faza, screenshotovi
prompts/             promptovi po kojima je projekt izgrađen
data/                (gitignored) baza, media, outbox, backupi
```

## Višejezičnost

Svi tekstovi sučelja prolaze kroz `_()`; ključ je hrvatski izvorni tekst. Novi jezik:
`python scripts/extract_strings.py --lang en` → prevedi vrijednosti u `app/i18n/en.json` →
`LANGUAGE=en`.

## Prilagodbe po klijentu

Vidi [`overrides/README.md`](overrides/README.md).
