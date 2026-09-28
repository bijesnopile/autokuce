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

## Katalog, vozila i slike (faza 3)

- **Katalog u `seed --minimal`**: spec (pogl. 19) kaže da `--minimal` sadrži "postavke i katalog", pa
  se generički katalog (31 marka, ~240 modela s vrstama vozila) puni već sada (`app/seed_catalog.py`).
- **Model je obavezan** pri unosu vozila (slug `{marka}-{model}-{godina}-{id}` i filteri ga trebaju).
  Nedostaje li model u katalogu, dodaje se u Katalog → marka → Novi model.
- **Gorivo i mjenjač obavezni su za automobile, kombije, motocikle i kamione**, a ne za kampere
  (kamp prikolica nema motor).
- **Potrošnja i CO2 za nova vozila**: obavezni (dopuštena vrijednost 0); za električna vozila potrošnja
  se upisuje u kWh/100 km (napomena uz polje).
- **Polja `doors`, `seats`, `drive`** su kolone u bazi (pogl. 6), ali se prikazuju samo za vrste gdje
  imaju smisla (vrata: automobil; sjedala: automobil, kombi, kamper — kod kampera "sjedala s pojasom";
  pogon: sve osim motocikla, koji ima polje "prijenos" lanac/kardan/remen).
- **Polja specifična za vrstu** imaju u formi ime `<vrsta>__<ključ>` (npr. `truck__axles`) jer više
  vrsta ima isto polje (npr. nosivost); server čita samo polja odabrane vrste.
- **Status pri kreiranju**: skica ili aktivno. Ručni prijelazi prema `STATUS_TRANSITIONS`; prodano →
  arhivirano samo automatski (maintenance). Povratak iz "prodano" u "aktivno" briše `sold_at`.
- **Dupliciranje** kopira sve podatke osim slika, VIN-a, pregleda, istaknutosti i datuma objave.
- **Obrada slika** radi se sinkrono u threadpoolu tijekom upload zahtjeva (`run_in_threadpool`), ne kroz
  `BackgroundTasks`, jer korisnik odmah vidi rezultat; JS šalje jednu datoteku po zahtjevu s prikazom
  napretka. `BackgroundTasks` se koriste za emailove.
- **Ograničenje veličine slike**: osim 12.000 px po stranici i ukupno najviše 64 MP (zaštita od
  "decompression bomb" i preopterećenja memorije na malom VPS-u). Veličina cijelog upload zahtjeva
  ograničena je na 10 × `MAX_UPLOAD_MB`.
- **Alt tekst**: ako nije upisan, javni prikaz koristi "{naslov} – slika {n}" (n prema trenutnom
  redoslijedu), pa promjena redoslijeda ne kvari numeraciju.
- **Logo** zadržava prozirnost (WebP s alfa kanalom); fotografije vozila se poravnavaju na bijelu pozadinu.
- **Opis vozila** koristi isti jednostavni editor (`editor.js`) koji će koristiti kampanje i stranice —
  napravljen je već u fazi 3 da prodavači ne bi pisali HTML ručno. Lijepljenje uvijek ubacuje čisti tekst.
- **S3 backend** testiran s `moto` (lažni S3 u memoriji): spremanje, čitanje, URL preko `MEDIA_URL`, brisanje.
- **Uvoz CSV-a** prihvaća `;` ili `,`, UTF-8 ili Windows-1250 (Excel na hrvatskom Windowsu), zaglavlje
  opcionalno, tip kao kod (`car`) ili hrvatska riječ (`osobni`, `kombi`, `motocikl`, `kamper`, `kamion`).
- Na mobitelu HTML5 drag&drop ne radi, pa kartice slika imaju i strelice ← → (rade i tipkovnicom).
- Admin na desktopu koristi CSS grid (sidebar kao "sticky" stupac) umjesto fiksnog sidebara.

## Javni frontend i SEO (faza 4)

