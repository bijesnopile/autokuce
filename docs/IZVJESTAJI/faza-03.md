# Izvještaj — Faza 3: Katalog, vozila i slike (admin)

Datum: 28.09.2026.

## Što je napravljeno

- **Shema** (`app/vehicle_schema.py`): 5 vrsta vozila (automobil, kombi, motocikl, kamper, kamion) s
  labelama i ikonama; 27 zajedničkih polja (kolone) i specifična polja po vrsti (JSON `attributes`);
  liste goriva, mjenjača, pogona, boja, Euro normi (3–6e), načina oporezivanja; statusi s dopuštenim
  prijelazima; oprema u 5 kategorija (57 stavki, svaka s popisom vrsta). Funkcije `schema_for`,
  `validate_attributes`, `validate_common`, `equipment_for`, `equipment_grouped`, `label`,
  `allowed_transitions`, `power_hp`.
- **Katalog** (`/admin/katalog/*`): marke (dodaj, preimenuj, aktiviraj/deaktiviraj, briši samo bez
  vozila), modeli (naziv + vrsta ili "sve vrste"), uvoz CSV-a s pregledom prije potvrde (preskače
  duplikate, UTF-8/cp1250), pregled vrsta i polja (samo čitanje). Javni `GET /api/modeli?marka=&tip=`
  (rate limit 60/min, cache 5 min). Slugovi s transliteracijom č/ć/š/ž/đ.
- **Vozila** (`/admin/vozila*`): tablica s thumbnailom, pretragom (naslov/VIN/ID), filterima (status
  kao "pilule" s brojačima, vrsta, marka), sortiranjem, paginacijom 25, brzom promjenom statusa,
  oznakama "Bez slika" i "Istaknuto". Dinamička forma u 8 sekcija (odabir vrste karticama; JS
  prikazuje/skriva polja i onemogućuje skrivena; model ovisan o marki preko `/api/modeli`; KS iz kW;
  "cijena na upit" skriva cijenu; nova vozila traže potrošnju i CO2 — klijent i server). Server
  validira prema shemi, greške uz polja uz zadržane vrijednosti. Opis kroz nh3 allowlistu.
  Akcije: status (prijelazi, `published_at`, `sold_at`), istaknuto, dupliciraj (skica bez slika i
  VIN-a), obriši (owner+; prodavač samo vlastite skice). Slug `{marka}-{model}-{godina}-{id}`,
  stari slug u `vehicle_slug_history`. Audit: `vehicle.create/update/status/feature/duplicate/delete/images`.
- **Slike** (`app/services/images.py`, `/admin/vozila/{id}/slike`): provjera veličine, Pillow
  `verify` + ponovno otvaranje, samo JPEG/PNG/WebP po sadržaju, max 12.000 px i 64 MP, EXIF
  orijentacija, re-enkodiranje u WebP 400/1000/1600 bez metapodataka, nasumični ključevi
  `vehicles/{id}/{uuid}_{size}.webp`. Stranica: drag&drop + klasični input, napredak po datoteci,
  obavezna potvrda zamagljenih tablica (ako je uključena u postavkama), limit broja slika, sortiranje
  povlačenjem i strelicama (JSON + `X-CSRF-Token`), glavna slika, brisanje (uklanja sve varijante),
  alt tekstovi. Storage: lokalni i S3 (testiran s moto).
- **Editor** (`app/static/js/editor.js`): vanilla `contenteditable` s alatnom trakom (B, I, H2, H3,
  odlomak, popisi, poveznica, očisti), lijepljenje kao čisti tekst — koristi se i u fazama 6–7.
- **Seed**: `--minimal` sada puni i generički katalog (31 marka, 243 modela).

## Rute

`GET /api/modeli`, `/admin/katalog/marke` (+ `POST`, `/{id}`, `/{id}/aktivno`, `/{id}/obrisi`,
`/{id}/modeli`), `/admin/katalog/modeli/{id}` (+ `/aktivno`, `/obrisi`), `/admin/katalog/uvoz`,
`/admin/katalog/tipovi`, `/admin/vozila`, `/admin/vozila/novo`, `/admin/vozila/{id}` (+ `/status`,
`/istaknuto`, `/dupliciraj`, `/obrisi`), `/admin/vozila/{id}/slike` (+ `/redoslijed`, `/alt`,
`/{img}/glavna`, `/{img}/obrisi`).

## Kako dodati novo polje u shemu

Polje specifično za vrstu: dodaj rječnik u `TYPE_FIELDS["<vrsta>"]` (npr.
`{"key": "sleeping_places", "label": "Broj ležajeva", "type": "int", "min": 1, "max": 10}`) — forma,
validacija i pregled vrsta ažuriraju se automatski, migracija nije potrebna. Zajedničko polje s
kolonom: model + Alembic migracija + `COMMON_FIELDS`. Detaljno u README-u.

## Provjera

- Playwright: kroz admin uneseno po jedno vozilo svih 5 vrsta s 3 slike (generirane Pillowom),
  status "aktivno", promjena redoslijeda slika (spremljeno i provjereno nakon osvježavanja). Bez
  grešaka u konzoli; strogi CSP blokirao je Playwrightov `eval` (dokaz da CSP radi — za test
  korišten `bypass_csp`).
- Screenshotovi: `docs/screenshots/admin-vozila.png`, `admin-vozilo-forma.png`,
  `admin-vozilo-slike.png`; mobilni (390 px) pregledani — bez horizontalnog skrola.
  Ispravljeno nakon pregleda: artefakti fiksnog sidebara u snimkama (desktop layout prebačen na CSS
  grid), nestala strelica na status-selectu, predugačke kartice vozila na mobitelu (kompaktni
  prikaz), prazna kategorija opreme.
- `ruff check .` ✔, `ruff format --check .` ✔, `pytest`: **87 passed** (40 novih u
  `test_catalog.py`, `test_vehicles.py`, `test_images.py`).

## Pretpostavke

`docs/PRETPOSTAVKE.md` → "Katalog, vozila i slike (faza 3)".

## Poznati nedostaci

- HEIC (iPhone) nije podržan — korisnik mora poslati JPEG (iPhone to radi automatski pri dijeljenju);
  zapisano za `docs/SIGURNOST.md`.
- Nema masovnog uređivanja vozila (nije traženo u MVP-u).
