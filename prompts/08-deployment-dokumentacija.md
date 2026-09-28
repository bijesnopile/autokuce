# FAZA 8/8 — Deployment, backup, testovi, dokumentacija, završni pregled

## Kontekst

Faza 8 od 8. Prvo pročitaj `CLAUDE.md` i `docs/SPECIFIKACIJA.md` [ako je nema u `docs/`, kopiraj `prompts/SPECIFIKACIJA.md` u `docs/`] (posebno poglavlja 13, 14, 17, 18, 21, 22, 24). Provjeri stanje repozitorija (faze 1–7 gotove). Ne postavljaj pitanja; nedefinirano odluči sam i zabilježi u `docs/PRETPOSTAVKE.md`.

## Cilj faze

Projekt spreman za instalaciju po klijentu na VPS-u (Netcup, Docker, Caddy iza Cloudflarea), s backupom, kompletnom testnom suitom, dokumentacijom i završnim pregledom kvalitete. Na kraju: demo koji se pokreće s `docker compose up`.

## Zadaci

1. **Docker**
   - `Dockerfile`: multi-stage (`python:3.11-slim`), pinane ovisnosti, non-root korisnik `app`, `HEALTHCHECK` na `/zdravlje`, entrypoint koji čeka bazu, pokreće `alembic upgrade head`, `seed --minimal` (ili puni demo ako `DEMO_SEED=true`) i uvicorn s 2 workera. Bez dev alata u finalnoj slici.
   - `docker-compose.yml` (jedan klijent): `app` (env iz `.env`, volumeni `./data/media`, `./overrides`, `./data/backups`), `db` (`postgres:16`, volume, healthcheck, samo interna mreža), `caddy` (`Caddyfile` s `{$DOMAIN}`, automatski TLS, reverse proxy na `app:8000`, `encode gzip zstd`, sigurnosni headeri se ne dupliraju — ostaju u aplikaciji, cache za `/static` i `/media`). Dokumentiraj Cloudflare "Full (strict)" i opciju Cloudflare Origin certifikata umjesto Let's Encrypta (jer iza proxyja HTTP-01 ne prolazi bez DNS izazova — objasni i ponudi obje varijante u Caddyfileu).
   - `.dockerignore`. `.env.example` dopuni s `DOMAIN`, `DEMO_SEED`, `POSTGRES_PASSWORD`.
   - Provjera: `docker compose up --build` (ako je Docker dostupan u okruženju) → aplikacija radi s Postgresom, seed prolazi, `/zdravlje` 200 kroz Caddy na `http://localhost` (za lokalni test `DOMAIN=localhost` s `auto_https off`). Ako Docker nije dostupan, provjeri barem `docker build` sintaksu i zabilježi.

2. **Više klijenata na jednom VPS-u** (`deploy/`)
   - `deploy/caddy/docker-compose.yml` + `Caddyfile`: **jedan zajednički Caddy** na portovima 80/443, Docker mreža `web`, `import sites/*.caddy`.
   - `deploy/client-template/docker-compose.yml`: samo `app` + `db` s prefiksom imena (`${CLIENT}_app`), spojen na `web` mrežu, bez otvorenih portova.
   - `deploy/new-client.sh <ime> <domena> [--demo]`: kreira `clients/<ime>/` (compose iz predloška, `.env` s generiranim `SECRET_KEY`, `POSTGRES_PASSWORD`, `SEED_PASSWORD`, `DOMAIN`, `BASE_URL`, `HTTPS=true`, `TRUST_PROXY=true`, `APP_ENV=production`, `EMAIL_BACKEND=brevo` s praznim ključem i komentarom), mape `data/media`, `overrides`, `data/backups`, doda `deploy/caddy/sites/<ime>.caddy` i reloada Caddy, pokrene stack, ispiše podatke za prvu prijavu i checklistu iz `docs/ONBOARDING-KLIJENTA.md`. `deploy/remove-client.sh` (zaustavi, arhiviraj podatke, ukloni site — s potvrdom).
   - `deploy/update-all.sh`: povuče novu sliku, redom za svakog klijenta `up -d` + migracije, provjeri `/zdravlje`, u slučaju greške zaustavi i ispiši.

3. **Backup i vraćanje**
   - `deploy/backup.sh <ime|all>`: `pg_dump` (custom format) → gzip → šifriranje `age` (ili `gpg` ako `age` nije dostupan; javni ključ u `.env` `BACKUP_AGE_RECIPIENT`) → `rclone copy` na off-site (`BACKUP_RCLONE_REMOTE`, npr. Hetzner Storage Box ili S3) → lokalna i udaljena retencija 30 dana → provjera integriteta (`pg_restore --list` na dešifriranoj kopiji) → izlazni kod i log; ako je `STORAGE_BACKEND=local`, dodatno `rclone sync` media mape. Bez čistih lozinki u procesnoj listi (`PGPASSWORD` kroz `.pgpass` ili `--env-file`).
   - `deploy/restore.sh <ime> <datoteka>`: dešifriranje, `pg_restore` u novu bazu, zamjena, provjera `/zdravlje`; korak-po-korak upute i **test vraćanja** kao dio dokumentacije (provjeri da skripta radi na lokalnom Postgres kontejneru ako je Docker dostupan).
   - `deploy/crontab.example`: backup 03:00, maintenance 04:00 (`docker compose exec app python -m app.cli maintenance`), tjedni `update-all` isključen po defaultu (komentar).

