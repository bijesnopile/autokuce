# Feedovi za oglasnike (paket Standard)

Funkcija `feed_portali`. Admin: **/admin/feed** (vlasnik i superadmin). Javni URL:

```
GET /feed/{portal}.{xml|csv}?token={feed_token}
```

- Portali: `njuskalo`, `index`, `mobile_de`, `autoscout24`, `meta`.
- **Token** se izrađuje pri prvom otvaranju /admin/feed. To je `secrets.token_urlsafe(32)` od 43 znaka.
  Kriv ili nepostojeći token, nepoznat portal ili format te zaključan paket daju isti odgovor: `404`.
  Novi token odmah poništava stare URL-ove (potvrda u sučelju, audit `feed.token`).
- **Sadržaj:** samo aktivna i rezervirana vozila, sortirana od najnovije objave.
  - Slike su apsolutni URL-ovi varijante od 1600 px, najviše 20.
  - Opis je običan tekst (HTML se uklanja).
  - **VIN se ne izvozi** osim kad je uključena postavka `feed_include_vin` na /admin/feed.
- **Tehnički:** keš 5 minuta po portalu i formatu, gzip kad klijent šalje `Accept-Encoding: gzip`.
  Rate limit je 30 zahtjeva u minuti po IP-u. Zaglavlja: `Cache-Control: private, max-age=300`,
  `X-Robots-Tag: noindex`, a `robots.txt` sadrži `Disallow: /feed/`.
- **Zadnje preuzimanje** se bilježi po portalu u tablici `feed_access` (vrijeme, format, broj preuzimanja,
  bez IP-a). Pregled u adminu (`/admin/feed/pregled/...`) se ne broji.
- **Provjera podataka** na /admin/feed navodi vozila kojima nedostaje obavezno polje nekog portala, uz
  poveznicu na uređivanje.

Kod: `app/services/feeds.py` (zajednički zapis, keš, token), `app/services/feed_formats.py` (formati,
mapiranja, obavezna polja), `app/routers/admin_feed.py` (rute).

## Stanje specifikacija (provjereno 29.09.2026.)

| Portal | Javna specifikacija | Kako portal prima oglase | Naš feed |
|---|---|---|---|
| Meta (Facebook/Instagram) | **da** | preuzima URL (zakazani feed, CSV/TSV/XML) | **prema specifikaciji** |
| mobile.de | da (API i CSV) | **push**: Seller API ili CSV+ZIP upload, nema preuzimanja URL-a | generički XML/CSV + kodovi mobile.de, **treba potvrditi** |
| AutoScout24 | da (API) | **push**: Listing Creation API (JSON), slike se šalju kao datoteke | generički XML/CSV + kodovi AS24, **treba potvrditi** |
| Njuškalo | **ne** (samo za partnere) | partnerski XML uvoz uz aktivacijski kod | generički XML, **treba potvrditi** |
| Index oglasi | **ne** (nije pronađena) | nepoznato (DMS-ovi navode "prijenos na Index") | generički XML, **treba potvrditi** |

**Ne tvrdimo usklađenost** ni za jedan portal osim Mete. Generički feed na korijenskom elementu nosi
oznaku `napomena="Format treba potvrditi s portalom"`, a u adminu stoji oznaka "format treba potvrditi s
portalom".

---

## Meta — katalog vozila (Automotive Inventory Ads)

- **Izvori** (pregledano 29.09.2026.):
  - <https://developers.facebook.com/docs/marketing-api/auto-ads/reference/>
  - <https://developers.facebook.com/docs/marketing-api/auto-ads/guides/catalog/>
- **Formati:** CSV, TSV, XML. Feed se hostira na URL-u i preuzima po rasporedu iz Commerce Managera.
  - XML: korijen `<listings>`, zapisi `<listing>`.
  - Ugniježđeno: `<image><url>`, `<mileage><value>/<unit>`,
    `<address format="simple"><component name="addr1|city|region|postal_code|country">`.
  - U CSV-u su `image[n].url` i `mileage.value/unit` zasebni stupci. `address` je jedan stupac s JSON
    objektom (`{"addr1": …, "city": …, "region": …, "postal_code": …, "country": "HR"}`).
- Vrijednosti enumeracija ne razlikuju velika i mala slova.

