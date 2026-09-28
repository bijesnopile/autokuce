# Izvještaj — Faza 6: Newsletter

Datum: 28.09.2026.

## Što je napravljeno

- **Prijava i double opt-in** (`app/services/newsletter.py`, `POST /newsletter/prijava`): email +
  privola ("…radi primanja newslettera s ponudama vozila") + Turnstile + honeypot + vremenska provjera +
  CSRF, rate limit 5 / 10 min po IP-u, uvijek ista neutralna poruka. Logika po stanju: potvrđen → ništa;
  na čekanju → ponovno slanje najviše 1× u 10 min; odjavljen (anonimiziran) → nova prijava; nov → kreiraj.
  Spremaju se `consent_at/ip/user_agent/policy_version/source` (`footer`, `home`, `vehicle`).
  Email `newsletter_confirm` (LOGO, gumb "Potvrdi prijavu", napomena o brisanju za 7 dana, impressum).
- **Potvrda** `GET /newsletter/potvrda/{token}` (7 dana, jednokratna) → `confirmed`, trajni token za
  odjavu (u bazi samo hash).
- **Odjava**: `GET /newsletter/odjava/{token}` (potvrda s gumbom; `?potvrdi=1` odjavljuje odmah),
  `POST` (i RFC 8058 one-click). Status `unsubscribed`, **email → NULL**, ostaje `email_hash`, tokeni
  poništeni. Kampanje imaju `List-Unsubscribe` i `List-Unsubscribe-Post` (Brevo: kroz `headers` API-ja).
- **Admin — pretplatnici**: tablica (email ili "anonimizirano", status, izvor, privola + verzija,
  potvrđeno), filter statusa, pretraga (hash ili prefiks), brojači; ručni unos (owner+, obavezna
  napomena o privoli, jasno označen); CSV potvrđenih (owner+, audit); brisanje (owner+, audit s hashom).
- **Admin — kampanje**: lista (status, primatelji, poslano/neuspjelo, datum), nova/uredi (samo skica),
  dupliciraj, obriši skicu; editor (`editor.js`) s gumbom "+ Umetni vozilo" (kartica vozila: slika 400,
  naslov, cijena, poveznica); nh3 sanitizacija (slike samo s vlastitog media); pregled u
  `<iframe sandbox srcdoc>`; testni email prijavljenom korisniku; "Pošalji svima potvrđenima" s potvrdom i
  brojem primatelja; izvještaj; ponovno slanje neuspjelima. Prodavač: samo pregled (403 za izmjene).
- **Slanje** (`send_campaign`): zasebna nit s vlastitom DB sesijom, serije od 50 uz pauzu 1 s, zapis po
  primatelju, personalizirana poveznica za odjavu, idempotentno (preskače isporučene).
- **Predložak** `emails/newsletter_campaign` (HTML tablični + tekst): LOGO/logo, sadržaj, "Primate ovaj
  email jer ste se prijavili {datum} na {domena}", odjava jednim klikom, politika privatnosti, impressum.
- **Retencija**: `purge_pending_subscribers` (> 7 dana), `purge_old_unsubscribed` (> 3 godine), pozivaju
  se iz `python -m app.cli maintenance`.
- Audit: `newsletter.manual_add/delete/export`, `campaign.create/update/send/delete`.

## Rute

`POST /newsletter/prijava`, `GET /newsletter/potvrda/{token}`, `GET|POST /newsletter/odjava/{token}`,
`/admin/newsletter/pretplatnici` (+ `/novi`, `/izvoz.csv`, `/{id}/obrisi`),
`/admin/newsletter/kampanje` (+ `/nova`, `/{id}`, `/{id}/pregled`, `/{id}/test`, `/{id}/posalji`,
`/{id}/ponovi`, `/{id}/dupliciraj`, `/{id}/obrisi`), `/admin/newsletter/api/vozila`.

## Privola i anonimizacija (ukratko)

Pri prijavi se sprema dokaz privole (vrijeme, IP, preglednik, verzija politike, izvor), a kampanje
primaju samo adrese potvrđene klikom na poveznicu iz emaila. Odjava jednim klikom odmah briše adresu i
ostavlja samo njezin SHA-256 hash (lista zabrane ponovnog slanja, 3 godine), pa ponovna prijava iste
adrese prolazi novi double opt-in.

## Provjera

- Playwright: prijava iz podnožja (mobitel) → poveznica iz `data/outbox/` → "Prijava je potvrđena" →
  admin: nova kampanja s umetnutim vozilom (dijalog "Octavia") → testni email → slanje → izvještaj
  (1/1 poslano) → poveznica `List-Unsubscribe` iz emaila kampanje → "Odjavljeni ste". Bez grešaka u konzoli.
- Screenshotovi: `docs/screenshots/admin-newsletter-pretplatnici.png`, `admin-newsletter-kampanja.png`
  (uključuje renderirani email), `javno-newsletter-potvrda-mobile.png` — pregledani, uredni.
- `ruff check .` ✔, `ruff format --check .` ✔, `pytest`: **153 passed** (15 novih u `test_newsletter.py`).

## Pretpostavke

`docs/PRETPOSTAVKE.md` → "Newsletter (faza 6)"; Brevo/SPF/DKIM/DMARC upute u README-u.

## Poznati nedostaci

- Nema praćenja otvaranja/klikova (namjerno — privatnost, bez piksela).
- Slanje u niti preživljava samo dok proces radi; nakon restarta se nastavlja ručno ("Ponovno pošalji
  neuspjelima" / ponovno pokretanje preskače isporučene). Za velike liste (> nekoliko tisuća) preporuka je
  red zadataka (RQ/Celery) — izvan MVP-a.
