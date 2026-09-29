# SPECIFIKACIJA: Autokuća SaaS — MVP template (blank framework za demo)

> Ovaj dokument je izvor istine za cijeli projekt. Isporučuje se u `prompts/SPECIFIKACIJA.md`; agent ga na početku kopira u `docs/SPECIFIKACIJA.md` (verzija u `docs/` je mjerodavna i ide u git) i čita ga na početku svake faze. Build se vodi promptovima iz mape `prompts/` (00 orkestrator ili 01–08 pojedinačno). Odluke u dokumentu su konačne — ne mijenjaj ih; ako nešto nije definirano, odaberi razumnu opciju i zabilježi je u `docs/PRETPOSTAVKE.md`.

---

## 1. Uloga i cilj

Ti si senior full-stack developer. Izgradi **kompletan, pokretljiv MVP template** web-platforme za autokuće u Hrvatskoj. Platforma se instalira **zasebno za svakog klijenta** (jedna instanca = jedna autokuća, na njezinoj vlastitoj domeni), a hostam ih ja na jednom VPS-u (Netcup) kao Docker kontejnere.

Svrha ove verzije: **"blank framework" za demonstraciju potencijalnim klijentima**. Sve funkcionalnosti moraju stvarno raditi (oglasi, slike, upiti, newsletter, admin, 2FA), ali su svi podaci placeholder — nema pravih imena firmi, ljudi, slika ni tekstova. Klijent kasnije unese svoje podatke u admin > Postavke i cijela stranica se promijeni bez diranja koda.

Osnovne funkcionalnosti MVP-a:
1. Objavljivanje oglasa vozila sa slikama i specifikacijama (svi tipovi vozila, dinamička polja po tipu)
2. Skupljanje upita kupaca + mini-CRM
3. Newsletter s double opt-inom i slanjem kampanja iz admina
4. Admin panel (uloge, obavezna 2FA, postavke, statistika, audit log)
5. Čist, mobile-first javni frontend s dobrim SEO-om

## 2. Kako radiš

- Radi **samostalno do kraja**. Ne postavljaj pitanja. Kad nešto nije definirano, odaberi razumnu opciju i zabilježi je u `docs/PRETPOSTAVKE.md`.
- Radi **fazu po fazu** (poglavlje 20). Nakon svake faze pokreni aplikaciju, prođi kroz relevantne stranice (curl + Playwright), ispravi greške, pa tek onda nastavi.
- Sve mora raditi s **dvije naredbe**: lokalno (`python run.py` sa SQLite-om, bez Dockera) i u produkcijskom obliku (`docker compose up` s PostgreSQL-om).
- Na kraju napravi screenshotove ključnih stranica (desktop + mobile) u `docs/screenshots/` i pregledaj ih: dizajn mora izgledati profesionalno i uredno, bez slomljenih layouta.
- Piši čitljiv, komentiran kod koji ću kasnije održavati uz pomoć Claude Codea. Bez "pametnih" apstrakcija; radije jednostavno i eksplicitno.
- Jezik sučelja: **hrvatski** (ispravni dijakritici: č ć š ž đ). Kod, nazivi varijabli i komentari: engleski. Nazivi ruta na hrvatskom (`/vozila`, `/kontakt`, `/admin/upiti`).

### Razvojno okruženje

- Build se izvodi na **Windows računalu** (mapa projekta `C:\Users\matej\Documents\projekti\autokuce`), u PowerShellu ili WSL-u — ne pretpostavljaj koje. Sve što se pokreće lokalno (`run.py`, `scripts/*.py`, testovi, seed, screenshotovi) mora raditi na Windowsu i Linuxu: Python skripte umjesto shell skripti, `pathlib` umjesto ručnog spajanja putanja, bez POSIX-only poziva, bez oslanjanja na `make`, `bash` ili simboličke linkove.
- Skripte u `deploy/*.sh` namijenjene su Linux VPS-u i **ne pokreću se lokalno**; `.gitattributes` mora osigurati LF završetke redaka za `*.sh`, `Dockerfile`, `Caddyfile` i `*.py` (`* text=auto`, eksplicitno `eol=lf` za te datoteke), da se ne pokvare pri commitu s Windowsa.
- Docker Desktop možda nije instaliran: ako `docker` naredba nije dostupna, preskoči Docker provjere, provjeri barem sintaksu `Dockerfile`/`compose` datoteka i zabilježi u `docs/PRETPOSTAVKE.md` što nije testirano.
- Virtualno okruženje: `python -m venv .venv` (aktivacija ovisi o ljusci — dokumentiraj obje varijante u README-u).

### Strogo zabranjeno
- Vanjski CDN-ovi za CSS/JS/fontove (nema Google Fonts, nema Bootstrap/Tailwind CDN-a). Sve se servira lokalno. Fontovi: sistemski font stack.
- Kolačići za praćenje, Google Analytics, ugrađene Google karte (iframe), social pluginovi.
- Prava imena tvrtki, pravi logotipi, prave fotografije, prave osobe, pravi brojevi telefona.
- Pohrana lozinki ili tajni u kodu; sve tajne iz `.env`.
- Inline `<script>` u templateima (CSP bez `unsafe-inline` za skripte).

## 3. Placeholder pravila (obavezno, dosljedno)

Svi podaci o tvrtki dolaze **iz tablice postavki u bazi** (nikad hardkodirano u templateima). Seed puni te postavke sljedećim vrijednostima:

| Podatak | Placeholder vrijednost |
|---|---|
| Logo | Tekst `LOGO` u obrubljenom okviru (header, footer, admin login, emailovi). Favicon: SVG s velikim slovom "L". Kad klijent uploada logo u postavkama, zamjenjuje se slikom. |
| Naziv tvrtke | `IME PODUZEĆA` |
| Email | `mailpoduzeca@domena.com` |
| Telefon | `+385XXXXXXXXXX` |
| Adresa | `Ulica i broj 1, 10000 Grad` |
| OIB | `XXXXXXXXXXX` |
| Web | `www.domena.com` |
| Radno vrijeme | `Pon–Pet 08:00–17:00, Sub 09:00–13:00` |
| Društvene mreže | `https://facebook.com/imepoduzeca`, `https://instagram.com/imepoduzeca` |
| Google Maps link | `https://maps.google.com/?q=Ulica+i+broj+1+Grad` (samo gumb/link, bez iframea) |
| Osobe (prodavači, kupci u demo podacima) | `Ime Prezime`, `Prodavač 1`, `Prodavač 2`; emailovi `kupac1@primjer.hr`, `prodavac1@domena.com` |

