# GDPR i zaštita osobnih podataka

Ovaj dokument opisuje kako platforma obrađuje osobne podatke, na kojoj pravnoj osnovi, koliko
ih čuva i kako se ostvaruju prava ispitanika. Tehnički je točan za verziju v0.1.0; **nije pravni
savjet** — pravni tekstovi na stranicama (Politika privatnosti, Kolačići, Uvjeti) i ugovor o obradi
moraju proći pregled pravnika (oznake `[PRAVNIK: …]`).

## 1. Uloge

| Tko | Uloga | Za koje podatke |
|---|---|---|
| Autokuća (klijent) | **voditelj obrade** | podaci kupaca (upiti, pretplatnici newslettera), zaposlenici koji koriste admin |
| Operater platforme (izrađivač/održavatelj, hosting) | **izvršitelj obrade** (čl. 28) | sve gore navedeno, samo po uputi voditelja; potreban je **ugovor o obradi** — predložak: [`pravno/UGOVOR-O-OBRADI-PODATAKA.md`](pravno/UGOVOR-O-OBRADI-PODATAKA.md) |
| Podizvršitelji (vidi 5.) | podizvršitelji | hosting, email, CDN/anti-spam, backup |

Kontakt za privatnost na javnim stranicama je `company_email` iz Postavki (impressum).

## 2. Koji se podaci obrađuju i zašto

| Podaci | Izvor | Svrha | Pravna osnova (čl. 6. GDPR-a) |
|---|---|---|---|
| Upit: ime, email, telefon (neobavezno), poruka, vozilo, željeni termin pregleda | forme na stranici | odgovor na upit, dogovor pregleda/kupnje | **(1)(b)** predugovorne radnje na zahtjev ispitanika |
| Upit za financiranje (paket Standard): željeno učešće i rok, izračunata informativna rata | forma na oglasu | priprema ponude leasinga/kredita | **(1)(b)** predugovorne radnje; ne šalje se leasing kući bez dogovora s kupcem |
| Potvrđeni termin pregleda (paket Standard) | prodavač u adminu | dogovor pregleda, kalendarski poziv kupcu | **(1)(b)** |
| Dokaz privole uz upit: vrijeme, IP, preglednik, verzija politike, izvor forme | automatski | dokazivanje da je korisnik pročitao politiku | (1)(c)/(1)(f) — dokazivost; čuva se uz upit |
| Newsletter: email, vrijeme i dokaz privole (IP, preglednik, verzija, izvor), vrijeme potvrde | forma + potvrda iz emaila (double opt-in) | slanje ponude vozila | **(1)(a)** privola, povlačiva jednim klikom |
| Hash emaila odjavljenog pretplatnika | nakon odjave | sprječavanje ponovnog slanja (lista zabrane) | (1)(f) legitimni interes / (1)(c) |
| Admin korisnici: ime, email, uloga, lozinka (Argon2id), 2FA tajna (šifrirana), sesije (maskirani IP, preglednik), audit log | admin | pristup administraciji, sigurnost | **(1)(b)** ugovor (radni odnos/ugovor s klijentom), (1)(f) sigurnost |
| Analitika (Umami, bez kolačića, opcionalno) | posjet stranici | broj posjeta, najgledaniji oglasi | (1)(f) legitimni interes — Umami ne sprema IP ni kolačiće |
| Brojanje pregleda oglasa | posjet oglasu | statistika oglasa | (1)(f); dnevni zbroj po vozilu, bez identifikacije posjetitelja |
| Zapisi o poslanim emailovima | slanje | dijagnostika isporuke | (1)(f); samo SHA-256 hash adrese |

Posebne kategorije podataka se ne prikupljaju. Nema profiliranja ni automatiziranog odlučivanja.

**Funkcije paketa Standard**

- **Automatski odgovor kupcu i kalendarski poziv (.ics)** su dio obrade upita (čl. 6(1)(b)), a ne
  marketing. Šalju se samo na adresu koju je kupac upisao u upit i sadrže samo potvrdu primitka, vozilo,
  radno vrijeme, termin i impressum. Nema ponuda drugih vozila ni poveznice za odjavu jer to nije
  newsletter. `.ics` ne sadrži osobne podatke kupca (samo vozilo, adresu tvrtke i poveznicu na oglas).
