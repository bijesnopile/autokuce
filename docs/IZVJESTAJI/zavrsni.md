# Završni izvještaj — Autokuća MVP (v0.1.0-mvp)

Datum: 28.09.2026. Sve faze (1–8) su gotove i commitane; tag `v0.1.0-mvp`.
Provjera: `python scripts/check.py` — ruff ✔, format ✔, **pytest 281 passed** (176 testova u 19
datoteka; ista suita prolazi i na PostgreSQL-u 16), pip-audit 0 nalaza. `docker compose` nije
izveden jer Docker nije dostupan na razvojnom računalu (vidi 7.).

## 1. Što je izgrađeno

**Javna stranica** — naslovnica (hero s brzom pretragom, istaknuta i nova vozila, kategorije, "Zašto mi",
newsletter, kontakt), `/vozila` (filteri kao dijeljivi GET parametri, sortiranje, paginacija s
`rel=prev/next`), detalj vozila (galerija s lightboxom i swipeom, ključni podaci, specifikacije po
vrsti, oprema, opis, YouTube na klik preko `youtube-nocookie.com`, upit i dogovor pregleda, slična
vozila, ispis; potrošnja i CO2 za nova vozila), kontakt, Usluge/O nama, pravne stranice s verzijom,
404/410/500. Pet vrsta vozila (osobni, kombi, motocikl, kamper, kamion) iz jedne sheme
(`app/vehicle_schema.py`). Bez vanjskih resursa i kolačića za praćenje; responzivno.

**SEO** — title/description, canonical, Open Graph/Twitter, JSON-LD (`AutoDealer`,
`Car`/`Motorcycle`/`Vehicle` + `Offer`, `BreadcrumbList`), `sitemap.xml`, `robots.txt`, 301 sa starih
URL-ova, 410 za prodana/arhivirana, WebP `srcset` i lazy load.

**Upiti (mini-CRM)** — upit za vozilo, dogovor pregleda (termin), opći upit; CSRF, honeypot, vremenska
provjera, Turnstile, rate limit po IP-u i emailu; privola s dokazom; email dealeru s `Reply-To`; inbox
s filterima, statusi, dodjela prodavaču, interne bilješke, "Odgovori emailom", CSV (Excel).

**Newsletter** — prijava s privolom, double opt-in, odjava jednim klikom (i RFC 8058) s anonimizacijom
(ostaje hash), kampanje u editoru s umetanjem kartice vozila, pregled, testni email, slanje u pozadini
u serijama od 50, izvještaj i ponovno slanje neuspjelima.

**Administracija** — prijava s **obaveznom 2FA** (TOTP, kodovi za oporavak), pozivnice i reset
lozinke, uloge (superadmin, vlasnik, prodavač), profil i sesije; nadzorna ploča (kartice, SVG graf,
zadnji upiti, najgledanija vozila, podsjetnici), statistika 30/90/365 dana s CSV-om; vozila (dinamička
forma po vrsti, statusi i prijelazi, slug s poviješću, dupliciranje), slike (drag&drop, redoslijed,
glavna, alt, WebP 400/1000/1600, bez EXIF-a, potvrda zamagljenih tablica); katalog marki/modela s CSV
uvozom; postavke (podaci tvrtke, logo, boje s provjerom kontrasta, tekstovi, pravno, traka za
kolačiće); stranice (editor, verzije, objava); prava ispitanika (pretraga, JSON izvoz, brisanje);
audit log; sustav (dijagnostika, testni email, održavanje).

**Operativa** — dnevno održavanje (retencija prema GDPR-u, arhiva prodanih) u aplikaciji i CLI-jem,
zaštićeno od dvostrukog izvođenja; demo seed (16 vozila sa siluetama po vrsti, 60 dana pregleda,
upiti, pretplatnici, kampanje, 3 korisnika); Docker slika i compose; zajednički Caddy za više klijenata;
skripte `new-client`, `remove-client`, `update-all`, `backup` (šifrirano, off-site, provjera), `restore`;
`scripts/check.py`, `scripts/screenshots.py`; višejezičnost sučelja pripremljena (`_()`, `en.json`).

**Dokumentacija** — README, CLAUDE.md, ARHITEKTURA, SIGURNOST, GDPR, ONBOARDING-KLIJENTA,
ROADMAP, predložak ugovora o obradi, PRETPOSTAVKE, izvještaji svih faza.

