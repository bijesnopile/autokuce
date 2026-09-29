# Autokuća — web-platforma za autokuće (MVP template)

Kompletan, pokretljiv predložak web-stranice i administracije za autokuće u Hrvatskoj: oglasi vozila
(osobni automobili, kombiji, motocikli, kamperi, kamioni) s galerijom i specifikacijama, upiti kupaca
s mini-CRM-om, newsletter s double opt-inom, administracija s obaveznom 2FA, statistikom, audit logom
i alatom za prava ispitanika (GDPR). Stranica je brza, bez vanjskih resursa i kolačića za praćenje,
optimizirana za tražilice (JSON-LD, sitemap) i mobitele.

Jedna instalacija = jedna autokuća na vlastitoj domeni, s vlastitom bazom; sve instalacije rade kao
Docker kontejneri na jednom VPS-u iza zajedničkog Caddyja i Cloudflarea. Svi podaci tvrtke su
placeholderi (`IME PODUZEĆA`, `LOGO`, lorem ipsum, generirane slike vozila) — klijent unese svoje
podatke u **Admin → Postavke** i cijela stranica (i emailovi) se promijeni bez diranja koda.

Stack: Python 3.11+, FastAPI, Jinja2 (SSR), SQLAlchemy 2 + Alembic, PostgreSQL 16 (SQLite lokalno),
vlastiti CSS i vanilla JS (bez build koraka), Pillow, nh3, argon2, pyotp. Detalji: [docs/ARHITEKTURA.md](docs/ARHITEKTURA.md).

## Brzi start lokalno (Windows / Linux, bez Dockera)

Potrebno: Python 3.11+ i Git.

```bash
python -m venv .venv && .venv/Scripts/activate      # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt                  # (PowerShell: .venv\Scripts\Activate.ps1)
python run.py
```

`run.py` primijeni migracije, na praznoj bazi napuni **cijeli demo** (16 vozila sa slikama, upiti,
pretplatnici, statistika) i pokrene server s automatskim ponovnim učitavanjem:
<http://localhost:8000> (javno) i <http://localhost:8000/admin>. Baza je `data/app.db` (SQLite),
emailovi se spremaju u `data/outbox/*.eml`.

| Korisnik | Uloga | Lozinka |
|---|---|---|
| `admin@domena.com` | superadmin | `SEED_PASSWORD` (zadano `Promijeni-me-2026!`) |
| `vlasnik@domena.com` | vlasnik | isto (samo demo) |
| `prodavac1@domena.com` | prodavač | isto (samo demo) |

Pri **prvoj prijavi** sustav traži postavljanje dvofaktorske autentikacije: skeniraj QR kod
aplikacijom (Google/Microsoft Authenticator, 1Password…), upiši kod i spremi 10 kodova za oporavak.

Provjera kvalitete (ruff, format, pytest, pip-audit): `python scripts/check.py`. Nakon promjene
pinova: `python scripts/check_wheels.py` (ima li svaki paket binarni wheel za Docker sliku).
Screenshotovi i prolaz tijekova kao klijent: `python -m playwright install chromium` pa
`python scripts/screenshots.py` (vlastita privremena instanca, rezultat u `docs/screenshots/`).

## Brzi start u Dockeru (demo ili jedan klijent)

```bash
docker compose up -d --build
```

