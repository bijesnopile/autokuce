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
  suita (`TEST_DATABASE_URL=... pytest`), a u fazi 8 i `deploy/backup.sh` / `restore.sh`
  (`AK_PG_LOCAL=1`). `docker build` i `docker compose` nisu mogli biti izvedeni (vidi "Otvoreno").
- Windows konzola (cp1252) ruši `print()` s hrvatskim znakovima kad je izlaz preusmjeren —
  sve ulazne točke (`run.py`, `app.cli`, `app.seed`, `scripts/*`) pozivaju `ensure_utf8_console()`.
- Za lokalni test šifriranja backupa korišten je GPG iz Git for Windows s privremenim keyringom u
  `data/gpgtest` (gitignored, obrisan nakon testa) — putanja u privremenoj mapi bila je preduga za
  socket gpg-agenta. `age`, `rclone` i `shellcheck` nisu dostupni; skripte su provjerene `bash -n`.
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

## Upiti i mini-CRM (faza 5)

- **Turnstile fail-open kod mrežne greške**: ako Cloudflare ne odgovori (timeout), upit se prihvaća
  (i dalje vrijede honeypot, vremenska provjera i rate limit) — ispad Cloudflarea ne smije blokirati
  kupce. Eksplicitni "success: false" odbija upit.
- **Vremenska provjera**: svaka javna forma nosi potpisani timestamp (`form_ts`); slanje < 3 s nakon
  prikaza ili s nevaljanim/starijim od 24 h timestampom odbija se porukom (forma se prikazuje ponovno).
- **Honeypot** (`website`, skriven CSS-om) → lažni uspjeh (redirect s porukom zahvale), ništa se ne sprema.
- **Rate limit**: 5 upita / 10 min po IP-u (broji svaki pokušaj) i 3 / sat po hashu emaila (broji
  valjane upite). Preko limita HTTP 429 s porukom u formi.
- **Telefon**: hrvatski brojevi (`+385…`, `0…`, `00385…`) normaliziraju se u `+385…`; strani brojevi
  u E.164 obliku (`+49…`) se prihvaćaju (kupci iz inozemstva).
- **Upit za prodano vozilo** (dok je javno vidljivo) je dopušten; za skicu, arhivirano ili nepostojeće
  vozilo odbija se (400).
- **Nakon slanja** korisnik se preusmjerava (PRG) na istu stranicu s porukom zahvale na vrhu; kupcu se
  ne šalje email (MVP). Dealer dobiva email s `Reply-To` = email kupca.
- **Retencija upita** računa se od `created_at`, jednako za otvorene i zatvorene upite (365 dana);
  bilješke se brišu zajedno s upitom.
- **Status**: novi → kontaktiran → zatvoren, povratak dopušten; `contacted_at` se postavlja pri prvom
  kontaktu (i pri zatvaranju ako kontakt nije zabilježen) — koristi se za statistiku.
- **Bilješke**: autor može obrisati vlastitu bilješku unutar 15 minuta; ostale se ne brišu.
- **CSV izvoz** (owner+): UTF-8 s BOM-om, separator `;`, prati trenutne filtere; audit bilježi samo broj redaka.
- Prodavač vidi i obrađuje sve upite (status, dodjela, bilješke), ne može brisati ni izvoziti.

## Newsletter (faza 6)

- **Token za odjavu** je HMAC (SHA-256, ključ `SECRET_KEY`) nad ID-om pretplatnika, hashom emaila i
  vremenom potvrde; u bazi je samo njegov hash (`unsubscribe_token_hash`). Tako se isti "trajni" link
  može generirati za svaki email kampanje bez čuvanja sirovog tokena. Odjava briše hash → stari
  linkovi prestaju vrijediti; nova prijava daje novo vrijeme potvrde → novi token.
