# Sigurnost

Sigurnosni model platforme za verziju v0.1.0: od čega se branimo, što je implementirano (s
datotekom i testom za svaki zahtjev iz specifikacije, pogl. 13) i što još treba napraviti.

## 1. Model prijetnji

**Imovina:** podaci kupaca (upiti, pretplatnici), računi administracije, sadržaj oglasa i ugled
autokuće (stranica, email domena), dostupnost stranice, tajne (`SECRET_KEY`, API ključevi, backup ključ).

| Prijetnja | Tko / kako | Glavne mjere |
|---|---|---|
| Preuzimanje admin računa | pogađanje/credential stuffing, phishing lozinke | Argon2id, min. 12 znakova + popis čestih lozinki, **obavezna 2FA (TOTP)**, lockout 5/15 min, rate limit 10/min, ista poruka za sve greške |
| Krađa sesije | XSS, presretanje | HttpOnly + Secure + SameSite=Lax kolačić, `Path=/admin`, sesija na serveru (hash tokena), 12 h, odjava sa svih uređaja, strogi CSP bez inline skripti, HSTS |
| CSRF | zlonamjerna stranica šalje formu | CSRF token na **svakom** POST-u (ovisnost na razini routera), SameSite=Lax |
| XSS | unos u opise, kampanje, stranice, upite | Jinja autoescape, nh3 allowlist za rich-text, CSP `script-src 'self'`, bez inline event handlera |
| SQL injection | parametri filtera/pretrage | samo SQLAlchemy ORM/parametrizirani upiti |
| Zlonamjerni upload | skripta/SVG/polyglot/"decompression bomb" kao slika | provjera sadržaja Pillowom, samo JPEG/PNG/WebP, limiti veličine i piksela, re-enkodiranje u WebP (briše EXIF/GPS/skriveni sadržaj), nasumična imena, pohrana izvan webroota |
| Spam i zlouporaba formi | botovi, masovni upiti, email bombing kroz newsletter | Turnstile, honeypot, vremenska provjera (< 3 s), rate limit po IP-u i po emailu, double opt-in, ista poruka (bez otkrivanja postoji li adresa) |
| Enumeracija korisnika | login / zaboravljena lozinka | iste poruke i isto vrijeme (lažna Argon2 provjera), odgoda 0,6 s |
| Curenje podataka | logovi, greške, backupi, health endpoint | bez access loga, maskirani emailovi/IP-ovi, stack trace samo u razvoju, šifrirani backupi, `/zdravlje` bez detalja |
| Open redirect | `?next=` nakon prijave | samo relativne `/admin` putanje |
| Iskorištavanje ranjivih ovisnosti | poznati CVE | pinane verzije, `pip-audit` u `scripts/check.py` |
| Napad na infrastrukturu | skeniranje portova, DoS | samo Caddy (80/443) izložen, baza na internoj mreži, Cloudflare proxy/WAF, opcionalni `ADMIN_IP_ALLOWLIST` |
| Zaobilaženje Cloudflarea | izravni pristup IP-u servera uz lažni `CF-Connecting-IP` | **firewall: 80/443 samo s Cloudflare IP raspona** (vidi 4.) |

## 2. Implementirane mjere (spec pogl. 13) → gdje → test