Bez `.env` diže se lokalni demo na <http://localhost> (app + PostgreSQL 16 + Caddy; `DEMO_SEED=true`,
HTTP bez TLS-a, emailovi u `data/outbox`). `SECRET_KEY` se tada **jednom** generira u
`data/.secret_key` (`app.cli ensure-secret-key`) i više nikad ne mijenja; bez trajnog `data/` volumena
start se odbija. Pri svakom startu `app.cli check-secret-key` uspoređuje ključ s otiskom u bazi i
odbija start ako se ključ promijenio (izgubljen `data/`, pogrešan `.env`) — inače bi 2FA prestala raditi.
Za jednog klijenta bez zajedničkog Caddyja kopiraj `.env.example` u `.env` i postavi barem `DOMAIN`,
`BASE_URL=https://…`, `HTTPS=true`, `SECRET_KEY`, `POSTGRES_PASSWORD`, `SEED_PASSWORD`, `DEMO_SEED=false`,
`EMAIL_BACKEND=brevo` + ključ. Više klijenata na istom VPS-u: [Deployment](#deployment-više-klijenata-na-jednom-vps-u).

Kontejner `app` pri svakom startu čeka bazu, pokreće `alembic upgrade head` i seed (na praznoj bazi
minimalni ili demo; na postojećoj samo nove ključeve postavki), zatim uvicorn s 2 workera
(`WEB_CONCURRENCY`) kao korisnik `app`. Healthcheck: `GET /zdravlje`.

## Konfiguracija (env varijable)

Sve varijable s komentarima su u [`.env.example`](.env.example). Prazna vrijednost = zadano.
**[P]** = obavezno u produkciji (aplikacija odbija start bez `SECRET_KEY` ≥ 32 znaka i PostgreSQL-a).

| Varijabla | Zadano | Opis |
|---|---|---|
| `APP_ENV` | `development` (Docker: `production`) | `development` / `production` / `test` |
| `SECRET_KEY` **[P]** | generira se lokalno | potpis kolačića, šifriranje 2FA tajni |
| `DATABASE_URL` **[P]** | SQLite `data/app.db` | `postgresql://korisnik:lozinka@db:5432/baza` |
| `BASE_URL` **[P]** | `http://localhost:8000` | javni URL (emailovi, sitemap, canonical) |
| `HTTPS` | `false` | `true` → Secure kolačići + HSTS |
| `TRUST_PROXY` | `false` | `true` iza Caddyja/Cloudflarea (pravi IP) |
| `LANGUAGE` | `hr` | jezik sučelja (`en` je primjer) |
| `DATA_DIR`, `OVERRIDES_DIR` | `./data`, `./overrides` | podaci (media, outbox, backupi); prilagodbe |
| `LOG_LEVEL` | `INFO` | razina logiranja |
| `STORAGE_BACKEND` | `local` | `local` (`data/media`) ili `s3` |
| `S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_REGION`, `MEDIA_URL` | — | R2 / Hetzner Object Storage, CDN URL slika |
| `EMAIL_BACKEND` | `file` | `file` (`data/outbox`), `console`, `brevo` |
| `EMAIL_FROM` **[P]**, `BREVO_API_KEY` | `noreply@domena.com`, — | pošiljatelj (verificirana domena), Brevo ključ |
| `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY` | — | Cloudflare Turnstile na javnim formama |
| `UMAMI_SCRIPT_URL`, `UMAMI_WEBSITE_ID` | — | analitika bez kolačića |
| `INQUIRY_RETENTION_DAYS` | `365` | brisanje upita |
| `SOLD_VISIBLE_DAYS` | `30` | prodano vozilo javno vidljivo, zatim arhiva |
| `SESSION_HOURS` | `12` | trajanje admin sesije |
| `MAX_IMAGES_PER_VEHICLE`, `MAX_UPLOAD_MB` | `30`, `10` | ograničenja uploada |
| `ADMIN_IP_ALLOWLIST` | — | `/admin` samo s ovih IP-ova/CIDR-ova |
| `MAINTENANCE_IN_APP` | `true` | dnevno održavanje u aplikaciji u 04:00 |
| `SEED_PASSWORD` **[P]** | `Promijeni-me-2026!` | lozinka seed korisnika (samo pri prvom seedu) |
| `DEMO_SEED` | `false` (Docker bez `.env`: `true`) | demo podaci pri prvom startu |
| `DOMAIN` **[P]**, `POSTGRES_PASSWORD` **[P]**, `POSTGRES_USER`, `POSTGRES_DB` | — | Docker Compose / Caddy |
| `AUTOKUCA_IMAGE`, `WEB_CONCURRENCY` | `autokuca:latest`, `2` | Docker slika, broj workera |
| `BACKUP_AGE_RECIPIENT` / `BACKUP_GPG_RECIPIENT`, `BACKUP_RCLONE_REMOTE`, `BACKUP_RETENTION_DAYS` | —, —, `30` | `deploy/backup.sh` (obično u `deploy/backup.env`) |

## Struktura projekta

```
app/
  main.py          aplikacija, middleware (pravi IP, sigurnosni headeri/CSP, 500, IP allowlist), rute
  config.py        postavke iz env-a;  database.py  engine/sesije;  models.py  svi modeli
  security.py      Argon2id, tokeni, CSRF, rate limit, TOTP, Fernet, sanitizacija
  permissions.py   uloge i ovlasti, admin navigacija;  deps.py  prijava, ovlasti, CSRF ovisnosti
  templating.py    Jinja2 (overrides → app), filteri, render()
  vehicle_schema.py  vrste vozila, polja, opcije, oprema, statusi — jedini izvor istine
  services/        site, storage, images, vehicles, inquiries, newsletter, email, seo, stats,
                   charts, maintenance, audit, auth, turnstile, placeholder_images
  routers/         public, seo, admin_* (auth, users, audit, catalog, vehicles, inquiries,
                   newsletter, settings, pages, privacy, dashboard)
  templates/       public/, admin/, emails/;  static/  css/, js/, img/;  i18n/  prijevodi
  cli.py, seed.py, seed_demo.py, seed_catalog.py, seed_content.py
migrations/        Alembic
docker/            entrypoint.sh
deploy/            caddy/ (zajednički Caddy), client-template/, new-client.sh, remove-client.sh,
                   update-all.sh, backup.sh, restore.sh, crontab.example, backup.env.example
overrides/         prilagodbe po klijentu (templatei, custom.css) — overrides/README.md
scripts/           check.py, screenshots.py, extract_strings.py, make_placeholder_images.py
tests/             pytest (Windows i Linux; TEST_DATABASE_URL=postgresql://… za PostgreSQL)
docs/              specifikacija, arhitektura, sigurnost, GDPR, onboarding, roadmap, pravno/,
                   pretpostavke, izvještaji faza, screenshots/
Dockerfile, docker-compose.yml, Caddyfile, run.py, requirements*.txt, pyproject.toml
```

## Funkcionalnosti ukratko

- **Javno**: naslovnica (hero + brza pretraga, istaknuta i nova vozila, "Zašto mi", newsletter,
  kontakt), `/vozila` (filteri kao GET parametri, sortiranje, paginacija), detalj vozila (galerija s
  lightboxom i swipeom, specifikacije, oprema, video na klik, upit, dogovor pregleda, slična vozila,
  ispis), kontakt, CMS i pravne stranice, 404/410/500. SEO: title/description, canonical, Open Graph,
  JSON-LD (`AutoDealer`, `Car`/`Motorcycle`/`Vehicle` + `Offer`, `BreadcrumbList`), sitemap, robots,
  301 sa starih URL-ova.
- **Upiti (mini-CRM)**: tri vrste (vozilo, pregled, opći), zaštita (CSRF, honeypot, < 3 s, Turnstile,
  rate limit), privola s dokazom, email dealeru s `Reply-To`, inbox s filterima, status, dodjela,
  bilješke, CSV.
- **Newsletter**: prijava s privolom, double opt-in, odjava jednim klikom (RFC 8058) s anonimizacijom,
  kampanje u editoru s umetanjem vozila, testni email, slanje u serijama, izvještaj.
- **Podstranice**: Usluge (kartice usluga iz uređivog teksta — svaki naslov H3 postaje kartica,
  koraci kupnje, CTA), O nama (podaci tvrtke, brojke iz trenutne ponude, "Zašto kupiti kod nas").
  "Zašto kupiti kod nas" uređuje se u Postavke → Izgled (jedna stavka po retku `Naslov | opis`) i
  prikazuje na naslovnici, O nama i uz svako vozilo.
- **Administracija**: nadzorna ploča, statistika (SVG grafovi, CSV), vozila (dinamička forma po vrsti,
  statusi, dupliciranje, slike: drag&drop, redoslijed, alt, WebP), katalog marki (CSV uvoz), korisnici
  (pozivnice, uloge, reset 2FA), postavke (podaci tvrtke, logo, boje, pravno), stranice, prava
  ispitanika, audit log, sustav (dijagnostika, testni email, održavanje).
- **Operativa**: dnevno održavanje (retencija), šifrirani backupi s provjerom, skripte za klijente.

## Kako dodati…

**Novo polje za vrstu vozila** (bez migracije, sprema se u `vehicles.attributes`) — rječnik u
`TYPE_FIELDS["<vrsta>"]` u [`app/vehicle_schema.py`](app/vehicle_schema.py):

```python
({"key": "sleeping_places", "label": "Broj ležajeva", "type": "int", "min": 1, "max": 10},)
```

Tipovi: `text`, `int`, `float`, `select` (+ `options` = lista `(kod, labela)`), `bool`, `month`, `url`;
opcionalno `required`, `unit`, `min`, `max`, `help`. Forma, validacija, prikaz i filteri se generiraju.

**Zajedničko polje s vlastitom kolonom**: kolona u `app/models.py` → `alembic revision --autogenerate
-m "opis"` (pregledaj migraciju) → rječnik u `COMMON_FIELDS` (s `group`).

**Novu vrstu vozila**: unos u `VEHICLE_TYPES` i `TYPE_FIELDS` (`vehicle_schema.py`), kod u
`models.VEHICLE_TYPES`, po želji opremu u `EQUIPMENT` (ključ `types`) i siluetu u
`services/placeholder_images.py`. **Stavku opreme**: `{"code", "label", "cat", "types"}` u `EQUIPMENT`.

**Novi jezik sučelja**: `python scripts/extract_strings.py --lang en` → prevedi vrijednosti u
`app/i18n/en.json` → `LANGUAGE=en`. Sadržaj (opisi, stranice) je jednojezičan — put do prijevoda:
[ARHITEKTURA.md → 6](docs/ARHITEKTURA.md#6-put-do-višejezičnosti-sadržaja).

**Novu vrstu upita**: kod i labela u `INQUIRY_TYPE_LABELS` (`services/inquiries.py`) i
`models.INQUIRY_TYPES`, varijanta forme u `templates/public/_inquiry_form.html`, dodatna polja u
`inquiries.extra` (JSON) s validacijom u `validate_inquiry`, prikaz u `admin/inquiries/detail.html` i
emailu `emails/inquiry_notification.*`.

**Novu postavku tvrtke**: ključ u `DEFAULTS` (`services/site.py`), polje u `FIELDS`
(`routers/admin_settings.py`), u templateu `{{ site.kljuc }}`.

**Vlastiti raspored CMS stranice**: `templates/public/pages/<slug>.html` (ili isto u `overrides/templates/`)
— dobiva `page`, `lead`, `rest`, `sections` (uvod, kartice iz H3, završni dio) i za O nama `stats`.

Pravila za svaku promjenu (CSRF, audit, `_()`, bez inline skripti i vanjskih resursa, migracije,
`scripts/check.py`) su u [CLAUDE.md](CLAUDE.md).

## Deployment: više klijenata na jednom VPS-u

Raspored na serveru (npr. Netcup VPS, Ubuntu/Debian): klon ovog repozitorija u `/opt/autokuca`,
klijenti u `/opt/autokuca/clients/<ime>/` (gitignored).

**Prvi put na VPS-u**

1. Docker Engine + Compose plugin (službene upute za distribuciju), `git`, `age` (`apt install age`),
   `rclone` (+ `rclone config` za off-site odredište). Vremenska zona: `timedatectl set-timezone
   Europe/Zagreb`. Firewall i SSH: [docs/SIGURNOST.md → 4](docs/SIGURNOST.md#4-preporuke-za-server-vps).
2. `git clone <repo> /opt/autokuca && cd /opt/autokuca && docker build -t autokuca:latest .`
3. Zajednički Caddy: `cd deploy/caddy && docker compose up -d` (mreža `web`, portovi 80/443). Po želji
   `email` u `deploy/caddy/Caddyfile`.
4. Backup: `cp deploy/backup.env.example deploy/backup.env`, upiši javni age ključ i rclone odredište;
   cron: `sudo cp deploy/crontab.example /etc/cron.d/autokuca`.

**Novi klijent (5 koraka)**

1. Cloudflare: domena, DNS `A` zapis (+`www`) na IP VPS-a s proxyjem, SSL **Full (strict)**, Origin
   certifikat u `deploy/caddy/certs/<domena>/{cert.pem,key.pem}`.
2. `deploy/new-client.sh <ime> <domena>` — kreira `clients/<ime>/` (compose iz predloška, `.env` s
   generiranim `SECRET_KEY`, `POSTGRES_PASSWORD`, `SEED_PASSWORD`), dodaje `deploy/caddy/sites/<ime>.caddy`,
   pokreće app + bazu (migracije, minimalni seed; `--demo` za demo podatke), reloada Caddy i ispisuje
   pristupne podatke.
3. U `clients/<ime>/.env` upiši Brevo, Turnstile (i po želji Umami/S3) → `docker compose -p ak_<ime>
   --project-directory clients/<ime> up -d`. Brevo domena: SPF, DKIM, DMARC.
4. Prijava, 2FA, Postavke (podaci tvrtke, logo, boje), pravni tekstovi od pravnika, korisnici, vozila.
5. Provjera: testni upit, newsletter, `deploy/backup.sh <ime>`, uptime monitor.

Cijela checklista: [docs/ONBOARDING-KLIJENTA.md](docs/ONBOARDING-KLIJENTA.md).
Uklanjanje klijenta (backup → arhiva → uklanjanje): `deploy/remove-client.sh <ime>`.

**TLS iza Cloudflarea**: s narančastim oblakom Cloudflare se spaja na server preko HTTPS-a i u načinu
"Full (strict)" provjerava certifikat. Let's Encrypt HTTP-01 izazov iza proxyja prolazi samo bez
preusmjeravanja HTTP→HTTPS, a TLS-ALPN-01 nikad, pa su podržane dvije varijante: **Cloudflare Origin
certifikat** (preporučeno; `new-client.sh` ga koristi ako postoji) ili **Let's Encrypt preko DNS
izazova** (Caddy s modulom `caddy-dns/cloudflare`, `deploy/caddy/Dockerfile.cloudflare`). Bez proxyja
(sivi oblak) Caddy sam dobiva Let's Encrypt certifikat.

## Ažuriranje

```bash
cd /opt/autokuca && deploy/update-all.sh          # git pull + docker build + za svakog klijenta:
                                                  # backup → up -d (migracije) → čekaj /zdravlje
deploy/update-all.sh --pull                       # slika iz registryja umjesto builda
deploy/update-all.sh autokuca-horvat              # samo jedan klijent
```

Kod prve greške skripta staje (ostali klijenti ostaju na staroj verziji) i ispisuje log. Prethodna
slika ostaje kao `autokuca:previous`; kako su migracije već primijenjene, siguran povratak je
`deploy/restore.sh` iz backupa napravljenog neposredno prije ažuriranja.

## Backup i vraćanje

`deploy/backup.sh <ime|all>` (cron u 03:00): `pg_dump` (custom format, unutar kontejnera baze — bez
lozinke u listi procesa) → gzip → provjera integriteta (`gzip -t` + `pg_restore --list`) → šifriranje
**age** (ili GPG) javnim ključem → `clients/<ime>/data/backups/` → `rclone` na off-site odredište →
retencija 30 dana lokalno i na odredištu. Uz `STORAGE_BACKEND=local` i slike se kopiraju
(`rclone sync`, obrisane ostaju 30 dana u `media-deleted/`). Nešifrirani backup se odbija.

Šifriranje je obavezno i provjerava se **prije** dumpa: bez `age` (ili `gpg`), s neispravnim
ključem primatelja ili bez ključa skripta pada s uputom (`sudo apt install age`) i ne sprema ništa.

**SECRET_KEY nije u backupu baze.** Za vraćanje na drugi server trebaju i `clients/<ime>/.env`
(odnosno `data/.secret_key`) — čuvaj ih u password manageru. Vraćena baza s drugim ključem: start se
odbija (`check-secret-key`), jer bi 2FA tajne bile nečitljive.

**Vraćanje** (`deploy/restore.sh <ime> <datoteka> [--yes]`):

1. Privatni age ključ (`BACKUP_AGE_IDENTITY=/sigurna/putanja/autokuca-backup.key` u `deploy/backup.env`
   ili okruženju) ili GPG ključ u keyringu.
2. `deploy/restore.sh autokuca-horvat autokuca-horvat-20260928-030000.dump.gz.age` — datoteka se traži
   lokalno, pa na rclone odredištu; skripta dešifrira, provjeri arhivu, traži potvrdu (upis imena),
   zaustavi aplikaciju, vrati u **novu** bazu, zamijeni je s trenutnom (stara ostaje kao
   `<baza>_old_<datum>`), pokrene aplikaciju i čeka `/zdravlje`.
3. Slike (lokalna pohrana): `rclone copy <remote>/<ime>/media clients/<ime>/data/media`.
4. Nakon provjere stranice obriši staru bazu (naredbu ispisuje skripta).

**Test vraćanja** (preporuka: mjesečno i pri onboardingu) — na testnom klijentu (`new-client.sh test-
restore test.domena.hr`) vrati zadnji backup produkcijskog klijenta i provjeri broj vozila i upita.
Skripte su provjerene lokalno bez Dockera (`AK_PG_LOCAL=1`, PostgreSQL 16, GPG): backup → brisanje
podataka → vraćanje → podaci ponovno na mjestu (docs/IZVJESTAJI/faza-08.md).

## Prilagodbe po klijentu (overrides)

`clients/<ime>/overrides/` (lokalno `overrides/`) montira se u kontejner samo za čitanje: vlastiti
templatei (`overrides/templates/public/home.html` ima prednost pred originalom) i
`overrides/static/custom.css` (učitava se nakon glavnog CSS-a). Nova verzija slike ne dira prilagodbe.
Primjeri i pravila: [overrides/README.md](overrides/README.md).

## Sigurnost i GDPR (sažetak)

Argon2id lozinke, **obavezna 2FA** za sve korisnike administracije, lockout i rate limit, sesije na
serveru, CSRF na svakom POST-u, strogi CSP bez inline skripti, sigurnosni headeri i HSTS, provjera i
re-enkodiranje slika (bez EXIF/GPS), nh3 sanitizacija, audit log, pip-audit, non-root Docker.
Privola s dokazom (vrijeme, IP, preglednik, verzija politike), double opt-in, odjava jednim klikom s
anonimizacijom, automatsko brisanje (upiti 365 dana…), alat za pristup/izvoz/brisanje podataka osobe,
bez vanjskih resursa i kolačića za praćenje, impressum u podnožju.

- [docs/SIGURNOST.md](docs/SIGURNOST.md) — model prijetnji, mjere (s testovima), što ostaje
- [docs/GDPR.md](docs/GDPR.md) — uloge, pravne osnove, rokovi, podizvršitelji, postupci (30 dana, AZOP 72 h)
- [docs/pravno/UGOVOR-O-OBRADI-PODATAKA.md](docs/pravno/UGOVOR-O-OBRADI-PODATAKA.md) — predložak čl. 28

Pravni tekstovi na stranicama su lorem ipsum s oznakama `[PRAVNIK: dopuniti]` — **pravnik ih mora
napisati/pregledati prije objave** za pravog klijenta.

## Premium roadmap

Kalkulator leasinga, novosti/blog, dodatne vrste upita, automatsko zamagljivanje tablica, XML feedovi
prema portalima, višejezični sadržaj, SMS/WhatsApp, više poslovnica: [docs/ROADMAP.md](docs/ROADMAP.md).

## Dokumentacija

[Specifikacija](docs/SPECIFIKACIJA.md) · [Arhitektura](docs/ARHITEKTURA.md) · [Sigurnost](docs/SIGURNOST.md) ·
[GDPR](docs/GDPR.md) · [Onboarding klijenta](docs/ONBOARDING-KLIJENTA.md) ·
[Pretpostavke i odluke](docs/PRETPOSTAVKE.md) · [Izvještaji faza](docs/IZVJESTAJI/) ·
[Screenshotovi](docs/screenshots/) · [CLAUDE.md](CLAUDE.md) (rad s Claude Codeom)

## Licenca

Sva prava pridržana — [IME PODUZEĆA VLASNIKA PLATFORME].
