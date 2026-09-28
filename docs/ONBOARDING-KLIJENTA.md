# Onboarding novog klijenta (checklista)

Redoslijed od potpisa do predaje. Tehnički koraci pretpostavljaju VPS pripremljen prema README-u
("Deployment — prvi put na VPS-u") i klon repozitorija u `/opt/autokuca`.

## 0. Prije početka (s klijentom)

- [ ] Potpisan ugovor o usluzi i **ugovor o obradi podataka** (predložak
      `docs/pravno/UGOVOR-O-OBRADI-PODATAKA.md`, pregledan od pravnika).
- [ ] Prikupljeno: naziv tvrtke, adresa, OIB, email, telefon, radno vrijeme, web, društvene mreže,
      Google Maps poveznica, logotip (PNG/SVG→PNG s prozirnom pozadinom, širine ≥ 400 px), boje.
- [ ] Email za obavijesti o upitima i ime pošiljatelja newslettera.
- [ ] Tko su korisnici administracije (vlasnik, prodavači) i njihovi emailovi.
- [ ] Pravni tekstovi: politika privatnosti, kolačići, uvjeti — pripremio/pregledao pravnik klijenta.
- [ ] Domena: tko je registrar, ima li klijent Cloudflare račun (ili ga otvaramo mi).

## 1. Domena i Cloudflare

- [ ] Domena dodana u Cloudflare, nameserveri kod registrara promijenjeni na Cloudflareove.
- [ ] DNS: `A` zapis `@` i `www` → IP VPS-a, **proxy uključen** (narančasti oblak).
- [ ] SSL/TLS način **Full (strict)**; "Always Use HTTPS" uključen; minimalni TLS 1.2.
- [ ] Certifikat za server: Cloudflare → SSL/TLS → Origin Server → Create Certificate (RSA, domena +
      `*.domena`, 15 godina) → spremi u `deploy/caddy/certs/<domena>/cert.pem` i `key.pem`
      (`chmod 600`). (Alternativa: Let's Encrypt preko DNS izazova — `deploy/caddy/Dockerfile.cloudflare`.)
- [ ] WAF: managed rules uključena, rate limiting pravilo za `/admin/prijava` i `/upit`.
- [ ] Turnstile: Cloudflare → Turnstile → Add site (domena, način "Managed") → Site key i Secret key.

## 2. Instalacija na VPS-u

```bash
cd /opt/autokuca
deploy/new-client.sh <ime> <domena> [--admin-email operater@domena.hr]
```

- [ ] Skripta je ispisala URL, lozinku za `admin@domena.com` i checklistu; `https://<domena>/zdravlje`
      vraća `{"status": "ok", "db": "ok"}`.
- [ ] U `clients/<ime>/.env` upisani `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY`, `BREVO_API_KEY`,
      `EMAIL_FROM` (npr. `noreply@<domena>`); po želji `UMAMI_*`, `STORAGE_BACKEND=s3` + S3 varijable.
      Zatim `docker compose -p ak_<ime> --project-directory clients/<ime> up -d`.

## 3. Brevo (email)

- [ ] Brevo → Senders, Domains & Dedicated IPs → Domains → dodaj `<domena>`.
- [ ] DNS zapisi u Cloudflareu (kao "DNS only", sivi oblak): **SPF** (`v=spf1 include:spf.brevo.com
      ~all` — spoji s postojećim SPF zapisom ako klijent već šalje poštu), **DKIM** (TXT
      `brevo._domainkey`), **DMARC** (`_dmarc`: `v=DMARC1; p=none; rua=mailto:dmarc@<domena>`; nakon
      nekoliko tjedana `p=quarantine`), Brevo verifikacijski TXT.
- [ ] Domena u Brevu "Authenticated"; API ključ (SMTP & API → API Keys) upisan u `.env`.
- [ ] Admin → Sustav → "Pošalji testni email meni" stiže u inbox (ne u spam).

## 4. Podaci tvrtke i izgled (Admin → Postavke)

- [ ] Prva prijava kao `admin@domena.com` + postavljanje 2FA; lozinka promijenjena (Profil).
- [ ] Tvrtka: naziv, adresa, OIB, email, telefon, web, radno vrijeme (impressum u podnožju).
- [ ] Kontakt i mreže: email za obavijesti o upitima, ime pošiljatelja, Facebook, Instagram, Maps.
- [ ] Izgled: logo, primarna i akcentna boja (kontrast ≥ 4,5:1 prema bijeloj), naslov i podnaslov
      naslovnice, tekst podnožja.
- [ ] OG slika za dijeljenje (opcionalno): `clients/<ime>/overrides/static/og-default.png` (1200×630).
- [ ] Posebne želje dizajna: `clients/<ime>/overrides/` (vidi `overrides/README.md`).

## 5. Pravni dokumenti (Admin → Stranice)

- [ ] Politika privatnosti, Kolačići, Uvjeti korištenja: tekst pravnika umjesto lorem ipsuma, **nijedna
      oznaka `[PRAVNIK: …]` ne smije ostati**. Podizvršitelji i rokovi prema `docs/GDPR.md`.
- [ ] Postavke → Pravno: verzija politike privatnosti (npr. `1.0`) — datum se upisuje automatski.
- [ ] Usluge i O nama: tekst klijenta; stranice objavljene.
- [ ] Traka za kolačiće ostaje isključena, osim ako klijent traži GA/Pixel (tada uključiti i provjeriti).

## 6. Sadržaj i korisnici

- [ ] Katalog marki/modela provjeren (dodati što nedostaje, po potrebi CSV uvoz).
- [ ] Vozila unesena (ili uvezena); fotografije s **zamagljenim tablicama**; nova vozila s potrošnjom i CO2.
- [ ] Korisnici pozvani (Admin → Korisnici): vlasnik (owner), prodavači; svi postavili 2FA.
- [ ] `admin@domena.com` deaktiviran ili preimenovan ako ga operater ne koristi.

## 7. Provjera prije predaje

- [ ] Testni upit s javne stranice (s mobitela) → stiže u Admin → Upiti i na email za obavijesti.
- [ ] Prijava na newsletter → potvrda iz emaila → pretplatnik "Potvrđen" → testna kampanja → odjava
      jednim klikom radi.
- [ ] Google Search Console: domena dodana, `https://<domena>/sitemap.xml` poslan.
- [ ] Uptime monitor na `https://<domena>/zdravlje`.
- [ ] **Backup**: `deploy/backup.sh <ime>` prošao; **vraćanje testirano** (`deploy/restore.sh` na
      testnoj kopiji ili provjera `pg_restore --list` dešifrirane kopije s privatnim ključem).
- [ ] Firewall: 80/443 samo s Cloudflare IP raspona.

## 8. Predaja

- [ ] Klijentu predani: URL administracije, upute za 2FA i kodove za oporavak, kratke upute za rad
      (unos vozila, upiti, newsletter), kontakt za podršku.
- [ ] Zapisano u evidenciju operatera: ime instance, domena, datum, verzija (`git describe`), gdje su
      ključevi (backup privatni ključ, Cloudflare/Brevo pristupi).
