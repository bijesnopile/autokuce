# FAZA 9 — Paket "Standard": funkcionalnosti za demo

## Kontekst

Projekt je gotov MVP (faze 1–8, tag `v0.1.0-mvp`). Prvo pročitaj `CLAUDE.md`, `docs/SPECIFIKACIJA.md` i `docs/PRETPOSTAVKE.md`, pa `git log --oneline | head -20`. Sva pravila iz specifikacije i CLAUDE.md i dalje vrijede (podaci tvrtke samo iz postavki, bez CDN-ova i inline skripti, CSRF na svakom POST-u, audit log, `_()` za stringove, migracije Alembicom, testovi). Ne postavljaj pitanja; nedefinirano odluči sam i zabilježi u `docs/PRETPOSTAVKE.md`.

Radi **redom A → F**; nakon svake stavke: testovi prolaze, `git commit`. Ako stavka ne prolazi ni nakon 3 pokušaja, zabilježi pod "Otvoreno" i nastavi.

## Cilj

Platforma dobiva tri paketa (Osnovni / Standard / Premium) i šest Standard funkcija koje se mogu pokazati autokući uživo. Demo instanca radi s `PLAN=standard`; s `PLAN=osnovni` iste funkcije su vidljive, ali zaključane.

---

## A. Sustav paketa

- Env varijabla `PLAN` (`osnovni` | `standard` | `premium`, default `osnovni`) u `config.py` i `.env.example`; superadmin je može privremeno nadjačati na stranici Sustav (sprema se u `settings` ključ `plan_override`; prikaži jasno da je override aktivan).
- `app/plans.py`: `PLANS` (naziv, opis, redoslijed) i `FEATURES` — rječnik `{kod: {"label": ..., "plans": {...}, "description": ...}}`. Kodovi za ovu fazu: `whatsapp`, `izlog_kartica`, `ponuda_pdf`, `auto_odgovor`, `kalendar_termin`, `kalkulator_rate`, `upit_financiranje`, `feed_portali`, `korisnici_5` (limit korisnika: osnovni 2, standard 5, premium neograničeno). Ostavi mjesto za buduće (`ugovor_pdf`, `marza`, `poslovnice`, `jezici`, `blog`…) — samo kao zapise, bez implementacije.
- `has_feature(code)` dostupan u Jinji (globalno) i u Pythonu; `require_feature(code)` dependency za rute → stranica 403 u admin dizajnu s naslovom "Dostupno u paketu Standard" i kratkim opisom funkcije.
- Admin sidebar i stranice: zaključane stavke **ostaju vidljive** s oznakom (badge) "Standard"/"Premium"; klik vodi na tu 403 stranicu. Na javnoj strani zaključane funkcije se jednostavno ne renderiraju.
- Stranica Sustav: prikaz aktivnog paketa i tablice svih funkcija s oznakom uključeno/zaključano. Limit korisnika provjerava se pri pozivnici.
- `docs/PAKETI.md`: tablica funkcija po paketu (ovo je i temelj cjenika). Preimenuj `docs/PREMIUM-ROADMAP.md` u `docs/ROADMAP.md` i uskladi s paketima.
- Testovi: `has_feature` po planu, `require_feature` → 403, badge u sidebaru kad je zaključano, limit korisnika, override samo superadmin.

## B. WhatsApp / Viber gumb (`whatsapp`)

- Postavke: `whatsapp_number`, `viber_number` (opcionalno; validacija međunarodnog formata, placeholder `+385XXXXXXXXXX`).
- Javno: na detalju vozila (uz upit), u sticky traci na mobitelu i na kontaktu — gumbi "WhatsApp" / "Viber" s inline SVG ikonama. Linkovi: `https://wa.me/{broj}?text={urlencoded}` i `viber://chat?number=%2B{broj}`; tekst "Pozdrav, zanima me {naslov vozila} ({apsolutni URL oglasa})". Bez vanjskih skripti. Prikaži samo ako je broj postavljen i funkcija u planu.
- Statistika: broji klikove kroz internu redirekt rutu `/idi/whatsapp/{vehicle_id}` (bez osobnih podataka), prikaz u statistici po vozilu kao "kontakti".
- Testovi: gumb se renderira samo s brojem i planom; tekst sadrži naslov i URL; redirekt broji i preusmjerava.

## C. A4 kartica za izlog + PDF ponuda (`izlog_kartica`, `ponuda_pdf`)