## 2. Kako pokrenuti demo

**Lokalno (Windows/Linux, Python 3.11+):**

```bash
python -m venv .venv
.venv/Scripts/activate            # Linux/macOS: source .venv/bin/activate; PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python run.py                     # http://localhost:8000  i  http://localhost:8000/admin
```

Na praznoj bazi `run.py` sam pokreće migracije i puni cijeli demo. Emailovi: `data/outbox/*.eml`.

**Docker:**

```bash
docker compose up -d --build      # http://localhost  (app + PostgreSQL 16 + Caddy, demo podaci)
```

**Pristup (demo):** `admin@domena.com` (superadmin), `vlasnik@domena.com` (vlasnik),
`prodavac1@domena.com` (prodavač) — lozinka `Promijeni-me-2026!` (`SEED_PASSWORD`). **Prva prijava traži
postavljanje 2FA** (QR kod u aplikaciji za autentikaciju + 10 kodova za oporavak).

Provjere: `python scripts/check.py`; screenshotovi i prolaz tijekova kao klijent:
`python -m playwright install chromium` pa `python scripts/screenshots.py`.

## 3. Instalacija novog klijenta na VPS-u (5 koraka)

(Jednom po VPS-u: Docker + Compose, `git clone` u `/opt/autokuca`, `docker build -t autokuca:latest .`,
`cd deploy/caddy && docker compose up -d`, `deploy/backup.env` s javnim age ključem i rclone
odredištem, `deploy/crontab.example` → `/etc/cron.d/autokuca`, firewall 80/443 samo za Cloudflare.)

1. **Cloudflare**: domena, `A` zapis (+`www`) na IP VPS-a s proxyjem, SSL "Full (strict)", Origin
   certifikat u `deploy/caddy/certs/<domena>/cert.pem` i `key.pem`, Turnstile site.
2. **`deploy/new-client.sh <ime> <domena>`** — generira `.env` (tajne), mape, Caddy site, pokreće app i
   bazu (migracije + minimalni seed), reloada Caddy, ispisuje pristup i checklistu.
3. **Ključevi u `clients/<ime>/.env`**: Brevo (domena verificirana: SPF, DKIM, DMARC), Turnstile, po
   želji Umami/S3 → `docker compose -p ak_<ime> --project-directory clients/<ime> up -d`.
4. **Podešavanje s klijentom**: prijava + 2FA, Postavke (tvrtka, logo, boje), pravni tekstovi od
   pravnika, korisnici, vozila.
5. **Provjera i predaja**: testni upit i newsletter, `deploy/backup.sh <ime>` i test vraćanja, uptime
   monitor, predaja pristupa — `docs/ONBOARDING-KLIJENTA.md`.

## 4. Definition of done (pogl. 24)

| Stavka | Status | Napomena |
|---|---|---|
| `python run.py` i `docker compose up` rade bez ručnih koraka | ⚠ djelomično | `run.py`: ✔ provjereno na svježoj bazi (migracije + demo automatski). `docker compose up`: implementiran (entrypoint: ključ, čekanje baze, migracije, seed; `init` za prava nad `./data`; demo bez `.env`), ali **nije izveden** — Docker nije dostupan; logika entrypointa pokrivena testovima |
| Sve stranice i tijekovi iz pogl. 8, 10, 11, 12 rade i vidljivi su na screenshotovima | ✔ | 34 screenshota (desktop + mobitel) iz `scripts/screenshots.py`, koji prolazi pretragu, upit, newsletter s potvrdom, 2FA, obradu upita i slanje kampanje uz provjeru HTTP statusa, skrola i konzole |
| Nigdje u templateima nema hardkodiranih podataka tvrtke | ✔ | `test_placeholders.py` (66 predložaka + zamjena svih placeholdera stvarnim podacima) |
| Nema vanjskih resursa u HTML-u (test) | ✔ | `test_no_external_resources.py` (javne stranice, sve vrste vozila, CSS/JS, 5 email predložaka) |
| Sigurnosna (13) i GDPR (14) checklista implementirane; iznimke u PRETPOSTAVKE | ✔ | iznimke zapisane: retencija app logova po veličini (ne strogo 30 dana, logovi bez osobnih podataka); pentest, WAF, Redis limiter, HEIC izvan MVP-a |
| `scripts/check.py` prolazi | ✔ | ruff, format, 281 test, pip-audit 0 nalaza |
| Dokumentacija iz pogl. 22 | ✔ | README, CLAUDE.md, ARHITEKTURA, SIGURNOST, GDPR, PRETPOSTAVKE, ONBOARDING-KLIJENTA, ROADMAP, pravno/UGOVOR-O-OBRADI-PODATAKA |
| Završni izvještaj | ✔ | ovaj dokument (i poruka u chatu) |