- **Informativni izračun rate** radi u pregledniku. Klizači ne šalju podatke; ništa se ne sprema dok
  kupac sam ne pošalje upit za financiranje.
- **Feed za portale** sadrži samo javne podatke oglasa koji su već na web-stranici (vozilo, cijena,
  slike, opis, podaci tvrtke). **Nema osobnih podataka kupaca.** VIN je zadano isključen. Tablica
  `feed_access` bilježi samo portal, vrijeme, format i broj preuzimanja, bez IP-a.
- **WhatsApp/Viber gumbi** su obične poveznice preko internog preusmjeravanja `/idi/...`, koje broji
  samo klik po vozilu i danu, bez IP-a i kolačića. **Dok kupac ne klikne, podaci se ne prenose
  Meti/Rakutenu.** Ne učitavaju se vanjske skripte ni ikone. Nakon klika razgovor se vodi u
  aplikaciji kupca, pod uvjetima WhatsAppa ili Vibera. Prodavač tada ondje postaje voditelj obrade
  razgovora, što politika privatnosti treba spomenuti (`[PRAVNIK]`).
Poruke u formama su slobodan tekst — upute na stranici ne traže osjetljive podatke.

## 3. Kolačići

| Kolačić | Svrha | Trajanje | Privola |
|---|---|---|---|
| `st` | CSRF zaštita formi, poruke nakon slanja, sprječavanje dvostrukog brojanja pregleda | do zatvaranja preglednika | nije potrebna (nužan) |
| `session` | prijava u administraciju (samo `/admin`) | 12 h | nije potrebna (nužan) |
| `ak_pending` | korak između lozinke i 2FA koda (samo `/admin`) | 10 min | nije potrebna (nužan) |
| `cookie_consent` | pamti izbor s trake za kolačiće (samo ako je traka uključena) | 180 dana | — |

Umami radi bez kolačića. YouTube se učitava tek na klik i preko `youtube-nocookie.com`; karte su
samo poveznica na Google Maps (ništa se ne učitava). Fontovi, CSS i JS su lokalni.
**Traka za kolačiće je zadano isključena** (spec pogl. 14). Ako klijent doda alat koji traži privolu
(GA, Meta Pixel…), uključuje se u Postavke → Pravno; skripte označene `data-consent="analytics"`
učitavaju se tek nakon "Prihvaćam", a "Odbijam" je jednako istaknut (README → Administracija).

## 4. Rokovi čuvanja i automatsko brisanje

Brisanje radi `app/services/maintenance.py` jednom dnevno u 04:00 (u aplikaciji,
`MAINTENANCE_IN_APP=true`, i/ili cron `python -m app.cli maintenance`). Pregled bez brisanja:
`python -m app.cli maintenance --dry-run` ili Admin → Sustav.

| Podaci | Rok | Kako |
|---|---|---|
| Upiti i interne bilješke | `INQUIRY_RETENTION_DAYS` = **365 dana** od primitka | `purge_old_inquiries` briše zapis |
| Nepotvrđene prijave na newsletter | **7 dana** nakon slanja potvrde | `purge_pending_subscribers` |
| Potvrđeni pretplatnici | do odjave (povlačenja privole) | odjava jednim klikom → adresa odmah obrisana |
| Odjavljeni (samo hash emaila) | **3 godine** | `purge_old_unsubscribed` |
| Sesije, tokeni (pozivnice, reset lozinke, potvrde) | po isteku (iskorišteni tokeni +7 dana) | `purge_expired_sessions_and_tokens` |
| Zapisi o poslanim emailovima (hash adrese) | 90 dana | `purge_old_email_log` |
| Audit log (bez podataka kupaca) | 2 godine | `purge_old_audit` |
| Dnevni pregledi oglasa (bez osobnih podataka) | 400 dana | `purge_old_vehicle_views` |
| Prodana vozila | javno 30 dana, zatim arhiva (nema osobnih podataka) | `archive_sold_vehicles` |
| Aplikacijski logovi | bez osobnih podataka (nema access loga, emailovi maskirani); rotacija po veličini 5 × 10 MB | Docker `json-file` (za strogih 30 dana: `journald` s `MaxRetentionSec=30day`) |
| Šifrirani backupi baze | **30 dana** (lokalno i off-site) | `deploy/backup.sh` — obrisani podaci nestaju iz backupa najkasnije za 30 dana |

