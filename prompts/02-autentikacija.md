# FAZA 2/8 — Autentikacija, 2FA, korisnici, admin okvir

## Kontekst

Faza 2 od 8. Prvo pročitaj `CLAUDE.md` i `docs/SPECIFIKACIJA.md` [ako je nema u `docs/`, kopiraj `prompts/SPECIFIKACIJA.md` u `docs/`] (posebno poglavlja 6, 10, 12 — email backend, 13). Provjeri stanje repozitorija (faza 1 mora biti gotova: modeli, migracije, templating, sigurnosni headeri). Ne postavljaj pitanja; nedefinirano odluči sam i zabilježi u `docs/PRETPOSTAVKE.md`.

## Cilj faze

Potpun, siguran tijek prijave u admin s **obaveznom 2FA**, sesijama na serveru, upravljanjem korisnicima i ulogama, audit logom i gotovim admin layoutom. Email servis se implementira sada jer ga trebaju pozivnice i reset lozinke.

## Zadaci

1. **Email servis** (`app/services/email.py`)
   - Sučelje `send(to, subject, text, html=None, template=None)`; backendi: `console` (log), `file` (zapiše `.eml` s datumom i subjectom u `data/outbox/` — default za razvoj), `brevo` (HTTP API `POST https://api.brevo.com/v3/smtp/email`, ključ iz env-a, timeout, retry 1×).
   - Svako slanje zapiše u `email_log` (to_hash SHA-256, template, status, provider_message_id, error) — bez čiste adrese.
   - Predlošci u `app/templates/emails/`: `base.html` + `base.txt` (tekst `LOGO`, naziv tvrtke, impressum, link na politiku privatnosti iz `site`), `user_invite`, `password_reset`. Sve kroz `BackgroundTasks`.

2. **Prijava i sesije** (`app/routers/admin_auth.py`, `app/deps.py`)
   - `GET/POST /admin/prijava`: email + lozinka; Argon2 provjera; iste poruke za nepostojeći email i krivu lozinku; rate limit 10/min po IP-u; nakon 5 neuspjelih pokušaja zaključaj račun 15 min (`failed_attempts`, `locked_until`); mala fiksna odgoda kod neuspjeha.
   - Nakon ispravne lozinke: ako `totp_enabled` → `GET/POST /admin/prijava/2fa` (6-znamenkasti kod ili kod za oporavak); ako nije → **prisilni** `GET/POST /admin/2fa/postavljanje` (QR kod kao data-URI generiran qrcode bibliotekom, tajna za ručni unos, potvrda kodom; nakon potvrde prikaži 10 kodova za oporavak jednom, spremi ih hashirane). Međustanje ("lozinka OK, čeka 2FA") drži u potpisanom kolačiću s rokom 10 min, ne u DB sesiji.
   - TOTP tajna šifrirana u bazi (Fernet iz `app/security.py`). Zaštita od ponovne upotrebe istog TOTP koda unutar prozora.
   - Tek nakon 2FA kreiraj zapis u `sessions` (token nasumičan 32 bajta, u bazi samo hash; `ip`, `user_agent`, `expires_at = now + SESSION_HOURS`), kolačić `session`: HttpOnly, SameSite=Lax, Secure kad `HTTPS=true`, Path=/admin. Regeneriraj token pri prijavi. Ažuriraj `last_seen_at` najviše jednom u 5 min.
   - `get_current_user` dependency: čita kolačić, provjerava sesiju (istek, aktivan korisnik), vraća korisnika ili redirecta na prijavu (`?next=`). `require_role(*roles)` prema matrici u poglavlju 10 — zabranjeno vraća 403 stranicu u admin dizajnu.
   - `POST /admin/odjava` (briše sesiju), `POST /admin/odjava-svugdje` (briše sve sesije korisnika). Sve POST rute kroz `verify_csrf`.
   - `ADMIN_IP_ALLOWLIST` (opcionalno): ako je postavljen, `/admin/*` dostupan samo s tih IP-ova/CIDR-ova.