Sav **sadržajni tekst** (hero naslov i podnaslov, O nama, Usluge, opisi vozila, pravni dokumenti, tekst newslettera) je **lorem ipsum**. Naslovi, labele, gumbi i poruke sučelja su na hrvatskom.

Slike vozila: **generirane placeholder slike** (Pillow, u seedu) — neutralna svijetlosiva pozadina s blagim gradijentom i tekstom `FOTOGRAFIJA VOZILA 1/8`, `2/8`… u različitim nijansama da se galerija vidi kao galerija. Omjer 4:3, 1600×1200.

## 4. Tech stack (fiksno)

- **Backend:** Python 3.11+, FastAPI, Jinja2 (server-side rendering), SQLAlchemy 2.0 (sync sesije), Alembic (migracije), pydantic-settings (konfiguracija), uvicorn.
- **Baza:** PostgreSQL 16 u Dockeru; SQLite za lokalni razvoj (default kad `DATABASE_URL` nije postavljen). Koristi JSON tip koji radi na obje.
- **Frontend:** HTML5 + vlastiti CSS (CSS varijable za temu) + vanilla JS. **Bez frontend frameworka i bez build koraka.**
- **Sigurnost:** argon2-cffi (lozinke), pyotp + qrcode (TOTP 2FA), itsdangerous (potpisani tokeni), nh3 (sanitizacija HTML-a), python-multipart.
- **Slike:** Pillow (re-enkodiranje u WebP), boto3 (S3-kompatibilni storage, opcionalno).
- **Vanjski servisi (svi opcionalni, isključeni ako ključ nije postavljen):** Brevo (email), Cloudflare Turnstile (anti-spam), Umami (analitika, cookieless, self-hosted).
- **Deployment:** Docker + Docker Compose, Caddy (reverse proxy, automatski TLS), iza Cloudflare proxyja.
- **Testovi:** pytest + FastAPI TestClient; Playwright (Chromium) za screenshotove.

## 5. Arhitektura

```
autokuca-template/
├── README.md, CLAUDE.md, .env.example, .gitignore, requirements.txt, run.py
├── Dockerfile, docker-compose.yml, Caddyfile, alembic.ini
├── app/
│   ├── main.py            # create_app(), middleware, routeri, startup
│   ├── config.py          # Settings (pydantic-settings)
│   ├── database.py        # engine, SessionLocal, Base, get_db
│   ├── models.py          # svi SQLAlchemy modeli
│   ├── security.py        # hashing, TOTP, tokeni, CSRF, rate limiter
│   ├── deps.py            # current_user, require_role, csrf
│   ├── templating.py      # Jinja env, filteri, i18n, globalne varijable (settings)
│   ├── vehicle_schema.py  # definicije tipova vozila i dinamičkih polja
│   ├── i18n/ hr.json, en.json, __init__.py
│   ├── services/          # email.py, storage.py, images.py, turnstile.py, audit.py,
│   │                      # newsletter.py, maintenance.py, vehicles.py, seo.py
│   ├── routers/           # public.py, seo.py, admin_auth.py, admin_dashboard.py,
│   │                      # admin_vehicles.py, admin_catalog.py, admin_inquiries.py,
│   │                      # admin_newsletter.py, admin_users.py, admin_settings.py,
│   │                      # admin_pages.py, admin_privacy.py, admin_audit.py
│   ├── templates/ public/, admin/, emails/
│   ├── static/ css/public.css, css/admin.css, js/public.js, js/admin.js, img/
│   ├── seed.py            # python -m app.seed
│   └── cli.py             # python -m app.cli maintenance | create-superadmin | ...
├── migrations/            # Alembic
├── overrides/             # prilagodbe po klijentu (templates/, static/custom.css) — volume
├── deploy/                # new-client.sh, backup.sh, restore.sh, crontab.example, caddy/
├── scripts/               # extract_strings.py, make_placeholder_images.py
├── tests/
├── docs/
└── data/                  # gitignored: app.db, media/, outbox/, backups/
```

Principi:
- Jedna Docker slika za sve klijente; razlike po klijentu su samo `.env`, baza, media i `overrides/`.
- Endpointi `async def`, DB sinkroni (prihvatljivo za ovaj volumen; zabilježi u docs).
- Sve postavke tvrtke i teme učitavaju se jednom po requestu i dostupne su u svim templateima kao `site`.
- Pozadinski poslovi (slanje emaila, obrada slika) kroz FastAPI `BackgroundTasks`. Dnevni maintenance kroz `python -m app.cli maintenance` (cron) i opcionalno pozadinsku nit u aplikaciji (`MAINTENANCE_IN_APP=true`).
- Iza proxyja: pravi IP iz `CF-Connecting-IP` / `X-Forwarded-For` samo kad je `TRUST_PROXY=true`.

## 6. Model podataka

Implementiraj sljedeće tablice (SQLAlchemy modeli + Alembic inicijalna migracija):

