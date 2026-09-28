# Izvještaj — Faza 8: Deployment, backup, testovi, dokumentacija

Datum: 28.09.2026.

## Što je napravljeno

**Docker**
- `Dockerfile`: `python:3.11-slim`, multi-stage (venv s pinanim ovisnostima → runtime bez dev alata),
  korisnik `app` (uid 1000), `fonts-dejavu-core`, `HEALTHCHECK` na `/zdravlje`, uvicorn s 2 workera,
  `--no-access-log`, `--no-server-header`.
- `docker/entrypoint.sh`: SECRET_KEY (generira se i čuva ako nije zadan), `app.cli wait-db` (novo),
  `app.cli migrate`, `app.seed --if-empty` (novo: seed samo na praznoj bazi; `--minimal` ili demo uz
  `DEMO_SEED=true`), zatim uvicorn.
- `docker-compose.yml` (app + postgres:16 + caddy + jednokratni `init` za vlasništvo nad `./data`;
  baza samo na internoj mreži; rotacija logova), `Caddyfile` (`{$DOMAIN}`, `encode zstd gzip`, cache
  statike, bez dupliciranja sigurnosnih headera, komentirane varijante TLS-a iza Cloudflarea),
  `.dockerignore`, `.env.example` dopunjen (`DEMO_SEED`, `DOMAIN`, `POSTGRES_*`, `AUTOKUCA_IMAGE`,
  `WEB_CONCURRENCY`, `BACKUP_*`).

**Više klijenata (`deploy/`)**
- `caddy/` — zajednički Caddy (80/443, mreža `web`, `import sites/*.caddy`, snippet `(autokuca)`),
  `Dockerfile.cloudflare` za Let's Encrypt preko DNS izazova, `certs/` za Origin certifikate.
- `client-template/docker-compose.yml` — app + db s imenima `<ime>_app`/`<ime>_db`, bez portova.
- `new-client.sh <ime> <domena> [--demo] [--admin-email]` — `.env` s generiranim tajnama, mape,
  site datoteka (Origin cert ako postoji), pokretanje, čekanje healthchecka, reload Caddyja, ispis
  pristupa i checkliste. `remove-client.sh` (potvrda, zadnji backup, `down -v`, arhiva, uklanjanje
  site datoteke). `update-all.sh` (git pull + build ili `--pull`, `:previous` slika, backup, `up -d`,
  čekanje zdravlja, zaustavljanje kod prve greške). `lib.sh` — zajedničke funkcije.
- `backup.sh <ime|all>` — pg_dump u kontejneru baze → gzip → provjera (`gzip -t`, `pg_restore --list`)
  → age/gpg → rclone → retencija 30 dana (lokalno i off-site) → media sync uz lokalnu pohranu →
  `last-success.txt`; odbija nešifrirani backup. `restore.sh <ime> <datoteka>` — dešifriranje, provjera,
  potvrda, vraćanje u novu bazu, zamjena, start, čekanje `/zdravlje`. `crontab.example`,
  `backup.env.example`.

**Kvaliteta i testovi**
- `scripts/check.py`: ruff, `ruff format --check`, pytest, pip-audit (kritično = ranjivost u
  produkcijskim ovisnostima).
- Novi testovi: `test_security_headers.py` (headeri na svim vrstama odgovora, CSP prema specifikaciji,
  CSP s konfiguriranim hostovima, HSTS i Secure kolačići samo uz HTTPS, zastavice admin kolačića, noindex,
  bez inline skripti i event handlera, health bez detalja, API 100/min, **svaka POST/PUT/PATCH/DELETE ruta
  ima CSRF**), `test_no_external_resources.py` (13 javnih stranica, detalj svake vrste vozila s galerijom,
  YouTube, CSS/JS, **svih 5 email predložaka** i kartica vozila u emailu), `test_placeholders.py`
  (nijedan od 66 predložaka nema hardkodirane podatke tvrtke; s pravim podacima u postavkama nijedan
  placeholder ne ostaje ni na stranicama ni u emailu), `test_overrides.py` (override naslovnice +
  `custom.css`; read-only overrides ne ruše start). Dodano: TOTP tajna šifrirana u bazi, privola
  neoznačena, `wait-db`, seed `--if-empty`, CLI održavanje jednom dnevno.