4. **Kvaliteta i testovi**
   - `pyproject.toml` s ruff konfiguracijom; `scripts/check.py`: `ruff check .`, `ruff format --check .`, `pytest -q`, `pip-audit` (upozorenje ne ruši, kritični nalaz ruši). Sve mora prolaziti.
   - Dopuni testove do pokrivenosti popisa u poglavlju 21 specifikacije (prođi stavku po stavku i dodaj što nedostaje). Dodaj `tests/test_security_headers.py` (CSP bez `unsafe-inline` za skripte, HSTS samo uz `HTTPS=true`, `X-Frame-Options`), `tests/test_no_external_resources.py` (svi javni templatei + email predlošci), `tests/test_placeholders.py` (nijedan template ne sadrži hardkodirane podatke tvrtke — grep za `@` adrese, `+385`, `d.o.o.` u `app/templates` osim kroz `site`).
   - Playwright skripta `scripts/screenshots.py`: automatski generira sve screenshotove iz prethodnih faza (desktop 1440×900 i mobile 390×844) za javne i admin stranice s demo podacima, u `docs/screenshots/`. Pokreni je i **pregledaj svaki screenshot**: uredan raspored, bez preklapanja/odsječenog teksta/horizontalnog skrola, dosljedne boje i razmaci, čitljiva tipografija, placeholderi na mjestu. Ispravi što ne valja i ponovi.
   - Ručna provjera "kao klijent": otvori demo, pretraži vozilo, pošalji upit, prijavi se na newsletter, prijavi se u admin (2FA setup), obradi upit, pošalji kampanju. Sve bez greške.

5. **Dokumentacija (hrvatski)** — prema poglavlju 22
   - `README.md` finalno: što je ovo (2 odlomka), brzi start lokalno (3 koraka), brzi start Docker, tablica env varijabli, struktura projekta, kako dodati tip vozila / polje / jezik / vrstu upita, deployment novog klijenta (korak po korak), ažuriranje, backup/restore, overrides, sigurnost i GDPR sažetak s linkovima na docs, premium roadmap, licenca (placeholder "Sva prava pridržana — [IME PODUZEĆA VLASNIKA PLATFORME]").
   - `CLAUDE.md` finalno (pravila iz specifikacije, sve faze označene gotovima, "kako raditi promjene" upute).
   - `docs/ARHITEKTURA.md` (dijagram komponenti u tekstu/ASCII-u, tok requesta, model podataka, odluke i razlozi, put do višejezičnosti sadržaja i feedova prema portalima), `docs/SIGURNOST.md` (model prijetnji, implementirane mjere po checklisti iz poglavlja 13, što ostaje: pentest, WAF pravila, Redis limiter, HEIC, rotacija tajni, plan za incidente), `docs/GDPR.md` (uloge, pravne osnove, rokovi čuvanja i kako su automatizirani, popis podizvršitelja s lokacijama i osnovama prijenosa, postupak zahtjeva ispitanika u 30 dana, postupak incidenta i prijava AZOP-u u 72 h, napomena o backupima), `docs/ONBOARDING-KLIJENTA.md` (checklista: domena i Cloudflare DNS/proxy, Brevo verifikacija domene SPF/DKIM/DMARC, unos podataka tvrtke i logotipa, pravni dokumenti pregledani od pravnika + verzija, potpisan ugovor o obradi, uvoz vozila, testni upit i newsletter, provjera backupa, predaja pristupnih podataka i 2FA), `docs/PREMIUM-ROADMAP.md` (stavke iz poglavlja 23 s kratkim opisom implementacije i ovisnostima), `docs/pravno/UGOVOR-O-OBRADI-PODATAKA.md` (predložak čl. 28 GDPR s poljima `[NAZIV AUTOKUĆE]`, `[NAZIV OPERATORA]` i oznakama `[PRAVNIK: provjeriti]`), `docs/PRETPOSTAVKE.md` sređen i kompletan.
   - `overrides/README.md` provjeri s konkretnim primjerom (override `public/home.html` + `custom.css`).

6. **Završni pregled**
   - Prođi **Definition of done** iz poglavlja 24 stavku po stavku i označi u izvještaju što je ispunjeno; sve što nije, navedi izričito s razlogom.
   - Sigurnosna checklista (13) i GDPR checklista (14): tablica "zahtjev → gdje je implementirano (datoteka/ruta) → test koji to pokriva".
   - Git commit: `Faza 8: deployment, backup, testovi, dokumentacija`. Tag `v0.1.0-mvp`.

## Završni izvještaj (zadnja poruka)

1. Što je izgrađeno (sažetak funkcionalnosti po području).
2. Kako pokrenuti demo lokalno i u Dockeru (točne naredbe) i pristupni podaci (`admin@domena.com` / lozinka; prva prijava traži 2FA).
3. Kako instalirati novog klijenta na VPS-u (5 koraka).
4. Tablica Definition of done s statusima.
5. Tablica sigurnost/GDPR → implementacija → test.
6. Popis pretpostavki (iz `docs/PRETPOSTAVKE.md`).
7. Poznati nedostaci i preporučeni sljedeći koraci (uključujući što treba pravnik, pentest, Brevo/Cloudflare podešavanje po klijentu).
8. Popis screenshotova u `docs/screenshots/`.