- **users**: id, email (unique), name, role (`superadmin` | `owner` | `salesperson`), password_hash, totp_secret, totp_enabled, recovery_codes (JSON, hashirani), is_active, failed_attempts, locked_until, last_login_at, created_at.
- **sessions**: id, token_hash, user_id, ip, user_agent, created_at, expires_at, last_seen_at. (Sesije na serveru → "Odjavi sve uređaje".)
- **auth_tokens**: id, user_id, purpose (`invite` | `reset`), token_hash, expires_at, used_at.
- **makes**: id, name, slug, is_active. **vehicle_models**: id, make_id, name, slug, vehicle_type (nullable), is_active.
- **vehicles**: id, slug (unique), vehicle_type (`car` | `van` | `motorcycle` | `camper` | `truck`), make_id, model_id, variant (npr. "320d xDrive M Sport"), title (generira se: marka + model + varijanta), condition (`new` | `used`), status (`draft` | `active` | `reserved` | `sold` | `archived`), year, first_registration (mjesec/godina), mileage_km, price_eur (integer, cent-precizno nije potrebno), price_old_eur (nullable, za prekriženu cijenu), price_on_request (bool), tax_type (`pdv` = "PDV uračunat u cijenu (R1)" | `marza` = "Posebni postupak oporezivanja marže" | `bez_pdv` = "Cijena bez PDV-a"), fuel, power_kw, power_hp (izračun), engine_ccm, transmission, drive, color, doors, seats, euro_norm, fuel_consumption_l100 (obavezno za nova), co2_g_km (obavezno za nova), registered_until, first_owner (bool), service_book (bool), warranty_months, vin (**samo admin, nikad javno**), description (sanitizirani HTML), equipment (JSON lista kodova), attributes (JSON — polja specifična za tip), featured (bool), views_total, video_url (YouTube link, opcionalno), created_by, created_at, updated_at, published_at, sold_at.
- **vehicle_slug_history**: id, vehicle_id, old_slug (unique), created_at. (Stari slug → 301 na novi.)
- **vehicle_images**: id, vehicle_id, file_key (bazni ključ; varijante `_400.webp`, `_1000.webp`, `_1600.webp`), sort_order, alt, width, height, created_at.
- **vehicle_views**: vehicle_id, date, count (unique par).
- **inquiries**: id, type (`vehicle` | `general` | `viewing`), vehicle_id (nullable), name, email, phone, message, preferred_date (za `viewing`), status (`new` | `contacted` | `closed`), assigned_to (user_id, nullable), consent_at, consent_ip, consent_user_agent, consent_policy_version, source_url, created_at, closed_at.
- **inquiry_notes**: id, inquiry_id, user_id, body, created_at.
- **subscribers**: id, email (unique, nullable), email_hash (SHA-256, unique — ostaje i nakon anonimizacije), status (`pending` | `confirmed` | `unsubscribed`), confirm_token_hash, unsubscribe_token_hash, consent_at, consent_ip, consent_user_agent, consent_policy_version, source, manual_consent_note (za ručni unos), confirmed_at, unsubscribed_at, created_at. Pri odjavi se email odmah anonimizira (email → NULL, ostaje samo hash); ponovna prijava iste adrese ide kroz novi double opt-in.
- **campaigns**: id, subject, body_html (sanitizirano), status (`draft` | `sending` | `sent`), recipients_count, sent_at, created_by, created_at.
- **campaign_deliveries**: id, campaign_id, subscriber_id, status (`sent` | `failed`), error, created_at.
- **settings**: key (PK), value (tekst/JSON). Ključevi: company_name, company_email, company_phone, company_address, company_oib, company_web, working_hours, facebook_url, instagram_url, maps_url, logo_key (nullable → prikaži tekst LOGO), primary_color, accent_color, hero_title, hero_subtitle, footer_text, inquiry_notify_email, newsletter_sender_name, privacy_policy_version, cookie_banner_enabled (default false), plates_reminder_enabled (default true).
- **pages**: id, slug (`o-nama`, `usluge`, `privatnost`, `kolacici`, `uvjeti`), title, body_html (sanitizirano), version, updated_by, updated_at, is_published.
- **audit_log**: id, user_id, action (npr. `vehicle.create`, `user.login`, `settings.update`, `privacy.export`), entity_type, entity_id, details (JSON bez osobnih podataka kupaca), ip, created_at.
- **email_log**: id, to_hash (SHA-256, ne čisti email), template, status, provider_message_id, error, created_at. (Za dijagnostiku isporuke bez čuvanja adresa.)

Polja oglasa uskladi s konvencijama Njuškala i mobile.de (nazivi goriva, mjenjača, tipova karoserije, opreme), kako bi izvoz feedova u fazi 2 bio samo mapiranje.

## 7. Tipovi vozila i dinamička polja

Definicije u `app/vehicle_schema.py` (Python dict; nije potreban admin editor). Admin pri unosu bira tip vozila i forma prikazuje odgovarajuća polja (JS prikazuje/skriva sekcije; server validira prema shemi).

Zajednička polja (svi tipovi): marka, model, varijanta, stanje (novo/rabljeno), godina, prva registracija, kilometraža, cijena, stara cijena, način oporezivanja, "cijena na upit", gorivo, snaga kW (KS izračun), ccm, mjenjač, boja, Euro norma, registriran do, prvi vlasnik, servisna knjižica, garancija (mj.), potrošnja, CO2, VIN, opis, oprema, video link, istaknuto.

Specifična polja po tipu (`attributes` JSON):
- **Osobni automobil (car):** karoserija (limuzina, karavan, hatchback, SUV/terenac, coupé, kabriolet, monovolumen, pickup), vrata, sjedala, pogon (prednji, stražnji, 4x4).
- **Kombi / laka dostavna (van):** tip (furgon, putnički, šasija/kabina, hladnjača), nosivost kg, volumen tereta m³, sjedala, međuosovinski razmak (kratki/srednji/dugi), visina krova (H1/H2/H3).
- **Motocikl (motorcycle):** tip (naked, sport, touring, enduro, cross, skuter, chopper/cruiser, moped), cilindri, hlađenje, prijenos (lanac/kardan/remen), ABS (bool), A2 prikladan (bool).
- **Kamper (camper):** tip (alkoven, poluintegrirani, integrirani, kombi-kamper, kamp prikolica), ležajeva, sjedala s pojasom, duljina m, dopuštena masa kg, WC/tuš (bool), grijanje.
- **Kamion (truck):** tip nadogradnje (sanduk, kiper, hladnjača, cisterna, šleper/tegljač, kran, cerada), dopuštena ukupna masa kg, nosivost kg, osovine, kabina (dnevna/spavaća), tahograf (bool).