- Bez novih ovisnosti za PDF: stranice s print CSS-om (`@page { size: A4; margin: 12mm }`), gumb "Ispiši / Spremi kao PDF" (`window.print()` iz `admin.js`). Dokumentiraj da se PDF sprema kroz dijalog ispisa browsera.
- `GET /admin/vozila/{id}/izlog`: A4 portret — LOGO/logo, naslov vozila, velika cijena + način oporezivanja (+ prekrižena stara), 8 ključnih podataka (godina, km, gorivo, snaga, mjenjač, boja, prva registracija, registriran do), do 12 stavki opreme, glavna slika, **QR kod** (postojeća qrcode biblioteka, data-URI) koji vodi na javni oglas, podnožje s telefonom i adresom. Varijanta bez slike (`?slika=0`) i pejzažna polovica A4 za manji izlog (`?format=a5`).
- `GET/POST /admin/vozila/{id}/ponuda`: forma (ime kupca, email — opcionalno, popust ili konačna cijena, vrijedi do — default +7 dana, napomena) → A4 dokument "Ponuda br. {godina}-{id}" s podacima tvrtke (naziv, adresa, OIB), vozilom, cijenom i načinom oporezivanja, opremom, uvjetima (napomena: informativna ponuda, ne obvezuje), potpis. Iz detalja upita gumb "Napravi ponudu" koji predispuni kupca. Ponuda se ne sprema u bazu (MVP), ali se bilježi u audit (`offer.print`, bez podataka kupca).
- Testovi: stranice 200 za owner i salesperson, sadrže cijenu, QR data-URI i podatke iz `site`; VIN se ne prikazuje na izlogu (na ponudi da, jer ide kupcu — zabilježi); zaključano u Osnovnom → 403.

## D. Automatski odgovor kupcu + kalendarski poziv (`auto_odgovor`, `kalendar_termin`)

- Postavke: `auto_reply_enabled` (default true kad je u planu), `auto_reply_text` (predložak s placeholderima `{ime}`, `{vozilo}`, `{radno_vrijeme}`, `{tvrtka}`; seed s lorem-neutralnim, ali smislenim hrvatskim tekstom: "Poštovani {ime}, primili smo Vaš upit za {vozilo}. Javit ćemo Vam se u najkraćem roku, radnim danom {radno_vrijeme}.").
- Nakon svakog upita: email kupcu (predložak `emails/inquiry_auto_reply`, tekst + HTML, impressum, bez marketinga, bez linka za odjavu jer nije newsletter — zabilježi pravnu osnovu: obrada upita). Rate limit po emailu ostaje.
- Termin (`viewing`): kupac i dealer dobivaju `.ics` privitak (VEVENT: naslov "Pregled vozila: {naslov}", lokacija = adresa tvrtke, početak = zatraženi termin, trajanje 60 min, opis s linkom na oglas, `STATUS:TENTATIVE`, podsjetnik 60 min prije). Email backend mora podržati privitke (file backend zapisuje `.ics` uz `.eml`; Brevo API `attachment` polje).
- Admin, detalj upita tipa termin: polje "Potvrđeni termin" (datum/vrijeme, predispunjeno zatraženim) + gumb "Potvrdi termin" → kupcu email potvrde s `.ics` `STATUS:CONFIRMED` i istim `UID` (ažurira postojeći događaj u kalendaru), status upita → kontaktiran, audit. Nova kolona `scheduled_at` (migracija).
- Testovi: auto-odgovor se šalje samo kad je uključen i u planu; `.ics` sadrži ispravne `DTSTART`/`UID`/`LOCATION`; potvrda koristi isti `UID`; kupac ne dobije `.ics` za obični upit.

## E. Kalkulator rate + zahtjev za financiranje (`kalkulator_rate`, `upit_financiranje`)

- Postavke: `financing_enabled`, `financing_rate_percent` (godišnja kamata, default 6,9), `financing_max_months` (84), `financing_min_down_percent` (20), `financing_disclaimer` (seed: "Informativni izračun, ne predstavlja ponudu. Konačne uvjete određuje leasing kuća ili banka.").
- Javno, detalj vozila: blok "Financiranje" s klizačima učešće (%) i rok (mjeseci), izračun mjesečne rate anuitetnom formulom u `public.js` (bez vanjskih biblioteka), prikaz "≈ {rata} €/mj" + disclaimer; bez JS-a prikazuje statični primjer izračunat na serveru (isti algoritam u Pythonu). Na karticama u listi mala oznaka "od {rata} €/mj" (server, default parametri) ako je uključeno.
- Forma "Zatraži ponudu financiranja" (tip upita `financing`, polja: iznos financiranja, učešće, rok, napomena + standardna polja i privola) — koristi postojeći mehanizam upita, tip vidljiv u CRM-u s posebnom ikonom; email dealeru sadrži parametre.
- Ne prikazuj za vozila s "cijena na upit".
- Testovi: izračun rate (poznati primjer: 10.000 € / 60 mj / 6,9 % → ~197,5 €), server i JS daju isti rezultat (test na Python funkciji + Playwright provjera vrijednosti), forma financiranja sprema tip i parametre, sve zaključano u Osnovnom.