## 5. Sigurnost i GDPR → implementacija → test

| Zahtjev | Implementacija | Test |
|---|---|---|
| Argon2id, min. 12 znakova, česte lozinke | `app/security.py` | `test_auth.py::test_weak_password_rejected_on_reset` |
| Lockout 5/15 min; rate limit login 10/min, forme 5/10 min, API 100/min | `services/auth.py`, `security.py` | `test_auth.py::test_lockout_after_five_failed_attempts`, `::test_login_rate_limit`, `test_inquiries.py::test_rate_limit_per_ip`, `test_security_headers.py::test_public_api_rate_limit_100_per_minute` |
| Obavezna 2FA, TOTP, zaštita od ponovne upotrebe koda | `routers/admin_auth.py`, `deps.py` | `test_auth.py::test_login_without_2fa_redirects_to_forced_setup`, `::test_totp_login_and_replay_protection` |
| Kodovi za oporavak hashirani; TOTP tajna šifrirana (Fernet) | `security.py` | `test_auth.py::test_recovery_code_works_only_once`, `::test_totp_secret_is_encrypted_at_rest` |
| Sesije na serveru; HttpOnly/Secure/SameSite=Lax; 12 h; odjava svugdje | `services/auth.py` | `test_security_headers.py::test_admin_session_cookie_flags`, `::test_hsts_and_secure_cookies_only_with_https`, `test_auth.py::test_logout_everywhere_invalidates_other_sessions` |
| CSRF na svakom POST-u | `deps.py::csrf_protect` (router) | `test_auth.py::test_post_without_csrf_is_forbidden`, `test_security_headers.py::test_every_state_changing_route_requires_csrf` |
| CSP bez `unsafe-inline` za skripte, headeri, HSTS samo uz HTTPS | `main.py` | `test_security_headers.py` (headeri, CSP, inline skripte) |
| Upload: sadržaj, formati, veličina, broj, WebP, bez EXIF-a, izvan webroota | `services/images.py`, `storage.py` | `test_images.py`, `test_temelj.py::test_media_path_traversal_rejected` |
| Sanitizacija (nh3), autoescape, ORM | `security.clean_html`, `newsletter.clean_campaign_html` | `test_newsletter.py::test_campaign_html_is_sanitized`, `test_pages.py::test_page_edit_increments_version_and_sanitizes` |
| Produkcija bez `SECRET_KEY`/PostgreSQL-a ne starta | `config.py` | `test_temelj.py::test_production_requires_secret_and_postgres` |
| Bez enumeracije korisnika; open redirect | `admin_auth.py`, `services/auth.py::safe_next` | `test_auth.py::test_wrong_password_same_message_as_unknown_email`, `::test_open_redirect_is_blocked` |
| Health bez detalja; `/admin` noindex + robots; IP allowlist | `public.py`, `seo.py`, `main.py` | `test_security_headers.py::test_health_endpoint_reveals_nothing`, `::test_admin_pages_are_noindex_and_not_cached`, `test_auth.py::test_admin_ip_allowlist_middleware` |
| Audit svih admin akcija, bez podataka kupaca | `services/audit.py` | `test_auth.py::test_audit_entries_are_created`, `test_privacy.py::test_gdpr_delete_requires_confirmation_and_erases` |
| pip-audit; Docker non-root, multi-stage, pinano | `scripts/check.py`, `Dockerfile` | `scripts/check.py` (slika nije izgrađena — Docker nedostupan) |
| Privola neoznačena, tekst, dokaz (vrijeme, IP, UA, izvor, verzija) | `_inquiry_form.html`, `_macros.html`, `services/inquiries.py`, `newsletter.py` | `test_privacy.py::test_consent_checkboxes_are_unchecked_by_default`, `test_inquiries.py::test_inquiry_with_consent_is_saved_and_dealer_notified`, `::test_inquiry_without_consent_is_rejected` |
| Double opt-in, odjava jednim klikom, anonimizacija | `services/newsletter.py` | `test_newsletter.py::test_double_opt_in_flow`, `::test_unsubscribe_anonymises_and_resubscribe_needs_new_opt_in` |
| Pravne stranice sa sekcijama i `[PRAVNIK: dopuniti]`; impressum | `seed_content.py`, `public/base.html` | `test_public.py::test_legal_pages_show_version_and_lawyer_markers`, `test_placeholders.py::test_changed_settings_replace_every_placeholder` |
| Rokovi čuvanja, automatsko brisanje, arhiva prodanih | `services/maintenance.py`, `cli.py` | `test_maintenance.py` (svi) |
| Alat za prava ispitanika (pristup, izvoz, brisanje) | `routers/admin_privacy.py` | `test_privacy.py::test_gdpr_search_and_export`, `::test_gdpr_delete_requires_confirmation_and_erases` |
| Bez cookie bannera; opcionalni banner s jednako lakim odbijanjem | `public/base.html`, `public.js` | `test_settings.py::test_cookie_banner_only_when_enabled` |
| Lokalni fontovi/JS/CSS, karte kao link, YouTube nocookie na klik | templatei, `static/` | `test_no_external_resources.py` |
| Nova vozila: potrošnja i CO2 | `vehicle_schema.py`, `public/vehicle.html` | `test_vehicles.py::test_new_vehicle_requires_consumption_and_co2`, `test_public.py::test_new_vehicle_shows_consumption_and_co2` |
| Uloge, pravne osnove, podizvršitelji, postupci (30 dana, AZOP 72 h), ugovor o obradi | `docs/GDPR.md`, `docs/pravno/UGOVOR-O-OBRADI-PODATAKA.md` | — (dokumentacija) |