Gorivo: benzin, dizel, hibrid, plug-in hibrid, električni, LPG, CNG. Mjenjač: ručni, automatski. Boja: standardna lista + "metalik" checkbox.

Oprema: zajednička lista kodova (klima, automatska klima, navigacija, kamera, parking senzori, tempomat, adaptivni tempomat, grijana sjedala, kožna sjedala, alu felge, LED/xenon, panoramski krov, Apple CarPlay/Android Auto, kuka, Isofix, alarm, start-stop, …) grupirana po kategorijama (sigurnost, udobnost, multimedija, eksterijer) + dodatne stavke po tipu (motocikl: kofer, grijane ručke, quickshifter; kamper: solarni panel, tenda, nosač bicikala…).

## 8. Javni frontend

Stranice (sve SSR, čisti URL-ovi):
- `/` — hero (naslov, podnaslov iz postavki, CTA "Pregledaj vozila"), brza pretraga (tip, marka, model, cijena do), istaknuta vozila (grid), zadnje dodana vozila, blok "Zašto mi" (3 stavke, lorem), CTA newsletter, kontakt blok.
- `/vozila` — lista s filterima (tip, marka, model — ovisan o marki, cijena od/do, godina od/do, kilometraža do, gorivo, mjenjač, stanje novo/rabljeno) + sortiranje (najnovije, cijena ↑↓, kilometraža ↑, godina ↓) + paginacija (12 po stranici). Filteri kao GET parametri (dijeljivi URL). Na mobitelu filteri u sklopivom panelu. Prikaz kartice: slika, naslov, godina · km · gorivo · mjenjač, cijena (+ prekrižena stara), badge "NOVO"/"REZERVIRANO"/"PRODANO".
- `/vozila/{slug}` — galerija (glavna slika + thumbnailovi, lightbox u vanilla JS-u, strelice, swipe), naslov, cijena + način oporezivanja + stara cijena, ključni podaci (grid), tabovi/sekcije: specifikacije (po tipu), oprema (po kategorijama), opis, video (samo ako postoji, kao klik-za-učitavanje, ne autoload iframea). Sidebar/sticky: kontakt blok tvrtke + forma "Upit za vozilo" + gumb "Dogovori pregled vozila" (forma tipa `viewing` s datumom). Na mobitelu sticky traka s "Nazovi" i "Pošalji upit". Slična vozila (isti tip/marka). Gumb "Ispiši" (print CSS).
- `/kontakt` — podaci tvrtke, radno vrijeme, gumb "Otvori u Google kartama" (link), opći kontakt formular.
- `/o-nama`, `/usluge` — iz tablice pages (lorem).
- `/privatnost`, `/kolacici`, `/uvjeti` — iz tablice pages, s prikazom verzije i datuma.
- `/newsletter/prijava` (POST), `/newsletter/potvrda/{token}`, `/newsletter/odjava/{token}` — stranice s porukom uspjeha/greške.
- `/sitemap.xml`, `/robots.txt`, `/zdravlje` (health check, JSON), stranica 404 i 500 u dizajnu stranice.

Zaglavlje: LOGO, navigacija (Vozila, Usluge, O nama, Kontakt), telefon kao `tel:` link. Podnožje: impressum blok (naziv, adresa, OIB, email, telefon), linkovi na pravne stranice, društvene mreže, newsletter prijava, "© {godina} IME PODUZEĆA".

Svi formulari: honeypot polje, Turnstile widget (ako je konfiguriran), CSRF token, checkbox privole (default neoznačen) s linkom na politiku privatnosti, server-side validacija, prikaz grešaka uz polja, poruka uspjeha.

## 9. Dizajn

Nemam referentni dizajn — predloži **čist, moderan, mobile-first** dizajn:
- Neutralna paleta (bijela/svijetlosiva podloga, tamno siva tipografija) + jedna primarna boja i jedna akcentna boja iz postavki (CSS varijable `--color-primary`, `--color-accent`, injektirane u `<style>` blok u `<head>` — stilovi smiju biti inline, skripte ne).
- Sistemski font stack, jasna hijerarhija, velik razmak, zaobljene kartice, suptilne sjene, konzistentni gumbi i forme.
- Responsivno: 360 px do 1440 px; grid vozila 1/2/3/4 stupca.
- Pristupačnost: semantički HTML, labele na svim poljima, vidljiv focus, kontrast AA, tipke dostupne tipkovnicom, `alt` na slikama, `aria` na lightboxu i mobilnom izborniku.
- Slike: `<img loading="lazy" srcset sizes>` s WebP varijantama.
- Admin: sidebar navigacija, pregledne tablice s pretragom/filterima/paginacijom, jasne forme, flash poruke, potvrda prije brisanja, isti vizualni jezik ali gušći raspored. Također responsivan (prodavač na mobitelu).

## 10. Admin panel (`/admin`)

Uloge i ovlasti:
| | superadmin (ja) | owner (vlasnik autokuće) | salesperson (prodavač) |
|---|---|---|---|
| Vozila, slike, katalog marki | ✔ | ✔ | ✔ |
| Upiti + CRM | ✔ | ✔ | ✔ (svi upiti; brisanje ne) |
| Newsletter (pretplatnici, kampanje) | ✔ | ✔ | samo pregled |
| Statistika | ✔ | ✔ | ✔ |
| Korisnici | ✔ | ✔ (ne može dirati superadmina) | ✘ |
| Postavke tvrtke, stranice | ✔ | ✔ | ✘ |
| Alat za prava ispitanika (GDPR) | ✔ | ✔ | ✘ |
| Audit log | ✔ | ✔ (pregled) | ✘ |
| Sistemske postavke (env/dijagnostika) | ✔ | ✘ | ✘ |

