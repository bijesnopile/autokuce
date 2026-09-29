# FAZA 10 — Sitnice koje daju dojam premium proizvoda

## Kontekst

Projekt je na `v0.2.0-standard` (faze 1–9). Prvo pročitaj `CLAUDE.md`, `docs/SPECIFIKACIJA.md`, `docs/PRETPOSTAVKE.md` i `docs/PAKETI.md`, pa `git log --oneline | head -20`. Sva pravila i dalje vrijede: podaci tvrtke samo iz postavki, bez vanjskih skripti/CDN-ova/inline skripti (CSP), CSRF na svakom POST-u, audit log za admin akcije, `_()` za stringove, migracije Alembicom, testovi, `scripts/check.py` prije završetka. Ne postavljaj pitanja; nedefinirano odluči sam i zabilježi u `docs/PRETPOSTAVKE.md`.

Radi **redom A → E**; nakon svake stavke testovi prolaze i `git commit`. Ako stavka ne prolazi ni nakon 3 pokušaja, zabilježi pod "Otvoreno" i nastavi. Sve stavke pripadaju paketu **Osnovni** (nema zaključavanja) — ažuriraj `docs/PAKETI.md`.

## Cilj

Pet manjih funkcija koje javnu stranicu i admin čine "dotjeranima": favoriti i usporedba vozila, oznaka snižene cijene s poviješću, socijalni dokaz pregleda, dijeljenje s QR kodom, te admin kao aplikacija na telefonu (PWA).

---

## A. Favoriti i usporedba vozila (javno, bez računa)

**Favoriti**
- Gumb-srce na kartici vozila (lista, naslovnica, slična vozila) i na detalju. Stanje u `localStorage` (samo ID-ovi vozila; zabilježi u stranici Kolačići kao "lokalna pohrana za favorite i usporedbu", bez privole jer je funkcija koju korisnik sam traži). Bez JS-a gumb se ne prikazuje (progressive enhancement).
- Link "Favoriti (n)" u zaglavlju (brojač iz JS-a) vodi na `GET /favoriti?v=12,34,56` — **server renderira** vozila po ID-ovima iz upita (samo javno vidljiva; nepostojeća/skrivena se preskaču; max 50). JS pri otvaranju stranice sam sastavi URL iz `localStorage`. Prazno stanje s pozivom na pretragu. Stranica je time i dijeljiva linkom.

**Usporedba**
- Gumb "Usporedi" na kartici i detalju (max 3; kod četvrtog toast "Najviše 3 vozila"). Plutajuća traka pri dnu "Usporedi (2) →" kad je odabrano ≥ 2.
- `GET /usporedba?v=12,34,56` (server-rendered, dijeljiv link, max 3): tablica jedno uz drugo — slika, naslov s linkom, cijena + način oporezivanja (+ stara cijena), godina, prva registracija, km, gorivo, snaga kW/KS, ccm, mjenjač, pogon, karoserija, boja, vrata/sjedala, Euro norma, potrošnja, CO2, garancija, registriran do, polja specifična za tip (unija; "—" gdje nema), oprema kao unija svih stavki s ✓/— po vozilu (grupirano po kategorijama). Prekidač "Prikaži samo razlike" (JS, sakriva retke s istim vrijednostima). Na mobitelu horizontalni skrol s "zalijepljenim" prvim stupcem naziva. Print CSS. Gumb "Ukloni" po vozilu (JS + redirect na novi URL). Meta `noindex` (kombinatorne stranice).
- `public.js`: modul za favorite/usporedbu (čitanje/pisanje `localStorage` u try/catch, sinkronizacija stanja gumba nakon učitavanja, brojači, toast). Sve bez vanjskih biblioteka.
- Testovi: `/favoriti` i `/usporedba` renderiraju samo javna vozila i ignoriraju nevaljane ID-ove; usporedba odbija > 3 (uzima prva 3); unija opreme ispravna; `noindex` prisutan; Playwright: klik na srce → brojač u zaglavlju → stranica favorita prikazuje vozilo; odabir 2 vozila → traka → tablica; "samo razlike" sakriva jednake retke; stanje preživi osvježavanje stranice.

