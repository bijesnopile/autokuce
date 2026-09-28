# Izvještaj — Faza 7: Dashboard, statistika, postavke, stranice, GDPR alat, maintenance, demo seed

Datum: 28.09.2026.

## Što je napravljeno

- **Nadzorna ploča** (`/admin`): četiri kartice (aktivna vozila + rezervirana/skice, novi upiti + bez
  odgovora > 48 h, potvrđeni pretplatnici + novi ovaj mjesec, pregledi 30 dana + promjena u % prema
  prethodnih 30), graf pregleda po danu (inline SVG iz `app/services/charts.py`, tooltip `<title>`),
  zadnjih 10 upita, top 5 vozila po pregledima, podsjetnici (upiti > 48 h, aktivna vozila i skice bez
  slika, neposlane kampanje starije od 7 dana).
- **Statistika** (`/admin/statistika`, 30/90/365 dana): pregledi po danu, tablica pregleda/upita/
  konverzije po vozilu (sortiranje), upiti po vrsti i statusu, prosječno vrijeme do prvog kontakta,
  newsletter prijave/odjave po tjednu (dvostruki SVG graf), top marke. CSV izvoz (`vozila`, `marke`,
  `dani`), audit `stats.export`.
- **Postavke** (`/admin/postavke`, owner+): sekcije Tvrtka, Kontakt i mreže, Izgled, Pravno;
  validacija (email, telefon, OIB ili `XXXXXXXXXXX`, hex boje, URL-ovi), keš `site` se invalidira,
  audit `settings.update` s popisom ključeva. Logo kroz `images.py` (PNG/WebP/JPEG ≤ 2 MB, 200/400 px,
  prozirnost), uklanjanje vraća tekst LOGO. Boje s `<input type="color">`, živim pregledom (gumb,
  oznaka, cijena) i WCAG kontrastom prema bijeloj. Promjena verzije politike upisuje
  `privacy_policy_updated_at`.
- **Traka za kolačiće** (zadano isključena): "Prihvaćam"/"Odbijam" jednako istaknuti, kolačić
  `cookie_consent` (180 dana), skripte `type="text/plain" data-consent="analytics"` učitavaju se tek
  nakon prihvaćanja. Umami (cookieless) bez privole.
- **Stranice** (`/admin/stranice`): lista pet stranica, editor (bez "umetni vozilo"), nh3
  sanitizacija, verzija +1 pri svakom spremanju, objavi/sakrij, pregled neobjavljene stranice.
- **Prava ispitanika** (`/admin/gdpr`, owner+): pretraga po emailu (+ telefon), sažetak upita/bilješki/
  pretplate s privolom, **JSON izvoz** (audit `privacy.export` s hashom), **brisanje** uz upis `OBRIŠI`
  (upiti + bilješke, anonimizacija pretplate, `email_log` po hashu; audit `privacy.delete` s hashom i
  brojevima), napomena o rotaciji backupa (30 dana).
- **Održavanje** (`app/services/maintenance.py`): `run_all(db, dry_run)` s osam koraka, svaki logira
  broj zapisa, audit `system.maintenance` (user_id NULL). `python -m app.cli maintenance [--dry-run]`.
  Dnevna pozadinska nit (`MAINTENANCE_IN_APP=true`) u 04:00 s atomskim preuzimanjem dana
  (`maintenance_last_run`) — jedan izvođač i kad radi više workera.
- **Sustav** (`/admin/sustav`, superadmin — dodatak): konfiguracija bez tajni, dry-run pregled
  održavanja s hrvatskim opisima koraka, ručno pokretanje, testni email.
- **Puni demo seed** (`app/seed_demo.py`): 16 vozila prema poglavlju 19 (8 osobnih, 3 kombija,
  2 motocikla, 2 kampera, 1 kamion; 12 aktivnih, 1 rezervirano, 2 prodana — prije 10 i 45 dana,
  1 skica; 3 istaknuta; "cijena na upit"; stara cijena; 2 nova s potrošnjom i CO2), 5–8 generiranih
  fotografija po vozilu kroz pravi upload pipeline (siluete prema vrsti vozila), pregledi za 60 dana,
  10 upita + 4 bilješke + 3 dodijeljena, 15 pretplatnika (10/3/2), kampanja (9 sent / 1 failed) i
  skica, 3 korisnika, 10 audit zapisa. Idempotentan (oznaka `demo_seeded`), `--minimal`,
  `--reset-demo` (u produkciji samo uz `DEMO_SEED=true` ili `--potvrdi`). `run.py` na praznoj bazi puni
  demo u `development`. Katalog: 31 marka, 243 modela.