Ekrani:
- **Prijava** (`/admin/prijava`): email + lozinka → 2FA kod → dashboard. Ako korisnik nema postavljen 2FA: obavezni ekran postavljanja (QR kod + ručni ključ + potvrda koda + 10 kodova za oporavak koji se prikažu jednom). "Zaboravljena lozinka" → email s linkom (token 1 h). Odjava. "Odjavi sve uređaje" u profilu.
- **Dashboard**: kartice (aktivna vozila, novi upiti, potvrđeni pretplatnici, pregledi zadnjih 30 dana), graf pregleda po danu (inline SVG, bez biblioteka), zadnjih 10 upita, top 5 vozila po pregledima, podsjetnici (skice bez slika, upiti bez odgovora > 48 h).
- **Vozila**: lista (pretraga, filter po statusu/tipu, sortiranje), novo/uredi (dinamička forma po tipu; model ovisan o marki; validacija; nova vozila zahtijevaju potrošnju i CO2), promjena statusa (skica → aktivno → rezervirano → prodano; prodano ostaje javno 30 dana pa auto-arhiva), dupliciraj oglas, brisanje s potvrdom. **Slike**: drag-and-drop upload više slika, sortiranje povlačenjem (vanilla JS), postavi glavnu, obriši, alt tekst; obavezan checkbox "Potvrđujem da su registarske tablice zamagljene ili prekrivene" (ako je `plates_reminder_enabled`).
- **Katalog**: marke i modeli (CRUD, aktiviraj/deaktiviraj, uvoz iz CSV-a), pregled tipova vozila i njihovih polja (samo čitanje).
- **Upiti**: inbox s filterima (status, tip, dodijeljeno, vozilo), detalj s podacima kupca, poveznicom na vozilo, promjenom statusa, dodjelom prodavaču, internim bilješkama, gumbom "Odgovori emailom" (`mailto:` s predloženim subjectom). Brisanje (owner+). Izvoz CSV (owner+).
- **Newsletter**: pretplatnici (lista sa statusom, izvorom i vremenom privole; ručni unos samo uz oznaku "privola prikupljena izvan sustava"; izvoz CSV), kampanje (novo/uredi: subject, sadržaj s jednostavnim editorom; pregled; testni email; slanje svim potvrđenima u pozadini; izvještaj poslano/neuspjelo). Svaki email ima link za odjavu jednim klikom i impressum.
- **Statistika**: pregledi po danu (30/90 dana), pregledi i upiti po vozilu, upiti po tipu i statusu, prijave/odjave newslettera po tjednu. Bez vanjskih biblioteka (SVG/tablice).
- **Korisnici**: lista, pozivnica emailom (link za postavljanje lozinke, 48 h), uloga, deaktivacija, reset 2FA (owner+ za druge, uz audit zapis).
- **Postavke**: podaci tvrtke (svi placeholderi iz poglavlja 3), upload logotipa, boje (color picker), hero tekstovi, email za obavijesti o upitima, ime pošiljatelja newslettera, verzija politike privatnosti (promjena verzije zabilježi datum).
- **Stranice**: uređivanje pet stranica iz tablice pages s jednostavnim editorom (podebljano, kurziv, naslovi H2/H3, popisi, linkovi) — sanitizirano nh3-om; verzija se povećava pri spremanju.
- **Prava ispitanika (GDPR)**: unos emaila → pronađi sve podatke (upiti, bilješke, pretplata) → izvoz JSON + gumb "Obriši sve podatke ove osobe" (s potvrdom; audit zapis bez emaila, samo hash).
- **Audit log**: tablica s filterima po korisniku/akciji/datumu.
- **Profil**: promjena lozinke, ponovno postavljanje 2FA, popis aktivnih sesija + odjava svih.

## 11. Upiti + mini-CRM

Tipovi u MVP-u: `vehicle` (upit za konkretno vozilo), `general` (opći kontakt), `viewing` (dogovor termina za pregled vozila: vozilo + željeni datum/vrijeme + napomena). Model mora dopustiti kasnije dodavanje tipova (probna vožnja, financiranje, procjena vozila za zamjenu, povratni poziv) bez migracije strukture.

Tijek: forma → validacija + honeypot + Turnstile + rate limit (npr. 5 upita / 10 min po IP-u) → zapis s metapodacima privole → email obavijest na `inquiry_notify_email` (predložak s podacima upita i linkom na admin) → potvrdna poruka kupcu na ekranu (bez slanja emaila kupcu u MVP-u). Statusi: novi → kontaktiran → zatvoren. Automatsko brisanje nakon `INQUIRY_RETENTION_DAYS` (default 365).

## 12. Newsletter

- Prijava (footer + naslovnica + stranica vozila): email + checkbox privole + Turnstile. Ako email već postoji kao potvrđen → neutralna poruka (bez otkrivanja postoji li).
- **Double opt-in**: email s linkom za potvrdu (token, 7 dana). Nepotvrđeni se brišu nakon 7 dana. Potvrda sprema `confirmed_at`.
- Odjava jednim klikom putem tokena u svakom emailu (bez prijave), plus stranica s potvrdom.
- Kampanje iz admina; slanje kroz `EmailService` u pozadini, u serijama (npr. 50 po seriji, pauza), zapis po primatelju. Predložak emaila: jednostavan HTML + tekstualna verzija, LOGO tekst, impressum, link za odjavu, link na politiku privatnosti.
- Email backend: `console` (log), `file` (zapiši .eml/.txt u `data/outbox/` — default za demo), `brevo` (HTTP API `api.brevo.com/v3/smtp/email`). Dokumentiraj potrebu za verifikacijom domene pošiljatelja u Brevu (SPF/DKIM/DMARC) po klijentu.

## 13. Sigurnost (checklista — sve obavezno)