- **Odjava jednim klikom**: link u emailu ima `?potvrdi=1` i odjavljuje odmah (GET). Bez parametra
  prikazuje se potvrda s gumbom. Klijenti emaila koji prefetchaju linkove mogli bi okinuti odjavu —
  svjesna odluka radi jednostavnosti za primatelja (zahtjev "odjava jednim klikom" u specifikaciji).
  `List-Unsubscribe` + `List-Unsubscribe-Post: List-Unsubscribe=One-Click` (RFC 8058): klijent šalje
  POST bez CSRF tokena, pa je ta jedna ruta (`POST /newsletter/odjava/{token}`) namjerno na routeru
  bez CSRF ovisnosti — autorizacija je nepogodivi token.
- **Prijava iz podnožja/naslovnice/vozila** koristi PRG s flash porukom (greške i uspjeh), jer je
  forma na svakoj stranici; poruka uspjeha je uvijek ista (ne otkriva postoji li adresa).
- Ponovno slanje potvrde za `pending` adresu najviše jednom u 10 minuta; nepotvrđeni se brišu 7 dana
  nakon zadnjeg slanja potvrde.
- **Slanje kampanje**: `BackgroundTasks` pokreće zasebnu nit s vlastitom DB sesijom (u testovima se
  izvodi sinkrono). Serije od 50, pauza 1 s. Zapis po primatelju u `campaign_deliveries` (jedinstven
  par kampanja+pretplatnik) → ponovno pokretanje preskače već isporučene; "Ponovno pošalji neuspjelima"
  šalje samo `failed`. Ime pošiljatelja = postavka "Ime pošiljatelja newslettera".
- **Sanitizacija kampanja** (nh3): osnovna allowlista + `table/tr/td/img/span/div` i `style` atribut
  (za karticu vozila); `img[src]` samo s vlastitog `/media`, `BASE_URL/media` ili `MEDIA_URL`;
  `style` s `url(`, `expression`, `@import` ili `javascript:` se uklanja.
- **Pregled emaila** u adminu je `<iframe sandbox srcdoc=…>` (bez skripti, izoliran); "Otvori zasebno"
  ima vlastiti restriktivni CSP.
- **Ručni unos** pretplatnika (owner+) odmah je `confirmed` sa `source=manual` i obaveznom napomenom o
  načinu prikupljanja privole; bez IP-a i user agenta.
- **Pretraga pretplatnika**: puna adresa (s `@`) traži se preko hasha (nalazi i anonimizirane zapise);
  bez `@` traži se po početku adrese među zapisima koji još imaju email.
- **Tekstualna verzija** kampanje generira se iz HTML-a (poveznice u zagradama).

## Admin: nadzorna ploča, postavke, stranice, GDPR, održavanje, demo (faza 7)

- **"Bez odgovora > 48 h"** = upit u statusu `new` stariji od 48 sati (ista definicija u karticama,
  podsjetnicima i brojaču u izborniku).
- **Promjena pregleda u %** uspoređuje zadnjih 30 dana s prethodnih 30; ako je prethodno razdoblje 0,
  prikazuje se "nema usporedbe" (umjesto beskonačnog postotka).
- **Grafovi** su inline SVG generirani u Pythonu (`app/services/charts.py`), tooltip kroz `<title>`,
  oznake osi uvijek cijeli brojevi; bez JS biblioteka.
- **Prosječno vrijeme do prvog kontakta** računa se iz `inquiries.contacted_at` (postavlja se pri
  prvoj promjeni statusa u "kontaktiran"/"zatvoren", faza 5) umjesto parsiranja audit loga — isto
  značenje, jednostavniji i brži upit. Upiti bez kontakta ne ulaze u prosjek.
- **Konverzija** po vozilu = upiti za vozilo / pregledi vozila u odabranom razdoblju.
- **Statistika** je dostupna svima s pravom `statistics` (owner+); CSV izvoz (vozila, marke, dani)
  UTF-8 s BOM-om i `;` separatorom, audit `stats.export` bez osobnih podataka.
- **Postavke**: OIB mora imati 11 znamenki ili biti placeholder `XXXXXXXXXXX`; telefon u obliku
  `+385…` ili s razmacima; poveznice (web, mreže, Maps) moraju počinjati s `http(s)://` (web može i bez);
  boje samo `#rrggbb`. Audit `settings.update` sadrži samo popis promijenjenih ključeva.
