# FAZA 3/8 — Katalog, vozila i slike (admin)

## Kontekst

Faza 3 od 8. Prvo pročitaj `CLAUDE.md` i `docs/SPECIFIKACIJA.md` [ako je nema u `docs/`, kopiraj `prompts/SPECIFIKACIJA.md` u `docs/`] (posebno poglavlja 6, 7, 10, 13 — upload). Provjeri stanje repozitorija (faze 1–2 gotove). Ne postavljaj pitanja; nedefinirano odluči sam i zabilježi u `docs/PRETPOSTAVKE.md`.

## Cilj faze

Admin može održavati katalog marki/modela i unositi oglase **svih tipova vozila** s dinamičkom formom, statusima, slugovima i sigurnim uploadom slika. Javni prikaz dolazi u fazi 4.

## Zadaci

1. **Shema tipova vozila** (`app/vehicle_schema.py`)
   - Za svaki tip (`car`, `van`, `motorcycle`, `camper`, `truck`): labela (hrv.), ikona (inline SVG naziv), popis zajedničkih polja koja se prikazuju/skrivaju (npr. motocikl nema vrata), specifična polja iz poglavlja 7 kao lista `{key, label, type: text|int|float|select|bool, options, required, unit, min, max, group}`, kategorije opreme i stavke (zajedničke + po tipu).
   - Zajedničke liste: goriva, mjenjači, pogoni, boje, Euro norme (Euro 3–6e), načini oporezivanja s hrvatskim labelama, statusi s labelama i dopuštenim prijelazima (`draft→active`, `active→reserved/sold/draft`, `reserved→active/sold`, `sold→active`, `sold→archived` automatski, `archived→draft`).
   - Funkcije: `schema_for(type)`, `validate_attributes(type, data) -> (clean, errors)`, `equipment_for(type)`, `label(field, value)`. Ovo je jedini izvor istine za polja — forma i validacija se generiraju iz njega.

2. **Katalog** (`app/routers/admin_catalog.py`)
   - `/admin/katalog/marke`: lista s brojem modela i vozila, novo/uredi/aktiviraj/deaktiviraj (brisanje samo ako nema vozila), `/admin/katalog/marke/{id}/modeli` s CRUD-om modela (naziv, tip vozila ili "svi").
   - Uvoz CSV (`marka;model;tip`) s pregledom prije potvrde; preskače duplikate.
   - `GET /api/modeli?marka={id}&tip={tip}` → JSON (koristi ga admin forma sada i javni filter u fazi 4). Ruta javna, samo čitanje, rate limit 60/min.
   - `/admin/katalog/tipovi`: pregled tipova i polja (samo čitanje, generirano iz sheme).
   - Slug za marke/modele (unidecode-stil transliteracija bez vanjske ovisnosti: č→c, ć→c, š→s, ž→z, đ→d).

3. **Vozila** (`app/routers/admin_vehicles.py`, `app/services/vehicles.py`)
   - `/admin/vozila`: tablica (thumbnail, naslov, tip, status badge, cijena, godina, km, pregledi, ažurirano), pretraga (naslov/VIN/ID), filteri (status, tip, marka), sortiranje, paginacija 25; brzo mijenjanje statusa iz liste; oznaka ako oglas nema slika.
   - `/admin/vozila/novo` i `/admin/vozila/{id}`: forma u sekcijama (Osnovno, Cijena, Motor i pogon, Karoserija/specifično za tip, Stanje i dokumenti, Oprema, Opis i mediji, Objava). Odabir tipa vozila na vrhu — JS (`admin.js`) prikazuje/skriva sekcije i polja prema `data-types`; model ovisan o marki (fetch `/api/modeli`); KS se računa iz kW automatski; "cijena na upit" skriva cijenu; `condition=new` čini potrošnju i CO2 obaveznima (server + klijent).
   - Server-side validacija prema shemi (obavezna polja, rasponi: godina 1950–tekuća+1, km 0–2.000.000, cijena 0–10.000.000, kW 1–2000), greške prikazane uz polja uz zadržane unesene vrijednosti. Opis kroz nh3 (allowlist: p, br, strong, em, ul, ol, li, h2, h3, a[href] s `rel="nofollow noopener"`). Oprema kao checkboxi po kategorijama. VIN se sprema, nikad se ne prikazuje izvan admina (faza 4 to testira).
   - `title` = "{marka} {model} {varijanta}"; `slug` = `{marka}-{model}-{godina}-{id}` (generira se nakon inserta; pri promjeni marke/modela/godine regeneriraj i stari slug upiši u `vehicle_slug_history`).
   - Akcije: promjena statusa (provjera dopuštenih prijelaza; `published_at` pri prvoj objavi, `sold_at` pri prodaji), istaknuto on/off, dupliciraj (kopija kao skica bez slika), obriši (potvrda; briše slike iz storagea; owner+ — prodavač može brisati samo skice koje je sam kreirao).
   - Audit: `vehicle.create/update/status/feature/duplicate/delete` s `entity_id` i promijenjenim poljima (bez opisa).

