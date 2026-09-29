# Paketi: Osnovni, Standard, Premium

Tri paketa iste platforme (jedna Docker slika). Aktivni paket određuje env varijabla `PLAN`
(`osnovni` | `standard` | `premium`, default `osnovni`). Superadmin ga može privremeno nadjačati na
stranici **Admin → Sustav** (npr. za demo), što se sprema u postavku `plan_override` i jasno
prikazuje kao aktivno nadjačavanje. Definicija u kodu: [`app/plans.py`](../app/plans.py).

Ova tablica je i temelj cjenika.

## Funkcije po paketu

| Funkcija | Osnovni | Standard | Premium |
|---|:-:|:-:|:-:|
| Web-stranica s oglasima (5 vrsta vozila), filteri, galerija, SEO, sitemap | ✔ | ✔ | ✔ |
| Upiti (vozilo, pregled, opći) i mini-CRM, bilješke, dodjela, CSV | ✔ | ✔ | ✔ |
| Newsletter (double opt-in, kampanje, odjava jednim klikom) | ✔ | ✔ | ✔ |
| Nadzorna ploča i statistika, audit log, prava ispitanika (GDPR) | ✔ | ✔ | ✔ |
| Postavke tvrtke, logo, boje, stranice, 2FA za sve korisnike | ✔ | ✔ | ✔ |
| **Broj korisnika administracije** | **2** | **5** | **neograničeno** |
| WhatsApp i Viber gumbi (`whatsapp`) | — | ✔ | ✔ |
| Kartica za izlog A4/A5 s QR kodom (`izlog_kartica`) | — | ✔ | ✔ |
| Ponuda kupcu, ispis/PDF (`ponuda_pdf`) | — | ✔ | ✔ |
| Automatski odgovor kupcu (`auto_odgovor`) | — | ✔ | ✔ |
| Kalendarski poziv (.ics) i potvrda termina pregleda (`kalendar_termin`) | — | ✔ | ✔ |
| Kalkulator rate na oglasu i u listi (`kalkulator_rate`) | — | ✔ | ✔ |
| Upit za financiranje (`upit_financiranje`) | — | ✔ | ✔ |
| Feed prema portalima: Njuškalo, Index, mobile.de, AutoScout24, Meta (`feed_portali`) | — | ✔ | ✔ |
| Kupoprodajni ugovor PDF (`ugovor_pdf`) — *planirano* | — | — | ✔ |
| Nabavna cijena i marža (`marza`) — *planirano* | — | — | ✔ |
| Više poslovnica (`poslovnice`) — *planirano* | — | — | ✔ |
| Višejezični sadržaj (`jezici`) — *planirano* | — | — | ✔ |
| Novosti / blog (`blog`) — *planirano* | — | — | ✔ |
| Automatsko zamagljivanje tablica (`zamagljivanje_tablica`) — *planirano* | — | — | ✔ |

Limit korisnika broji **aktivne** korisnike s ulogom vlasnik ili prodavač (superadmin je operater
platforme i ne troši mjesto). Provjerava se pri pozivnici i ponovnoj aktivaciji korisnika.

## Ponašanje zaključanih funkcija

- **Administracija**: zaključane stavke ostaju vidljive s oznakom "Standard"/"Premium" (izbornik,
  gumbi, postavke). Klik vodi na stranicu *"Dostupno u paketu Standard"* s opisom funkcije (HTTP 403).
- **Javna stranica**: zaključane funkcije se ne prikazuju (bez gumba WhatsApp, kalkulatora…); javne
  rute zaključanih funkcija (npr. `/feed/...`, `/idi/whatsapp/...`) vraćaju 404.
- Postavke zaključanih funkcija vide se u Postavkama, ali su onemogućene (oznaka paketa); spremanje
  postavki ne briše njihove vrijednosti.

## Kako dodati funkciju u paket

1. Zapis u `FEATURES` (`app/plans.py`): kod, naziv, opis, skup paketa (`planned=True` dok nije gotovo).
2. Admin ruta: `Depends(require_feature("kod"))`; javna ruta: `Depends(public_feature("kod"))`;
   template: `{% if has_feature("kod") %}` (javno) ili `lock_badge("kod")` (oznaka u adminu).
3. Test za oba paketa (uključeno / zaključano) i red u ovoj tablici.