- Lozinke Argon2id; minimalna duljina 12; provjera protiv 100 najčešćih lozinki.
- Zaključavanje računa nakon 5 neuspjelih pokušaja na 15 min; rate limit na login (10/min po IP), forme (5/10 min), API (100/min). In-memory limiter je dovoljan, s napomenom o Redisu za više workera.
- **2FA (TOTP) obavezna za sve admin korisnike**; kodovi za oporavak hashirani; tajna TOTP-a šifrirana u bazi ključem iz `SECRET_KEY` (Fernet ili ekvivalent).
- Sesije na serveru (tablica), kolačić HttpOnly + Secure (kad je HTTPS) + SameSite=Lax, trajanje 12 h, obnavljanje ID-a nakon prijave, odjava sa svih uređaja.
- CSRF token (vezan uz sesiju) na svakom POST/PUT/DELETE formularu, uključujući upload.
- Sigurnosni headeri: CSP (`default-src 'self'; script-src 'self' https://challenges.cloudflare.com [UMAMI_HOST]; style-src 'self' 'unsafe-inline'; img-src 'self' data: [MEDIA_HOST]; frame-src https://challenges.cloudflare.com https://www.youtube-nocookie.com; frame-ancestors 'none'`), X-Content-Type-Options, X-Frame-Options DENY, Referrer-Policy strict-origin-when-cross-origin, Permissions-Policy, HSTS (samo kad `HTTPS=true`).
- Upload: provjera sadržaja Pillowom (ne samo ekstenzije), dopušteno JPEG/PNG/WebP, max `MAX_UPLOAD_MB` (10), max `MAX_IMAGES_PER_VEHICLE` (30), re-enkodiranje u WebP 400/1000/1600 px (time se briše EXIF/GPS i skriveni sadržaj), nasumična imena datoteka, pohrana izvan webroota (`data/media/`) ili u S3, servirano kroz `/media/` rutu ili CDN URL. SVG/HTML/PDF upload zabranjen. Logo: isti postupak (PNG/WebP/JPEG, max 2 MB).
- Sanitizacija svakog rich-text unosa (nh3, allowlist tagova); Jinja autoescape uključen; ORM parametrizirani upiti; nikakav raw SQL s konkatenacijom.
- Tajne isključivo iz `.env`; `.env.example` bez vrijednosti; `SECRET_KEY` obavezan u produkciji (aplikacija odbija start bez njega kad `APP_ENV=production`).
- Logovi bez osobnih podataka (emailovi hashirani ili maskirani), rotacija, retencija 30 dana. Audit log svih admin akcija (tko, što, kada, IP).
- Zaštita od enumeracije korisnika (iste poruke za nepostojeći email), odgode na login.
- Health endpoint bez osjetljivih podataka. Admin ruta `/admin` s `noindex` i `Disallow` u robots.txt. Opcionalni `ADMIN_IP_ALLOWLIST`.
- `pip-audit` u CI skripti (`scripts/check.py`: ruff + pytest + pip-audit). Dockerfile: non-root korisnik, multi-stage, pinned verzije.
- Dokumentiraj u `docs/SIGURNOST.md`: model prijetnji, što je pokriveno, što ostaje (pentest, WAF pravila, Redis limiter, HEIC podrška, backup šifriranje).

## 14. GDPR i pravni zahtjevi (obavezno)

- Privola: checkbox neoznačen po defaultu, tekst "Pročitao/la sam Politiku privatnosti i pristajem na obradu podataka radi odgovora na upit" (upiti) / "…radi primanja newslettera" (newsletter). Spremi: vrijeme, IP, user agent, izvor forme, verziju politike.
- Pravne osnove dokumentirane u `docs/GDPR.md`: upiti = predugovorne radnje (čl. 6(1)(b)); newsletter = privola (6(1)(a)); analitika Umami bez kolačića = legitimni interes; admin korisnici = ugovor. Uloge: autokuća = voditelj obrade za podatke kupaca, ja (operator platforme) = izvršitelj obrade → potreban ugovor o obradi (čl. 28). Pripremi predložak `docs/pravno/UGOVOR-O-OBRADI-PODATAKA.md` s poljima za popunjavanje i oznakom `[PRAVNIK: provjeriti]`.
- Pravne stranice (privatnost, kolačići, uvjeti) seedaj **lorem ipsum strukturom** s naslovima sekcija koje pravi dokument mora imati (voditelj obrade, svrhe, pravne osnove, primatelji/podizvršitelji, prijenos izvan EU, rokovi čuvanja, prava ispitanika, pritužba AZOP-u, kontakt) i oznakom `[PRAVNIK: dopuniti]` u svakoj sekciji.
- Impressum u podnožju svake stranice (naziv, adresa, OIB, email, telefon) — obveza po Zakonu o elektroničkoj trgovini.
- Rokovi čuvanja i automatsko brisanje (`maintenance`): upiti 365 dana, nepotvrđene pretplate 7 dana, odjavljeni pretplatnici zadržavaju se samo kao hash emaila (suppression lista) 3 godine, sesije/tokeni po isteku, logovi 30 dana, audit 2 godine, prodana vozila arhiva (bez osobnih podataka, mogu ostati).
- Alat za prava ispitanika (pristup/izvoz/brisanje) u adminu — poglavlje 10.
- Bez cookie bannera dok se koriste samo nužni kolačići (sesija admina, CSRF) i cookieless Umami; opcija `cookie_banner_enabled` za slučaj da klijent kasnije doda GA/Pixel (tada banner s odbijanjem jednako lakim kao prihvaćanje; skripte se ne učitavaju bez privole).
- Fontovi i sav JS/CSS lokalno; karte samo kao link; YouTube preko `youtube-nocookie.com` i tek na klik.
- Popis podizvršitelja u `docs/GDPR.md`: hosting (Netcup, DE), Cloudflare (proxy, Turnstile, R2 — EU-US DPF), Brevo (FR), Umami (self-hosted, nema podizvršitelja), off-site backup lokacija (definirati). Napomena o procedurama: zahtjevi ispitanika u 30 dana, prijava incidenta AZOP-u u 72 h, kontakt za privatnost = `company_email`.
- Za nova vozila oglas obavezno prikazuje potrošnju i CO2 emisije (EU/HR propis o označavanju); za rabljena jasno stanje, kilometraža i način oporezivanja.

## 15. SEO