| Zahtjev | Implementacija | Test |
|---|---|---|
| Argon2id; min. 12 znakova; 100 najčešćih lozinki | `app/security.py` (`hash_password`, `validate_password`, `COMMON_PASSWORDS` — 104 stavke) | `test_auth.py::test_weak_password_rejected_on_reset` |
| Lockout 5 pokušaja / 15 min | `app/services/auth.py` | `test_auth.py::test_lockout_after_five_failed_attempts` |
| Rate limit: login 10/min, forme 5/10 min, API 100/min | `app/security.py` (`RateLimiter`, `rate_limit`, `check_rate_limit`); rute u `routers/` | `test_auth.py::test_login_rate_limit`, `test_inquiries.py::test_rate_limit_per_ip`, `::test_rate_limit_per_email`, `test_newsletter.py::test_honeypot_and_rate_limit`, `test_security_headers.py::test_public_api_rate_limit_100_per_minute` |
| 2FA (TOTP) obavezna za sve | `routers/admin_auth.py`, `deps.py` (`TwoFactorSetupRequired`) | `test_auth.py::test_login_without_2fa_redirects_to_forced_setup`, `::test_session_without_2fa_is_forced_to_setup`, `::test_full_2fa_setup_flow_reaches_dashboard`, `::test_totp_login_and_replay_protection` |
| Kodovi za oporavak hashirani, jednokratni | `app/security.py`, `services/auth.py` | `test_auth.py::test_recovery_code_works_only_once` |
| TOTP tajna šifrirana ključem iz `SECRET_KEY` (Fernet) | `app/security.py` (`encrypt_secret`/`decrypt_secret`) | `test_auth.py::test_totp_secret_is_encrypted_at_rest` |
| Sesije na serveru; HttpOnly, Secure (HTTPS), SameSite=Lax; 12 h; nova sesija pri prijavi; odjava svugdje | `services/auth.py`, `models.UserSession` | `test_security_headers.py::test_admin_session_cookie_flags`, `::test_hsts_and_secure_cookies_only_with_https`, `test_auth.py::test_expired_session_redirects_to_login`, `::test_logout_everywhere_invalidates_other_sessions` |
| CSRF na svakom POST-u (i upload) | `deps.py::csrf_protect` na svakom routeru; `security.verify_csrf` | `test_auth.py::test_post_without_csrf_is_forbidden` |
| Sigurnosni headeri: CSP (prema specifikaciji), nosniff, X-Frame-Options DENY, Referrer-Policy, Permissions-Policy, HSTS samo uz HTTPS | `app/main.py` (`build_csp`, `SecurityHeadersMiddleware`) | `test_security_headers.py` (svi) |
| Bez inline skripti | templatei, `static/js/*.js` | `test_security_headers.py::test_no_inline_scripts_in_rendered_pages`, `::test_templates_have_no_inline_event_handlers_or_javascript_urls` |
| Upload: Pillow provjera, JPEG/PNG/WebP, `MAX_UPLOAD_MB`, `MAX_IMAGES_PER_VEHICLE`, WebP 400/1000/1600, bez EXIF-a, nasumična imena, izvan webroota; SVG/HTML/PDF zabranjeni; logo isto (2 MB) | `services/images.py`, `services/storage.py`, `/media` ruta | `test_images.py` (svi), `test_temelj.py::test_media_path_traversal_rejected` |
| Sanitizacija rich-texta (nh3), autoescape, ORM | `security.clean_html`, `newsletter.clean_campaign_html` | `test_newsletter.py::test_campaign_html_is_sanitized`, `test_pages.py::test_page_edit_increments_version_and_sanitizes` |
| Tajne samo iz `.env`; produkcija odbija start bez `SECRET_KEY` | `config.py::validate_for_startup` | `test_temelj.py::test_production_requires_secret_and_postgres` |
| Logovi bez osobnih podataka; audit svih admin akcija (tko, što, kada, IP) | `services/audit.py`, `services/email.py` (maskiranje), uvicorn `--no-access-log` | `test_auth.py::test_audit_entries_are_created`, `test_privacy.py::test_gdpr_delete_requires_confirmation_and_erases` |
| Zaštita od enumeracije, odgode na loginu | `routers/admin_auth.py` | `test_auth.py::test_wrong_password_same_message_as_unknown_email`, `::test_forgot_password_unknown_email_same_message_no_email` |
| Health bez osjetljivih podataka; `/admin` noindex + Disallow; `ADMIN_IP_ALLOWLIST` | `routers/public.py`, `routers/seo.py`, `main.py` (`AdminIPAllowlistMiddleware`) | `test_security_headers.py::test_health_endpoint_reveals_nothing`, `::test_admin_pages_are_noindex_and_not_cached`, `test_public.py::test_robots_txt`, `test_auth.py::test_admin_ip_allowlist_middleware` |
| Open redirect | `services/auth.py::safe_next` | `test_auth.py::test_open_redirect_is_blocked` |
| `pip-audit` u `scripts/check.py`; Dockerfile non-root, multi-stage, pinane verzije | `scripts/check.py`, `Dockerfile` | `python scripts/check.py` (Docker slika nije izgrađena lokalno — vidi PRETPOSTAVKE "Otvoreno") |
| Bez vanjskih resursa | templatei, email predlošci, `static/` | `test_no_external_resources.py` |