- **Logo**: PNG/WebP/JPEG do 2 MB kroz `images.py`, varijante 200 i 400 px (WebP, prozirnost se
  čuva), bez EXIF-a. "Ukloni logo" briše datoteke i vraća tekstualni `LOGO`.
- **Kontrast boja** u postavkama računa se u pregledniku (WCAG omjer prema bijeloj); upozorenje ispod
  4,5:1, spremanje se ne blokira (odluka vlasnika).
- **Verzija politike privatnosti**: kad se promijeni, `privacy_policy_updated_at` = današnji datum;
  datum se prikazuje na pravnim stranicama. Nova verzija se sprema uz svaku sljedeću privolu.
- **Traka za kolačiće je zadano isključena**: MVP koristi samo nužne kolačiće (`st`, `session`,
  `ak_pending`) i cookieless Umami, za koje privola nije potrebna. Kad se uključi: "Prihvaćam" i
  "Odbijam" su jednako istaknuti, izbor se pamti 180 dana u kolačiću `cookie_consent`
  (`accepted`/`rejected`), a skripte napisane kao
  `<script type="text/plain" data-consent="analytics" data-src="…">` učitavaju se tek nakon
  prihvaćanja (blok `consent_scripts` u `public/base.html`). Umami se učitava bez privole.
- **Stranice**: svako spremanje povećava `version` (i bez promjene sadržaja — jednostavno i
  predvidljivo). Neobjavljena stranica vraća 404 javno i nije u sitemapu; admin je vidi kroz "Pregled".
  Editor bez "umetni vozilo" (samo newsletter).
- **GDPR alat**: traži po emailu (upiti bez obzira na velika/mala slova, pretplatnici po hashu, pa
  nalazi i anonimizirane) i opcionalno po telefonu (normaliziranom). Brisanje traži upis `OBRIŠI`,
  briše upite+bilješke i `email_log` po hashu, pretplatnika anonimizira kao pri odjavi (hash ostaje
  kao lista zabrane). Audit `privacy.export` / `privacy.delete` sadrži samo hash i brojeve.
- **Održavanje u aplikaciji** (`MAINTENANCE_IN_APP=true`, zadano): pozadinska nit svakih 10 minuta
  provjerava je li prošlo 04:00 (Europe/Zagreb) i je li današnje izvođenje već preuzeto; preuzimanje je
  atomski `UPDATE settings … WHERE value != danas`, pa od više workera radi točno jedan. Alternativa je
  cron (`python -m app.cli maintenance`, primjer u `deploy/crontab.example`, faza 8) uz
  `MAINTENANCE_IN_APP=false`.
- **Prodana vozila** se nakon `SOLD_VISIBLE_DAYS` (30) arhiviraju (ne brišu) — ostaju u adminu i
  statistici, javno vraćaju 410.
- **Dodatno uz specifikaciju**: stranica `/admin/sustav` (samo superadmin) — konfiguracija bez tajni,
  pregled "što bi održavanje sada obrisalo" (dry-run), ručno pokretanje održavanja i testni email.
- **Demo seed**: oznaka `demo_seeded` u `settings` čini ga idempotentnim. Katalog ima 31 marku i 243
  modela (spec traži ~25). Placeholder fotografije imaju siluetu prema vrsti vozila (auto, kombi,
  motocikl, kamper, kamion) i sistemski TrueType font (DejaVu/Segoe/Arial) zbog hrvatskih znakova, uz
  `ImageFont.load_default(size)` kao rezervu. Generiraju se paralelno (dretve) i prolaze kroz pravi
  upload pipeline. Pregledi su deterministični (fiksni seed slučajnih brojeva).