- SSR, čisti URL-ovi: `/vozila/{marka}-{model}-{godina}-{id}` (slug se regenerira pri promjeni, stari slug 301).
- `<title>` i `meta description` po stranici (vozilo: "BMW 320d 2019, 145.000 km – IME PODUZEĆA"), canonical, Open Graph + Twitter Card (slika = glavna slika vozila), JSON-LD `Vehicle`/`Car`/`Motorcycle` + `Offer` (cijena, valuta EUR, dostupnost) + `AutoDealer` (Organization) na naslovnici + `BreadcrumbList`.
- `sitemap.xml` (aktivna vozila + stranice, lastmod), `robots.txt` (Disallow: /admin, /media/private), prodana vozila nakon arhive → 410/redirekt na listu; paginacija s `rel=prev/next`; slike s `alt` (naslov vozila + redni broj); brzina: WebP, lazy load, minimalan CSS/JS, cache headeri za static/media.
- Struktura spremna za hreflang kad dođu jezici.

## 16. Višejezičnost (pripremiti, ne aktivirati)

- Helper `_()` u Jinji i Pythonu; **ključ = hrvatski izvorni tekst** (gettext stil). `app/i18n/hr.json` je prazan/identitet, `en.json` primjer s ~30 prevedenih stringova.
- `LANGUAGE=hr` u env-u; novi jezik = nova JSON datoteka, bez diranja koda. `scripts/extract_strings.py` skuplja sve `_()` pozive u JSON.
- Sadržaj u bazi (opisi, stranice) ostaje jednojezičan u MVP-u; dokumentiraj put do prijevoda sadržaja (kolone `_en` ili tablica prijevoda) u `docs/ARHITEKTURA.md`.

## 17. Prilagodbe po klijentu (overrides)

- Mapa `overrides/` montira se kao volume u kontejner. Jinja `ChoiceLoader`: prvo `overrides/templates/`, zatim `app/templates/`. `overrides/static/custom.css` učitava se nakon glavnog CSS-a ako postoji.
- Time mogu Claude Codeom mijenjati izgled pojedinog klijenta bez diranja zajedničke Docker slike; ažuriranje slike ne pregazi prilagodbe. Napiši `overrides/README.md` s primjerom (override `public/home.html` i promjena boje).

## 18. Deployment i operativa

