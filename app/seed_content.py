"""Placeholder content for the five CMS pages (lorem ipsum + required legal structure).

Legal pages contain the section headings a real document must have (spec
chapter 14) and a `[PRAVNIK: dopuniti]` marker in every section.
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

ABOUT_HTML = f"""<p>{LOREM_P}</p>
<h2>Lorem ipsum dolor sit amet</h2>
<p>{LOREM_P2} {LOREM_P}</p>
<h3>Consectetur adipiscing elit</h3>
<ul>
<li>Lorem ipsum dolor sit amet</li>
<li>Consectetur adipiscing elit</li>
<li>Integer posuere erat a ante</li>
</ul>
<p>{LOREM_P2}</p>"""

SERVICES_HTML = f"""<p>{LOREM_P}</p>
<h2>Lorem ipsum</h2>
<p>{LOREM_P2}</p>
<h2>Dolor sit amet</h2>
<p>{LOREM_P}</p>
<h3>Consectetur adipiscing</h3>
<ul>
<li>Lorem ipsum dolor sit amet</li>
<li>Maecenas faucibus mollis interdum</li>
<li>Cras mattis consectetur purus</li>
</ul>
<h2>Integer posuere</h2>
<p>{LOREM_P2}</p>"""

PAGES = [
    {"slug": "o-nama", "title": "O nama", "body_html": ABOUT_HTML},
    {"slug": "usluge", "title": "Usluge", "body_html": SERVICES_HTML},
    {"slug": "privatnost", "title": "Politika privatnosti", "body_html": _legal(PRIVACY_SECTIONS)},
    {"slug": "kolacici", "title": "Politika kolačića", "body_html": _legal(COOKIE_SECTIONS)},
    {"slug": "uvjeti", "title": "Uvjeti korištenja", "body_html": _legal(TERMS_SECTIONS)},
]
