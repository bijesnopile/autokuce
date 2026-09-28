# FAZA 6/8 — Newsletter

## Kontekst

Faza 6 od 8. Prvo pročitaj `CLAUDE.md` i `docs/SPECIFIKACIJA.md` [ako je nema u `docs/`, kopiraj `prompts/SPECIFIKACIJA.md` u `docs/`] (posebno poglavlja 6 — subscribers/campaigns, 10, 12, 14). Provjeri stanje repozitorija (faze 1–5 gotove). Ne postavljaj pitanja; nedefinirano odluči sam i zabilježi u `docs/PRETPOSTAVKE.md`.

## Cilj faze

Prijava na newsletter s double opt-inom i dokazom privole, odjava jednim klikom s anonimizacijom, kampanje koje dealer uređuje i šalje iz admina, s izvještajem o isporuci.

## Zadaci

1. **Prijava i double opt-in** (`app/services/newsletter.py`, `app/routers/public.py`)
   - `POST /newsletter/prijava` (forme u footeru, na naslovnici, na detalju vozila): email + privola (neoznačena, tekst "…radi primanja newslettera s ponudama vozila") + Turnstile + honeypot + CSRF; rate limit 5/10 min po IP-u.
   - Logika `subscribe(email, meta)`: normaliziraj email (lowercase, trim), `email_hash = sha256(email)`. Ako postoji `confirmed` → ne radi ništa; ako `pending` → ponovno pošalji potvrdu (najviše 1× u 10 min); ako `unsubscribed` (anonimiziran) → tretiraj kao novu prijavu (ponovno popuni `email`, novi tokeni, status `pending`); inače kreiraj. **Uvijek ista poruka** korisniku: "Ako adresa još nije potvrđena, poslali smo vam email s linkom za potvrdu." Spremi `consent_at/ip/user_agent/policy_version/source` (`footer`, `home`, `vehicle`).
   - Tokeni: sirovi u linku, hash u bazi; potvrda vrijedi 7 dana. Email `emails/newsletter_confirm` (LOGO tekst, naziv tvrtke, gumb "Potvrdi prijavu", impressum, napomena da se bez potvrde ništa ne šalje i adresa se briše za 7 dana).
   - `GET /newsletter/potvrda/{token}`: valjan → `confirmed`, `confirmed_at`, generiraj trajni `unsubscribe_token`; poruka uspjeha. Nevaljan/istekao → poruka s mogućnošću ponovne prijave.
   - `GET /newsletter/odjava/{token}` prikazuje potvrdu s gumbom; `POST` odjavljuje (ali podrži i jedan klik: GET s `?potvrdi=1` iz emaila radi odmah, jer klijenti emaila prefetchaju linkove — zabilježi odluku). Odjava: status `unsubscribed`, `unsubscribed_at`, **email → NULL**, ostaje `email_hash`; tokeni poništeni. `List-Unsubscribe` i `List-Unsubscribe-Post` headeri u kampanjama (Brevo backend: kroz `headers` polje API-ja).

2. **Admin — pretplatnici** (`app/routers/admin_newsletter.py`)
   - `/admin/newsletter/pretplatnici`: tablica (email ili "anonimizirano" za odjavljene, status, izvor, privola vrijeme + verzija politike, potvrđeno), filteri po statusu, pretraga po emailu (točan hash-match ili prefiks za aktivne), paginacija, brojači po statusu.
   - Ručni unos (owner+): email + obavezno polje "Kako je prikupljena privola" (`manual_consent_note`, npr. "papirnati obrazac u salonu, 12.09.2026.") → status `confirmed` s `source=manual`; jasno označeno u listi. Izvoz CSV potvrđenih (owner+; audit). Brisanje pretplatnika (owner+; audit s hashom).

