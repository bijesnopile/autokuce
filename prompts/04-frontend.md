# FAZA 4/8 — Javni frontend i SEO

## Kontekst

Faza 4 od 8. Prvo pročitaj `CLAUDE.md` i `docs/SPECIFIKACIJA.md` [ako je nema u `docs/`, kopiraj `prompts/SPECIFIKACIJA.md` u `docs/`] (posebno poglavlja 3, 8, 9, 14 — kolačići/vanjski resursi, 15). Provjeri stanje repozitorija (faze 1–3 gotove). Ne postavljaj pitanja; nedefinirano odluči sam i zabilježi u `docs/PRETPOSTAVKE.md`.

## Cilj faze

Kompletan javni dio stranice: čist, mobile-first dizajn, lista vozila s filterima, detalj s galerijom, statične i pravne stranice, kontakt, SEO. Nakon ove faze stranica se već može pokazati kao demo (uz ručno unesena vozila; demo seed dolazi u fazi 7).

## Zadaci

1. **Upiti za podatke** (`app/services/vehicles.py`)
   - `public_query(db)`: samo `status in (active, reserved, sold)`; prodana vidljiva do `sold_at + SOLD_VISIBLE_DAYS`.
   - Filteri iz GET parametara: `tip`, `marka`, `model`, `cijena_od`, `cijena_do`, `godina_od`, `godina_do`, `km_do`, `gorivo`, `mjenjac`, `stanje`; validacija (nevaljane vrijednosti se ignoriraju); sortiranje `najnovije` (default), `cijena_uzlazno`, `cijena_silazno`, `km_uzlazno`, `godina_silazno`; paginacija 12 po stranici; brojači rezultata. Opcije filtera (marke s brojem vozila, rasponi godina/cijena) računaju se iz aktivnih vozila.
   - `similar(vehicle, n=4)`: isti tip, prednost istoj marki, sličan cjenovni razred.

2. **Stranice** (`app/routers/public.py`) — sve prema poglavlju 8
   - `/`: hero (naslov, podnaslov iz `site`, CTA "Pregledaj vozila"), brza pretraga (tip, marka, model ovisan o marki preko `/api/modeli`, cijena do → redirect na `/vozila?…`), istaknuta vozila (do 8), zadnje dodana (do 8), blok "Zašto mi" (3 stavke lorem ipsum s inline SVG ikonama), newsletter CTA (forma se renderira; POST handler dolazi u fazi 6 — do tada ruta vraća flash "Dostupno uskoro"), kontakt blok (radno vrijeme, telefon, adresa, gumb "Otvori u Google kartama" kao link).
   - `/vozila`: filteri (desktop: lijevi panel; mobitel: gumb "Filteri" otvara sklopivi panel s brojem aktivnih filtera), aktivni filteri kao uklonjive oznake, sortiranje, grid kartica (slika 4:3 s `srcset` 400/1000, naslov, godina · km · gorivo · mjenjač, cijena + prekrižena stara ili "Cijena na upit", badge NOVO/REZERVIRANO/PRODANO/ISTAKNUTO), paginacija s `rel=prev/next`, prazno stanje s prijedlogom uklanjanja filtera. Kanonski URL bez praznih parametara.
   - `/vozila/{slug}`: ako slug u `vehicle_slug_history` → 301 na trenutni; arhivirano → 410 s porukom i linkom na listu; skica → 404. Galerija: glavna slika (1000/1600 `srcset`), thumbnailovi, lightbox u vanilla JS-u (strelice, tipkovnica, swipe, zatvaranje, `aria`), brojač slika. Naslov, badge statusa, cijena + način oporezivanja + stara cijena, ključni podaci (godina, km, gorivo, snaga kW/KS, mjenjač, stanje), sekcije: Specifikacije (zajednička + specifična polja iz sheme, po grupama; potrošnja i CO2 istaknuti kod novih vozila), Oprema (po kategorijama), Opis (sanitizirani HTML), Video (samo ako postoji: slika s gumbom "Učitaj video", tek na klik iframe `youtube-nocookie.com`). Sidebar (desktop) / ispod (mobitel): kontakt tvrtke + forma "Upit za vozilo" + gumb "Dogovori pregled vozila" (otvara istu formu s poljem datuma — handleri u fazi 5, zasad flash "Dostupno uskoro"). Sticky traka na mobitelu: "Nazovi" (`tel:`) i "Pošalji upit" (skrol na formu). Slična vozila. Gumb "Ispiši" s print CSS-om (bez navigacije, sve slike malo, specifikacije u dva stupca). **VIN se nigdje ne prikazuje.**
   - `/kontakt`: podaci tvrtke, radno vrijeme, karta samo kao gumb-link, opći kontakt formular (POST u fazi 5).
   - `/o-nama`, `/usluge`, `/privatnost`, `/kolacici`, `/uvjeti`: iz tablice `pages`; pravne stranice prikazuju "Verzija X · ažurirano DD.MM.GGGG."; neobjavljena stranica → 404.
   - `/newsletter/potvrda/{token}`, `/newsletter/odjava/{token}`: templatei s porukama (logika u fazi 6).
   - Brojanje pregleda: pri svakom prikazu detalja upsert u `vehicle_views` (vehicle_id, date) i `views_total += 1`, osim za poznate botove (UA sadrži bot/crawler/spider/preview) i osim ako je isti posjetitelj već brojan u zadnjih 6 h (potpisani kolačić s listom ID-ova, bez osobnih podataka, bez pristanka jer nije praćenje između stranica — zabilježi obrazloženje u PRETPOSTAVKE.md; alternativno skip dedupe).