## 5. Podizvršitelji i lokacije

| Podizvršitelj | Usluga | Lokacija | Osnova za prijenos |
|---|---|---|---|
| Netcup GmbH | VPS (aplikacija, baza, slike, lokalni backup) | Njemačka (EU) | — (EU) |
| Cloudflare, Inc. | DNS, proxy/CDN, Turnstile anti-spam, opcionalno R2 za slike | globalno (SAD) | EU-US Data Privacy Framework + SCC |
| Brevo (Sendinblue SAS) | slanje emailova (obavijesti, newsletter) | Francuska (EU) | — (EU) |
| Umami (self-hosted, opcionalno) | analitika bez kolačića | na vlastitom serveru | nema podizvršitelja |
| Off-site backup (npr. Hetzner Storage Box) | šifrirane kopije baze | **definirati po klijentu** (preporuka: EU, npr. Hetzner DE/FI) | — (EU) ako je u EU |

Popis mora odgovarati stanju u ugovoru o obradi; promjena podizvršitelja najavljuje se klijentu.

## 6. Prava ispitanika — postupak (rok 30 dana)

1. Zahtjev stiže na `company_email` (ili bilo kojim kanalom). Autokuća (voditelj) provjerava identitet
   podnositelja (npr. odgovor s iste adrese).
2. Vlasnik u adminu otvara **Prava ispitanika** (`/admin/gdpr`), upisuje email (i po potrebi telefon)
   → vidi sve upite, bilješke i status pretplate s dokazom privole.
3. **Pristup / prenosivost**: "Preuzmi JSON" — svi podaci osobe u strojno čitljivom obliku; šalje se
   ispitaniku. Audit bilježi `privacy.export` samo s hashom emaila.
4. **Brisanje**: upis riječi `OBRIŠI` → brišu se upiti i bilješke, zapisi o emailovima, pretplata se
   anonimizira (ostaje hash kao zaštita od ponovnog slanja). Audit `privacy.delete` (hash + brojevi).
   Ispitaniku se odgovara da podaci ostaju u šifriranim backupima najviše 30 dana i zatim nestaju.
5. **Ispravak**: upiti se mogu urediti u adminu (bilješka), pretplatnik se može obrisati i ponovno
   prijaviti.
6. **Povlačenje privole za newsletter**: poveznica u svakom emailu (jednim klikom) ili ručno u adminu.
7. **Prigovor / ograničenje**: voditelj odlučuje; tehnički — brisanje ili zadržavanje zapisa.
8. Odgovor ispitaniku u roku **30 dana** (produljivo za 60 uz obrazloženje). Zabilježiti datum zahtjeva i
   odgovora (preporuka: interna evidencija voditelja).

Operater platforme pomaže voditelju u tehničkom dijelu (čl. 28(3)(e)).

## 7. Povreda osobnih podataka (incident)

1. **Otkrivanje** (neuobičajeni zapisi u audit logu, obavijest Cloudflarea/Netcupa, dojava): operater
   odmah obavještava klijenta (voditelja) — ugovor o obradi: bez nepotrebnog odgađanja.
2. **Ograničavanje**: rotacija tajni (`SECRET_KEY` — poništava sesije i zahtijeva ponovno šifriranje
   2FA tajni, vidi SIGURNOST.md), odjava svih sesija, `ADMIN_IP_ALLOWLIST`, po potrebi gašenje stranice.