## 3. Tajne i ključevi

| Tajna | Gdje | Rotacija |
|---|---|---|
| `SECRET_KEY` | `clients/<ime>/.env` (generira `new-client.sh`) | promjena poništava sve sesije i CSRF tokene **i čini postojeće 2FA tajne nečitljivima** (šifrirane su tim ključem) → nakon rotacije za svakog korisnika `python -m app.cli reset-2fa --email …` i ponovno postavljanje 2FA |
| `POSTGRES_PASSWORD` | `.env` | `ALTER USER autokuca PASSWORD '…'` u bazi + `.env` + restart |
| `BREVO_API_KEY`, Turnstile, S3 ključevi | `.env` | u sučelju pružatelja, zatim `.env` + restart |
| Backup ključ (age/GPG) | javni na serveru, **privatni izvan servera** | novi par ključeva; stari privatni ključ čuvati dok postoje stari backupi (30 dana) |
| Cloudflare Origin certifikat | `deploy/caddy/certs/` (izvan gita) | u Cloudflareu, 15 godina |

## 4. Preporuke za server (VPS)

- SSH samo ključem (`PasswordAuthentication no`), bez root prijave, `fail2ban`, automatske sigurnosne
  nadogradnje (`unattended-upgrades`).
- Firewall (`ufw`): 22 samo s poznatih IP-ova; 80/443 **samo s Cloudflare IP raspona**
  (<https://www.cloudflare.com/ips/>) — inače netko može zaobići Cloudflare i lažirati
  `CF-Connecting-IP` (utječe na rate limit i zapis IP-a uz privolu).
- Cloudflare: SSL/TLS "Full (strict)", "Always Use HTTPS", minimalni TLS 1.2, WAF managed rules,
  rate limiting pravilo za `/admin/prijava` i `/upit`, Bot Fight Mode po potrebi.
- Docker: kontejneri bez `--privileged`, aplikacija kao korisnik `app` (uid 1000), baza bez otvorenih portova.

## 5. Što ostaje (izvan MVP-a ili izvan koda)

- **Penetracijski test** prije prvog pravog klijenta (vanjski ispitivač) i nakon većih promjena.
- **WAF pravila** u Cloudflareu po klijentu (gore) — konfiguracija, ne kod.
- **Rate limiter u memoriji** vrijedi po workeru (2 workera → efektivno do 2× limit). Za više workera ili
  više servera: Redis (npr. `limits` biblioteka) — sučelje `RateLimiter` je izolirano u `app/security.py`.
- **HEIC/HEIF** (fotografije s iPhonea) nisu podržane — prodavač ih mora izvesti kao JPEG. Dodavanje:
  `pillow-heif` + dopuštanje formata u `services/images.py`.
- **Šifriranje backupa** je implementirano (age/gpg), ali upravljanje ključem (gdje je privatni ključ,
  tko mu ima pristup) je organizacijska mjera operatera.
- **Rotacija tajni** je ručna (gore); nema automatske rotacije ni ponovnog šifriranja 2FA tajni.
- **Plan za incidente**: postupak u `docs/GDPR.md` → 7; kontakt lista i uvježbavanje su na operateru.
- **Nadzor dostupnosti** (uptime monitor na `/zdravlje`, npr. Uptime Kuma/Better Stack) i obavijest
  kad backup ne uspije (`data/backups/last-success.txt` + cron `MAILTO`).
- **CSP report-uri** i centralno praćenje grešaka (npr. self-hosted GlitchTip) — nije uključeno.
- **Retencija logova 30 dana** je po veličini (Docker `json-file` 5 × 10 MB); za strogi vremenski rok
  koristiti `journald` driver s `MaxRetentionSec=30day`. Logovi ne sadrže osobne podatke.
