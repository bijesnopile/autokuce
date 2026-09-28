# ORKESTRATOR — izvrši sve faze 1–8 bez zaustavljanja

## Što imaš

Mapa projekta je `C:\Users\matej\Documents\projekti\autokuce` (radni direktorij; projekt se gradi u njezinom korijenu, **ne** u `prompts/`). U njoj je mapa `prompts/` sa:
- `SPECIFIKACIJA.md` — izvor istine za cijeli projekt (pročitaj cijelu prije početka)
- `01-temelj.md` … `08-deployment-dokumentacija.md` — detaljni zadaci za svaku fazu
- ovim dokumentom (`00-orkestrator.md`) i `UPUTE.md` (upute za mene, ne za tebe)

**Prvi korak:** ako `docs/SPECIFIKACIJA.md` ne postoji, kopiraj `prompts/SPECIFIKACIJA.md` u `docs/SPECIFIKACIJA.md`. Mapa `prompts/` ostaje u repozitoriju (commitaj je) — to je dokumentacija kako je projekt nastao.

Tvoj zadatak: **izvrši svih 8 faza redom, jednu za drugom, bez čekanja na moju potvrdu.** Radiš samostalno dok faza 8 nije gotova i završni izvještaj napisan. Ja nisam prisutan — ne postavljaj pitanja; svaku nedefiniranu odluku donesi sam i zabilježi u `docs/PRETPOSTAVKE.md`.

## Okruženje

Radiš na Windows računalu (PowerShell ili WSL — provjeri u kojoj si ljusci i prilagodi naredbe). Pravila iz odjeljka "Razvojno okruženje" u specifikaciji vrijede u svakoj fazi: lokalne skripte samo u Pythonu, `pathlib`, `.gitattributes` s LF za shell/Docker datoteke, Docker provjere samo ako je Docker dostupan. Prije prve faze provjeri `python --version` (3.11+), `git --version`, `docker --version` (može nedostajati) i kreiraj `.venv`.

## Postupak za svaku fazu N (1 → 8)

1. Pročitaj `CLAUDE.md` (ako postoji), `docs/SPECIFIKACIJA.md` i `prompts/0N-*.md`.
2. Provjeri stanje repozitorija (`git log --oneline`, status faza u `CLAUDE.md`) i utvrdi je li faza već djelomično napravljena. Nastavi gdje je stalo; nikad ne radi ispočetka ono što već postoji i radi.
3. Izvrši **sve** zadatke faze, uključujući testove i provjeru ("Provjera prije završetka"). Ne preskači Playwright provjere i screenshotove — pregledaj ih i ispravi što ne valja.
4. Ako nešto ne prolazi ni nakon 3 ozbiljna pokušaja: zabilježi problem (što, zašto, što si pokušao) u `docs/PRETPOSTAVKE.md` pod "Otvoreno" i **nastavi dalje** — ne ostaj zaglavljen. U fazi 8 vrati se na sve otvorene stavke i pokušaj ih riješiti.
5. Ažuriraj `CLAUDE.md`: odjeljak "Status faza" (`Faza N: gotova — datum`) i "Trenutno" (što je sljedeće).
6. Napiši izvještaj faze u `docs/IZVJESTAJI/faza-0N.md` (sadržaj prema odjeljku "Završni izvještaj faze" u promptu faze) i u chatu daj samo 3–5 redaka sažetka.
7. `git add -A && git commit -m "Faza N: <naziv>"`. Odmah prijeđi na fazu N+1.

## Pravila za dug samostalan rad

- **Commitaj često**, ne samo na kraju faze — nakon svakog zaokruženog koraka (`WIP faza N: <korak>`). Ako se sesija prekine, to je točka povratka.
- **CLAUDE.md je tvoja memorija.** Kontekst razgovora može biti komprimiran ili izgubljen; sve što sljedeća faza mora znati (rute, konvencije, gdje je što, odluke) mora biti u `CLAUDE.md`, `docs/SPECIFIKACIJA.md` ili `docs/PRETPOSTAVKE.md`, ne samo u chatu. Održavaj i "Trenutno: faza N, zadnji dovršeni korak: …" u `CLAUDE.md`, ažuriran na kraju svakog većeg koraka.
- Ako u bilo kojem trenutku ustanoviš da si izgubio kontekst (ne sjećaš se što je napravljeno): pročitaj `CLAUDE.md`, `git log`, `docs/IZVJESTAJI/` i nastavi.
- Ne mijenjaj odluke iz specifikacije da bi si olakšao posao. Ne smanjuj opseg faze bez zapisa u PRETPOSTAVKE.md.
- Ne instaliraj ništa izvan `requirements*.txt` bez da to zapišeš. Ne mijenjaj ništa izvan mape projekta.
- Prije prelaska u sljedeću fazu `ruff check .` i `pytest` moraju prolaziti (ili je iznimka zabilježena pod "Otvoreno").

## Kraj

Nakon faze 8: završni izvještaj prema `prompts/08-…` u `docs/IZVJESTAJI/zavrsni.md` **i** u cijelosti u chatu (to je jedina duga poruka koju očekujem), git tag `v0.1.0-mvp`. Tek tada stani.

## Ako sam te ponovno pokrenuo ovim istim promptom

Znači da je prethodna sesija prekinuta. Ne počinji ispočetka: utvrdi stanje iz `CLAUDE.md`, `git log` i `docs/IZVJESTAJI/`, nastavi od zadnjeg nedovršenog koraka i prođi sve preostale faze.
