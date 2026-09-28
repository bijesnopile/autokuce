# FAZA 7/8 — Dashboard, statistika, postavke, stranice, GDPR alat, maintenance, demo seed

## Kontekst

Faza 7 od 8. Prvo pročitaj `CLAUDE.md` i `docs/SPECIFIKACIJA.md` [ako je nema u `docs/`, kopiraj `prompts/SPECIFIKACIJA.md` u `docs/`] (posebno poglavlja 3, 10, 14, 19). Provjeri stanje repozitorija (faze 1–6 gotove). Ne postavljaj pitanja; nedefinirano odluči sam i zabilježi u `docs/PRETPOSTAVKE.md`.

## Cilj faze

Admin postaje potpun (dashboard, statistika, postavke s brandingom, uređivanje stranica, alat za prava ispitanika), automatsko održavanje radi, a **puni demo seed** puni instancu placeholder sadržajem tako da se može pokazati klijentu.

## Zadaci

1. **Dashboard** (`/admin`, `app/routers/admin_dashboard.py`)
   - Kartice: aktivna vozila (+ rezervirana, skice), novi upiti (+ bez odgovora > 48 h), potvrđeni pretplatnici (+ novi ovaj mjesec), pregledi zadnjih 30 dana (+ promjena u % prema prethodnih 30).
   - Graf pregleda po danu (30 dana) kao **inline SVG** generiran u Pythonu/Jinji (stupci ili linija, osi, tooltip kroz `<title>`), bez biblioteka.
   - Zadnjih 10 upita (link na detalj), top 5 vozila po pregledima (30 dana), podsjetnici: skice bez slika, aktivna vozila bez slika, upiti bez odgovora, kampanja u skici starija od 7 dana.

2. **Statistika** (`/admin/statistika`)
   - Razdoblje 30/90/365 dana. Pregledi po danu (SVG), pregledi i upiti po vozilu (tablica, sortiranje, konverzija upiti/pregledi), upiti po tipu i statusu, prosječno vrijeme do prvog kontakta (iz audit/status promjene), prijave/odjave newslettera po tjednu, top marke po pregledima. Izvoz CSV tablica (owner+).

3. **Postavke** (`/admin/postavke`, owner+)
   - Sekcije: Tvrtka (naziv, adresa, OIB, email, telefon, web, radno vrijeme), Kontakt i mreže (email za obavijesti o upitima, ime pošiljatelja newslettera, Facebook, Instagram, Google Maps link), Izgled (upload logotipa kroz `images.py` — PNG/WebP/JPEG max 2 MB, varijante 200/400 px, ukloni logo → natrag na tekst LOGO; primarna i akcentna boja s `<input type="color">` i pregledom kontrasta prema bijeloj; hero naslov i podnaslov; tekst podnožja), Pravno (verzija politike privatnosti — promjena verzije zapiše datum u `privacy_policy_updated_at` i prikazuje se na pravnim stranicama; `cookie_banner_enabled`; `plates_reminder_enabled`).
   - Validacija (email format, telefon, OIB 11 znamenki ili `XXXXXXXXXXX` placeholder, boje hex), keš `site` invalidiran pri spremanju, audit `settings.update` s popisom promijenjenih ključeva (bez vrijednosti).
   - Cookie banner (samo ako uključen): mala traka s "Prihvaćam"/"Odbijam" jednako istaknutima, sprema izbor u kolačić `cookie_consent`; skripte označene `data-consent="analytics"` učitavaju se samo nakon prihvaćanja. Umami ostaje bez privole (cookieless). Dokumentiraj.