3. **SEO** (`app/services/seo.py`, `app/routers/seo.py`)
   - Po stranici `<title>` i `meta description` (vozilo: "{naslov}, {godina}, {km} – {company_name}"), canonical, Open Graph + Twitter Card (vozilo: glavna slika 1600; ostalo: generirana OG slika s tekstom LOGO nije potrebna — koristi `static/img/og-default.png` generiran Pillowom u seedu/skripti s tekstom `IME PODUZEĆA`).
   - JSON-LD: naslovnica `AutoDealer` (naziv, adresa, telefon, email, radno vrijeme iz `site`); vozilo `Car`/`Motorcycle`/`Vehicle` (prema tipu) s `brand`, `model`, `vehicleModelDate`, `mileageFromOdometer`, `fuelType`, `vehicleTransmission`, `color`, `vehicleEngine` (kW), `itemCondition` (NewCondition/UsedCondition), `image[]`, `offers` (`Offer` s `price`, `priceCurrency: EUR`, `availability` InStock/SoldOut, `seller`); `BreadcrumbList` na listi i detalju. Bez cijene kad je "na upit".
   - `/sitemap.xml` (statične stranice + aktivna/rezervirana vozila s `lastmod`, bez prodanih), `/robots.txt` (`Disallow: /admin`, `Disallow: /api`, `Sitemap:`), `X-Robots-Tag: noindex` na 410/404 i admin rutama.
   - Slike: `alt` = "{naslov} – slika {n}", `loading="lazy"` (osim glavne na detalju), `width/height` atributi, cache headeri na `/media`.

4. **Dizajn i front-end kod**
   - Dovrši `public.css` prema poglavlju 9: kartice, filteri, galerija, lightbox, sticky traka, badge boje (novo = primary, rezervirano = žuta, prodano = siva), prazna stanja, print stilovi. Sve komponente rade od 360 do 1440 px.
   - `public.js` (bez biblioteka): mobilni izbornik, panel filtera, ovisni select modela, lightbox, video-na-klik, skrol na formu, zatvaranje flash poruka. Bez inline skripti (CSP). Progressive enhancement — stranica radi i bez JS-a (filteri su običan GET formular).
   - Pristupačnost: skip-link, landmarks (`header/nav/main/footer`), `aria-label` na ikonskim gumbima, focus trap u lightboxu, kontrast AA na badgeovima.

5. **Testovi** (`tests/test_public.py`)
   - Naslovnica/lista/detalj/kontakt/pravne stranice 200 i sadrže placeholdere iz `site`; skica i arhivirano nisu javno dostupni (404/410); stari slug → 301; filteri vraćaju točan skup (fixture s 6 vozila); sortiranje; paginacija; detalj sadrži JSON-LD s `"@type"` i `"priceCurrency":"EUR"`, **ne sadrži VIN**; nova vozila prikazuju potrošnju/CO2; prodano nakon `SOLD_VISIBLE_DAYS` nestaje s liste; sitemap sadrži samo aktivna/rezervirana; robots sadrži `Disallow: /admin`; brojanje pregleda ne broji botove; **HTML javnih stranica ne sadrži nijedan vanjski URL u `src`, `href` (osim `mailto:`/`tel:`/društvenih mreža iz `site`), `@import` ili `url()`** (Turnstile/Umami samo kad su konfigurirani — testiraj oba slučaja).

## Provjera prije završetka

- Playwright na 1440×900 i 390×844: screenshotovi `docs/screenshots/javno-naslovnica-{desktop,mobile}.png`, `javno-lista-*.png`, `javno-detalj-*.png`, `javno-kontakt-*.png`, `javno-lightbox-desktop.png`, `javno-404-mobile.png`. Ako nema vozila u bazi, privremeno kreiraj 6 testnih vozila sa slikama kroz servis (ne kroz seed). **Pregledaj screenshotove**: bez preklapanja, odsječenog teksta, horizontalnog skrola, praznih rupa; hijerarhija jasna; ispravi što ne valja i ponovi.
- Playwright: bilježi sve mrežne zahtjeve tijekom posjeta 4 stranice — smiju ići samo na `localhost`. Konzola bez grešaka.
- `ruff check .` i `pytest` prolaze. Ažuriraj `CLAUDE.md` i README.
- Git commit: `Faza 4: javni frontend i SEO`.

## Ne raditi u ovoj fazi

Obradu POST-a upita i newslettera (faze 5–6), statistiku, seed demo podataka (faza 7).

## Završni izvještaj faze

Što je napravljeno, popis ruta, kratki opis dizajna (paleta, komponente), rezultati provjere vanjskih zahtjeva, pretpostavke, poznati nedostaci, potvrda testova. Priloži popis screenshotova.