3. **Admin — kampanje**
   - `/admin/newsletter/kampanje`: lista (subject, status, primatelja, poslano/neuspjelo, datum), novo, uredi (samo `draft`), dupliciraj, obriši skicu.
   - Forma: subject (max 120), sadržaj s **jednostavnim editorom** (`app/static/js/editor.js` — vanilla: toolbar podebljano/kurziv/H2/H3/popis/link/„umetni vozilo" koje ubacuje karticu vozila kao HTML blok s linkom, slikom 400 i cijenom; `contenteditable` + skriveni `textarea` s HTML-om; ista komponenta koristi se u fazi 7 za stranice). Server sanitizira nh3-om (allowlist + `img[src]` samo s vlastitog `MEDIA_URL`/`/media`, `a[href]`, `table` za karticu vozila).
   - Pregled (renderirani email u iframe `sandbox` s `srcdoc`), testni email na adresu prijavljenog korisnika, "Pošalji svima potvrđenima" s potvrdom i brojem primatelja.
   - Slanje: `send_campaign(campaign_id)` u pozadini (BackgroundTasks; za robusnost pokreni u zasebnoj niti s vlastitom DB sesijom): status `sending`, serije od 50 uz pauzu 1 s, po primatelju zapis u `campaign_deliveries` (sent/failed + error), personalizirani link za odjavu, headeri `List-Unsubscribe`; na kraju `sent`, `sent_at`, `recipients_count`. Ponovno slanje samo neuspjelima. Ako se proces sruši usred slanja, ponovno pokretanje preskače već isporučene (idempotentno po `campaign_deliveries`).
   - Predložak `emails/newsletter_campaign` (HTML + tekst): LOGO tekst / logo slika, naziv, sadržaj, podnožje s impressumom, "Primate ovaj email jer ste se prijavili na {datum} na {domena}", link za odjavu, link na politiku privatnosti. Tablični layout kompatibilan s email klijentima, inline stilovi, bez vanjskih resursa osim slika vozila s vlastite domene.
   - Salesperson: samo pregled lista i kampanja, bez uređivanja/slanja (403).
   - Audit: `newsletter.manual_add`, `newsletter.delete`, `newsletter.export`, `campaign.create/update/send/delete`.

4. **Retencija**: u `maintenance.py` dodaj `purge_pending_subscribers(db)` (nepotvrđeni > 7 dana → obriši) i `purge_old_unsubscribed(db)` (anonimizirani zapisi > 3 godine → obriši). CLI `maintenance` ih poziva.

5. **Testovi** (`tests/test_newsletter.py`)
   - Prijava bez privole odbijena; prijava → `pending` + email s linkom u `data/outbox/`; potvrda → `confirmed` (token jednokratan; istekli token odbijen); ponovna prijava potvrđene adrese ne otkriva stanje (ista poruka) i ne šalje novi email; odjava → `email` NULL, hash ostaje, tokeni nevaljani; ponovna prijava odjavljene adrese prolazi kroz novi opt-in; ručni unos zahtijeva napomenu; kampanja se šalje samo potvrđenima, po jedan email po pretplatniku, s odjavnim linkom i `List-Unsubscribe`; ponovno pokretanje slanja ne duplicira; nh3 uklanja `<script>` i vanjske `<img>`; prodavač ne može slati (403); `purge_pending_subscribers` briše samo starije od 7 dana.

## Provjera prije završetka

- Playwright: prijava iz footera → otvori link iz `data/outbox/` → potvrda → u adminu kreiraj kampanju s umetnutim vozilom → testni email → pošalji → izvještaj → odjava kroz link iz emaila. Screenshotovi `docs/screenshots/admin-newsletter-pretplatnici.png`, `admin-newsletter-kampanja.png`, `javno-newsletter-potvrda-mobile.png`; pregledaj urednost, uključujući email HTML u pregledu.
- `ruff check .` i `pytest` prolaze. Ažuriraj `CLAUDE.md` i README (Brevo: verifikacija domene pošiljatelja, SPF/DKIM/DMARC po klijentu).
- Git commit: `Faza 6: newsletter`.

## Ne raditi u ovoj fazi

Statistiku, postavke, editor stranica (koristi editor, ali stranice su faza 7), GDPR alat, seed demo pretplatnika (faza 7).

## Završni izvještaj faze

Što je napravljeno, popis ruta, tijek privole i anonimizacije u dvije rečenice, pretpostavke, poznati nedostaci, potvrda testova.