| Polje Meta | Obavezno | Izvor u aplikaciji |
|---|---|---|
| `vehicle_id` | da | `vehicles.id` |
| `title` (≤500) | da | naslov oglasa |
| `description` (≤5000, bez poveznica) | da | opis kao tekst, poveznice uklonjene, skraćeno na 5000 znakova; bez opisa ide naslov |
| `url` | da | apsolutni URL oglasa |
| `image[].url` (1–20) | da | slike od 1600 px |
| `make`, `model`, `year` | da | marka, model, godina |
| `mileage.value`, `mileage.unit` | da | kilometraža, `KM` |
| `price` | da | `"15000 EUR"`; vozila s cijenom na upit se ne izvoze |
| `body_style` | da | limuzina→SEDAN, karavan→WAGON, hatchback→HATCHBACK, SUV→SUV, coupé→COUPE, kabriolet→CONVERTIBLE, monovolumen→MINIVAN, pickup→TRUCK; kombi/kamper→VAN, kamion→TRUCK; inače OTHER |
| `exterior_color` | da | boja (engleski naziv) |
| `state_of_vehicle` | da | New / Used |
| `address` (city, region, country) | da | adresa tvrtke (ulica, poštanski broj i grad iz postavke adrese) + **županija s /admin/feed**, `country=HR` |
| `latitude`, `longitude` | da | **koordinate s /admin/feed** |
| `fuel_type` | ne | benzin→GASOLINE, dizel→DIESEL, hibrid i plug-in→HYBRID, električni→ELECTRIC, LPG/CNG→OTHER |
| `transmission` | ne | Manual / Automatic |
| `drivetrain` | ne | prednji→FWD, stražnji→RWD, 4x4→4X4 |
| `trim` | ne | izvedba |
| `vin` | ne | samo uz `feed_include_vin` |
| `availability` | ne | aktivno→`available`, rezervirano→`not_available` (ostaje u katalogu, ne oglašava se) |
| `dealer_name`, `dealer_phone` | ne | postavke tvrtke |

**Praznine:**
- Meta nema polje za PDV ili maržu, pa se cijena šalje kakva je objavljena.
- Za električna vozila nema posebnog polja za podatke o bateriji.
- Regija i koordinate nisu dio postavki tvrtke, pa se upisuju na /admin/feed. Dok nisu upisane, stranica
  upozorava. Bez županije se kao regija šalje grad.

## mobile.de

- **Izvori** (pregledano 29.09.2026.):
  - Seller API: <https://services.mobile.de/docs/seller-api.html>
  - CSV sučelje: <https://services.mobile.de/manual/upload-interface-csv_de.html>
  - Referentni podaci: <https://services.mobile.de/refdata/fuels>
- **Seller API:** REST (JSON ili XML), HTTP Basic auth.
  - Pristup imaju pružatelji prijenosa i trgovci registrirani na mobile.de; aktivacija ide preko
    service@team.mobile.de.
  - Oglas se šalje s `POST /seller-api/sellers/{id}/ads`. Slike se prvo učitavaju, a oglas se na njih
    poziva.
  - Cijena se šalje objektom `consumerPriceGross` / `consumerPriceNet` / `vatRate` / `type`
    (FIXED, ON_REQUEST).
- **CSV upload:** ISO-8859-15, odvojeno točkom-zarezom, **bez zaglavlja** (fiksni redoslijed stupaca).
  - Datoteka se može zapakirati u ZIP; slike su u ZIP-u kao `{bild_id}_1.jpg` … `_15.jpg`.
  - Svaki upload zamjenjuje cijelu ponudu.
  - `mwst`: 0 = PDV iskaziv, 1 = PDV nije iskaziv (marža).
- **Zaključak:** mobile.de ne preuzima feed s URL-a. Naš feed je izvor podataka za integratora ili za
  buduću izravnu integraciju s API-jem (vidi `docs/ROADMAP.md`).

Mapiranje koje nosi atribut `kod` u generičkom XML-u (`/feed/mobile_de.xml`):

| Naše | mobile.de (Seller API) |
|---|---|
| gorivo | benzin→PETROL, dizel→DIESEL, hibrid i plug-in→HYBRID, električni→ELECTRICITY, LPG→LPG, CNG→CNG |
| mjenjač | ručni→MANUAL_GEAR, automatski→AUTOMATIC_GEAR |
| karoserija | limuzina→Limousine, karavan→EstateCar, hatchback→SmallCar, SUV→OffRoad, coupé→SportsCar, kabriolet→Cabrio, monovolumen→Van, pickup→OtherCar |
| stanje | NEW / USED |
| PDV | `cijena@odbitni_pdv`: da = R1 (PDV iskaziv), ne = marža ili cijena bez PDV-a |

**Treba potvrditi:**
- `hatchback→SmallCar` i `coupe→SportsCar` su najbliža, ali nesavršena preslikavanja.
- Za plug-in hibrid mobile.de ima dodatna polja.
- Marka i model u API-ju koriste njihove šifre (referentni podaci), a mi šaljemo nazive.

## AutoScout24

- **Izvori** (pregledano 29.09.2026.):
  - Dokumentacija: <https://listing-creation.api.autoscout24.com/docs>
  - OpenAPI: <https://listing-creation.api.autoscout24.com/assets/openapi/spec.yml>
  - Referentni podaci: `/references` na istom API-ju
- **Listing Creation API:** REST/JSON, Basic auth. Pristupne podatke izdaje AutoScout24 pružatelju
  podataka, a trgovac mu prosljeđuje svoj `customerId`.
  - Obavezna polja: `availability`, `make`, `offerType`, `publication`, `vehicleType`, a za EU i
    `prices`.
  - Cijena: `prices.public.isTaxDeductible` (false = marža).
  - **Slike se šalju kao binarne datoteke**, najviše 50 po oglasu.
  - Postoji i stariji FTP upload.
