# Izvještaj — Faza 10: sitnice koje daju dojam premium proizvoda

Datum: 29.09.2026. · Oznaka: `v0.3.0-sitnice` · Prompt: `prompts/10-sitnice.md` · Paket: **Osnovni**
(bez zaključavanja; `docs/PAKETI.md`).

Prije faze, na zahtjev: administracija preko cijelog ekrana, vlastite opcije u formi vozila
("+ Nova opcija…", "+ Dodaj opremu", Katalog → Vlastite opcije) i polja za električna vozila
(kWh/100 km, domet, baterija umjesto l/100 km). Commit `8506a5c`.

## Što je napravljeno (svaka stavka zaseban commit)

| | Funkcija | Glavno |
|---|---|---|
| A | Favoriti i usporedba | srce i "Usporedi" na karticama i oglasu (localStorage, bez JS-a skriveno), "Favoriti (n)" u zaglavlju, traka "Usporedi (n)", toast (max 3); `/favoriti?v=` i `/usporedba?v=` renderira poslužitelj (samo javna vozila, `noindex`, dijeljiv link); tablica s unijom opreme, "samo razlike", sticky stupac, ispis; popis lokalne pohrane na stranici Kolačići |
| B | Snižena cijena | tablica `vehicle_price_history` (migracija 0007), zapis svake promjene cijene objavljenog vozila i početne cijene pri objavi, automatska stara cijena pri sniženju, oznaka "Snižena cijena" (postavka, 30 dana), javno samo sniženja (zadnja 3), filter "Samo snižena", admin povijest i sortiranje "Nedavno sniženo", audit `vehicle.price` |
| C | Socijalni dokaz | "Pregledano n puta u zadnjih 7 dana" (od 10), "Popularno" (top 5, od 20, jedan upit, keš 10 min), postavka `social_proof_enabled` |
| D | Dijeljenje i QR | `<details>` izbornik (bez JS-a radi; Web Share API na dodirnim uređajima), WhatsApp/Viber/Facebook preko internog `/podijeli/…` (samo putevi ove stranice), email, kopiranje s toastom; QR "Otvori na mobitelu" (data-URI, keš) u izborniku i bočnoj kartici (≥ 1024 px); isto na favoritima i usporedbi |
| E | PWA admina | manifest iz postavki, ikone 180/192/512 (logotip na primarnoj boji ili početno slovo, maskable margina, keš na disku s hashom), minimalan network-only service worker (keš samo `/static/*`), meta oznake, CSP `worker-src`/`manifest-src`, Profil → "Aplikacija na telefonu" |

**Završetak**
- Demo: dva sniženja (BMW jedno, Škoda dva uzastopna), jedno povećanje (Toyota, javno se ne
  vidi), 4 popularna vozila i 3 samo s brojačem.
- Screenshotovi (61):
  - kartice s oznakama i srcem,
  - detalj sa sniženjem, poviješću i izbornikom dijeljenja s QR-om,
  - usporedba (desktop i mobitel), favoriti (mobitel), izbornik dijeljenja (mobitel),
  - Profil s PWA odjeljkom.
- Ispravci nađeni pregledom screenshotova:
  - Natpis na placeholder slici spušten je i sužen da ga oznake i gumbi ne prekrivaju.
  - Izbornik dijeljenja na mobitelu otvara se udesno.
  - Datumi uzastopnih sniženja u demu su razmaknuti.
  - Uklonjeni su razmaci u "Usporedi (3)" i "3/3".
- Testovi: **417** (SQLite i PostgreSQL 16). Uključuju Playwright scenarije: favoriti, usporedba,
  "samo razlike", preživljavanje osvježavanja, kopiranje linka i registracija service workera.
  `scripts/check.py` prolazi (ruff, format, pytest, pip-audit).

## Pretpostavke (detaljno u `docs/PRETPOSTAVKE.md` → "Faza 10")

**Oznake na kartici**
- Najviše 2 oznake, redom: status → Snižena cijena → Popularno → Novo → Istaknuto.
- Ostale oznake su vidljive na detalju.

**Povijest cijena**
- Bilježi se tek za objavljena vozila. Pri prvoj objavi zapisuje se početna cijena, pa skica ne
  dobiva oznaku "Snižena".

**Dijeljenje**
- Ide preko internog preusmjeravanja, pa stranica nema vanjskih URL-ova i test vanjskih resursa
  ostaje strog.
- Sistemski dijalog se koristi samo na dodirnim uređajima, da računalo zadrži izbornik s QR-om.

**PWA**
- Manifest, ikone i `sw.js` su dostupni bez prijave (sadrže samo naziv i boju).
- Ikona bez logotipa koristi početno slovo tvrtke. Za placeholder naziv to je "L".

**Favoriti i usporedba**
- Bez privole, jer ih korisnik sam pokreće.
- Na stranici Kolačići automatski se ispisuje popis kolačića i lokalne pohrane.

## Otvoreno

- Pravni tekst stranice Kolačići i politike privatnosti je i dalje predložak (`[PRAVNIK]`).
  Automatski popis lokalne pohrane je činjenični.
- Instalacija PWA na stvarnom Android i iOS uređaju nije provjerena (samo Chromium: service worker
  i manifest).
- Iz ranijih faza: `docker compose` na računalu s Dockerom, varijanta backupa s `age`, potvrda
  formata feeda s Njuškalom i Indexom.