3. **Procjena**: koji podaci, koliko osoba, rizik za prava i slobode.
4. **Prijava AZOP-u u 72 sata** od saznanja (voditelj; https://azop.hr) ako povreda vjerojatno
   uzrokuje rizik; obavijest ispitanicima bez odgađanja ako je rizik visok (čl. 33–34).
5. **Evidencija** svake povrede (i onih koje se ne prijavljuju) — interni zapis voditelja i operatera.
6. Nakon incidenta: analiza uzroka, ispravci, eventualno vraćanje iz backupa (`deploy/restore.sh`).

## 8. Backupi

Baza se svaki dan u 03:00 šifrira (`age` ili `gpg`, javni ključ na serveru, privatni izvan servera) i
kopira izvan servera. Retencija 30 dana — nakon brisanja podataka u aplikaciji oni u backupima postoje
najdulje 30 dana. Vraćanje se radi samo za obnovu sustava; nakon vraćanja se ponovno izvodi održavanje
(brisanje isteklih podataka) i ponavljaju se brisanja po zahtjevima ispitanika iz razdoblja od backupa.

## 9. Zahtjevi specifikacije (pogl. 14) → implementacija → test

| Zahtjev | Gdje | Test |
|---|---|---|
| Privola: checkbox neoznačen, tekst, spremanje vremena/IP-a/UA/izvora/verzije | `templates/public/_inquiry_form.html`, `_macros.html`; `services/inquiries.py`, `services/newsletter.py` | `test_privacy.py::test_consent_checkboxes_are_unchecked_by_default`, `test_inquiries.py::test_inquiry_with_consent_is_saved_and_dealer_notified`, `::test_inquiry_without_consent_is_rejected`, `test_newsletter.py::test_signup_without_consent_rejected` |
| Double opt-in, odjava jednim klikom, anonimizacija | `services/newsletter.py`, `routers/public.py` | `test_newsletter.py::test_double_opt_in_flow`, `::test_one_click_get_unsubscribe`, `::test_unsubscribe_anonymises_and_resubscribe_needs_new_opt_in` |
| Pravne osnove i uloge dokumentirane; predložak ugovora o obradi | ovaj dokument, `docs/pravno/UGOVOR-O-OBRADI-PODATAKA.md` | — (dokumentacija) |
| Pravne stranice s obaveznim sekcijama i `[PRAVNIK: dopuniti]` | `app/seed_content.py` | `test_public.py::test_legal_pages_show_version_and_lawyer_markers` |
| Impressum u podnožju svake stranice | `templates/public/base.html` (iz postavki) | `test_placeholders.py::test_changed_settings_replace_every_placeholder`, `test_public.py::test_public_pages_render_with_placeholders` |
| Rokovi čuvanja i automatsko brisanje | `services/maintenance.py`, `app/cli.py` | `test_maintenance.py` (sve), `test_inquiries.py::test_purge_old_inquiries_only_older_than_retention`, `test_newsletter.py::test_purge_pending_and_old_unsubscribed` |
| Alat za prava ispitanika (pristup, izvoz, brisanje) | `routers/admin_privacy.py` | `test_privacy.py::test_gdpr_search_and_export`, `::test_gdpr_delete_requires_confirmation_and_erases` |
| Bez cookie bannera; opcija `cookie_banner_enabled` s jednako lakim odbijanjem | `templates/public/base.html`, `static/js/public.js` | `test_settings.py::test_cookie_banner_only_when_enabled` |
| Fontovi/JS/CSS lokalno, karte kao link, YouTube nocookie na klik | templatei, `static/` | `test_no_external_resources.py` (javne stranice, e-mailovi, CSS/JS, YouTube) |
| Popis podizvršitelja, postupci (30 dana, AZOP 72 h) | ovaj dokument | — |
| Nova vozila: potrošnja i CO2; rabljena: stanje, km, oporezivanje | `vehicle_schema.py`, `templates/public/vehicle.html` | `test_vehicles.py::test_new_vehicle_requires_consumption_and_co2`, `test_public.py::test_new_vehicle_shows_consumption_and_co2` |
| Logovi bez osobnih podataka, audit bez podataka kupaca | `services/email.py` (maskiranje), `services/audit.py`, uvicorn `--no-access-log` | `test_privacy.py::test_gdpr_delete_requires_confirmation_and_erases` (audit bez emaila), `test_auth.py::test_audit_entries_are_created` |
