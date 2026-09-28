# Izvještaj — Faza 4: Javni frontend i SEO

Datum: 28.09.2026.

## Što je napravljeno

- **Servis** (`app/services/vehicles.py`, javni dio): `public_query` (aktivna, rezervirana i prodana
  unutar `SOLD_VISIBLE_DAYS`), `parse_filters` (validacija svih GET parametara; nevaljano se ignorira),
  `apply_filters`, `apply_sort` (dostupna prije prodanih), `filter_options` (marke s brojem vozila,
  vrste, rasponi), `similar_vehicles` (ista vrsta, prednost marki, najbliža cijena), `count_view`
  (dnevna tablica + ukupno, bez botova, dedupe 6 h), `spec_sections`, `key_facts`, `youtube_id`.
- **Stranice** (`app/routers/public.py`): naslovnica (hero s brzom pretragom i ovisnim modelom, pločice
  vrsta, istaknuta i zadnje dodana vozila, "Zašto mi", newsletter traka, kontakt), `/vozila` (filteri u
  lijevom panelu / mobilni panel, uklonjive oznake filtera, sortiranje, 12 po stranici, prazno stanje),
  `/vozila/{slug}` (301 sa starog sluga, 410 arhivirano/isteklo, 404 skica; galerija 1000/1600 +
  thumbnailovi, lightbox s tipkovnicom, swipeom i focus trapom; ključni podaci; kutija potrošnje i CO2
  za nova vozila; specifikacije po grupama iz sheme; oprema; opis; video na klik; sidebar s kontaktom,
  formom upita i dogovorom pregleda; mobilna sticky traka "Nazovi / Pošalji upit"; slična vozila;
  ispis), `/kontakt`, `/o-nama`, `/usluge`, `/privatnost`, `/kolacici`, `/uvjeti` (verzija + datum),
  newsletter stranice rezultata. POST upita i newslettera privremeno vraćaju flash "uskoro" (faze 5–6).
- **SEO** (`app/services/seo.py`, `app/routers/seo.py`): title/description/canonical/OG/Twitter po
  stranici; JSON-LD `AutoDealer`, `Car`/`Motorcycle`/`Vehicle` + `Offer` (bez cijene kad je "na upit"),
  `BreadcrumbList`; `/sitemap.xml` (statične + CMS + aktivna/rezervirana vozila s `lastmod`);
  `/robots.txt`; `X-Robots-Tag: noindex` na 404/410/admin; `rel=prev/next`.
- **Dizajn** (`public.css`): kartice vozila (cijela kartica klikabilna, badgeovi NOVO/REZERVIRANO/
  PRODANO/ISTAKNUTO, broj fotografija, prekrižena cijena), filteri s segmentiranim izborom stanja,
  paginacija, galerija, lightbox, sticky traka, kartice kontakta, newsletter traka, print stilovi.
- **JS** (`public.js`): mobilni izbornik, panel filtera, ovisni select modela (`/api/modeli`), galerija
  i lightbox, video na klik (`youtube-nocookie.com`), skrol/fokus na formu, otvaranje forme za pregled,
  ispis, auto-submit sortiranja. Progressive enhancement — sve radi i bez JS-a.
- **Placeholder slike** (`app/services/placeholder_images.py`, `scripts/make_placeholder_images.py`):
  OG slika `static/img/og-default.png` (1200×630) i ilustracije vozila za demo seed.

## Kratki opis dizajna

Neutralna paleta (bijela, svijetlosiva `#f5f6f8`, tamna tipografija `#161a22`, tamno podnožje) +
primarna (`#1e40af`) i akcentna (`#e11d48`) boja iz postavki; sistemski font stack; zaobljene kartice
(10–22 px), suptilne sjene, gumbi min. 44 px (dodir). Grid vozila 1/2/3/4 stupca (lista s filterima
1/2/3). Hero s gradijentom iz primarne boje i blagom mrežom linija (bez fotografija).

## Rezultati provjere vanjskih zahtjeva

Playwright je bilježio sve mrežne zahtjeve na naslovnici, listi, detalju i kontaktu (desktop i
mobitel): **svi zahtjevi idu samo na localhost**; konzola bez grešaka. Test
`test_no_external_resources_*` provjerava `src`, `href`, `srcset`, `url()` i `@import` (dopuštene su
samo poveznice tvrtke iz postavki: društvene mreže i Google Maps); Turnstile/Umami provjereni u oba
stanja (uključeno/isključeno). HTML dobro formiran (test ravnoteže tagova).

## Screenshotovi

`docs/screenshots/javno-naslovnica-desktop.png`, `javno-naslovnica-mobile.png`,
`javno-lista-desktop.png`, `javno-lista-mobile.png`, `javno-detalj-desktop.png`,
`javno-detalj-mobile.png`, `javno-kontakt-desktop.png`, `javno-kontakt-mobile.png`,
`javno-lightbox-desktop.png`, `javno-404-mobile.png` — pregledani (bez horizontalnog skrola na 390 i
1440 px). Ispravljeno nakon pregleda: odrezan panel filtera (bio sticky s max-height), godina prikazana
kao "2.021", dvostruka cijena na desktopu, `_` prepisan u makrou kartice.

## Testovi

`ruff check .` ✔, `ruff format --check .` ✔, `pytest`: **118 passed** (31 novi u `test_public.py`).

## Pretpostavke

`docs/PRETPOSTAVKE.md` → "Javni frontend i SEO (faza 4)".

## Poznati nedostaci

- Screenshotovi koriste privremena vozila iz faze 3 (puni demo seed dolazi u fazi 7 — tada se
  screenshotovi ponavljaju).
- Hreflang još nije potreban (jedan jezik); struktura je spremna (`LANGUAGE`, `og:locale`).
