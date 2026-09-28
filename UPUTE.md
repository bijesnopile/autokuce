# Upute: build MVP-a — sve odjednom ili fazu po fazu

## Struktura na tvom računalu

```
C:\Users\matej\Documents\projekti\autokuce\        ← mapa projekta (tu se gradi kod)
└── prompts\                                        ← sadržaj ovog paketa
    ├── UPUTE.md                                    (ovo)
    ├── SPECIFIKACIJA.md                            (izvor istine; agent je kopira u docs\)
    ├── 00-orkestrator.md                           (sve faze odjednom)
    └── 01-temelj.md … 08-deployment-dokumentacija.md
```

Agent u prvom koraku sam kopira `prompts\SPECIFIKACIJA.md` u `docs\SPECIFIKACIJA.md` i dalje radi s tom kopijom. Mapa `prompts\` ostaje u repozitoriju.

## Priprema (jednom)

1. Raspakiraj ZIP tako da datoteke završe u `C:\Users\matej\Documents\projekti\autokuce\prompts\`.
2. Na računalu trebaš: Python 3.11+ (`python --version`), Git. Docker Desktop je opcionalan — bez njega agent preskače Docker provjere i zabilježi to.
3. Otvori Claude Code / Claude s povezanom mapom **`autokuce`** (korijen projekta, ne `prompts`). Radni direktorij mora biti `autokuce`.

## Opcija A — sve odjednom (agent sam prolazi faze 1–8)

- Zalijepi cijeli sadržaj `prompts\00-orkestrator.md` kao poruku i pusti ga da radi.
- Agent nakon svake faze piše izvještaj u `docs\IZVJESTAJI\faza-0N.md`, ažurira `CLAUDE.md` i commita, pa odmah nastavlja. U chatu daje samo kratke sažetke; završni izvještaj dolazi na kraju.
- **Dozvole:** da bi radio bez tebe, sesija mora imati unaprijed dopušteno izvršavanje naredbi i pisanje datoteka; inače će stati na svakom pitanju za dozvolu. Provjeri postavke dozvola sesije prije pokretanja.
- **Prekid sesije** (limit, greška, zatvoren laptop): otvori novu sesiju u istoj mapi i ponovno zalijepi `00-orkestrator.md`. Agent iz `CLAUDE.md`, `git log` i izvještaja utvrdi gdje je stao i nastavlja — ne počinje ispočetka.
- Očekuj da build traje satima. Kad završi, pregledaj `docs\IZVJESTAJI\zavrsni.md`, screenshotove u `docs\screenshots\` i pokreni demo.
- Nedostatak: ne možeš usmjeravati dizajn između faza. Ispravke tražiš naknadno (agent ima `CLAUDE.md` i specifikaciju, pa su naknadne promjene jednostavne).

## Opcija B — fazu po fazu (ti pregledavaš između faza)

- Zalijepi cijeli sadržaj `01-temelj.md` kao poruku. Pričekaj završni izvještaj faze.
- Pregledaj izvještaj (i screenshotove gdje ih ima). Ako nešto ne valja, traži ispravak **prije** sljedeće faze.
- Zatim `02`, pa `03`… do `08`. Svaka faza počinje čitanjem `CLAUDE.md` i specifikacije i provjerom stanja repozitorija, pa je svejedno nastavljaš li istu sesiju ili otvaraš novu.
- Faze 4 i 8 daju screenshotove — to su trenuci za pregled dizajna. Napiši konkretno što želiš drugačije (npr. "kartice vozila neka imaju veću sliku, cijena istaknutija").

## Kombinacija (preporuka)

Opcija A do kraja faze 4, pregled dizajna, pa opet Opcija A za faze 5–8: zalijepi `00-orkestrator.md` uz dodanu rečenicu *"Stani nakon faze 4 i čekaj moj pregled."*, a nakon pregleda ponovno `00-orkestrator.md` (nastavlja od faze 5).

## Nakon završetka

- Lokalno: u mapi `autokuce` aktiviraj `.venv` i pokreni `python run.py` → `http://localhost:8000` (javna stranica) i `/admin` (prijava `admin@domena.com`, lozinka iz izvještaja; prva prijava traži postavljanje 2FA).
- Za prezentaciju klijentu pokreni Docker verziju (`docker compose up`, treba Docker Desktop) — bliža je produkciji.
- Ako agent unatoč uputama nešto pita, odgovori kratko ili napiši "odluči sam i zabilježi u PRETPOSTAVKE.md".
