# Izvještaj — Faza 5: Upiti, anti-spam i mini-CRM

Datum: 28.09.2026.

## Što je napravljeno

- **Anti-spam**: `app/services/turnstile.py` (`verify_turnstile`, isključen bez ključa, upozorenje pri
  startu; widget i skripta samo uz `TURNSTILE_SITE_KEY`), honeypot `website` (lažni uspjeh), potpisani
  timestamp forme (`form_ts`, odbija < 3 s), rate limit 5 / 10 min po IP-u i 3 / h po hashu emaila (429).
- **Javne forme** (`templates/public/_inquiry_form.html`): varijante `vehicle` (detalj vozila),
  `viewing` (detalj, u `<details>`, polje datuma/vremena s `min` = sutra) i `general` (kontakt).
  Polja: ime, email, telefon (opcionalno, normalizacija na `+385…`), poruka (10–2000), privola
  (neoznačena, tekst iz pogl. 14), Turnstile, honeypot, CSRF.
- **`POST /upit`**: validacija s greškama uz polja i zadržanim vrijednostima (bez gubitka konteksta
  vozila), provjera vozila (skica/nepostojeće → 400), spremanje s `consent_at/ip/user_agent`,
  verzijom politike i izvorom, PRG s porukom "Hvala, javit ćemo vam se u najkraćem roku.", email
  dealeru u pozadini (`emails/inquiry_notification`, `Reply-To` kupca) + `email_log`.
- **Mini-CRM** (`/admin/upiti`): inbox (status "pilule" s brojačima, filteri vrsta/dodijeljeno/vozilo/
  razdoblje, pretraga ime/email/telefon, sortiranje, paginacija 25, oznaka "> 48 h", zadnja bilješka),
  badge broja novih upita u sidebaru; detalj (poruka, termin, "Odgovori emailom" s predloženim
  subjectom, podaci kupca, status, dodjela, bilješke s brisanjem vlastitih unutar 15 min, kartica
  vozila, podaci o privoli s maskiranim IP-om, noviji/stariji); brisanje (owner+); CSV izvoz (owner+,
  BOM + `;`). Audit: `inquiry.status/assign/note/delete/export` samo s ID-ovima.
- **Nadzorna ploča**: kartice sada prikazuju prave brojeve (aktivna vozila, novi upiti, pretplatnici,
  pregledi 30 dana).
- **Retencija**: `app/services/maintenance.py::purge_old_inquiries` + `python -m app.cli maintenance
  [--dry-run]`.

## Rute

`POST /upit`, `GET /admin/upiti`, `GET /admin/upiti/izvoz.csv`, `GET /admin/upiti/{id}`,
`POST /admin/upiti/{id}/status|dodjela|biljeske|obrisi`, `POST /admin/upiti/{id}/biljeske/{note}/obrisi`.

## Turnstile u produkciji

Cloudflare → Turnstile → Add site (domena klijenta, "Managed") → `TURNSTILE_SITE_KEY` i
`TURNSTILE_SECRET_KEY` u `.env` klijenta → restart. CSP se automatski proširuje; bez ključeva forme rade
samo s honeypotom, vremenskom provjerom i rate limitom.

## Provjera

- Playwright (mobitel): upit za vozilo iz sticky trake i zahtjev za pregled (otvaranje `<details>`,
  termin) — obje poruke zahvale prikazane; u adminu upiti vidljivi, status promijenjen u "Kontaktiran",
  dodana bilješka. U `data/outbox/` dva emaila dealeru s ispravnim `To`, `Reply-To` i podacima.
  Bez grešaka u konzoli, mobilni admin bez horizontalnog skrola.
- Screenshotovi: `docs/screenshots/javno-upit-forma-mobile.png`, `admin-upiti.png`,
  `admin-upit-detalj.png` — pregledani. Ispravljeno: ikona u info-alertu lomila je redak; polja
  toolbara rastezala su se preko cijelog reda.
- `ruff check .` ✔, `ruff format --check .` ✔, `pytest`: **138 passed** (20 novih u
  `test_inquiries.py`).

## Pretpostavke

`docs/PRETPOSTAVKE.md` → "Upiti i mini-CRM (faza 5)".

## Poznati nedostaci

- Rate limiter je po procesu (s 2 workera limit je efektivno 2×) — Redis opcija u `docs/SIGURNOST.md`.
- Nema automatskog emaila kupcu (izvan MVP-a po specifikaciji).