Potpune tablice: `docs/SIGURNOST.md` → 2 i `docs/GDPR.md` → 9.

## 6. Pretpostavke (sažetak `docs/PRETPOSTAVKE.md`)

- **Okruženje**: lokalno Python 3.14, u Dockeru 3.11 (sve verzije podržavaju ≥ 3.11); Windows Smart App
  Control → pinani `sqlalchemy==2.1.0` i `nh3==0.3.6`; PostgreSQL provjeren prijenosnim binarnim
  datotekama 16.2 (ništa nije instalirano u sustav); Docker nedostupan.
- **Arhitektura**: vlastiti `render()`; klijentsko stanje (CSRF, flash, dedup pregleda) u potpisanom
  kolačiću `st`; CSRF na razini routera; čisti ASGI middleware; naivni UTC u bazi; string konstante
  umjesto enuma; nekoliko dodatnih kolona (`totp_last_step`, `color_metallic`, `inquiries.extra`,
  `contacted_at`, `confirm_sent_at`).
- **Autentikacija**: jedinstvena poruka o grešci i lažna Argon2 provjera; lockout broji i 2FA kodove;
  `ak_pending` kolačić između lozinke i koda; kodovi za oporavak `xxxx-xxxx-xxxx`; reset lozinke ne
  poništava 2FA.
- **Vozila**: katalog u minimalnom seedu; model obavezan; gorivo/mjenjač nisu obavezni za kampere;
  potrošnja/CO2 obavezni za nova vozila; polja po vrsti u JSON-u (`<vrsta>__<ključ>` u formi); obrada
  slika sinkrono u threadpoolu; limiti 12.000 px / 64 MP; logo zadržava prozirnost.
- **Javno**: prodana vozila vidljiva 30 dana na kraju liste, zatim 410; cijena "na upit" izvan filtera
  cijene; dedup pregleda 6 h bez privole (nužni kolačić); YouTube bez sličice do klika; 12 vozila po
  stranici.
- **Upiti**: Turnstile fail-open kod mrežne greške; < 3 s = bot; limiti 5/10 min po IP-u i 3/h po emailu;
  hrvatski i E.164 telefoni; retencija od `created_at`; bilješke brisive 15 min.
- **Newsletter**: HMAC token za odjavu (u bazi samo hash); odjava GET-om uz `?potvrdi=1`; ponovno slanje
  potvrde 1×/10 min; slanje u zasebnoj niti; sanitizacija kampanja sa slikama samo s vlastitog media.