- **`--reset-demo` briše SVA vozila, upite, pretplatnike, kampanje, preglede i audit** te demo
  korisnike (ne superadmina) — namijenjeno demo instanci. U produkciji demo seed i reset rade samo uz
  `DEMO_SEED=true` ili `--potvrdi`; `run.py` na praznoj bazi puni demo samo u `development` ili uz
  `DEMO_SEED=true`, inače minimalni seed.

## Deployment, backup i provjera (faza 8)

- **Docker slika** (`Dockerfile`): `python:3.11-slim`, dvije faze (venv s pinanim ovisnostima →
  runtime bez pip cachea, testova i dev alata), korisnik `app` (uid 1000), `fonts-dejavu-core` za
  placeholder slike, `HEALTHCHECK` Pythonom (slim slika nema curl), uvicorn s `WEB_CONCURRENCY=2`,
  `--no-access-log` (IP adrese su osobni podaci), `--no-server-header`, bez uvicornovih proxy headera
  (pravi IP određuje naš `RealIPMiddleware` uz `TRUST_PROXY`).
- **Entrypoint** (`docker/entrypoint.sh`): ako `SECRET_KEY` nije zadan, generira se jednom i čuva u
  `data/.secret_key` (lokalni demo "bez ručnih koraka"; `new-client.sh` uvijek postavlja ključ u `.env`)
  → `app.cli wait-db` → `app.cli migrate` → `app.seed --if-empty` (`--minimal`, ili puni demo uz
  `DEMO_SEED=true`). **Seed samo na praznoj bazi**: pri restartu postojeće instance ne vraćaju se
  marke/modeli koje je klijent obrisao; dodaju se samo novi ključevi postavki iz nove verzije.
- **Vlasništvo nad `./data`**: jednokratni servis `init` (ista slika, root) napravi mape i `chown`
  na `app` samo za datoteke koje to nisu — bind mount radi bez ručnog `chown`a, a aplikacija i dalje
  radi kao non-root. `overrides/` je montiran samo za čitanje; aplikacija ga nikad ne mijenja (ispravljen
  `mkdir` pri startu koji bi na read-only volumenu srušio kontejner — test `test_overrides.py`).
- **Korijenski `docker-compose.yml`** služi za lokalni demo i jednog klijenta: bez `.env` pokreće demo
  na `http://localhost` (`DOMAIN` prazno → Caddy adresa `http://localhost`, tj. HTTP bez TLS-a —
  ekvivalent `auto_https off` iz specifikacije, bez posebne varijable). Bind mount `./data` umjesto
  zasebnih `./data/media` i `./data/backups` (jedan mount pokriva media, outbox, backupe i generirani ključ).
  `env_file` s `required: false` traži Docker Compose ≥ 2.24.
- **Produkcijski raspored**: `deploy/client-template` (samo app + db, bez portova, mreža `web`, imena
  kontejnera `<ime>_app`/`<ime>_db`, projekt `ak_<ime>`), zajednički `deploy/caddy` (`import
  sites/*.caddy`, snippet `(autokuca)`). Slika se gradi iz repozitorija (`autokuca:latest`); `--pull` za
  registry. `update-all.sh` čuva prethodnu sliku kao `:previous` i prije ažuriranja radi backup.
- **TLS**: `new-client.sh` koristi Cloudflare Origin certifikat ako postoji
  `deploy/caddy/certs/<domena>/{cert,key}.pem`, inače Let's Encrypt (upozorenje). Varijanta DNS izazova:
  `deploy/caddy/Dockerfile.cloudflare`. Caddy ne dodaje sigurnosne headere (postavlja ih aplikacija),
  samo `encode`, `?Cache-Control` (ako ga odgovor nema) i uklanja `Server`.
- **Održavanje**: `MAINTENANCE_IN_APP=true` ostaje zadano i u `new-client.sh`; cron u
  `crontab.example` pokreće i CLI u 04:00 — CLI sada koristi istu atomsku oznaku dana (`--force` za
  ponovno izvođenje), pa se retencija izvede točno jednom dnevno bez obzira na to tko je prvi.
