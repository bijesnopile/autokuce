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
| `vlasnik@domena.com` | vlasnik (samo demo seed) | isto |
| `prodavac1@domena.com` | prodavač (samo demo seed) | isto |

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

## Newsletter

Prijava (podnožje, naslovnica, stranica vozila) s privolom → email s poveznicom za potvrdu (double
opt-in, 7 dana) → tek potvrđeni primaju kampanje. Svaki email ima impressum, poveznicu na politiku
privatnosti i odjavu jednim klikom (`List-Unsubscribe`); pri odjavi se adresa odmah briše (ostaje samo
hash). Kampanje se uređuju u adminu (editor s gumbom "Umetni vozilo"), pregled, testni email, slanje
u pozadini u serijama od 50, izvještaj poslano/neuspjelo i ponovno slanje neuspjelima.

**Brevo po klijentu** (`EMAIL_BACKEND=brevo`): u Brevu dodaj i verificiraj domenu pošiljatelja
(Senders & IP → Domains), u DNS klijenta upiši zapise koje Brevo zada — **SPF** (`include:spf.brevo.com`
u postojeći SPF zapis), **DKIM** (TXT zapis `brevo._domainkey`) i **DMARC** (`_dmarc` TXT, npr.
`v=DMARC1; p=none; rua=mailto:...` pa kasnije `quarantine`). `EMAIL_FROM` mora biti adresa na toj
domeni. Bez verifikacije emailovi završavaju u spamu ili ih Brevo odbija.

## Administracija — nadzorna ploča, postavke, stranice, GDPR

- **Nadzorna ploča** (`/admin`): aktivna vozila, novi upiti (i koliko ih čeka > 48 h), potvrđeni
  pretplatnici, pregledi oglasa (30 dana, promjena u %), graf pregleda po danu, zadnji upiti,
  najgledanija vozila i podsjetnici (vozila bez slika, upiti bez odgovora, stare skice kampanja).
- **Statistika** (`/admin/statistika`, 30/90/365 dana): pregledi po danu, pregledi/upiti/konverzija po
  vozilu, upiti po vrsti i statusu, prosječno vrijeme do prvog kontakta, newsletter po tjednu, top
  marke; CSV izvoz tablica.
- **Postavke** (`/admin/postavke`, vlasnik+): podaci tvrtke (impressum), kontakt i mreže, izgled
  (logo, primarna i akcentna boja s provjerom kontrasta, tekstovi naslovnice i podnožja), pravno
  (verzija politike privatnosti, traka za kolačiće, podsjetnik za zamagljivanje tablica). Promjene su
  odmah vidljive na cijeloj stranici i u emailovima.
- **Stranice** (`/admin/stranice`): Usluge, O nama, Politika privatnosti, Kolačići, Uvjeti korištenja —
  editor, pregled, objava/skrivanje; svako spremanje povećava verziju. Pravne stranice sadrže oznake
  `[PRAVNIK: dopuniti]` koje prije objave treba zamijeniti tekstom koji je pregledao pravnik.
- **Prava ispitanika** (`/admin/gdpr`, vlasnik+): pronađi sve podatke osobe po emailu (i telefonu),
  izvoz u JSON i brisanje (upiti, bilješke, zapisi emailova; pretplata se anonimizira).
- **Sustav** (`/admin/sustav`, superadmin): konfiguracija bez tajni, testni email, pregled i ručno
  pokretanje održavanja.

**Traka za kolačiće** je zadano isključena jer platforma koristi samo nužne kolačiće i Umami bez
kolačića. Ako klijent doda alat koji traži privolu, uključi traku u Postavkama → Pravno i skriptu
dodaj u `overrides/templates/public/base.html` (blok `consent_scripts`) kao
`<script type="text/plain" data-consent="analytics" data-src="https://…"></script>` — učitat će se
tek kad posjetitelj klikne "Prihvaćam".

## Održavanje i čuvanje podataka

Jednom dnevno (04:00, Europe/Zagreb) pokreće se održavanje — u aplikaciji (`MAINTENANCE_IN_APP=true`,
zadano; od više workera radi samo jedan) ili cronom:

```bash
python -m app.cli maintenance --dry-run   # samo prikaži što bi se obrisalo
python -m app.cli maintenance
```

| Podaci | Pravilo |
|---|---|
| Upiti i bilješke | brišu se `INQUIRY_RETENTION_DAYS` (365) dana nakon primitka |
| Nepotvrđene prijave na newsletter | brišu se 7 dana nakon slanja potvrde |
| Odjavljeni pretplatnici (samo hash) | brišu se nakon 3 godine |
| Prodana vozila | arhiviraju se `SOLD_VISIBLE_DAYS` (30) dana nakon prodaje (javno 410) |
| Sesije i tokeni | brišu se nakon isteka |
| Zapisi o poslanim emailovima | 90 dana |
| Audit log | 2 godine |
| Dnevni pregledi oglasa | 400 dana |

## Demo podaci (seed)

`python run.py` na praznoj bazi u razvoju (`APP_ENV=development`) puni **cijeli demo**: 16 vozila svih
vrsta (s 5–8 generiranih fotografija), preglede za 60 dana, 10 upita, 15 pretplatnika, kampanje i
audit zapise. U produkciji se puni samo minimum (postavke, stranice, katalog, superadmin), osim uz
`DEMO_SEED=true` (demo instanca za prezentaciju).

```bash
python -m app.seed               # puni demo (idempotentno — drugi put ništa ne duplicira)
python -m app.seed --minimal     # samo postavke, stranice, katalog marki i superadmin
python -m app.seed --reset-demo  # OBRIŠI sva vozila, upite, newsletter i audit pa ponovno kreiraj demo
```

Demo korisnici (lozinka `SEED_PASSWORD`, zadano `Promijeni-me-2026!`, 2FA se postavlja pri prvoj
prijavi): `admin@domena.com` (superadmin), `vlasnik@domena.com` (vlasnik), `prodavac1@domena.com`
(prodavač). `--reset-demo` u produkciji radi samo uz `DEMO_SEED=true` ili `--potvrdi`.

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
