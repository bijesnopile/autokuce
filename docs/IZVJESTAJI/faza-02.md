# Izvještaj — Faza 2: Autentikacija, 2FA, korisnici, admin okvir

Datum: 28.09.2026.

## Što je napravljeno

- **Email servis** (`app/services/email.py`): backendi `console`, `file` (`.eml` u `data/outbox/`,
  naziv = datum + subject), `brevo` (HTTP API, timeout 10 s, 1 retry); svako slanje u `email_log`
  (SHA-256 primatelja). Predlošci `emails/base.html|txt` (LOGO tekst ili logo slika, impressum, link na
  politiku privatnosti), `user_invite`, `password_reset`; slanje kroz `BackgroundTasks`.
- **Prijava** (`app/routers/admin_auth.py`, `app/services/auth.py`, `app/deps.py`): Argon2id, ista
  poruka za sve neuspjehe, lažna provjera za nepostojeći email, rate limit 10/min/IP, lockout 5 → 15 min
  (broji i 2FA kodove), odgoda 0,6 s. Međustanje u potpisanom kolačiću `ak_pending` (10 min).
- **Obavezna 2FA**: TOTP (pyotp) s QR kodom (data URI) i ključem za ručni unos, tajna šifrirana Fernetom,
  zaštita od ponovne upotrebe koda, 10 kodova za oporavak (hashirani, jednokratni, prikazani jednom).
  Sesija bez aktivne 2FA uvijek se preusmjerava na postavljanje.
- **Sesije na serveru** (tablica `sessions`, u bazi samo hash tokena), kolačić `session` HttpOnly,
  SameSite=Lax, Secure uz `HTTPS=true`, Path=/admin, 12 h; `last_seen_at` najviše 1× u 5 min;
  CSRF token se rotira pri prijavi; odjava i "odjavi sve uređaje".
- **Reset lozinke** (token 1 h) i **pozivnice** (48 h) — isti ekran; lozinka min 12 znakova + lista
  čestih lozinki; reset briše sve sesije.
- **Korisnici** (`/admin/korisnici`): lista, pozivnica, uređivanje, deaktivacija (briše sesije),
  ponovna aktivacija, reset 2FA, ponovno slanje pozivnice. Pravila: owner ne dira superadmina ni ne
  dodjeljuje ulogu superadmin; nitko ne mijenja vlastitu ulogu ni ne deaktivira sebe; uvijek barem
  jedan aktivni superadmin.
- **Profil** (`/admin/profil`): promjena lozinke (zatvara ostale sesije), ponovno postavljanje 2FA
  (uz trenutni kod), popis aktivnih sesija (maskiran IP, uređaj) + odjava sa svih uređaja.
- **Audit log** (`/admin/audit`, owner+): filteri korisnik/akcija/datum, paginacija 50, čitljive labele.
  Zapisi: `user.login`, `user.login_failed` (samo hash emaila), `user.logout`, `user.logout_all`,
  `user.2fa_setup`, `user.2fa_reset`, `user.recovery_code_used`, `user.password_change`,
  `user.password_reset`, `user.password_reset_request`, `user.password_set`, `user.invite`,
  `user.update`, `user.deactivate`.
- **Admin layout**: sidebar s ulogama (stavke skrivene prema matrici ovlasti), topbar s korisnikom i
  odjavom, flash poruke, responsivan sidebar (mobilni izbornik), `noindex`, 403 stranica u admin dizajnu.
  Cijeli `/admin/*` zaštićen osim prijave, 2FA i lozinka-ruta.
- **Seed/CLI**: `seed --minimal` dodaje `admin@domena.com` (superadmin, bez 2FA);
  `python -m app.cli create-superadmin` i `reset-2fa`.

## Rute

`GET/POST /admin/prijava`, `GET/POST /admin/prijava/2fa`, `GET/POST /admin/2fa/postavljanje`,
`POST /admin/odjava`, `POST /admin/odjava-svugdje`, `GET/POST /admin/lozinka/zaboravljena`,
`GET/POST /admin/lozinka/nova/{token}`, `GET/POST /admin/lozinka/postavi/{token}`,
`GET /admin/korisnici`, `GET/POST /admin/korisnici/novi`, `GET/POST /admin/korisnici/{id}`,
`POST /admin/korisnici/{id}/deaktiviraj|aktiviraj|reset-2fa|pozivnica`, `GET /admin/profil`,
`POST /admin/profil/lozinka`, `POST /admin/profil/2fa`, `GET /admin/audit`, `GET /admin`.

## Pristupni podaci za demo

`admin@domena.com` / `Promijeni-me-2026!` (ili `SEED_PASSWORD`) — prva prijava traži postavljanje 2FA.

## Provjera

- Playwright: prijava → prisilno postavljanje 2FA (kod iz tajne pyotp-om) → kodovi za oporavak →
  nadzorna ploča → korisnici → profil → audit → odjava → ponovna prijava s 2FA kodom. Bez grešaka u
  konzoli, bez vanjskih zahtjeva, mobilni prikaz bez horizontalnog skrola, sidebar radi na 390 px.
- Screenshotovi: `docs/screenshots/admin-prijava.png`, `admin-2fa-postavljanje.png`,
  `admin-korisnici.png` — pregledani, uredni. Ispravljeno: razmak kod oznake "(vi)", veličina naslova panela.
- `ruff check .` ✔, `ruff format --check .` ✔, `pytest`: **47 passed** (32 nova testa u
  `test_auth.py` i `test_users.py`).

## Pretpostavke

Zapisane u `docs/PRETPOSTAVKE.md` → odjeljak "Autentikacija i korisnici (faza 2)".

## Poznati nedostaci

- Rate limiter je u memoriji procesa (s 2 uvicorn workera efektivni limit je 2×) — napomena o Redisu u
  dokumentaciji (faza 8).
- Brevo backend testiran samo kroz kod (bez pravog API ključa); test s mockom dolazi u fazi 6/8.
