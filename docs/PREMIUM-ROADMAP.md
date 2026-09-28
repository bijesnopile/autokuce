# Premium paket — roadmap

Stavke iz specifikacije (pogl. 23) koje **nisu** u MVP-u, s prijedlogom implementacije i ovisnostima.
Model podataka i struktura koda već ih dopuštaju (bez prepravljanja postojećeg).

| # | Stavka | Implementacija | Ovisnosti / napomene | Procjena |
|---|---|---|---|---|
| 1 | **Kalkulator leasinga / kredita** | Komponenta na detalju vozila (vanilla JS, formula anuiteta), parametri (kamata, učešće, rokovi, napomena) u Postavkama; opcionalno "Pošalji upit za financiranje" s izračunom | nova vrsta upita (#3); pravna napomena da je izračun informativan | S |
| 2 | **Blog / novosti i dodatne stranice** | Tablica `posts` (naslov, slug, sadržaj, objava, slika) ili proširenje `pages` s `kind`; lista `/novosti`, detalj, sitemap, JSON-LD `Article`; isti editor i nh3 | slike kroz `images.py`; SEO meta kao kod stranica | M |
| 3 | **Dodatne vrste upita** (probna vožnja, financiranje, procjena vozila za zamjenu, povratni poziv) | Nova vrsta u `INQUIRY_TYPES` + varijanta forme u `_inquiry_form.html`; dodatna polja u `inquiries.extra` (JSON, bez migracije); zamjena: upload do 5 fotografija kroz `images.py` | CLAUDE.md → "Upiti — kako dodati novu vrstu upita" | S po vrsti |
| 4 | **Automatsko zamagljivanje tablica** | Detekcija tablica (npr. ONNX model za detekciju registarskih pločica, `onnxruntime` na CPU-u) u `images.py` prije re-enkodiranja; ručna korekcija pravokutnika u adminu | veća slika/memorija (~200 MB), sporiji upload → obrada u pozadinskom poslu; zadržati checkbox potvrde | L |
| 5 | **XML feedovi prema portalima** (Njuškalo, Index oglasi, mobile.de, AutoScout24) | `app/services/feeds/<portal>.py` + `GET /feed/<portal>.xml?token=`; tablica mapiranja šifrarnika; zastavica po vozilu; audit izvoza (detalji: ARHITEKTURA.md → 7) | ugovor/API pristup kod svakog portala; šifrarnici marki/modela/opreme | M–L po portalu |
| 6 | **Više jezika sa sadržajem** | Tablica `translations` + URL prefiks jezika + `hreflang` (ARHITEKTURA.md → 6); sučelje je već kroz `_()` | prijevod pravnih tekstova (pravnik); SEO po jeziku | M |
| 7 | **SMS / WhatsApp obavijesti** | Servis `app/services/notify.py` s backendima (Infobip/Twilio SMS, WhatsApp Business API); obavijest dealeru o novom upitu, opcionalno kupcu potvrda | pružatelj izvan EU → podizvršitelj i DPA; trošak po poruci; privola kupca za poruke | M |
| 8 | **Više poslovnica** | Tablica `locations` (adresa, telefon, radno vrijeme, Maps), `vehicles.location_id`, filter lokacije, kontakt stranica s više lokacija, JSON-LD `AutoDealer` po lokaciji | migracija + prilagodba postavki (impressum ostaje tvrtka) | M |
| 9 | **Naplata pretplate u aplikaciji** | Namjerno izvan aplikacije (fakturira se ručno). Ako zatreba: Stripe Billing na razini operatera, ne unutar instance klijenta | fiskalizacija/računi u HR — pravni i računovodstveni savjet | — |

Procjena: S ≈ 1–3 dana, M ≈ 1–2 tjedna, L ≈ 2+ tjedna (uključujući testove i dokumentaciju).

**Preporučeni redoslijed**: 3 (dodatne vrste upita) → 1 (kalkulator) → 2 (novosti) → 5 (feedovi) →
8 (poslovnice) → 6 (jezici) → 7 (SMS) → 4 (zamagljivanje tablica).

Svaka stavka mora zadržati pravila iz CLAUDE.md (podaci tvrtke iz postavki, bez vanjskih resursa i
inline skripti, CSRF, audit, `_()`, Alembic migracije, `scripts/check.py`).