- **Backup**: dump radi `pg_dump` unutar kontejnera baze preko lokalnog socketa (nema lozinke ni u
  listi procesa ni u `.pgpass`); `-Z0` + `gzip`; provjera integriteta prije šifriranja (`gzip -t`,
  `pg_restore --list`, mora sadržavati `alembic_version`) jer privatni ključ **nije** na serveru; ako je
  ključ dostupan (`BACKUP_AGE_IDENTITY` ili GPG tajni ključ), provjerava se i dešifrirana kopija (TOC mora
  biti identičan). Bez ključa za šifriranje backup se odbija. Konfiguracija u `deploy/backup.env`
  (zajednička) s prednošću `clients/<ime>/.env`. Status zadnjeg uspjeha: `data/backups/last-success.txt`.
- **Vraćanje** ide u novu bazu pa zamjena imena (stara ostaje `<baza>_old_<datum>`) — brz povratak ako
  backup nije dobar; ništa se ne briše automatski.
- **Lokalna provjera bez Dockera**: `AK_PG_LOCAL=1` (+ `PG*` varijable) izvodi PostgreSQL alate lokalno
  umjesto u kontejneru. Na Windowsu `pg_restore` ne čita arhivu iz cijevi (MSYS), pa skripte TOC čitaju
  iz privremene datoteke — radi jednako i na Linuxu.
- **`scripts/check.py`**: ruff, format, pytest, pip-audit. Ranjivost u paketu koji ide u produkcijsku
  sliku (requirements.txt i njegove ovisnosti) ruši provjeru ("kritično"); samo u dev alatima je
  upozorenje; bez mreže pip-audit je upozorenje. `--brzo` preskače pip-audit.
- **`scripts/screenshots.py`** pokreće vlastitu instancu (privremena SQLite baza + demo seed + outbox)
  na slobodnom portu i prolazi tijekove kao posjetitelj i administrator; za svaku stranicu provjerava HTTP
  status, horizontalni skrol i greške u konzoli. Tako ne ovisi o lokalnoj bazi ni o 2FA tajni.
- **Rate limit API-ja** usklađen sa specifikacijom: 100 zahtjeva/min po IP-u (`/api/modeli`,
  `/admin/newsletter/api/vozila`; prije 60/min).
- **Pronađeno i ispravljeno u fazi 8**: `vehicles.euro_norm` je bio `VARCHAR(10)`, a vrijednost
  `euro6d_temp` ima 11 znakova — SQLite to ne provjerava, PostgreSQL odbija (migracija `0002`, 20
  znakova); `LocalStorage` je na Windowsu u paralelnom seedu povremeno javljao "Path traversal" jer
  `Path.resolve()` pristupa disku u utrci s kreiranjem mape — provjera je sada leksička.
- **Mobilna traka "Nazovi / Pošalji upit"** skriva se dok je forma upita ili pregleda na ekranu ili se
  u nju upisuje (prije je prekrivala gumb za slanje).
- **Retencija aplikacijskih logova** je po veličini (Docker `json-file`, 5 × 10 MB), ne strogo 30 dana
  (spec pogl. 13/14). Logovi ne sadrže osobne podatke (bez access loga, maskirani emailovi); za strogi
  rok: `journald` driver s `MaxRetentionSec=30day` (SIGURNOST.md).
- **Penetracijski test, WAF pravila, Redis limiter, HEIC** — izvan MVP-a, opisano u SIGURNOST.md → 5.

## Demo sadržaj i podstranice (29.09.2026., na zahtjev)