- Prošao popis iz poglavlja 21 specifikacije — svaka stavka ima test (tablica u `docs/SIGURNOST.md` i
  `docs/GDPR.md`).
- `scripts/screenshots.py`: vlastita instanca (privremena baza, demo seed, outbox) → pretraga, upit s
  mobitela, newsletter prijava i potvrda iz emaila, prijava s postavljanjem 2FA, obrada upita (status +
  bilješka), kampanja s umetnutim vozilom (testni email, slanje, izvještaj), GDPR pretraga → 34
  screenshotova (desktop 1440×900, mobitel 390×844) uz automatsku provjeru HTTP statusa, horizontalnog
  skrola i grešaka u konzoli.

**Dokumentacija**: README (finalno), CLAUDE.md (finalno, "kako raditi promjene"), `docs/ARHITEKTURA.md`,
`docs/SIGURNOST.md`, `docs/GDPR.md`, `docs/ONBOARDING-KLIJENTA.md`, `docs/PREMIUM-ROADMAP.md`,
`docs/pravno/UGOVOR-O-OBRADI-PODATAKA.md`, `docs/PRETPOSTAVKE.md` (faza 8 + "Otvoreno"),
`overrides/README.md` (lokacija po klijentu, kada treba restart, test primjera).

## Pronađeno i ispravljeno tijekom provjere

| Nalaz | Ispravak |
|---|---|
| `vehicles.euro_norm` `VARCHAR(10)`, vrijednost `euro6d_temp` 11 znakova — **PostgreSQL odbija** demo seed (SQLite ne provjerava duljine) | migracija `0002` (20 znakova); suita pokrenuta i na PostgreSQL-u |
| `overrides/` je u Dockeru read-only, a start je radio `mkdir overrides/static` → kontejner bi se srušio | `mkdir` u try/except, mount samo ako mapa postoji; test |
| Docker restart bi ponovno dodavao marke koje je klijent obrisao (seed pri svakom startu) | `seed --if-empty`; test |
| `LocalStorage` na Windowsu povremeno "Path traversal attempt" u paralelnom seedu (`Path.resolve()` u utrci) | leksička provjera putanje (`os.path.abspath`) |
| Cron održavanje i nit u aplikaciji mogli su oba raditi isti dan | CLI koristi istu atomsku oznaku dana (`--force` za ručno) |
| API rate limit 60/min umjesto 100/min iz specifikacije | 100/min, i za admin editor API; test |
| Mobilna traka "Nazovi / Pošalji upit" prekrivala gumb za slanje forme | traka se skriva dok je forma na ekranu ili u fokusu |
| Audit log: "settings #None", detalji kao Python lista | prikaz bez `#None`, liste spojene zarezom |
| Screenshot skripta: lijene slike bez sadržaja, smooth scroll pomicao zaglavlje, kampanja snimljena dok se šalje | čekanje učitavanja slika, trenutni skrol, čekanje kraja slanja |

## Provjera

- `python scripts/check.py`: ruff ✔, format ✔ (98 datoteka), **pytest 281 passed** (176 test funkcija,
  19 datoteka), pip-audit ✔ (0 nalaza). Ista suita na **PostgreSQL 16**: 281 passed.
- `python scripts/screenshots.py`: svi tijekovi prošli, 34 slike, bez horizontalnog skrola i grešaka u
  konzoli; svaka slika pregledana.
- **Backup i vraćanje** (`AK_PG_LOCAL=1`, PostgreSQL 16, GPG): migracije + puni demo na PostgreSQL-u →
  `backup.sh all` (dump 19 tablica s podacima, provjera dešifrirane kopije, stari backup od 40 dana
  obrisan) → bez ključa backup odbijen → brisanje upita i promjena naziva tvrtke → `restore.sh --yes` →
  shema `0002`, 16 vozila / 10 upita / 15 pretplatnika i naziv tvrtke vraćeni, stara baza sačuvana.
- `bash -n` za sve `deploy/*.sh`, `sh -n` za entrypoint.
- **Nije izvedeno**: `docker build` / `docker compose up` (Docker nije dostupan) — `docs/PRETPOSTAVKE.md`
  → "Otvoreno" s točnim koracima provjere.

## Pretpostavke

`docs/PRETPOSTAVKE.md` → "Deployment, backup i provjera (faza 8)" i "Otvoreno".