- `github.com/smg-automotive/autoscout24-api-specs` je API **švicarskog** AutoScout24, a ne EU-a.
- **Zaključak:** AutoScout24 ne preuzima feed s URL-a. Naš feed služi integratoru.

| Naše | AutoScout24 (`/references`) |
|---|---|
| gorivo | benzin→B, dizel→D, hibrid i plug-in→2, električni→E, LPG→L, CNG→C |
| mjenjač | ručni→M, automatski→A |
| karoserija | hatchback→1, kabriolet→2, coupé→3, SUV/pickup→4, karavan→5, limuzina→6, monovolumen→12 |
| stanje (`offerType`) | novo→N, rabljeno→U |
| PDV | `cijena@odbitni_pdv` → `isTaxDeductible` |

**Treba potvrditi:** marka i model u API-ju su numerički ID-evi iz `/makes`, a mi šaljemo nazive.

## Njuškalo

- **Javna specifikacija nije dostupna.** Stranice njuskalo.hr zaštićene su od automatskog pristupa, a
  pretraga nije našla dokumentaciju uvoza (29.09.2026.).
- Posredni izvori:
  - Pomoć DMS-a AutoBrief (<https://autobrief.productfruits.help/hr/article/oglasavanje-njuskalo>):
    trgovac DMS-u daje Njuškalo aktivacijski kod, a aktivacija traje do 24 sata.
  - Neslužbeni izvor navodi da Njuškalo uvoz obrađuje noću.
  - Za nekretnine Njuškalo prima XML "prema službenoj specifikaciji portala" (partnerski).
- **Naš feed:** generički XML (`format="autokuca-generic-1"`) s opisom svih polja ispod. **Format treba
  potvrditi s Njuškalom:** zatražiti specifikaciju za auto-kuće i prilagoditi builder
  (`BUILDERS["njuskalo"]`).

## Index oglasi

- **Javna specifikacija nije pronađena.** Stranica pomoći index.hr/oglasi/pomoc ne spominje uvoz,
  a pretraga nije dala rezultat (29.09.2026.).
- DMS Centar MCS (<http://centar-mcs.hr/programi/dms/auto-salon/>) navodi "prijenos na Njuškalo,
  Index.hr" kao dodatak, što upućuje na partnersko sučelje.
- **Naš feed:** generički XML. **Format treba potvrditi s Indexom.**

---

## Generički format (`autokuca-generic-1`)

XML (UTF-8), korijen `<vozila format="autokuca-generic-1" portal="…" napomena="Format treba potvrditi s
portalom" generirano="…Z">`:

```xml
<prodavac><naziv/><adresa/><telefon/><email/></prodavac>
<vozilo id="12">
  <url/><naslov/><vrsta/><marka/><model/><izvedba/><stanje kod="…"/><status/>
  <godina/><prva_registracija>2019-05</prva_registracija>
  <kilometraza jedinica="km">120000</kilometraza>
  <cijena valuta="EUR" oporezivanje="marza|pdv|bez_pdv" odbitni_pdv="da|ne">15000</cijena>
  <!-- ili <cijena_na_upit>da</cijena_na_upit> -->
  <gorivo kod="…">dizel</gorivo><mjenjac kod="…"/><pogon/><karoserija kod="…"/>
  <snaga jedinica="kW" ks="150">110</snaga><obujam_ccm/><boja/><vrata/><sjedala/>
  <euro_norma/><co2_g_km/><potrosnja_l100/><potrosnja_kwh100/><domet_km/><baterija_kwh/>
  <opis>običan tekst</opis>
  <slike><slika>https://…_1600.webp</slika></slike>
  <oprema><stavka>abs</stavka></oprema>
  <vin/>          <!-- samo uz feed_include_vin -->
  <azurirano>2026-09-29T10:00:00Z</azurirano>
</vozilo>
```

- **Kodovi** (gorivo, mjenjač, karoserija, oprema) su iz `app/vehicle_schema.py`. Atribut `kod` postoji
  samo za portale s javnim referentnim podacima (mobile.de, AutoScout24).
- **Prazna polja** se izostavljaju.
- **CSV** (`mobile_de.csv`, `autoscout24.csv`): isti podaci, UTF-8, odvojeno točkom-zarezom, sa
  zaglavljem. Slike su u stupcu `slike` odvojene razmakom, oprema u stupcu `oprema` odvojena zarezom.

**Obavezna polja za provjeru:**
- Generički feed: marka, model, godina, kilometraža, cijena, gorivo, barem jedna slika.
- mobile.de i AutoScout24 još traže prvu registraciju i snagu.
- Meta: marka, model, godina, kilometraža, cijena, slika, boja.

## Otvoreno

- Za Njuškalo i Index zatražiti službenu specifikaciju i dodati builder u `BUILDERS`.
- Za mobile.de i AutoScout24: izravna API integracija (push) ili integrator. Za CSV prema mobile.de
  trebali bi fiksni stupci, ISO-8859-15 i ZIP sa slikama, pa je to zasebna funkcija.
- Meta feed je rađen prema javnoj referenci. **Prvo stvarno preuzimanje u Commerce Manageru još nije
  provjereno** (nema testnog kataloga).