- **Odstupanje od pogl. 3 specifikacije (lorem ipsum)**: na zahtjev vlasnika projekta ("da izgleda kao
  da je za autokuću, da mogu pokazati demo") sadržajni tekstovi više nisu lorem ipsum nego **generički
  tekst autokuće**: hero naslov/podnaslov i tekst podnožja (zadane postavke), stranice O nama i Usluge,
  opisi demo vozila, poruke demo upita, bilješke i demo kampanje. **Podaci tvrtke ostaju placeholderi**
  (`IME PODUZEĆA`, `LOGO`, `+385XXXXXXXXXX`…) i dolaze samo iz postavki; tekstovi ne sadrže naziv,
  godine poslovanja ni druge činjenice o tvrtki. **Pravne stranice ostaju lorem ipsum** s oznakama
  `[PRAVNIK: dopuniti]`.
- **"Zašto kupiti kod nas"** je nova postavka (`why_us`, Postavke → Izgled; jedna stavka po retku
  `Naslov | opis`, najviše 8) — jedan izvor za naslovnicu, O nama i bočnu karticu na stranici vozila,
  kako tvrdnje (financiranje, zamjena…) ne bi bile zapisane u predlošcima i autokuća ih može prilagoditi.
  Ikone se biraju prema ključnim riječima naslova (`app/services/content.py`).
- **Stranice s vlastitim rasporedom**: ako postoji `public/pages/<slug>.html` (i u `overrides/`), koristi
  se umjesto općeg `public/page.html`. Usluge: uvodni odlomak = podnaslov, svaki H3 s tekstom = kartica
  usluge, sve od prvog H2 nakon kartica = istaknuti okvir; dodani su koraci kupnje i CTA traka. O nama:
  kartica s podacima tvrtke, brojke iz trenutne ponude (vozila u ponudi, marke, vrste, novi oglasi u 30
  dana — samo ono što baza može potvrditi) i "Zašto kupiti kod nas". Sadržaj se i dalje uređuje u
  običnom editoru stranica; meta description stranice = prvi odlomak.
- **Specifikacije vozila**: kartice po grupama s ikonama raspoređene u dva stupca uravnotežena prema
  broju redaka (raspodjela u Pythonu, `split_columns`), na mobitelu jedan stupac u izvornom redoslijedu.
  Iznad specifikacija su oznake prednosti izvedene iz podataka vozila (prvi vlasnik, servisna knjižica,
  garancija, registracija još vrijedi, R1 račun, nekorišteno novo vozilo) — nikad izmišljene. Nova
  vozila imaju istaknutu karticu potrošnje i CO2 (WLTP). Oprema: kartice po kategorijama s brojem stavki.
- `--reset-demo` vraća i demo marketinške tekstove (hero, podnožje, `why_us`, O nama, Usluge) na zadane;
  podatke tvrtke i pravne stranice ne dira.

## Dizajn

- Zadane boje (postavke, mijenjaju se u adminu): primarna `#1e40af` (tamnoplava, kontrast s bijelim
  8,7:1), akcentna `#e11d48` (kontrast s bijelim 4,7:1 — AA). Nijanse (hover, soft) računaju se
  CSS-om `color-mix()` iz te dvije boje.
- Ikone su inline SVG (Feather/Lucide stil, `app/icons.py`) — bez icon fontova.

## Otvoreno

- **`docker build` i `docker compose up` nisu izvedeni** — Docker nije instaliran na razvojnom računalu
  (instalacija bi mijenjala sustav, što pravila projekta ne dopuštaju). Provjereno je sve što se moglo bez
  Dockera: aplikacija, migracije i cijela suita na PostgreSQL-u 16, entrypoint logika (`wait-db`,
  `migrate`, `seed --if-empty` — testovi), `sh -n`/`bash -n` sintaksa svih skripti, backup i vraćanje
  s pravim `pg_dump`/`pg_restore` i GPG šifriranjem (`AK_PG_LOCAL=1`).
  → Na računalu ili VPS-u s Dockerom: `docker compose up -d --build` → `curl http://localhost/zdravlje`
  (očekivano `{"status":"ok","db":"ok"}`), prijava u `/admin`, zatim `deploy/new-client.sh test
  test.domena.hr`, `deploy/backup.sh test`, `deploy/restore.sh test <datoteka>`.
- **Varijanta s `age`** (preporučena) nije izvedena lokalno (`age` nije dostupan); kod je simetričan
  GPG varijanti koja je testirana.
- **Pravni tekstovi** (politika privatnosti, kolačići, uvjeti, ugovor o obradi) su predlošci — pravnik.