3. **Reset lozinke i pozivnice**
   - `GET/POST /admin/lozinka/zaboravljena` → uvijek ista poruka; ako email postoji, kreiraj `auth_tokens` (purpose `reset`, 1 h) i pošalji link `/admin/lozinka/nova/{token}`. Rate limit 3/15 min po IP-u i po emailu.
   - `GET/POST /admin/lozinka/nova/{token}`: provjera tokena (hash, rok, neiskorišten), nova lozinka (min 12 znakova, provjera protiv liste 100 najčešćih lozinki u `app/security.py`), označi token iskorištenim, obriši sve sesije korisnika.
   - Pozivnica: `POST /admin/korisnici/novi` kreira korisnika bez lozinke + token `invite` (48 h) + email s linkom `/admin/lozinka/postavi/{token}` (isti ekran kao reset). Ponovno slanje pozivnice.

4. **Korisnici** (`app/routers/admin_users.py`)
   - `/admin/korisnici`: lista (ime, email, uloga, 2FA status, aktivan, zadnja prijava), novi (pozivnica), uredi (ime, uloga, aktivan), deaktiviraj (briše sesije), reset 2FA za drugog korisnika (owner+; korisnik pri sljedećoj prijavi mora ponovno postaviti; audit).
   - Pravila: owner ne može mijenjati ni deaktivirati superadmina; nitko ne može promijeniti vlastitu ulogu ni sebe deaktivirati; superadmin mora postojati barem jedan.
   - Pristup: superadmin i owner; salesperson dobiva 403.

5. **Profil** (`/admin/profil`): promjena lozinke (traži trenutnu; briše ostale sesije), ponovno postavljanje 2FA (traži trenutni TOTP kod), popis aktivnih sesija (IP maskiran, uređaj, vrijeme) + "Odjavi sve uređaje".

6. **Audit log**: zapiši `user.login`, `user.login_failed` (bez emaila — samo hash), `user.logout`, `user.2fa_setup`, `user.2fa_reset`, `user.password_change`, `user.password_reset`, `user.invite`, `user.update`, `user.deactivate`. Stranica `/admin/audit` (owner+): tablica s filterima po korisniku, akciji i datumu, paginacija.

7. **Admin layout**: dovrši `admin/base.html` — sidebar sa svim stavkama iz poglavlja 10 (stavke skrivene prema ulozi), gornja traka (ime korisnika, uloga, odjava), flash poruke, responsivan sidebar. Nepostojeće rute (vozila, upiti…) zasad vode na stranicu "U izradi — faza N". Zaštiti cijeli `/admin/*` osim prijave, 2FA i lozinka-ruta. `/admin` → dashboard placeholder (kartice s nulama; pravi u fazi 7). `noindex` meta na svim admin stranicama.

8. **Seed**: `seed --minimal` dodaje superadmina `admin@domena.com` s lozinkom iz `SEED_PASSWORD` (default `Promijeni-me-2026!`), **bez 2FA** (prva prijava demonstrira obavezno postavljanje). CLI: `python -m app.cli create-superadmin --email ... --password ...` i `python -m app.cli reset-2fa --email ...`.

9. **Testovi** (`tests/test_auth.py`, `tests/test_users.py`): prijava s krivom lozinkom daje istu poruku kao nepostojeći email; lockout nakon 5 pokušaja; prijava bez 2FA → redirect na postavljanje; postavljanje + provjera TOTP koda (pyotp u testu) → dashboard; kod za oporavak radi samo jednom; POST bez CSRF tokena → 403; `/admin/vozila` bez prijave → redirect; salesperson na `/admin/korisnici` → 403; reset lozinke tijek kroz `data/outbox/`; odjava svugdje poništava druge sesije; audit zapisi nastaju.

## Provjera prije završetka

- Playwright prolazak: prijava → prisilno postavljanje 2FA (unos koda iz tajne pyotp-om) → kodovi za oporavak → dashboard → profil → odjava → prijava s 2FA kodom. Screenshotovi `docs/screenshots/admin-prijava.png`, `admin-2fa-postavljanje.png`, `admin-korisnici.png` (desktop) i pregled da izgledaju uredno.
- `ruff check .` i `pytest` prolaze. Ažuriraj `CLAUDE.md` (faza 2 gotova, nove rute) i README (prijava, seed korisnici).
- Git commit: `Faza 2: autentikacija, 2FA, korisnici`.

## Ne raditi u ovoj fazi

Vozila, katalog, upite, newsletter, statistiku, postavke.

## Završni izvještaj faze

Što je napravljeno, popis ruta, pristupni podaci za demo, pretpostavke, poznati nedostaci, potvrda testova.