- **Prodana vozila** (vidljiva `SOLD_VISIBLE_DAYS` dana) prikazuju se na kraju liste, iza dostupnih,
  s oznakom PRODANO i sivom slikom. Nakon isteka roka detalj vraća **410** čak i prije nego što ih
  noćni maintenance arhivira. Arhivirano vozilo → 410 + `X-Robots-Tag: noindex`; skica → 404.
- **Filteri cijene** isključuju vozila s "cijenom na upit"; kod sortiranja po cijeni ta su vozila na kraju.
- **Brojanje pregleda** — deduplikacija 6 h preko potpisanog kolačića `st` (popis ID-ova vozila i
  vremena, najviše 50 stavki). Kolačić ne sadrži osobne podatke, ne prati korisnika između stranica
  trećih strana i nužan je za ispravnu statistiku oglasa (legitimni interes, bez pristanka — isti
  kolačić već nosi CSRF token). Botovi (UA s bot/crawler/spider/preview/headless) se ne broje.
  Brojanje ne mijenja `updated_at` vozila.
- **JSON-LD** se ispisuje kao `<script type="application/ld+json">` — to je podatkovni blok koji
  preglednik ne izvršava, pa nije u sukobu s CSP-om bez `unsafe-inline`. Sadržaj je escapean (`<`, `>`, `&`).
  Tipovi: `Car` (automobil), `Motorcycle`, `Vehicle` (kombi, kamper, kamion) + `Offer` (bez cijene kad je
  "na upit"), `AutoDealer` na naslovnici i kontaktu, `BreadcrumbList` na listi i detalju.
- **OG slika**: `app/static/img/og-default.png` (generirana skriptom, "LOGO" + "IME PODUZEĆA"); klijent je
  zamjenjuje datotekom `overrides/static/og-default.png` (template je automatski koristi). Vozila koriste
  glavnu sliku (1600 px).
- **Verzija pravnih stranica**: `/privatnost` prikazuje verziju i datum iz postavki
  (`privacy_policy_version`, `privacy_policy_updated_at` — ista verzija se sprema uz svaku privolu);
  `/kolacici` i `/uvjeti` prikazuju verziju stranice (`pages.version`) i datum izmjene.
- **Forma za pregled vozila** je u `<details>` elementu (radi i bez JavaScripta); gumb "Dogovori pregled"
  je otvara i fokusira.
- **YouTube**: prije klika prikazuje se neutralni okvir s gumbom (bez YouTube sličice — sličica bi bila
  zahtjev prema Googleu); iframe s `youtube-nocookie.com` stvara se tek na klik.
- `robots.txt` dodatno isključuje `/newsletter/` (stranice potvrde/odjave s tokenima).
- **Placeholder slike** (`app/services/placeholder_images.py`) koriste sistemski TTF font s hrvatskim
  znakovima (DejaVu u Dockeru — `fonts-dejavu-core`, Segoe UI/Arial na Windowsu); Pillowov ugrađeni font
  nema č/ć/š/ž/đ. Bez fonta tekst se transliterira.
- Lista vozila: 12 po stranici; kanonski URL sadrži samo neprazne filtre i broj stranice > 1;
  `rel=prev/next` u `<head>` i na paginaciji.
- Na mobitelu je panel filtera skriven iza gumba "Filteri (n)" (bez JS-a uvijek vidljiv).

## Dizajn

- Zadane boje (postavke, mijenjaju se u adminu): primarna `#1e40af` (tamnoplava, kontrast s bijelim
  8,7:1), akcentna `#e11d48` (kontrast s bijelim 4,7:1 — AA). Nijanse (hover, soft) računaju se
  CSS-om `color-mix()` iz te dvije boje.
- Ikone su inline SVG (Feather/Lucide stil, `app/icons.py`) — bez icon fontova.

## Otvoreno

- **Docker nije testiran lokalno** (Docker nije instaliran). Postgres jest (vidi gore).
  → Provjeriti `docker compose up` na računalu/VPS-u s Dockerom.
