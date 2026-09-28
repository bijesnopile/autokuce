# Arhitektura

## 1. Pregled

Jedna aplikacija (FastAPI + Jinja2, server-side rendering) poslužuje javnu stranicu i administraciju
jedne autokuće. Svaki klijent ima **vlastitu instancu**: kontejner aplikacije, PostgreSQL bazu, mapu sa
slikama i `overrides/`. Svi klijenti dijele istu Docker sliku i jedan Caddy na istom VPS-u.

```
                       Internet (posjetitelji, administratori)
                                     │  HTTPS
                     ┌───────────────▼────────────────┐
                     │ Cloudflare (DNS, proxy, WAF,    │── Turnstile (anti-spam, opcionalno)
                     │ TLS "Full (strict)")            │
                     └───────────────┬────────────────┘
                                     │  HTTPS (Origin cert ili Let's Encrypt)
 VPS (Netcup) ───────────────────────┼──────────────────────────────────────────────────
                     ┌───────────────▼────────────────┐
                     │ Caddy (deploy/caddy)            │  jedini s otvorenim portovima 80/443
                     │ sites/<klijent>.caddy           │  gzip/zstd, cache /static /media
                     └──────┬──────────────────┬──────┘
             Docker mreža `web`                │
          ┌─────────────────▼───────┐   ┌──────▼──────────────────┐
          │ klijentA_app (uvicorn×2)│   │ klijentB_app            │   … N klijenata
          │ FastAPI + Jinja2        │   │                         │
          └───┬─────────┬───────────┘   └──────┬──────────────────┘
   interna    │         │ ./data/media, ./overrides (bind mount)
   mreža      │         │
          ┌───▼───────┐ │                      ┌─────────────┐
          │klijentA_db│ │                      │klijentB_db  │
          │Postgres 16│ │                      └─────────────┘
          └───────────┘ │
                        ├──► Brevo API (email: obavijesti, newsletter)
                        ├──► S3/R2 (slike, ako STORAGE_BACKEND=s3)
                        └──► Umami (analitika bez kolačića, opcionalno)

 cron: 03:00 deploy/backup.sh all → pg_dump → gzip → age/gpg → rclone (off-site)
       04:00 održavanje (retencija) — i u aplikaciji (MAINTENANCE_IN_APP)
```

Lokalni razvoj: `python run.py` → isti kod sa SQLite bazom (`data/app.db`), emailovi u `data/outbox/`.

## 2. Tok zahtjeva

```
Caddy → uvicorn → ASGI middleware (izvana prema unutra):
  RealIPMiddleware          pravi IP iz CF-Connecting-IP / X-Forwarded-For (samo uz TRUST_PROXY)
  SecurityHeadersMiddleware CSP, HSTS, X-Frame-Options…, cache headeri, noindex za /admin
  ErrorPageMiddleware       dizajnirana 500 stranica (s headerima), stack trace samo u razvoju
  AdminIPAllowlistMiddleware opcionalno: /admin samo s dopuštenih IP-ova
  SessionMiddleware (st)    potpisani kolačić: CSRF token, flash poruke, dedup pregleda
→ router (public, seo, admin_*):
  ovisnosti: get_db → get_current_user / require_permission("…") → csrf_protect (router-level)
  handler: validacija forme → servis (app/services/*) → SQLAlchemy → audit.log(...)
  → render(request, "…html", ctx)  (Jinja: overrides/templates → app/templates; globali site, _(), csrf_token)
  → PRG: flash + 303 redirect  |  BackgroundTasks: slanje emailova nakon odgovora
```

Javni `POST /upit`: CSRF → honeypot → vremenska provjera → Turnstile → rate limit (IP, hash emaila)
→ validacija → spremanje s privolom → email dealeru (pozadinski) → 303 s porukom zahvale.

Newsletter kampanja: admin → "Pošalji" → zasebna nit s vlastitom DB sesijom → serije od 50 (pauza 1 s)
→ zapis po primatelju (`campaign_deliveries`) → personalizirana poveznica za odjavu + `List-Unsubscribe`.

## 3. Model podataka

```
users ─┬─< sessions            (hash tokena, istek, maskirani IP)
       ├─< auth_tokens         (pozivnica, reset lozinke — hash tokena)
       ├─< audit_log           (tko, akcija, objekt, detalji bez podataka kupaca, IP)
       ├─< pages.updated_by    (5 CMS stranica, verzija)
       └─< campaigns.created_by

makes ─< vehicle_models ─< vehicles >─ users (created_by)
                            ├─< vehicle_images       (file_key, sort_order, alt, dimenzije)
                            ├─< vehicle_slug_history (301 sa starih URL-ova)
                            ├─< vehicle_views        (dan, broj — bez osobnih podataka)
                            └─< inquiries >─ users (assigned_to)
                                   └─< inquiry_notes >─ users

subscribers ─< campaign_deliveries >─ campaigns
settings (ključ → vrijednost: podaci tvrtke, boje, tekstovi, verzija politike…)
email_log (hash primatelja, predložak, status)
```

Ključne odluke u modelu:

- **Zajednička polja vozila su kolone** (marka, model, cijena, km, gorivo…) — filtriranje i sortiranje
  u SQL-u; **polja specifična za vrstu** su u JSON-u `vehicles.attributes`, opis u
  `app/vehicle_schema.py` (jedini izvor istine: forma, validacija, prikaz, filteri).
- **Statusi, uloge i vrste su string konstante** (`models.py`), ne DB enumi — nova vrijednost ne treba
  migraciju tipa.