4. **Stranice** (`/admin/stranice`, owner+): lista pet stranica (naslov, verzija, ažurirano, objavljeno), uređivanje s editorom iz faze 6 (bez „umetni vozilo"), pregled, spremanje povećava `version`, `is_published` toggle. Sanitizacija nh3.

5. **Alat za prava ispitanika** (`/admin/gdpr`, owner+)
   - Unos emaila → pretraga po `email` u upitima i po `email_hash` u pretplatnicima (i po telefonu opcionalno) → prikaz sažetka: broj upita (s datumima i vozilima), bilješke, status pretplate s podacima privole.
   - "Izvoz (JSON)": svi podaci osobe u strojno čitljivom obliku (upiti s porukama, bilješke, pretplata s privolom) — preuzimanje datoteke; audit `privacy.export` (samo hash emaila).
   - "Obriši sve podatke ove osobe": potvrda unosom riječi OBRIŠI → briše upite i bilješke, pretplatnika anonimizira kao pri odjavi (hash ostaje kao suppression), briše `email_log` zapise po hashu; audit `privacy.delete` (samo hash, brojevi obrisanih zapisa). Napomena na ekranu: backupi se rotiraju za 30 dana (iz `docs/GDPR.md`).

6. **Maintenance** (`app/services/maintenance.py`, `app/cli.py`)
   - `run_all(db)`: `purge_old_inquiries`, `purge_pending_subscribers`, `purge_old_unsubscribed`, `archive_sold_vehicles` (`sold` starije od `SOLD_VISIBLE_DAYS` → `archived`), `purge_expired_sessions_and_tokens`, `purge_old_email_log` (> 90 dana), `purge_old_audit` (> 2 godine), `purge_old_vehicle_views` (> 400 dana). Svaki korak logira broj obrisanih; zapis u audit kao `system.maintenance` (user_id NULL).
   - `python -m app.cli maintenance` (+ `--dry-run`). Ako `MAINTENANCE_IN_APP=true`: pozadinska nit u aplikaciji pokreće `run_all` jednom dnevno u 04:00 (zaštita od dvostrukog izvođenja kod više workera: zapis zadnjeg izvođenja u `settings` ključ `maintenance_last_run` + provjera).

7. **Demo seed** (`python -m app.seed`, idempotentan — pokretanje drugi put ne duplicira; `--minimal` ostaje kao prije; `--reset-demo` briše demo podatke i ponovno ih kreira)
   - `scripts/make_placeholder_images.py` + korištenje iz seeda: 4:3, 1600×1200, svijetlosiva pozadina s blagim gradijentom (nijansa varira po slici), centrirani tekst `FOTOGRAFIJA VOZILA n/N` (Pillow `ImageFont.load_default(size=…)` ili ugrađeni bitmap font skaliran — mora biti čitljivo), ispod manji tekst `IME PODUZEĆA`. Prolaze kroz `images.py` kao pravi upload (varijante 400/1000/1600). OG default slika `static/img/og-default.png` (1200×630) s tekstom `LOGO` i `IME PODUZEĆA`.
   - Katalog: ~25 marki (osobni: Audi, BMW, Citroën, Dacia, Fiat, Ford, Honda, Hyundai, Kia, Mercedes-Benz, Nissan, Opel, Peugeot, Renault, Seat, Škoda, Suzuki, Tesla, Toyota, Volkswagen, Volvo; kombiji/kamioni: Iveco, MAN, Scania; motocikli: Yamaha, Kawasaki, KTM, Piaggio; kamperi: Adria, Knaus, Hymer) s 5–15 modela svaka i ispravnim tipovima.
   - 16 vozila prema poglavlju 19 (8 osobnih, 3 kombija, 2 motocikla, 2 kampera, 1 kamion; 12 aktivnih, 1 rezervirano, 2 prodana — jedno prije 10 dana, jedno prije 45 dana da se vidi arhiviranje, 1 skica; 3 istaknuta; jedno "cijena na upit"; jedno sa starom cijenom; 2 nova vozila s potrošnjom i CO2), realistične specifikacije i oprema, opisi lorem ipsum 2–3 odlomka s jednim `<h3>` i jednim popisom, 5–8 slika, `published_at` raspršen kroz zadnjih 60 dana.
   - Pregledi: `vehicle_views` za zadnjih 60 dana (0–40 dnevno po vozilu, vikendi manje, istaknuta više), `views_total` usklađen.
   - 10 upita (miks tipova/statusa, datumi kroz 30 dana, imena `Ime Prezime`, `kupacN@primjer.hr`, telefon `+385XXXXXXXXXX`, poruke lorem ipsum, privola zabilježena, verzija politike), 4 bilješke, 3 dodijeljena prodavaču.
   - 15 pretplatnika (10 `confirmed`, 3 `pending`, 2 `unsubscribed` anonimizirana), 1 poslana kampanja (subject "Nova vozila u ponudi", lorem, s isporukama 9 sent / 1 failed) i 1 skica.
   - Korisnici: `admin@domena.com` (superadmin), `vlasnik@domena.com` (owner, ime "Ime Prezime"), `prodavac1@domena.com` (salesperson, ime "Prodavač 1"); lozinka `SEED_PASSWORD`; bez 2FA. 10 demo audit zapisa.
   - `run.py` pri praznoj bazi pokreće **puni** demo seed u `APP_ENV=development`, a `--minimal` u produkciji (compose u fazi 8).

8. **Testovi** (`tests/test_dashboard.py`, `tests/test_settings.py`, `tests/test_pages.py`, `tests/test_privacy.py`, `tests/test_maintenance.py`, `tests/test_seed.py`)
   - Dashboard brojevi točni na fixturi; statistika CSV; postavke: promjena naziva mijenja javni header, upload logotipa zamjenjuje tekst LOGO, ne-slika odbijena, promjena verzije politike upisuje datum, prodavač 403; stranice: verzija raste, `<script>` uklonjen, neobjavljena → 404 javno; GDPR alat: izvoz sadrži sve zapise osobe, brisanje uklanja upite/bilješke i anonimizira pretplatu, audit bez emaila; maintenance: svaka funkcija briše/arhivira samo ono što treba, `--dry-run` ne mijenja ništa, dvostruko izvođenje istog dana preskače; seed: dvostruko pokretanje ne duplicira, sve slike imaju 3 varijante, sva vozila prolaze validaciju sheme, nova vozila imaju CO2.

## Provjera prije završetka

- Svježa baza + `python run.py` → puni demo bez ručnih koraka. Prođi javnu stranicu i cijeli admin s demo podacima.
- Screenshotovi (desktop + mobile) `docs/screenshots/admin-dashboard-*.png`, `admin-statistika-desktop.png`, `admin-postavke-desktop.png`, `admin-stranice-editor-desktop.png`, `admin-gdpr-desktop.png`, i **ponovno** javne stranice s demo podacima `javno-naslovnica-*.png`, `javno-lista-*.png`, `javno-detalj-*.png`. Pregledaj: dashboard čitljiv, graf uredan, galerija s 8 placeholder slika izgleda kao prava galerija.
- `ruff check .` i `pytest` prolaze. Ažuriraj `CLAUDE.md` i README (seed, maintenance, postavke).
- Git commit: `Faza 7: dashboard, postavke, GDPR alat, maintenance, demo seed`.

## Ne raditi u ovoj fazi

Docker/deployment, backup skripte, završnu dokumentaciju (faza 8).

## Završni izvještaj faze

Što je napravljeno, popis ruta, pristupni podaci za demo, popis retencijskih pravila kako su implementirana, pretpostavke, poznati nedostaci, potvrda testova.
