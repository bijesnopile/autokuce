# Pretpostavke i odluke

Ovdje su zapisane sve odluke koje specifikacija nije izričito definirala, odstupanja i
stvari koje nisu mogle biti testirane. Novi zapisi se dodaju na kraj odgovarajućeg odjeljka.

## Okruženje i alati

- **Python 3.14 lokalno, 3.11 u Dockeru.** Na razvojnom računalu dostupan je samo Python 3.14.
  Sve pinane verzije u `requirements.txt` provjerene su da podržavaju Python ≥ 3.11 (Requires-Python).
- **Windows Smart App Control** blokira nepotpisane nativne module bez reputacije
  (`ImportError: DLL load failed ... Application Control policy`). Najnovije verzije
  `sqlalchemy` (2.1.1) i `nh3` (0.3.7) bile su blokirane, pa su pinane `sqlalchemy==2.1.0`
  i `nh3==0.3.6` (funkcionalno ekvivalentne). Sigurnosne postavke sustava nisu mijenjane.
- **Docker nije instaliran** na razvojnom računalu. Umjesto privremenog `postgres:16` kontejnera
  korištene su prijenosne binarne datoteke **PostgreSQL 16.2** (raspakirane iz pip wheela `pgserver`
  u privremenu mapu izvan projekta, ništa nije instalirano u sustav). Na njima su provjerene
  migracije (`alembic upgrade head` + usporedba s modelima = bez razlike), seed i cijela pytest
  suita (`TEST_DATABASE_URL=... pytest`). `docker compose` nije mogao biti testiran (vidi "Otvoreno").
- Windows konzola (cp1252) ruši `print()` s hrvatskim znakovima kad je izlaz preusmjeren —
  sve ulazne točke (`run.py`, `app.cli`, `app.seed`, `scripts/*`) pozivaju `ensure_utf8_console()`.
- Starlette 1.x `TestClient` izbacuje upozorenje o `httpx` → `httpx2`; upozorenje je utišano
  u `pyproject.toml` jer TestClient radi ispravno.

## Arhitektura

- **Render bez `Jinja2Templates`**: vlastiti `render()` u `app/templating.py` (eksplicitno, jedno mjesto
  za globalne varijable `site`, `csrf_token()`, `flash_messages()`, `current_user`).
- **Klijentsko stanje** (CSRF token, flash poruke, popis pregledanih vozila za brojanje pregleda)
  u potpisanom kolačiću `st` (Starlette `SessionMiddleware`, itsdangerous), HttpOnly, SameSite=Lax,
  bez `Max-Age` (briše se zatvaranjem preglednika). Kolačić se postavlja samo kad se stanje promijeni.
  Admin sesije su zasebno, na serveru (tablica `sessions`) — faza 2.
- **CSRF "vezan uz sesiju"**: token živi u potpisanom kolačiću i **rotira se pri prijavi**
  (novi token za novu admin sesiju). Provjera: polje `csrf_token` ili header `X-CSRF-Token`.
- **Middleware je čisti ASGI** (ne `BaseHTTPMiddleware`) da `BackgroundTasks` rade pouzdano.
- **Stranica 500** renderira se u vlastitom `ErrorPageMiddleware` (unutar middlewarea za headere),
  pa i stranice grešaka imaju sigurnosne headere. Stack trace samo u `APP_ENV=development`.
- **Datumi** u bazi su naivni UTC (prenosivo SQLite ↔ Postgres); prikaz u Europe/Zagreb.
- **Enumi** su string konstante u `models.py`, ne DB enum tipovi (lakše migracije).
- **Dodatne kolone** izvan poglavlja 6 (namjerno, minimalno):
  - `users.totp_last_step` — zaštita od ponovne upotrebe istog TOTP koda.
  - `auth_tokens.created_at`, `campaigns.updated_at` — dijagnostika/sortiranje.
  - `vehicles.color_metallic` — spec traži "metalik" checkbox uz boju.
  - `inquiries.extra` (JSON) — polja budućih vrsta upita (financiranje, zamjena…) bez migracije.
  - `inquiries.contacted_at` — vrijeme prvog kontakta (statistika "prosječno vrijeme do prvog kontakta").
  - `subscribers.confirm_sent_at` — ograničenje ponovnog slanja potvrde (1× u 10 min) i rok tokena.
