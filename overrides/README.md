# Prilagodbe po klijentu (`overrides/`)

Ova mapa se u Dockeru montira kao volume **samo za čitanje** (`./overrides:/app/overrides:ro`) i
omogućuje prilagodbu izgleda **pojedinog klijenta bez mijenjanja zajedničke Docker slike**.
Ažuriranje slike (nova verzija aplikacije) ne dira ništa u ovoj mapi.

Gdje je mapa: lokalno i u korijenskom `docker-compose.yml` to je ova mapa (`overrides/`); na VPS-u
svaki klijent ima svoju — `clients/<ime>/overrides/` (kreira je `deploy/new-client.sh`).

## Kako radi

1. **Templatei** — Jinja koristi `ChoiceLoader`: prvo traži datoteku u
   `overrides/templates/`, a tek onda u `app/templates/`. Ako postoji
   `overrides/templates/public/home.html`, koristi se ona umjesto originalne.
2. **CSS** — ako postoji `overrides/static/custom.css`, učitava se na svim
   javnim stranicama **nakon** glavnog `public.css` (URL `/static/custom/custom.css`),
   pa može pregaziti bilo koji stil ili CSS varijablu.
3. Slike ili fontovi za override stavljaju se u `overrides/static/` i
   referenciraju kao `/static/custom/ime-datoteke`.

Boje, logo, tekstovi i podaci tvrtke **ne** idu ovdje — oni se mijenjaju u
adminu (Postavke). Overrides su za promjene koje postavke ne pokrivaju.

## Primjer 1: promjena boje i zaobljenja (custom.css)

`overrides/static/custom.css`:

```css
/* Tamnija primarna boja i oštriji kutovi samo za ovog klijenta. */
:root {
  --color-primary: #0b3d2e;
  --radius: 4px;
  --radius-lg: 6px;
}
.hero h1 {
  text-transform: uppercase;
  letter-spacing: 0.02em;
}
```

Napomena: `custom.css` se učitava nakon `<style>` bloka s bojama iz postavki,
pa boja iz `custom.css` ima prednost pred bojom iz admina.

## Primjer 2: vlastita naslovnica (override templatea)

1. Kopiraj original: `app/templates/public/home.html` → `overrides/templates/public/home.html`.
2. Uredi kopiju, npr. dodaj blok ispod heroja:

```jinja
{% extends "public/base.html" %}
{% block content %}
  {# ... originalni sadržaj ... #}
  <section class="section section-alt">
    <div class="container">
      <h2>Posebna ponuda ovog mjeseca</h2>
      <p>Tekst samo za ovog klijenta.</p>
    </div>
  </section>
{% endblock %}
```

3. Primjena: izmjene postojeće override datoteke vidljive su nakon osvježavanja stranice. **Novi**
   override (datoteka koje prije nije bilo) traži restart aplikacije (i lokalno), jer se predlošci
   keširaju; u produkciji restart treba i nakon promjene `custom.css` (verzija CSS-a za cache):
   `docker compose -p ak_<ime> --project-directory clients/<ime> restart app`.
4. Provjera: `tests/test_overrides.py` pokazuje isti primjer (override naslovnice + `custom.css`).

## Primjer 3: drukčiji raspored jedne stranice

Stranice Usluge i O nama imaju vlastite predloške (`app/templates/public/pages/usluge.html`,
`o-nama.html`). Za drugu stranicu (npr. Kolačići) ili drukčiji izgled postojeće, napravi
`overrides/templates/public/pages/<slug>.html` — koristi se umjesto općeg `public/page.html`.

## Pravila

- I u overrideima vrijedi: **nema inline `<script>`** (CSP ih blokira) ni vanjskih CDN-ova.
- Podatke tvrtke uvijek čitaj iz `site` (npr. `{{ site.company_phone }}`), ne upisuj ih ručno.
- Kad se originalni template promijeni u novoj verziji, override se **ne** ažurira
  automatski — usporedi ih (`git diff --no-index app/templates/public/home.html overrides/templates/public/home.html`).
