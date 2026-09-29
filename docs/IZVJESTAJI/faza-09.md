# Izvještaj — Faza 9: paket "Standard"

Datum: 29.09.2026. · Oznaka: `v0.2.0-standard` · Prompt: `prompts/09-standard-demo.md`

## Korak 0 (prije faze 9)

1. **SECRET_KEY**: ključ se generira samo jednom, u `data/.secret_key` (0400).
   - Produkcija bez ključa ili datoteke odbija start.
   - Fingerprint ključa (`check-secret-key`) upozorava na promjenu ključa.
   - Test: `tests/test_secret_key.py`.
2. **Wheelovi**: `pip download --only-binary=:all: --platform manylinux2014_x86_64 --python-version 3.11`.
   - Jedino Pillow 12.3 ima samo `manylinux_2_28`. Zadržan je (12.2 ima 6 CVE-ova).
   - Docker je fiksiran na `python:3.11-slim-trixie` + `--only-binary`, uz novu provjeru
     `scripts/check_wheels.py`.
3. **backup.sh**: bez `age` i `gpg` pada na samom početku, s uputom za instalaciju. Opisano u
   `docs/SIGURNOST.md`.

## Što je napravljeno (A–F, svaki korak zaseban commit)

| | Funkcija | Glavno |
|---|---|---|
| A | Sustav paketa | `app/plans.py`, `PLAN` + nadjačavanje na Sustavu, `require_feature`/`public_feature`, oznake u izborniku i postavkama, stranica 403 "Dostupno u paketu …", limit korisnika (2/5/∞), `docs/PAKETI.md`, `docs/ROADMAP.md` |
| B | WhatsApp i Viber | postavke brojeva, gumbi na oglasu, kontaktu i donjoj traci, `/idi/{kanal}/{id}` (brojanje "kontakata" u statistici, bez IP-a) |
| C | Kartica za izlog i ponuda | A4/A5 s QR kodom (bez VIN-a), ponuda A4 (broj `godina-id` iz audit loga, VIN), print CSS, "Napravi ponudu" iz upita |
| D | Automatski odgovor i .ics | email kupcu nakon upita (polja `{ime}` …), `.ics` TENTATIVE → potvrda termina CONFIRMED s istim UID-om i većim SEQUENCE, privitci u email backendu, `inquiries.scheduled_at` |
| E | Kalkulator rate i financiranje | anuitet (Python = JS, provjereno u Chromiumu), primjer bez JS-a, "od X €/mj", upit `financing` (parametri u `extra`), ikona u CRM-u, email prodavaču |
| F | Feed za portale | `/feed/{portal}.{xml,csv}?token=`, keš 5 min, gzip, rate limit, `/admin/feed` (URL-ovi, token, zadnje preuzimanje, pregled, provjera polja, upute, Meta lokacija), `docs/FEEDOVI.md` |

**Završetak**
- Demo (`PLAN=standard python -m app.seed --reset-demo`) ima:
  - WhatsApp broj `+385XXXXXXXXXX`,
  - upit za financiranje,
  - potvrđen termin pregleda,
  - prvu registraciju za sva rabljena vozila.
- `scripts/screenshots.py` radi s `PLAN=standard` i snima 50 slika. Nove slike:
  - financiranje (desktop i mobitel), WhatsApp na mobitelu,
  - kartica za izlog A4/A5, ponuda,
  - termin i financiranje u CRM-u, feed.
  - Set `osnovni-*` nastaje nadjačavanjem na Sustavu: oznake u izborniku, 403, zaključane postavke.
  - Sve provjere su prošle (HTTP, bez horizontalnog skrola, bez grešaka u konzoli).
- Ispravci nađeni pregledom screenshotova:
  - Horizontalni skrol na mobitelu: kartica "Financiranje" proširila je stupac. Ispravljeno s
    `grid-template-columns: minmax(0, 1fr)`.
  - Na stranici 403 ikone su bile prevelike, a označena je bila kriva stavka izbornika.
  - Provjera feeda tražila je prvu registraciju i za nova vozila.
- GDPR izvoz (pravo na pristup) sadrži potvrđeni termin i parametre financiranja.

Testovi: **368** (sve prolazi; nove funkcije i na PostgreSQL-u 16). `python scripts/check.py`: ruff, format, pytest, pip-audit.

## Feedovi — što je potvrđeno, a što treba provjeriti

Detalji su u `docs/FEEDOVI.md`. Specifikacije su istražene 29.09.2026. i navedeni su izvori.

- **Meta (Facebook/Instagram)**: izrađeno **prema javnoj referenci**.
  - Struktura: `<listings>/<listing>`, obavezna polja i dopuštene vrijednosti.
  - **Treba provjeriti**: prvo stvarno preuzimanje u Commerce Manageru. Regiju i koordinate prodajnog
    mjesta treba upisati na /admin/feed.
- **mobile.de** i **AutoScout24**: specifikacije su javne, ali oglase primaju **push** metodom (Seller
  API / Listing Creation API, CSV+ZIP), a ne preuzimanjem s URL-a.
  - Naš feed je generički XML/CSV s kodovima tih portala (atribut `kod`), namijenjen integratoru.
  - **Nije tvrdnja o usklađenosti.**
- **Njuškalo** i **Index oglasi**: **nema javne specifikacije**.
  - Feed je generički XML s oznakom "Format treba potvrditi s portalom".
  - Treba zatražiti specifikaciju od portala i dodati builder.

## Pretpostavke (sve u `docs/PRETPOSTAVKE.md` → "Faza 9 — paket Standard")

**Automatski odgovor**
- Pravna osnova je čl. 6(1)(b), bez marketinga i bez odjave.
- Prazan tekst vraća zadani, a nepoznato polje je greška.

**.ics**
- Vremena su u UTC-u, trajanje 60 min, podsjetnik 60 min prije, `METHOD:PUBLISH`.
- Kupac dobiva `.ics` uz automatski odgovor (ako je uključen), a sigurno uz potvrdu termina.

**Kalkulator**
- Reprezentativni primjer je najmanje učešće i najdulji rok. "od X €/mj" je zaokruženo naviše.
- Rok u koracima od 12 mjeseci, pa najdulji rok mora biti višekratnik od 12.
- Iznos financiranja se izračunava (cijena − učešće).

**Feed**
- Svaka greška daje 404.
- Meta: rezervirano vozilo ide kao `not_available`, a cijena na upit se ne izvozi.
- VIN je zadano isključen.
- Zadnje preuzimanje je u tablici `feed_access`, bez IP-a.

**Ponuda i kartica**
- Ponuda se ne sprema: broj je id audit zapisa.
- PDF se radi kroz ispis preglednika (bez novih ovisnosti).

## Otvoreno

- Potvrda formata feeda s Njuškalom i Indexom. Za mobile.de i AutoScout24: integrator ili izravna API
  integracija (`docs/ROADMAP.md`).
- Stvarno preuzimanje Meta kataloga još nije provjereno (nema testnog kataloga).
- Pravni tekst o WhatsAppu i Viberu te o automatskom odgovoru u politici privatnosti (`[PRAVNIK]`).
- Iz ranijih faza: `docker compose` na računalu s Dockerom, varijanta backupa s `age`.
- **Lokalna razvojna baza** ima `plan_override=standard` (demo). Ukloni ga na Admin → Sustav ili postavi
  `PLAN=standard` u `.env`.