- **Datumi su naivni UTC** (prenosivo SQLite ↔ PostgreSQL); prikaz u `Europe/Zagreb` kroz filtere.
- `inquiries.extra` (JSON) čuva polja budućih vrsta upita (financiranje, zamjena) bez migracije.
- Pretplatnik nakon odjave ostaje samo kao `email_hash` (lista zabrane), `email = NULL`.
- Migracije: Alembic (`migrations/versions/`), `render_as_batch` za SQLite; test
  `test_migrations_match_models` jamči da modeli i migracije odgovaraju.

## 4. Slojevi koda

| Sloj | Mjesto | Pravilo |
|---|---|---|
| Konfiguracija | `app/config.py` | sve iz env varijabli; produkcija odbija nesigurne postavke |
| Rute | `app/routers/` | tanke: parsiranje forme, ovlasti, poziv servisa, render/redirect |
| Servisi | `app/services/` | poslovna logika (vozila, upiti, newsletter, statistika, održavanje, email, slike, pohrana) |
| Prikaz | `app/templates/`, `app/templating.py` | Jinja2 autoescape, makroi, globali `site`/`_()`; bez inline JS-a |
| Statika | `app/static/` | vlastiti CSS (design tokeni) i vanilla JS, bez build koraka i CDN-a |
| Sigurnost | `app/security.py`, `app/deps.py`, `app/main.py` | hashiranje, tokeni, CSRF, rate limit, headeri |
| CLI | `app/cli.py`, `app/seed.py` | migracije, superadmin, 2FA reset, održavanje, seed |

## 5. Odluke i razlozi

| Odluka | Razlog |
|---|---|
| SSR (Jinja2) umjesto SPA | SEO bez dodatnog posla, brzo na slabim mobitelima, jednostavan CSP, manje koda |
| Bez CSS/JS frameworka i build koraka | nema ovisnosti o CDN-u i npm lancu; dovoljno za opseg; lako mijenjati po klijentu |
| Jedna instanca po klijentu (ne multi-tenant) | izolacija podataka (GDPR, ugovor o obradi po klijentu), jednostavan backup/brisanje klijenta, prilagodbe preko `overrides/` |
| Sync SQLAlchemy | jednostavnije; promet po klijentu je mali; FastAPI izvodi sync rute u threadpoolu |
| Sesije na serveru za admin, potpisani kolačić za javne forme | opoziv sesija (odjava svugdje, deaktivacija), a javni dio bez stanja na serveru |
| In-memory rate limiter | dovoljno za 2 workera po klijentu; Redis kad zatreba (SIGURNOST.md) |
| Slike u WebP (400/1000/1600) | manji promet, `srcset`, uklanjanje metapodataka re-enkodiranjem |
| Pohrana `local` ili `s3` iza istog sučelja | mali klijenti na disku VPS-a (backup rcloneom), veći na R2/Hetzner Object Storage s CDN-om |
| Održavanje u aplikaciji + CLI | retencija radi i kad operater zaboravi cron; atomska zaštita od dvostrukog izvođenja |
| Caddy iza Cloudflarea | automatski TLS, jednostavna konfiguracija po klijentu (`sites/*.caddy`) |

## 6. Put do višejezičnosti sadržaja

Sučelje je već prevodivo: svi tekstovi idu kroz `_()` (ključ = hrvatski tekst), prijevodi u
`app/i18n/<jezik>.json`, `LANGUAGE` u env-u. Za **sadržaj** (opisi vozila, stranice, kampanje):

1. **Model**: tablica prijevoda `translations(entity_type, entity_id, field, lang, value)` — bez
   mijenjanja postojećih tablica, radi za vozila, stranice i postavke (hero tekst, podnožje). Alternativa
   za 1–2 jezika: kolone `description_en`, `title_en` (jednostavnije, ali migracija po jeziku).
2. **URL-ovi**: prefiks jezika (`/en/vozila/...`), hrvatski ostaje bez prefiksa; `hreflang` i
   `<link rel="alternate">` u `public/base.html` (mjesto je već predviđeno), sitemap po jeziku.
3. **Odabir jezika**: iz URL-a (ne iz kolačića — SEO i dijeljivi linkovi); `_()` dobiva jezik iz
   `request.state`.
4. **Admin**: kartice po jeziku u editoru; nedostaje li prijevod, prikazuje se hrvatski.
5. **Specifikacije** se prevode kroz `_()` (labele i opcije su u `vehicle_schema.py`), pa ne trebaju
   prijevod po vozilu.

## 7. Put do XML feedova prema portalima (Njuškalo, Index oglasi, mobile.de, AutoScout24)

1. Novi router `app/routers/feeds.py`: `GET /feed/<portal>.xml?token=…` (tajni token po portalu u
   postavkama; portali povlače feed periodično) ili push preko API-ja portala gdje postoji.
2. Mapiranje po portalu u `app/services/feeds/<portal>.py`: naša polja (`vehicle_schema.py`) → šifrarnici
   portala (marke/modeli, gorivo, karoserija, oprema). Šifrarnici su najveći posao — tablica
   `portal_mappings(portal, our_code, their_code)` uređivana u adminu.
3. Slike: apsolutni URL-ovi na `/media/..._1600.webp` (neki portali traže JPEG → dodatna varijanta u
   `images.py`).
4. Po vozilu zastavica "objavi na portalima" (JSON `attributes` ili nova kolona) i zapis zadnjeg izvoza.
5. Status sinkronizacije u adminu (Sustav) i audit `feed.export`.
