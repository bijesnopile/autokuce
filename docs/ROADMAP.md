# Roadmap po paketima

Paketi i što je uključeno: [PAKETI.md](PAKETI.md). Ovdje su funkcije koje **još nisu gotove**, s
prijedlogom implementacije. Model podataka i struktura koda ih dopuštaju bez prepravljanja
postojećeg. Kod funkcije (`app/plans.py`) je u zagradi.

## Gotovo u paketu Standard (v0.2.0)

WhatsApp/Viber gumbi, kartica za izlog i PDF ponuda, automatski odgovor kupcu i kalendarski termini
(.ics), kalkulator rate i upit za financiranje, feed prema portalima, do 5 korisnika. Detalji:
[PAKETI.md](PAKETI.md), [FEEDOVI.md](FEEDOVI.md).

## Premium — planirano

| # | Funkcija | Implementacija | Ovisnosti / napomene | Procjena |
|---|---|---|---|---|
| 1 | **Kupoprodajni ugovor PDF** (`ugovor_pdf`) | Kao ponuda (print CSS, A4) s podacima kupca iz upita i vozila (uključujući VIN); obrazac pregledava pravnik; audit bez podataka kupca | predložak ugovora od pravnika; OIB kupca je osobni podatak → ne sprema se | S |
| 2 | **Nabavna cijena i marža** (`marza`) | Interna polja vozila (nabavna cijena, troškovi pripreme) u `attributes` ili zasebnoj tablici; izračun marže (i PDV-a na maržu) u adminu i statistici; nikad javno | pravila oporezivanja marže — računovođa | M |
| 3 | **Više poslovnica** (`poslovnice`) | Tablica `locations` (adresa, telefon, radno vrijeme, Maps), `vehicles.location_id`, filter lokacije, kontakt s više lokacija, JSON-LD `AutoDealer` po lokaciji; feed po lokaciji | migracija; impressum ostaje tvrtka | M |
| 4 | **Višejezični sadržaj** (`jezici`) | Tablica `translations` + URL prefiks jezika + `hreflang` (ARHITEKTURA.md → 6); sučelje je već kroz `_()` | prijevod pravnih tekstova (pravnik) | M |
| 5 | **Novosti / blog** (`blog`) | Tablica `posts` ili `pages.kind`; `/novosti`, sitemap, JSON-LD `Article`; isti editor i nh3 | slike kroz `images.py` | M |
| 6 | **Automatsko zamagljivanje tablica** (`zamagljivanje_tablica`) | Detekcija tablica (ONNX model, `onnxruntime` na CPU-u) u `images.py` prije re-enkodiranja; ručna korekcija u adminu | ~200 MB veća slika, obrada u pozadini; potvrda zamagljivanja ostaje | L |

## Ideje za kasnije (bez paketa)

| Funkcija | Napomena |
|---|---|
| Dodatne vrste upita (probna vožnja, procjena vozila za zamjenu s fotografijama, povratni poziv) | isti mehanizam kao upit za financiranje (`inquiries.extra`) |
| SMS / WhatsApp Business obavijesti prodavaču | pružatelj izvan EU → podizvršitelj i DPA; trošak po poruci |
| Izravni API prema portalima (umjesto feeda) | ugovor s portalom; feed ostaje rezerva |
| Naplata pretplate u aplikaciji | namjerno izvan aplikacije (ručno fakturiranje); fiskalizacija — računovođa |

Svaka nova funkcija: zapis u `FEATURES`, provjera paketa u ruti/templateu, test za oba stanja, red
u PAKETI.md, a pravila iz CLAUDE.md (podaci tvrtke iz postavki, bez vanjskih resursa i inline
skripti, CSRF, audit, `_()`, migracije, `scripts/check.py`) vrijede i dalje.