- `first_registration` i `registered_until` spremaju se kao `Date` (dan = 1), prikaz MM/GGGG.
- **SECRET_KEY u razvoju**: ako nije postavljen, generira se nasumični ključ i sprema u
  `data/.dev_secret_key` (nikad u kodu). U produkciji je obavezan (min 32 znaka).
- `.env` s praznim vrijednostima (npr. kopirani `.env.example`) = default vrijednosti
  (`env_ignore_empty=True`). Testovi ne čitaju `.env`.
- Admin koristi `public.css` + `admin.css` (isti tokeni i komponente, bez dupliciranja).
- `DATA_DIR` (default `./data`) i `OVERRIDES_DIR` dodatne su env varijable (izolacija testova, Docker volumeni).

## Autentikacija i korisnici (faza 2)

- **Jedinstvena poruka o grešci** pri prijavi za nepostojeći email, krivu lozinku i zaključan račun
  ("Prijava nije uspjela… nakon 5 neuspjelih pokušaja račun se zaključava na 15 minuta") — ne otkriva
  postoji li račun ni je li zaključan. Za nepostojeći email izvodi se lažna Argon2 provjera (isto vrijeme).
- **Lockout broji i neuspjele 2FA kodove** (5 uzastopnih neuspjeha lozinke ili koda → 15 min), jer je
  6-znamenkasti kod inače meta brute-forcea. Brojač se resetira nakon uspješne prijave.
- Fiksna odgoda 0,6 s nakon neuspjele prijave (0 s u testovima).
- **Međustanje "lozinka OK, čeka 2FA"** je potpisani kolačić `ak_pending` (10 min, Path=/admin, HttpOnly).
  TOTP tajna tijekom postavljanja sprema se **šifrirana u bazu** (`totp_enabled=false`) — nikad u kolačić.
- **2FA je obavezna i za postojeće sesije**: ako korisnik ima sesiju, a `totp_enabled=false` (npr. usred
  ponovnog postavljanja iz profila), svaka admin stranica preusmjerava na postavljanje 2FA.
- **Kodovi za oporavak**: 10 kodova formata `xxxx-xxxx-xxxx` (60 bita entropije), hashirani Argon2id s
  lakšim profilom (brža provjera; kodovi su nasumični, ne lozinke). Svaki vrijedi jednom.
- **Zaštita od ponovne upotrebe TOTP koda**: sprema se zadnji prihvaćeni vremenski korak (`totp_last_step`);
  isti ili stariji korak se odbija. Prihvaća se ±1 korak (30 s) zbog neusklađenih satova.
- **CSRF na razini routera**: `Depends(csrf_protect)` na svakom routeru provjerava token za sve
  POST/PUT/PATCH/DELETE zahtjeve — nova ruta ne može "zaboraviti" CSRF.
- **Reset lozinke** briše sve sesije korisnika, ali **ne** poništava 2FA. Promjena lozinke u profilu
  zadržava trenutnu sesiju, briše ostale.
- Rate limit "zaboravljena lozinka": 3 / 15 min po IP-u i po hashu emaila; preko limita HTTP 429
  (limit vrijedi i za nepostojeće adrese, pa ne otkriva postojanje računa).
- Pozivnica kreira korisnika bez lozinke; ponovno slanje poništava prethodni token. Owner može
  dodijeliti samo uloge owner/salesperson.
- **Email backend `console`** ispisuje tijelo poruke samo u `APP_ENV=development` (inače samo maskiranu
  adresu i subject) — logovi bez osobnih podataka.
- `email_log.to_hash` = SHA-256 normaliziranog emaila (lowercase, trim).
- Audit `user.login_failed` sprema samo hash upisanog emaila.
- Popis sesija u profilu prikazuje maskiran IP (`192.168.1.xxx`) i sažetak preglednika (npr. "Chrome · Windows").

## Dizajn

- Zadane boje (postavke, mijenjaju se u adminu): primarna `#1e40af` (tamnoplava, kontrast s bijelim
  8,7:1), akcentna `#e11d48` (kontrast s bijelim 4,7:1 — AA). Nijanse (hover, soft) računaju se
  CSS-om `color-mix()` iz te dvije boje.
- Ikone su inline SVG (Feather/Lucide stil, `app/icons.py`) — bez icon fontova.

## Otvoreno

- **Docker nije testiran lokalno** (Docker nije instaliran). Postgres jest (vidi gore).
  → Provjeriti `docker compose up` na računalu/VPS-u s Dockerom.