## B. Snižena cijena i povijest cijena

- Nova tablica `vehicle_price_history` (id, vehicle_id, old_price, new_price, changed_at, user_id) — migracija. Zapis pri svakoj promjeni `price_eur` kroz admin (i pri prvom objavljivanju kao početna cijena s `old_price = NULL`). Promjena "cijena na upit" ↔ cijena također se bilježi.
- Pri **sniženju** kroz admin: ako je `price_old_eur` prazno, automatski ga postavi na prethodnu cijenu (dealer ga može obrisati); pri povećanju ga ne diraj. Zabilježi ponašanje u PRETPOSTAVKE.
- Javno: oznaka **"Snižena cijena"** na kartici i detalju ako je zadnja promjena sniženje unutar `PRICE_DROP_BADGE_DAYS` (nova postavka, default 30). Na detalju uz cijenu: "Snižena {datum}: ~~{stara}~~ → {nova} (−{postotak} %)". Javno se prikazuju **samo sniženja** (zadnja 3, sklopivo "Povijest cijene"); povećanja se ne prikazuju javno.
- Admin, stranica vozila: puna povijest (sve promjene, tko, kada). Lista vozila: sortiranje "nedavno sniženo".
- Filter na `/vozila`: checkbox "Samo snižena".
- Demo seed: 2 aktivna vozila sa sniženjem unutar 30 dana (jedno s dva uzastopna sniženja), 1 s povećanjem (koje se javno ne vidi).
- Testovi: promjena cijene stvara zapis; sniženje puni `price_old_eur` samo ako je prazno; badge se prikazuje samo za sniženja unutar roka; povećanje nije javno; filter "samo snižena"; postotak točan; audit zapis.

## C. Socijalni dokaz pregleda

- Postavka `social_proof_enabled` (default true). Iz postojeće `vehicle_views` tablice.
- Detalj vozila: "Pregledano {n} puta u zadnjih 7 dana" — samo ako je `n ≥ 10` (ispod toga se ne prikazuje, da ne djeluje slabo). Bez animacija i lažnih brojki — isključivo stvarni podaci.
- Kartice: oznaka **"Popularno"** za vozila koja su u top 5 po pregledima u zadnjih 7 dana i imaju ≥ 20 pregleda (izračun keširan 10 min, jedan upit, ne po kartici).
- Ne prikazivati broj upita niti "X ljudi gleda upravo sada".
- Demo seed: pregledi raspoređeni tako da 3–4 vozila imaju oznaku i 2–3 prikazuju brojač.
- Testovi: prag 10 i 20; isključeno postavkom; keš; oznaka samo na top 5.

## D. Dijeljenje i QR kod

- Detalj vozila, gumb **"Podijeli"**: na uređajima s Web Share API-jem (`navigator.share`) otvara sistemski dijalog (naslov, cijena, URL); inače popover s: WhatsApp (`wa.me`), Viber, Facebook (običan link na `facebook.com/sharer/sharer.php?u=` — bez SDK-a, bez skripti), email (`mailto:` s naslovom i linkom), **Kopiraj link** (Clipboard API + toast "Link kopiran"; fallback odabir teksta). Nikakvi vanjski resursi se ne učitavaju dok korisnik ne klikne.
- **QR "Otvori na mobitelu"** u tom popoveru i u bočnom bloku detalja na širinama ≥ 1024 px: QR kod javnog URL-a vozila generiran server-side (postojeća `qrcode` biblioteka, data-URI, keširano po vozilu/slugu). Skriven na mobitelu.
- Ista komponenta dijeljenja na `/usporedba` (dijeljenje usporedbe) i `/favoriti`.
- Testovi: blok dijeljenja sadrži ispravne URL-ove i naslov; QR data-URI prisutan; nijedan vanjski `<script>`/`<img>` nije dodan (postojeći test vanjskih resursa mora i dalje prolaziti); Playwright: kopiranje linka daje toast.

