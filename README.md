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

## Javna stranica i SEO

- Stranice: naslovnica (hero + brza pretraga, istaknuta i zadnje dodana vozila, "Zašto mi",
  newsletter, kontakt), `/vozila` (filteri kao GET parametri — dijeljiv URL, sortiranje, 12 po stranici),
  `/vozila/{marka}-{model}-{godina}-{id}` (galerija s lightboxom, specifikacije, oprema, opis, video na
  klik, upit i dogovor pregleda, slična vozila, ispis), `/kontakt`, `/o-nama`, `/usluge`, pravne stranice.
- SEO: `<title>`/description po stranici, canonical, Open Graph i Twitter Card, JSON-LD (`AutoDealer`,
  `Car`/`Motorcycle`/`Vehicle` + `Offer`, `BreadcrumbList`), `/sitemap.xml`, `/robots.txt`,
  301 sa starog sluga, 410 za prodana/arhivirana vozila.
- Bez vanjskih resursa: nema CDN-a, fontova ni karata (Google Maps je samo poveznica); YouTube se
  učitava tek na klik s `youtube-nocookie.com`. Umami i Turnstile samo ako su konfigurirani.
- OG slika po klijentu: `overrides/static/og-default.png` (1200×630).

## Upiti kupaca (mini-CRM)

Tri vrste upita: za vozilo, dogovor pregleda (s terminom) i opći (kontakt). Zaštita: CSRF, honeypot,
vremenska provjera (< 3 s = bot), Cloudflare Turnstile (ako su postavljeni `TURNSTILE_SITE_KEY` i
`TURNSTILE_SECRET_KEY`), rate limit (5 / 10 min po IP-u, 3 / h po emailu). Uz svaki upit sprema se
privola (vrijeme, IP, preglednik, verzija politike). Dealer dobiva email na "Email za obavijesti o
upitima" (Postavke) s `Reply-To` kupca. U adminu: inbox s filterima, status, dodjela prodavaču,
interne bilješke, "Odgovori emailom", CSV izvoz (Excel). Upiti se automatski brišu nakon
`INQUIRY_RETENTION_DAYS` (365) — `python -m app.cli maintenance`.

**Turnstile u produkciji**: Cloudflare dashboard → Turnstile → Add site (domena klijenta, način
"Managed") → kopiraj Site key i Secret key u `.env` → restart. CSP automatski dopušta
`challenges.cloudflare.com`.

## Vrste vozila i polja

Sve vrste vozila, polja, popisi opcija i oprema definirani su na **jednom mjestu**:
[`app/vehicle_schema.py`](app/vehicle_schema.py). Admin forma, validacija, javne specifikacije i
filteri generiraju se iz njega.

**Novo polje specifično za vrstu** (sprema se u JSON `vehicles.attributes`, bez migracije) — dodaj
rječnik u `TYPE_FIELDS["<vrsta>"]`:

```python
({"key": "sleeping_places", "label": "Broj ležajeva", "type": "int", "min": 1, "max": 10},)
```

Tipovi polja: `text`, `int`, `float`, `select` (+ `options` kao lista `(kod, labela)`), `bool`,
`month`, `url`; opcionalno `required`, `unit`, `min`, `max`, `help`.

**Novo zajedničko polje s vlastitom kolonom**: dodaj kolonu u `app/models.py`, napravi migraciju
(`alembic revision --autogenerate -m "opis"`), pa rječnik u `COMMON_FIELDS` (s `group` = sekcija forme).

**Nova vrsta vozila**: dodaj unos u `VEHICLE_TYPES`, polja u `TYPE_FIELDS`, kod u `models.VEHICLE_TYPES`
i po želji opremu u `EQUIPMENT` (ključ `types`).

**Nova stavka opreme**: dodaj `{"code": ..., "label": ..., "cat": ..., "types": ...}` u `EQUIPMENT`.

Katalog marki i modela uređuje se u adminu (Katalog), a može se uvesti iz CSV-a (`marka;model;tip`).

## Višejezičnost

Svi tekstovi sučelja prolaze kroz `_()`; ključ je hrvatski izvorni tekst. Novi jezik:
`python scripts/extract_strings.py --lang en` → prevedi vrijednosti u `app/i18n/en.json` →
`LANGUAGE=en`.

## Prilagodbe po klijentu

Vidi [`overrides/README.md`](overrides/README.md).