4. **Slike** (`app/services/images.py`, `/admin/vozila/{id}/slike`)
   - `process_upload(file) -> ProcessedImage`: provjeri veličinu (`MAX_UPLOAD_MB`), otvori Pillowom (`Image.open` + `verify`, pa ponovno open), dopušteni formati JPEG/PNG/WebP (po stvarnom sadržaju, ne ekstenziji), odbij SVG/GIF/HTML/PDF i slike > 12.000 px, ispravi EXIF orijentaciju prije re-enkodiranja, konvertiraj u RGB, generiraj varijante 400/1000/1600 px širine (WebP, quality 82, bez metapodataka), spremi pod nasumičnim ključem `vehicles/{vehicle_id}/{uuid}_{size}.webp` kroz storage backend. Vrati dimenzije.
   - Stranica slika: grid postojećih slika (thumbnail, alt polje, glavna oznaka), upload više datoteka (drag-and-drop + klasični input, prikaz napretka po datoteci, vanilla JS), obavezan checkbox "Potvrđujem da su registarske tablice zamagljene ili prekrivene" (ako `site.plates_reminder_enabled`), limit `MAX_IMAGES_PER_VEHICLE` (server + poruka), sortiranje povlačenjem (HTML5 drag-and-drop, `POST /admin/vozila/{id}/slike/redoslijed` JSON lista ID-ova), "postavi kao glavnu" (sort_order 0), brisanje, spremanje alt teksta. Sve POST s CSRF tokenom (i JSON pozivi — token u headeru `X-CSRF-Token`).
   - Pri brisanju vozila ili slike obriši sve varijante iz storagea. Za S3 backend provjeri da radi s lažnim endpointom u testu (moto/moto-server ili mock — ako nije jednostavno, testiraj samo lokalni backend i zabilježi).

5. **Testovi** (`tests/test_catalog.py`, `tests/test_vehicles.py`, `tests/test_images.py`)
   - Validacija sheme za svaki tip (obavezna i specifična polja), novo vozilo bez CO2 odbijeno, prijelazi statusa, generiranje i regeneracija sluga + povijest, dupliciranje, brisanje briše slike.
   - Upload: ne-slika s ekstenzijom `.jpg` odbijena, SVG odbijen, iznad limita odbijen, JPEG s EXIF GPS podacima → varijante nemaju EXIF, tri varijante postoje, orijentacija ispravljena, limit broja slika, redoslijed se sprema, prodavač ne može obrisati tuđe aktivno vozilo.

## Provjera prije završetka

- Playwright: kroz admin unesi po jedno vozilo svakog od 5 tipova s 3 slike (generiraj testne slike Pillowom), promijeni status u aktivno, promijeni redoslijed slika. Screenshotovi `docs/screenshots/admin-vozila.png`, `admin-vozilo-forma.png`, `admin-vozilo-slike.png`; pregledaj da su forma i grid uredni na desktopu i na 390 px širine.
- `ruff check .` i `pytest` prolaze. Ažuriraj `CLAUDE.md` (kako dodati polje/tip vozila) i README.
- Git commit: `Faza 3: katalog, vozila, slike`.

## Ne raditi u ovoj fazi

Javne stranice vozila, upite, newsletter, statistiku, seed demo vozila (faza 7).

## Završni izvještaj faze

Što je napravljeno, popis ruta, kako dodati novo polje u shemu, pretpostavke, poznati nedostaci, potvrda testova.