- `Dockerfile` (python:3.11-slim, multi-stage, non-root, healthcheck).
- `docker-compose.yml` za jednog klijenta: `app` (uvicorn, 2 workera), `db` (postgres:16, volume), `caddy` (Caddyfile s domenom iz env-a; TLS automatski; iza Cloudflare proxyja — dokumentiraj "Full (strict)" način), volumeni za `data/media`, `overrides`, backupe.
- `deploy/new-client.sh <ime-klijenta> <domena>`: kreira `clients/<ime>/` s `.env` (generirane tajne), `docker-compose.yml` (iz predloška, s prefiksom imena kontejnera), doda domenu u zajednički Caddy (`deploy/caddy/` — jedan Caddy za sve klijente na VPS-u, klijentske aplikacije na zajedničkoj Docker mreži `web`), pokrene migracije i seed postavki (bez demo vozila: `--minimal`).
- `deploy/backup.sh`: `pg_dump` → gzip → šifriranje (`age` ili `gpg`) → off-site (`rclone` na S3/Storage Box), retencija 30 dana, provjera integriteta; media se ne kopira ako je u object storageu (verzioniranje bucketa), inače rsync. `deploy/restore.sh` s uputama i testom vraćanja. `deploy/crontab.example` (backup 03:00, maintenance 04:00).
- `scripts/check.py` (ruff, pytest, pip-audit). `run.py` za lokalni razvoj (reload, SQLite, file email backend).
- Storage backend: `local` (default) ili `s3` (S3-kompatibilni: Cloudflare R2 / Hetzner Object Storage) — `STORAGE_BACKEND`, `S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `MEDIA_URL` (CDN).
- Umami: samo `<script defer src=UMAMI_SCRIPT_URL data-website-id=...>` ako su varijable postavljene; CSP ga dopušta.
- Sve env varijable u `.env.example` s komentarom što rade i koje su obavezne u produkciji.

## 19. Seed / demo podaci (`python -m app.seed`, idempotentno; `--minimal` samo postavke i katalog)

- Postavke s placeholderima iz poglavlja 3; stranice s lorem ipsum strukturom (poglavlje 14).
- Katalog: ~25 marki s po 5–15 modela (stvarni nazivi marki i modela su OK — to je generički katalog, ne podaci tvrtke), pokrivajući sve tipove vozila.
- 16 demo vozila: 8 osobnih, 3 kombija, 2 motocikla, 2 kampera, 1 kamion; miks stanja (novo/rabljeno), statusa (12 aktivnih, 1 rezervirano, 2 prodana, 1 skica), 3 istaknuta, jedno s "cijena na upit", jedno sa starom cijenom; svako s 5–8 generiranih placeholder slika; opisi lorem ipsum (2–3 odlomka), realistične specifikacije i oprema.
- 10 upita raznih tipova i statusa (imena "Ime Prezime", `kupacN@primjer.hr`, telefon `+385XXXXXXXXXX`), nekoliko bilješki.
- 15 pretplatnika (10 potvrđenih, 3 na čekanju, 2 odjavljena), 1 poslana kampanja (s isporukama) i 1 skica.
- Pregledi vozila za zadnjih 60 dana (nasumični, realistični) da dashboard i statistika imaju sadržaj.
- Korisnici: `admin@domena.com` (superadmin), `vlasnik@domena.com` (owner), `prodavac1@domena.com` (salesperson); lozinka iz `SEED_PASSWORD` (default `Promijeni-me-2026!`); **bez postavljenog 2FA**, tako da prva prijava demonstrira obavezno postavljanje.
- Audit log s nekoliko demo zapisa.

## 20. Faze rada (redoslijed obvezan; nakon svake faze pokreni i provjeri)

Detaljni prompt za svaku fazu nalazi se u `prompts/0N-*.md`; ovdje je pregled.

1. **Temelj:** struktura projekta, config, DB, svi modeli, Alembic inicijalna migracija, templating (i18n, `site` globali, overrides loader), sigurnosni middleware/headeri, health endpoint, `run.py`, `.env.example`, `README` kostur, `CLAUDE.md`, temelj CSS-a (design system). Provjera: aplikacija se diže na SQLite-u i Postgresu, `/zdravlje` vraća 200.
2. **Autentikacija i korisnici:** email servis (console/file/brevo — potreban za pozivnice i reset), login, lockout, sesije, obavezni 2FA setup + provjera, kodovi za oporavak, pozivnice, reset lozinke, uloge i ovlasti, profil, audit log, admin base layout. Provjera: cijeli tijek prijave kroz Playwright.
3. **Katalog i vozila:** marke/modeli, `vehicle_schema.py`, CRUD vozila s dinamičkom formom, statusi, slug + povijest slugova, upload i obrada slika, sortiranje slika, storage backendi. Provjera: unos vozila svakog tipa sa slikama.
4. **Javni frontend + SEO:** sve javne stranice, filteri, detalj s galerijom, JSON-LD, sitemap, robots, 404/500, CSS/JS, responsivnost, brojanje pregleda. Provjera: screenshotovi desktop + mobile; nema vanjskih requesta (provjeri u Playwrightu); HTML dobro formiran.
5. **Upiti + CRM:** forme, Turnstile, honeypot, rate limit, obavijesti emailom, admin inbox, statusi, bilješke, dodjela, izvoz. Provjera: upit završi u adminu i u `data/outbox/`.
6. **Newsletter:** prijava, double opt-in, odjava s anonimizacijom, kampanje, jednostavni editor, slanje u pozadini, izvještaj. Provjera: cijeli tijek kroz `data/outbox/`.
7. **Statistika, postavke, stranice, GDPR alat, maintenance, seed:** dashboard, statistika, postavke + logo + boje, editor stranica, alat za prava ispitanika, `cli maintenance` (retencija, arhiva prodanih, čišćenje tokena), seed s punim demo podacima i generiranim slikama.
8. **Deployment, testovi, dokumentacija:** Dockerfile, compose, Caddy, `new-client.sh`, backup/restore, cron, `scripts/check.py`, cijela pytest suita, Playwright screenshotovi u `docs/screenshots/`, sva dokumentacija, završni pregled dizajna i završni izvještaj.

## 21. Testovi (pytest, moraju prolaziti)

Minimalno: javne stranice vraćaju 200 i sadrže placeholdere iz postavki; detalj vozila sadrži JSON-LD i ne sadrži VIN; filteri vraćaju ispravan skup; upit bez privole se odbija, s privolom se sprema i email završi u outboxu; honeypot odbija; rate limit blokira; newsletter double opt-in (prijava → pending → potvrda → confirmed → odjava); admin bez prijave → redirect; prijava bez 2FA → prisilni setup; TOTP tijek; CSRF bez tokena → 403; prodavač ne može na `/admin/korisnici` ni `/admin/postavke`; upload ne-slike odbijen; upload iznad limita odbijen; slika se re-enkodira i EXIF nestaje; maintenance briše stare upite i arhivira prodana vozila; GDPR alat briše sve podatke osobe; sitemap sadrži samo aktivna vozila; sigurnosni headeri prisutni; nema vanjskih URL-ova u HTML-u javnih stranica (osim Turnstile/Umami kad su konfigurirani).

## 22. Dokumentacija (sve na hrvatskom)

- `README.md`: što je ovo, brzi start lokalno (3 koraka), brzi start Docker, env varijable, struktura, kako dodati tip vozila / polje / jezik, deployment novog klijenta, backup/restore, overrides, sigurnost i GDPR sažetak, roadmap.
- `CLAUDE.md` (za budući rad s Claude Codeom): stack, kako pokrenuti i testirati, gdje je što, pravila: podaci tvrtke samo iz postavki; nema CDN-ova ni inline skripti; svaki novi POST ima CSRF; svaki novi upload prolazi kroz `images.py`; svaka admin akcija ide u audit log; svaki novi string kroz `_()`; migracije Alembicom; pokreni `scripts/check.py` prije završetka.
- `docs/ARHITEKTURA.md`, `docs/SIGURNOST.md`, `docs/GDPR.md`, `docs/PRETPOSTAVKE.md`, `docs/ONBOARDING-KLIJENTA.md` (checklista: domena i Cloudflare DNS, Brevo verifikacija domene, upis podataka tvrtke, logotip, pravni dokumenti pregledani od pravnika, potpisan ugovor o obradi, uvoz vozila, test upita i newslettera, backup provjeren), `docs/ROADMAP.md`, `docs/pravno/UGOVOR-O-OBRADI-PODATAKA.md`.

## 23. Izvan opsega MVP-a (ne implementirati, ali model podataka mora dopustiti)

Premium paket kasnije: kalkulator leasinga/rate, blog/novosti i dodatne stranice, dodatne vrste upita (probna vožnja, financiranje, procjena vozila za zamjenu, povratni poziv), automatsko zamagljivanje tablica, XML feedovi prema portalima (Njuškalo, Index oglasi, mobile.de, AutoScout24), više jezika sa sadržajem, SMS/WhatsApp obavijesti, više poslovnica, naplata pretplate u aplikaciji (fakturira se ručno).

## 24. Definition of done

- [ ] `python run.py` i `docker compose up` rade bez ručnih koraka (seed se pokreće automatski pri prvom startu ili jednom naredbom).
- [ ] Sve stranice i tijekovi iz poglavlja 8, 10, 11, 12 rade i vidljivi su na screenshotovima.
- [ ] Nigdje u templateima nema hardkodiranih podataka tvrtke; svi placeholderi dolaze iz postavki.
- [ ] Nema vanjskih resursa u HTML-u (provjereno testom).
- [ ] Sigurnosna checklista (13) i GDPR checklista (14) u cijelosti implementirane; sve stavke koje nisu, izričito navedene u `docs/PRETPOSTAVKE.md` s razlogom.
- [ ] `scripts/check.py` prolazi (ruff, pytest, pip-audit bez kritičnih nalaza).
- [ ] Dokumentacija iz poglavlja 22 napisana.
- [ ] Završni izvještaj u zadnjoj poruci: što je izgrađeno, kako pokrenuti, pristupni podaci za demo, popis pretpostavki, poznati nedostaci i preporučeni sljedeći koraci.
