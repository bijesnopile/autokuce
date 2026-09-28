# FAZA 5/8 — Upiti, anti-spam i mini-CRM

## Kontekst

Faza 5 od 8. Prvo pročitaj `CLAUDE.md` i `docs/SPECIFIKACIJA.md` [ako je nema u `docs/`, kopiraj `prompts/SPECIFIKACIJA.md` u `docs/`] (posebno poglavlja 6, 10, 11, 13, 14). Provjeri stanje repozitorija (faze 1–4 gotove: forme su renderirane, handleri vraćaju "Dostupno uskoro"). Ne postavljaj pitanja; nedefinirano odluči sam i zabilježi u `docs/PRETPOSTAVKE.md`.

## Cilj faze

Kupci šalju upite (za vozilo, opći, termin za pregled) sa zaštitom od spama i zabilježenom privolom; dealer dobiva email i obrađuje upite u mini-CRM-u.

## Zadaci

1. **Anti-spam** (`app/services/turnstile.py`, `app/security.py`)
   - `verify_turnstile(token, ip) -> bool`: POST na `https://challenges.cloudflare.com/turnstile/v0/siteverify` (httpx, timeout 5 s). Ako `TURNSTILE_SECRET_KEY` nije postavljen → vrati True i logiraj upozorenje jednom pri startu ("Turnstile isključen"). Widget se renderira samo kad je `TURNSTILE_SITE_KEY` postavljen (skripta `https://challenges.cloudflare.com/turnstile/v0/api.js` s `defer`, CSP je već dopušta).
   - Honeypot: skriveno polje `website` (CSS, ne `hidden` atribut) — ako je popunjeno, vrati lažni uspjeh bez spremanja. Vremenska provjera: potpisani timestamp u formi, odbij ako je poslano < 3 s nakon renderiranja.
   - Rate limit: 5 upita / 10 min po IP-u i 3 / sat po emailu (hash). Preko limita → prijazna poruka, HTTP 429.

2. **Javne forme i handleri** (`app/routers/public.py`)
   - Jedan include `public/_inquiry_form.html` s varijantama: `vehicle` (na detalju; skriveno `vehicle_id`), `viewing` (isti include + polje `preferred_date` datum/vrijeme, min = sutra, + napomena; otvara se klikom "Dogovori pregled vozila"), `general` (kontakt stranica). Polja: ime (2–100), email (validacija), telefon (opcionalno, HR format `+385…` ili `0…`, normaliziraj), poruka (10–2000), privola checkbox (**neoznačen**, tekst iz poglavlja 14 s linkom na `/privatnost`), Turnstile, honeypot, CSRF.
   - `POST /upit`: validacija (greške uz polja, zadržane vrijednosti, bez gubitka konteksta vozila), spremi `inquiries` s `consent_at`, `consent_ip`, `consent_user_agent` (skraćen na 300 znakova), `consent_policy_version` (iz `site.privacy_policy_version`), `source_url`, `type`, `vehicle_id`, `preferred_date`. Nakon uspjeha: redirect (PRG) na stranicu/anchor s porukom "Hvala, javit ćemo vam se u najkraćem roku." Kupcu se u MVP-u ne šalje email.
   - Email dealeru (BackgroundTasks) na `site.inquiry_notify_email` (fallback `site.company_email`): predložak `emails/inquiry_notification` (tip upita, vozilo s linkom na javnu i admin stranicu, ime, email, telefon, poruka, željeni termin, vrijeme, `Reply-To` = email kupca). Zapis u `email_log`.

3. **Mini-CRM** (`app/routers/admin_inquiries.py`)
   - `/admin/upiti`: inbox — tablica (status badge, tip, kupac, vozilo, dodijeljeno, primljeno, zadnja bilješka), filteri (status, tip, dodijeljeno, vozilo, razdoblje), pretraga (ime/email/telefon), sortiranje, paginacija 25, brojač novih u sidebaru (badge), oznaka "bez odgovora > 48 h".
   - `/admin/upiti/{id}`: podaci kupca (email i telefon kao `mailto:`/`tel:` linkovi), gumb "Odgovori emailom" (`mailto:` s predloženim subjectom "Vaš upit – {naslov vozila} – {company_name}"), kartica vozila s linkom, podaci o privoli (vrijeme, verzija politike, IP maskiran u prikazu), promjena statusa (`new → contacted → closed`, dopušten povratak), dodjela prodavaču (lista aktivnih korisnika), interne bilješke (dodavanje, autor, vrijeme; brisanje vlastite bilješke unutar 15 min), navigacija prethodni/sljedeći.
   - Brisanje upita (owner+) s potvrdom; izvoz CSV trenutnog filtera (owner+; UTF-8 s BOM-om, `;` separator zbog Excela na HR lokalizaciji).
   - Salesperson: vidi i obrađuje sve upite, ne može brisati ni izvoziti.
   - Audit: `inquiry.status`, `inquiry.assign`, `inquiry.note`, `inquiry.delete`, `inquiry.export` (bez osobnih podataka u `details`; samo ID-ovi).
   - Dashboard placeholder: kartica "Novi upiti" sada pokazuje pravi broj.

4. **Retencija (priprema)**: u `app/services/maintenance.py` dodaj `purge_old_inquiries(db)` — briše upite (i bilješke) starije od `INQUIRY_RETENTION_DAYS` po `created_at` (zatvorene i otvorene jednako; zabilježi u PRETPOSTAVKE.md). CLI `python -m app.cli maintenance` zasad poziva samo to; ostatak u fazi 7.

5. **Testovi** (`tests/test_inquiries.py`)
   - Upit bez privole → greška i ništa spremljeno; s privolom → zapis s metapodacima privole i verzijom politike, email u `data/outbox/` s `Reply-To`; honeypot popunjen → lažni uspjeh, ništa spremljeno; prebrzo slanje odbijeno; rate limit nakon 5 → 429; `viewing` bez datuma odbijen, datum u prošlosti odbijen; upit za skicu/nepostojeće vozilo odbijen; Turnstile isključen kad nema ključa (mock httpx kad ključ postoji: uspjeh i neuspjeh); admin: promjena statusa, dodjela, bilješka, CSV izvoz sadrži BOM i `;`, prodavač ne može brisati (403), `purge_old_inquiries` briše samo starije od retencije; audit zapisi bez emaila kupca.

## Provjera prije završetka

- Playwright: pošalji upit za vozilo i termin za pregled s javne stranice, pronađi ih u adminu, promijeni status, dodaj bilješku. Screenshotovi `docs/screenshots/javno-upit-forma-mobile.png`, `admin-upiti.png`, `admin-upit-detalj.png`; pregledaj urednost.
- Provjeri da `data/outbox/` sadrži obavijest s ispravnim podacima.
- `ruff check .` i `pytest` prolaze. Ažuriraj `CLAUDE.md` (kako dodati novi tip upita) i README.
- Git commit: `Faza 5: upiti i mini-CRM`.

## Ne raditi u ovoj fazi

Newsletter, statistiku, postavke, GDPR alat, seed demo upita (faza 7).

## Završni izvještaj faze

Što je napravljeno, popis ruta, kako se uključuje Turnstile u produkciji, pretpostavke, poznati nedostaci, potvrda testova.
