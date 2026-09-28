"""Default content for the five CMS pages.

"O nama" and "Usluge" contain generic dealership text (no company data — that always comes
from the settings) so that a demo looks like a real car dealer; every client edits it in
Admin → Stranice. On "Usluge" every H3 becomes a service card (app/services/content.py).
Legal pages stay lorem ipsum with the section headings a real document must have (spec
chapter 14) and a `[PRAVNIK: dopuniti]` marker in every section — a lawyer writes them.
"""

LOREM_P = (
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Integer posuere erat a ante "
    "venenatis dapibus posuere velit aliquet. Maecenas faucibus mollis interdum. Cras mattis "
    "consectetur purus sit amet fermentum."
)
LOREM_P2 = (
    "Donec ullamcorper nulla non metus auctor fringilla. Vestibulum id ligula porta felis "
    "euismod semper. Nullam quis risus eget urna mollis ornare vel eu leo."
)
LAWYER = "<p><strong>[PRAVNIK: dopuniti]</strong></p>"


def _legal(sections: list[str]) -> str:
    parts = [f"<p>{LOREM_P}</p>"]
    for heading in sections:
        parts.append(f"<h2>{heading}</h2>")
        parts.append(f"<p>{LOREM_P2}</p>")
        parts.append(LAWYER)
    return "\n".join(parts)


PRIVACY_SECTIONS = [
    "1. Voditelj obrade",
    "2. Svrhe obrade osobnih podataka",
    "3. Pravne osnove obrade",
    "4. Primatelji i izvršitelji obrade (podizvršitelji)",
    "5. Prijenos podataka izvan EU/EGP-a",
    "6. Rokovi čuvanja",
    "7. Prava ispitanika",
    "8. Pravo na pritužbu Agenciji za zaštitu osobnih podataka (AZOP)",
    "9. Kontakt za pitanja o privatnosti",
]

COOKIE_SECTIONS = [
    "1. Što su kolačići",
    "2. Nužni kolačići koje koristimo",
    "3. Analitika bez kolačića",
    "4. Kolačići trećih strana",
    "5. Upravljanje kolačićima",
    "6. Kontakt",
]

TERMS_SECTIONS = [
    "1. Opće odredbe",
    "2. Korištenje internetske stranice",
    "3. Podaci o vozilima i cijenama",
    "4. Upiti i dogovor pregleda vozila",
    "5. Ograničenje odgovornosti",
    "6. Intelektualno vlasništvo",
    "7. Mjerodavno pravo i rješavanje sporova",
    "8. Izmjene uvjeta",
]

ABOUT_HTML = """<p>Pomažemo kupcima pronaći vozilo koje odgovara njihovim potrebama i budžetu — \
bilo da je riječ o prvom automobilu, obiteljskom kombiju, kamperu za putovanja ili gospodarskom \
vozilu za posao.</p>
<h2>Kako radimo</h2>
<p>U ponudi držimo vozila za koja znamo podrijetlo i povijest održavanja. Svako vozilo prije \
objave pregledavamo, fotografiramo i opisujemo onako kako jest — s jasno navedenim stanjem, \
kilometražom, opremom i načinom oporezivanja.</p>
<p>Kupnja vozila velika je odluka, zato vam dajemo vremena: vozilo možete pogledati i isprobati \
u dogovorenom terminu, a na sva pitanja odgovaramo otvoreno — telefonom, emailom ili u salonu.</p>
<h2>Nakon kupnje</h2>
<p>Naš odnos ne završava predajom ključeva. Pomažemo oko registracije, osiguranja i servisa, a \
kupci nam se rado vraćaju kad dođe vrijeme za sljedeće vozilo.</p>
<ul>
<li>jasni podaci o stanju i povijesti vozila</li>
<li>pregled i probna vožnja uz dogovor</li>
<li>pomoć oko financiranja, registracije i prijenosa vlasništva</li>
</ul>"""

SERVICES_HTML = """<p>Uz prodaju novih i rabljenih vozila nudimo sve što vam treba da do \
vozila dođete jednostavno i bez skrivenih troškova — od financiranja do registracije.</p>
<h3>Prodaja novih i rabljenih vozila</h3>
<p>Osobni automobili, kombiji, motocikli, kamperi i gospodarska vozila. Svako vozilo prije \
prodaje pregledavamo i pripremamo, a dokumentaciju dajemo na uvid.</p>
<h3>Financiranje i leasing</h3>
<p>Pomažemo odabrati kredit ili leasing prema vašem budžetu i pripremamo potrebnu \
dokumentaciju. Informativnu ponudu dobivate brzo i bez obveze.</p>
<h3>Otkup i zamjena vozila</h3>
<p>Vaše dosadašnje vozilo možemo otkupiti ili uzeti u zamjenu pri kupnji novoga. Procjena \
vrijednosti je besplatna.</p>
<h3>Registracija i prijenos vlasništva</h3>
<p>Brinemo o tehničkom pregledu, registraciji, osiguranju i prijenosu vlasništva, tako da \
vozilo preuzimate spremno za vožnju.</p>
<h3>Priprema i servis vozila</h3>
<p>Prije predaje vozilo prolazi servisnu provjeru, čišćenje i pripremu. Po potrebi \
dogovaramo i redovni servis.</p>
<h3>Jamstvo</h3>
<p>Za odabrana vozila nudimo jamstvo — uvjete i trajanje navodimo u oglasu svakog vozila.</p>
<h2>Posebni uvjeti za tvrtke</h2>
<p>Pravnim osobama i obrtnicima izdajemo R1 račun, a za vozila s PDV-om moguć je odbitak \
pretporeza. Javite nam se za ponudu za više vozila ili dugoročni najam.</p>"""

PAGES = [
    {"slug": "o-nama", "title": "O nama", "body_html": ABOUT_HTML},
    {"slug": "usluge", "title": "Usluge", "body_html": SERVICES_HTML},
    {"slug": "privatnost", "title": "Politika privatnosti", "body_html": _legal(PRIVACY_SECTIONS)},
    {"slug": "kolacici", "title": "Politika kolačića", "body_html": _legal(COOKIE_SECTIONS)},
    {"slug": "uvjeti", "title": "Uvjeti korištenja", "body_html": _legal(TERMS_SECTIONS)},
]