## F. Feed prema portalima (`feed_portali`)

- **Istraži aktualne specifikacije** (WebSearch/WebFetch) za: Njuškalo (XML uvoz oglasa za poslovne korisnike), Index oglasi, mobile.de (sučelje za uvoz podataka o vozilima), AutoScout24 (uvoz oglasa), Meta katalog vozila (Vehicle feed). Za svaki portal zapiši u `docs/FEEDOVI.md`: izvor specifikacije (URL i datum), format (XML/CSV), obavezna polja, mapiranje naših polja (gorivo, mjenjač, karoserija, boja, oprema — točni nazivi/šifre koje portal očekuje), što nedostaje u našem modelu. **Ako službena specifikacija nije javno dostupna**, implementiraj dobro strukturiran generički XML za taj portal i jasno označi u dokumentaciji i na admin stranici "Format treba potvrditi s portalom" — ne izmišljaj da je usklađeno.
- Rute: `GET /feed/{portal}.{xml|csv}?token={feed_token}` — `feed_token` se generira pri prvom otvaranju admin stranice (settings), 32+ znaka; bez ispravnog tokena 404. Samo `active` i `reserved` vozila (rezervirana označena gdje portal to podržava), bez skica/prodanih. Slike kao apsolutni URL-ovi (1600 varijanta), opis kao čisti tekst (HTML uklonjen), cijena s načinom oporezivanja mapiranim na polja portala, **VIN isključen** osim ako je za portal uključen u postavkama (`feed_include_vin`, default false). Keširaj generirani feed 5 min; gzip; rate limit 30/min; `Cache-Control` odgovarajući.
- Admin `/admin/feed` (owner+): URL-ovi po portalu s gumbom kopiraj, regeneriraj token (poništava stare URL-ove; potvrda), zadnje preuzimanje po portalu (vrijeme + broj vozila — zapiši u `settings` ili malu tablicu `feed_access`), pregled feeda u novom tabu, **validacija**: popis vozila kojima nedostaju obavezna polja za pojedini portal (npr. mobile.de traži prvu registraciju) s linkom na uređivanje. Upute po portalu (kratko: gdje se u portalu unosi URL feeda / kome poslati).
- Meta katalog: koristi ga i za buduće oglase na Facebooku/Instagramu; standardna polja (`vehicle_id`, `title`, `description`, `url`, `image[0].url`, `make`, `model`, `year`, `mileage.value/unit`, `price`, `state_of_vehicle`, `exterior_color`, `fuel_type`, `transmission`, `body_style`, `vin` isključen, `address` iz postavki, `dealer_name`).
- Testovi: feed bez tokena 404; s tokenom sadrži samo aktivna/rezervirana; VIN odsutan po defaultu; slike apsolutne; HTML uklonjen iz opisa; validacija otkriva vozilo bez obaveznog polja; XML je dobro formiran (parsiraj u testu); CSV s ispravnim zaglavljem; kešira se; zaključano u Osnovnom → 403 i 404 na feedu.

---

## Završetak

- `python -m app.seed --reset-demo` s `PLAN=standard`: demo podaci uključuju WhatsApp broj (`+385XXXXXXXXXX`), jedan upit financiranja, jedan potvrđeni termin.
- `scripts/screenshots.py` proširi: izlog kartica, ponuda, blok financiranja (desktop + mobile), WhatsApp gumbi na mobitelu, admin feed stranica, stranica Sustav s paketima, i **jedan set s `PLAN=osnovni`** (sidebar s oznakama, 403 stranica). Pregledaj screenshotove i ispravi što ne valja.
- `python scripts/check.py` prolazi. Ažuriraj `CLAUDE.md` (paketi: kako dodati funkciju u plan), `README.md` (paketi, feed, `.ics`, financiranje), `docs/PRETPOSTAVKE.md`, `docs/GDPR.md` (auto-odgovor kupcu = obrada upita; feed = javni podaci oglasa bez osobnih podataka; WhatsApp link = bez prijenosa podataka dok kupac ne klikne), `docs/PAKETI.md`, `docs/FEEDOVI.md`.
- `git tag v0.2.0-standard`. Završni izvještaj u `docs/IZVJESTAJI/faza-09.md` i u chatu: što je napravljeno, što je u feedovima potvrđeno prema službenoj specifikaciji a što označeno za provjeru, pretpostavke, otvoreno.