## Rute

`/admin`, `/admin/statistika` (+ `/izvoz.csv?tablica=vozila|marke|dani&razdoblje=`),
`/admin/postavke` (GET/POST, `/logo`, `/logo/ukloni`), `/admin/stranice`, `/admin/stranice/{slug}`
(GET/POST, `/objava`, `/pregled`), `/admin/gdpr` (GET/POST, `/izvoz`, `/obrisi`), `/admin/sustav`
(+ `/testni-email`, `/odrzavanje`).

## Pristupni podaci (demo)

| Korisnik | Uloga | Lozinka |
|---|---|---|
| `admin@domena.com` | superadmin | `SEED_PASSWORD` (zadano `Promijeni-me-2026!`) |
| `vlasnik@domena.com` | vlasnik (owner) | isto |
| `prodavac1@domena.com` | prodavač | isto |

Svi bez 2FA — prva prijava traži postavljanje (QR + kodovi za oporavak).

## Retencijska pravila (kako su implementirana)

| Korak | Pravilo |
|---|---|
| `old_inquiries` | upiti + bilješke stariji od `INQUIRY_RETENTION_DAYS` (365) od `created_at` |
| `pending_subscribers` | nepotvrđeni 7 dana nakon zadnjeg slanja potvrde |
| `old_unsubscribed` | anonimizirani (samo hash) stariji od 3 godine |
| `archived_sold_vehicles` | `sold` → `archived` nakon `SOLD_VISIBLE_DAYS` (30); ne briše se |
| `expired_sessions_tokens` | istekle sesije; tokeni istekli ili iskorišteni prije > 7 dana |
| `old_email_log` | stariji od 90 dana |
| `old_audit` | stariji od 2 godine |
| `old_vehicle_views` | dnevni pregledi stariji od 400 dana |

## Provjera

- Svježa baza (privremeni `DATA_DIR`) + `python run.py` → migracije, puni demo, `/vozila` prikazuje
  14 javnih vozila, bez ručnih koraka.
- Playwright: prijava s 2FA, sve admin stranice s demo podacima, GDPR pretraga, javne stranice desktop
  i mobitel — bez grešaka u konzoli, bez horizontalnog pomicanja (scrollWidth = širina prozora).
- Pregled screenshotova i ispravci: mobilna nadzorna ploča je izlazila iz ekrana (grid `1fr` + `nowrap`
  → `minmax(0, 1fr)`), oznake osi grafa newslettera ponavljale su se ("2, 1, 1, 0, 0" → cjelobrojne
  podjele), dvostruka točka iza datuma u postavkama, sirovi nazivi koraka održavanja, placeholder slike
  s autom i za motocikl/kamper/kamion te natpis ispod oznaka "NOVO/ISTAKNUTO" na karticama.
- Screenshotovi: `admin-dashboard-desktop.png`, `admin-dashboard-mobile.png`,
  `admin-statistika-desktop.png`, `admin-postavke-desktop.png`, `admin-stranice-editor-desktop.png`,
  `admin-gdpr-desktop.png`, ponovno `javno-naslovnica-*`, `javno-lista-*`, `javno-detalj-*` (demo podaci).
- `ruff check .` ✔, `ruff format --check .` ✔, `pytest`: **171 passed** (18 novih u
  `test_dashboard.py`, `test_settings.py`, `test_pages.py`, `test_privacy.py`, `test_maintenance.py`,
  `test_seed.py`).

## Pretpostavke i poznati nedostaci

- Sve odluke: `docs/PRETPOSTAVKE.md` → "Admin: nadzorna ploča, postavke, stranice, GDPR, održavanje,
  demo (faza 7)".
- Pravni tekstovi su lorem ipsum s oznakama `[PRAVNIK: dopuniti]` — pravnik ih mora napisati prije
  objave za pravog klijenta.
- Oznake na x-osi grafova na mobitelu su sitne (SVG se skalira); podaci su dostupni i kroz tooltip i
  tablice/CSV.