## E. Admin kao aplikacija na telefonu (PWA)

- `GET /admin/manifest.webmanifest` (dinamički iz postavki): `name` = "{company_name} – Admin", `short_name` = skraćeno (max 12 znakova), `start_url` = `/admin/`, `scope` = `/admin/`, `display` = `standalone`, `theme_color` = primarna boja, `background_color` bijela, `lang` = `hr`, ikone 192/512 PNG (+ `maskable`).
- Ikone: `GET /admin/pwa-icon-{192|512}.png` — iz logotipa ako postoji (uklopljen na jednobojnu pozadinu primarne boje, s marginom za maskable), inače veliko slovo "L" (placeholder LOGO) na primarnoj boji; generirano Pillowom, keširano na disku, invalidirano pri promjeni logotipa/boje.
- `admin/base.html`: `<link rel="manifest">`, `<meta name="theme-color">`, `apple-touch-icon` (180 px), `apple-mobile-web-app-capable`, `apple-mobile-web-app-title`.
- Service worker `GET /admin/sw.js` (posluženo s `Content-Type: application/javascript` i `Service-Worker-Allowed: /admin/`): **minimalan i network-only** — registrira se, ima `fetch` handler koji samo prosljeđuje mrežne zahtjeve (bez keširanja admin stranica — sadrže osobne podatke i sesije); smije keširati isključivo `/static/*`. Bez push obavijesti u ovoj fazi. CSP `worker-src 'self'` ako je potrebno.
- Registracija SW-a iz `admin.js` (samo na HTTPS-u ili localhostu). Android: uhvati `beforeinstallprompt` i pokaži gumb "Instaliraj aplikaciju" u Profilu; iOS: u Profilu upute "Podijeli → Dodaj na početni zaslon" s ikonicom. Stranica Profil dobiva odjeljak "Aplikacija na telefonu".
- Javna stranica **ne** dobiva PWA (samo `theme-color` meta, već postoji ili dodaj).
- Testovi: manifest je valjan JSON s obveznim poljima i bojom iz postavki; ikone 200 i ispravnih dimenzija (Pillow u testu), mijenjaju se s logotipom; `sw.js` ispravan content-type i ne sadrži cache za `/admin/` rute (statička analiza u testu); admin base sadrži manifest link; Playwright (Chromium): SW se registrira bez grešaka u konzoli.

---

## Završetak

- `python -m app.seed --reset-demo` puni podatke za B i C (vidi gore).
- `scripts/screenshots.py` proširi: kartica sa srcem i "Popularno"/"Snižena cijena" oznakama, stranica favorita (mobile), usporedba (desktop + mobile), detalj s poviješću cijene i blokom dijeljenja s QR-om (desktop), popover dijeljenja (mobile), Profil s odjeljkom PWA. Pregledaj screenshotove; oznake na karticama ne smiju prekrivati placeholder natpis ni jedna drugu (kombinacija NOVO + Snižena + Popularno mora izgledati uredno — definiraj redoslijed i max 2 oznake po kartici, ostalo na detalju).
- `python scripts/check.py` prolazi; suita i na PostgreSQL-u (nova tablica).
- Ažuriraj `CLAUDE.md`, `README.md`, `docs/PAKETI.md` (sve u Osnovnom), `docs/GDPR.md` (localStorage bez privole — funkcija koju korisnik traži; dijeljenje bez vanjskih skripti; SW ne kešira osobne podatke), `docs/PRETPOSTAVKE.md`, stranica Kolačići (lokalna pohrana).
- `git tag v0.3.0-sitnice`. Izvještaj u `docs/IZVJESTAJI/faza-10.md` i kratko u chatu (što je napravljeno, pretpostavke, otvoreno).