- **Faza 7**: "bez odgovora" = status novi > 48 h; vrijeme do prvog kontakta iz `contacted_at`; traka za
  kolačiće zadano isključena; verzija stranice raste pri svakom spremanju; održavanje u 04:00 s atomskim
  preuzimanjem dana; `/admin/sustav` kao dodatak; `--reset-demo` zaštićen u produkciji.
- **Faza 8**: `SECRET_KEY` se u Dockeru generira ako nije zadan (lokalni demo); seed samo na praznoj
  bazi; `init` servis za vlasništvo nad `./data`; `DOMAIN` prazno = `http://localhost`; TLS: Origin
  certifikat ili DNS izazov; backup provjerava dump prije šifriranja (privatni ključ nije na serveru);
  vraćanje u novu bazu uz čuvanje stare; pip-audit kritično = produkcijske ovisnosti; API 100/min.

## 7. Poznati nedostaci i preporučeni sljedeći koraci

**Nije provjereno / poznati nedostaci**
- `docker build` i `docker compose up` nisu izvedeni (nema Dockera) → prvi korak na računalu s Dockerom:
  `docker compose up -d --build`, `curl http://localhost/zdravlje`, prijava, zatim `new-client.sh`,
  `backup.sh`, `restore.sh` na testnom klijentu (PRETPOSTAVKE → "Otvoreno").
- `age` varijanta backupa nije izvedena lokalno (GPG varijanta jest, s pravim PostgreSQL-om).
- Rate limiter je u memoriji po workeru (2 workera → do 2× limit); retencija app logova po veličini.
- HEIC fotografije (iPhone) nisu podržane; nema automatskog zamagljivanja tablica.
- Grafovi na mobitelu imaju sitne oznake osi (podaci su i u tablicama/CSV-u).

**Treba pravnik**
- Politika privatnosti, Kolačići, Uvjeti korištenja (zamijeniti lorem ipsum i sve `[PRAVNIK: dopuniti]`),
  ugovor o obradi podataka (`[PRAVNIK: provjeriti]`), popis podizvršitelja i lokacija off-site backupa.

**Sigurnost**
- Penetracijski test prije prvog pravog klijenta; Cloudflare WAF i rate limiting pravila; firewall
  80/443 samo za Cloudflare IP-ove; uptime monitor i obavijest o neuspjelom backupu; po potrebi Redis
  limiter i CSP reporting.

**Po klijentu (Brevo/Cloudflare)**
- Cloudflare: proxy, "Full (strict)", Origin certifikat, Turnstile ključevi.
- Brevo: verifikacija domene (SPF, DKIM, DMARC), API ključ, `EMAIL_FROM` na domeni klijenta; testni email.
- Google Search Console + sitemap; test vraćanja backupa pri onboardingu.

**Proizvod** — `docs/ROADMAP.md`: dodatne vrste upita → kalkulator leasinga → novosti →
feedovi prema portalima → više poslovnica → jezici → SMS → zamagljivanje tablica.

## 8. Screenshotovi (`docs/screenshots/`, generira `python scripts/screenshots.py`)

Javno — desktop: `javno-naslovnica-desktop.png`, `javno-lista-desktop.png`, `javno-detalj-desktop.png`,
`javno-lightbox-desktop.png`, `javno-kontakt-desktop.png`, `javno-privatnost-desktop.png`.
Javno — mobitel: `javno-naslovnica-mobile.png`, `javno-lista-mobile.png`, `javno-detalj-mobile.png`,
`javno-kontakt-mobile.png`, `javno-404-mobile.png`, `javno-upit-forma-mobile.png`,
`javno-newsletter-potvrda-mobile.png`.
Admin — desktop: `admin-prijava.png`, `admin-2fa-postavljanje.png`, `admin-dashboard-desktop.png`,
`admin-vozila.png`, `admin-vozilo-forma.png`, `admin-vozilo-slike.png`, `admin-upiti.png`,
`admin-upit-detalj.png`, `admin-newsletter-pretplatnici.png`, `admin-newsletter-kampanja.png`,
`admin-korisnici.png`, `admin-statistika-desktop.png`, `admin-postavke-desktop.png`,
`admin-stranice-editor-desktop.png`, `admin-gdpr-desktop.png`, `admin-audit.png`, `admin-sustav.png`.
Admin — mobitel: `admin-dashboard-mobile.png`, `admin-vozila-mobile.png`, `admin-upiti-mobile.png`,
`admin-statistika-mobile.png`.
