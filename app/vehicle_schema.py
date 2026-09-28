"""Vehicle types, fields, option lists and equipment — the ONLY source of truth.

The admin form, server-side validation, the public specification table and
filters are all generated from this module. Field/option naming follows
Njuškalo / mobile.de conventions so portal feeds (premium) are just mappings.

HOW TO ADD A FIELD
    1. Type-specific field (stored in `vehicles.attributes` JSON): add a dict to
       `TYPE_FIELDS[<type>]` — no migration needed.
    2. Common field stored in its own column: add the column in `models.py`
       (+ Alembic migration) and a dict to `COMMON_FIELDS`.
    Field keys: key, label, type (text|int|float|select|bool|month|url|textarea),
    options (list of (code, label) for select), required, unit, min, max,
    group (form section), types (None = all types), help.

HOW TO ADD A VEHICLE TYPE
    Add an entry to `VEHICLE_TYPES`, its fields to `TYPE_FIELDS` and optional
    equipment to `TYPE_EQUIPMENT`; add the code to `models.VEHICLE_TYPES`.
"""

from __future__ import annotations

from datetime import date

from app.models import (
    CONDITION_NEW,
    STATUS_ACTIVE,
    STATUS_ARCHIVED,
    STATUS_DRAFT,
    STATUS_RESERVED,
    STATUS_SOLD,
)

# ---------------------------------------------------------------------------
# Vehicle types
# ---------------------------------------------------------------------------
VEHICLE_TYPES: dict[str, dict] = {
    "car": {
        "label": "Osobni automobil",
        "plural": "Osobni automobili",
        "icon": "car",
        "schema_org": "Car",
    },
    "van": {
        "label": "Kombi / laka dostavna",
        "plural": "Kombiji i dostavna",
        "icon": "van",
        "schema_org": "Vehicle",
    },
    "motorcycle": {
        "label": "Motocikl",
        "plural": "Motocikli",
        "icon": "motorcycle",
        "schema_org": "Motorcycle",
    },
    "camper": {"label": "Kamper", "plural": "Kamperi", "icon": "camper", "schema_org": "Vehicle"},
    "truck": {"label": "Kamion", "plural": "Kamioni", "icon": "truck", "schema_org": "Vehicle"},
}
TYPE_CODES = tuple(VEHICLE_TYPES)
MOTOR_TYPES = ("car", "van", "motorcycle", "truck")  # engine/gearbox fields are mandatory

# ---------------------------------------------------------------------------
# Shared option lists
# ---------------------------------------------------------------------------
CONDITIONS = [("used", "Rabljeno"), ("new", "Novo")]

FUELS = [
    ("benzin", "Benzin"),
    ("dizel", "Dizel"),
    ("hibrid", "Hibrid"),
    ("plugin_hibrid", "Plug-in hibrid"),
    ("elektricni", "Električni"),
    ("lpg", "Benzin + LPG"),
    ("cng", "Benzin + CNG"),
]
TRANSMISSIONS = [("rucni", "Ručni"), ("automatski", "Automatski")]
DRIVES = [("prednji", "Prednji"), ("straznji", "Stražnji"), ("4x4", "4x4")]
COLORS = [
    ("bijela", "Bijela"),
    ("crna", "Crna"),
    ("siva", "Siva"),
    ("srebrna", "Srebrna"),
    ("plava", "Plava"),
    ("crvena", "Crvena"),
    ("zelena", "Zelena"),
    ("smeda", "Smeđa"),
    ("bez", "Bež"),
    ("zuta", "Žuta"),
    ("narancasta", "Narančasta"),
    ("ljubicasta", "Ljubičasta"),
    ("zlatna", "Zlatna"),
    ("ostalo", "Ostalo"),
]
EURO_NORMS = [
    ("euro3", "Euro 3"),
    ("euro4", "Euro 4"),
    ("euro5", "Euro 5"),
    ("euro6", "Euro 6"),
    ("euro6b", "Euro 6b"),
    ("euro6c", "Euro 6c"),
    ("euro6d_temp", "Euro 6d-TEMP"),
    ("euro6d", "Euro 6d"),
    ("euro6e", "Euro 6e"),
]
TAX_TYPES = [
    ("pdv", "PDV uračunat u cijenu (R1)"),
    ("marza", "Posebni postupak oporezivanja marže"),
    ("bez_pdv", "Cijena bez PDV-a"),
]

STATUSES = {
    STATUS_DRAFT: "Skica",
    STATUS_ACTIVE: "Aktivno",
    STATUS_RESERVED: "Rezervirano",
    STATUS_SOLD: "Prodano",
    STATUS_ARCHIVED: "Arhivirano",
}
# Allowed manual transitions. sold -> archived happens automatically (maintenance).
STATUS_TRANSITIONS = {
    STATUS_DRAFT: [STATUS_ACTIVE],
    STATUS_ACTIVE: [STATUS_RESERVED, STATUS_SOLD, STATUS_DRAFT],
    STATUS_RESERVED: [STATUS_ACTIVE, STATUS_SOLD],
    STATUS_SOLD: [STATUS_ACTIVE],
    STATUS_ARCHIVED: [STATUS_DRAFT],
}
PUBLIC_STATUSES = (STATUS_ACTIVE, STATUS_RESERVED, STATUS_SOLD)

# ---------------------------------------------------------------------------
# Form sections (order = order in the admin form and on the public page)
# ---------------------------------------------------------------------------
SECTIONS = [
    ("osnovno", "Osnovno"),
    ("cijena", "Cijena"),
    ("motor", "Motor i pogon"),
    ("karoserija", "Karoserija i specifikacije"),
    ("stanje", "Stanje i dokumenti"),
    ("oprema", "Oprema"),
    ("opis", "Opis i mediji"),
    ("objava", "Objava"),
]
SECTION_LABELS = dict(SECTIONS)

CURRENT_YEAR = date.today().year

# ---------------------------------------------------------------------------
# Common fields (own DB columns). make/model are special (catalog selects).
# ---------------------------------------------------------------------------
COMMON_FIELDS: list[dict] = [
    {
        "key": "variant",
        "label": "Varijanta / oprema",
        "type": "text",
        "group": "osnovno",
        "max_length": 120,
        "help": "npr. 320d xDrive M Sport",
    },
    {
        "key": "condition",
        "label": "Stanje",
        "type": "select",
        "options": CONDITIONS,
        "required": True,
        "group": "osnovno",
    },
    {
        "key": "year",
        "label": "Godina proizvodnje",
        "type": "int",
        "required": True,
        "min": 1950,
        "max": CURRENT_YEAR + 1,
        "group": "osnovno",
        "plain": True,  # shown without thousands separator
    },
    {
        "key": "first_registration",
        "label": "Prva registracija",
        "type": "month",
        "group": "osnovno",
    },
    {
        "key": "mileage_km",
        "label": "Kilometraža",
        "type": "int",
        "unit": "km",
        "required": True,
        "min": 0,
        "max": 2_000_000,
        "group": "osnovno",
    },
    {
        "key": "price_eur",
        "label": "Cijena",
        "type": "int",
        "unit": "€",
        "min": 0,
        "max": 10_000_000,
        "group": "cijena",
    },
    {
        "key": "price_old_eur",
        "label": "Stara cijena (prekrižena)",
        "type": "int",
        "unit": "€",
        "min": 0,
        "max": 10_000_000,
        "group": "cijena",
        "help": "Opcionalno — prikazuje se prekriženo.",
    },
    {"key": "price_on_request", "label": "Cijena na upit", "type": "bool", "group": "cijena"},
    {
        "key": "tax_type",
        "label": "Način oporezivanja",
        "type": "select",
        "options": TAX_TYPES,
        "required": True,
        "group": "cijena",
    },
    {
        "key": "fuel",
        "label": "Gorivo",
        "type": "select",
        "options": FUELS,
        "group": "motor",
        "required_types": MOTOR_TYPES,
    },
    {
        "key": "power_kw",
        "label": "Snaga",
        "type": "int",
        "unit": "kW",
        "min": 1,
        "max": 2000,
        "group": "motor",
        "help": "KS se izračunava automatski.",
    },
    {
        "key": "engine_ccm",
        "label": "Obujam motora",
        "type": "int",
        "unit": "ccm",
        "min": 0,
        "max": 20_000,
        "group": "motor",
    },
    {
        "key": "transmission",
        "label": "Mjenjač",
        "type": "select",
        "options": TRANSMISSIONS,
        "group": "motor",
        "required_types": MOTOR_TYPES,
    },
    {
        "key": "drive",
        "label": "Pogon",
        "type": "select",
        "options": DRIVES,
        "group": "motor",
        "types": ("car", "van", "camper", "truck"),
    },
    {
        "key": "euro_norm",
        "label": "Euro norma",
        "type": "select",
        "options": EURO_NORMS,
        "group": "motor",
    },
    {
        "key": "fuel_consumption_l100",
        "label": "Kombinirana potrošnja",
        "type": "float",
        "unit": "l/100 km",
        "min": 0,
        "max": 100,
        "group": "motor",
        "required_new": True,
        "help": "Obavezno za nova vozila (WLTP). Električna: kWh/100 km.",
    },
    {
        "key": "co2_g_km",
        "label": "Emisija CO2",
        "type": "int",
        "unit": "g/km",
        "min": 0,
        "max": 1000,
        "group": "motor",
        "required_new": True,
        "help": "Obavezno za nova vozila (WLTP).",
    },
    {"key": "color", "label": "Boja", "type": "select", "options": COLORS, "group": "karoserija"},
    {"key": "color_metallic", "label": "Metalik", "type": "bool", "group": "karoserija"},
    {
        "key": "doors",
        "label": "Broj vrata",
        "type": "int",
        "min": 1,
        "max": 6,
        "group": "karoserija",
        "types": ("car",),
    },
    {
        "key": "seats",
        "label": "Broj sjedala",
        "type": "int",
        "min": 1,
        "max": 60,
        "group": "karoserija",
        "types": ("car", "van", "camper"),
        "type_labels": {"camper": "Sjedala s pojasom"},
    },
    {"key": "registered_until", "label": "Registriran do", "type": "month", "group": "stanje"},
    {"key": "first_owner", "label": "Prvi vlasnik", "type": "bool", "group": "stanje"},
    {"key": "service_book", "label": "Servisna knjižica", "type": "bool", "group": "stanje"},
    {
        "key": "warranty_months",
        "label": "Garancija",
        "type": "int",
        "unit": "mj.",
        "min": 0,
        "max": 120,
        "group": "stanje",
    },
    {
        "key": "vin",
        "label": "VIN (broj šasije)",
        "type": "text",
        "group": "stanje",
        "max_length": 17,
        "admin_only": True,
        "help": "Vidljivo samo u administraciji — nikad na javnoj stranici.",
    },
    {
        "key": "video_url",
        "label": "YouTube video",
        "type": "url",
        "group": "opis",
        "help": "Poveznica na YouTube video (učitava se tek na klik posjetitelja).",
    },
    {
        "key": "featured",
        "label": "Istaknuto vozilo",
        "type": "bool",
        "group": "objava",
        "help": "Prikazuje se u bloku „Istaknuta vozila” na naslovnici.",
    },
]
COMMON_BY_KEY = {f["key"]: f for f in COMMON_FIELDS}

# ---------------------------------------------------------------------------
# Type-specific fields (stored in vehicles.attributes JSON)
# ---------------------------------------------------------------------------
TYPE_FIELDS: dict[str, list[dict]] = {
    "car": [
        {
            "key": "body_type",
            "label": "Karoserija",
            "type": "select",
            "required": True,
            "options": [
                ("limuzina", "Limuzina"),
                ("karavan", "Karavan"),
                ("hatchback", "Hatchback"),
                ("suv", "SUV / terenac"),
                ("coupe", "Coupé"),
                ("kabriolet", "Kabriolet"),
                ("monovolumen", "Monovolumen"),
                ("pickup", "Pickup"),
            ],
        },
    ],
    "van": [
        {
            "key": "van_type",
            "label": "Vrsta",
            "type": "select",
            "required": True,
            "options": [
                ("furgon", "Furgon (zatvoreni)"),
                ("putnicki", "Putnički kombi"),
                ("sasija", "Šasija / kabina"),
                ("hladnjaca", "Hladnjača"),
            ],
        },
        {
            "key": "payload_kg",
            "label": "Nosivost",
            "type": "int",
            "unit": "kg",
            "min": 0,
            "max": 10_000,
        },
        {
            "key": "cargo_volume_m3",
            "label": "Volumen teretnog prostora",
            "type": "float",
            "unit": "m³",
            "min": 0,
            "max": 100,
        },
        {
            "key": "wheelbase",
            "label": "Međuosovinski razmak",
            "type": "select",
            "options": [("kratki", "Kratki"), ("srednji", "Srednji"), ("dugi", "Dugi")],
        },
        {
            "key": "roof_height",
            "label": "Visina krova",
            "type": "select",
            "options": [("H1", "H1 (niski)"), ("H2", "H2 (srednji)"), ("H3", "H3 (visoki)")],
        },
    ],
    "motorcycle": [
        {
            "key": "moto_type",
            "label": "Vrsta motocikla",
            "type": "select",
            "required": True,
            "options": [
                ("naked", "Naked"),
                ("sport", "Sport"),
                ("touring", "Touring"),
                ("enduro", "Enduro"),
                ("cross", "Cross"),
                ("skuter", "Skuter"),
                ("chopper", "Chopper / cruiser"),
                ("moped", "Moped"),
            ],
        },
        {"key": "cylinders", "label": "Broj cilindara", "type": "int", "min": 1, "max": 8},
        {
            "key": "cooling",
            "label": "Hlađenje",
            "type": "select",
            "options": [
                ("zrak", "Zrakom"),
                ("tekucina", "Tekućinom"),
                ("ulje_zrak", "Uljem / zrakom"),
            ],
        },
        {
            "key": "final_drive",
            "label": "Prijenos",
            "type": "select",
            "options": [("lanac", "Lanac"), ("kardan", "Kardan"), ("remen", "Remen")],
        },
        {"key": "abs", "label": "ABS", "type": "bool"},
        {"key": "a2_suitable", "label": "Prikladan za A2 kategoriju", "type": "bool"},
    ],
    "camper": [
        {
            "key": "camper_type",
            "label": "Vrsta kampera",
            "type": "select",
            "required": True,
            "options": [
                ("alkoven", "Alkoven"),
                ("poluintegrirani", "Poluintegrirani"),
                ("integrirani", "Integrirani"),
                ("kombi_kamper", "Kombi-kamper"),
                ("kamp_prikolica", "Kamp prikolica"),
            ],
        },
        {"key": "berths", "label": "Broj ležajeva", "type": "int", "min": 1, "max": 12},
        {"key": "length_m", "label": "Duljina", "type": "float", "unit": "m", "min": 2, "max": 15},
        {
            "key": "gross_weight_kg",
            "label": "Najveća dopuštena masa",
            "type": "int",
            "unit": "kg",
            "min": 300,
            "max": 10_000,
        },
        {"key": "wc_shower", "label": "WC / tuš", "type": "bool"},
        {
            "key": "heating",
            "label": "Grijanje",
            "type": "select",
            "options": [
                ("plinsko", "Plinsko"),
                ("dizelsko", "Dizelsko"),
                ("elektricno", "Električno"),
                ("kombinirano", "Kombinirano"),
                ("bez", "Bez grijanja"),
            ],
        },
    ],
    "truck": [
        {
            "key": "truck_body",
            "label": "Nadogradnja",
            "type": "select",
            "required": True,
            "options": [
                ("sanduk", "Sanduk"),
                ("kiper", "Kiper"),
                ("hladnjaca", "Hladnjača"),
                ("cisterna", "Cisterna"),
                ("tegljac", "Tegljač (šleper)"),
                ("kran", "S kranom"),
                ("cerada", "Cerada"),
            ],
        },
        {
            "key": "gross_weight_kg",
            "label": "Najveća dopuštena masa",
            "type": "int",
            "unit": "kg",
            "min": 3500,
            "max": 60_000,
        },
        {
            "key": "payload_kg",
            "label": "Nosivost",
            "type": "int",
            "unit": "kg",
            "min": 0,
            "max": 50_000,
        },
        {"key": "axles", "label": "Broj osovina", "type": "int", "min": 2, "max": 5},
        {
            "key": "cabin",
            "label": "Kabina",
            "type": "select",
            "options": [("dnevna", "Dnevna"), ("spavaca", "Spavaća")],
        },
        {"key": "tachograph", "label": "Tahograf", "type": "bool"},
    ],
}
for _fields in TYPE_FIELDS.values():
    for _field in _fields:
        _field.setdefault("group", "karoserija")

# ---------------------------------------------------------------------------
# Equipment: categories with items; `types` limits an item to some vehicle types
# ---------------------------------------------------------------------------
FOUR_WHEELS = ("car", "van", "camper", "truck")
ALL = TYPE_CODES

EQUIPMENT_CATEGORIES = [
    ("sigurnost", "Sigurnost"),
    ("udobnost", "Udobnost"),
    ("multimedija", "Multimedija"),
    ("eksterijer", "Eksterijer"),
    ("specificno", "Posebna oprema"),
]

EQUIPMENT_ICONS = {
    "sigurnost": "shield-check",
    "udobnost": "star",
    "multimedija": "smartphone",
    "eksterijer": "car",
    "specificno": "wrench",
}

EQUIPMENT: list[dict] = [
    # Sigurnost
    {"code": "abs", "label": "ABS", "cat": "sigurnost", "types": ALL},
    {"code": "esp", "label": "ESP", "cat": "sigurnost", "types": FOUR_WHEELS},
    {"code": "zracni_jastuci", "label": "Zračni jastuci", "cat": "sigurnost", "types": FOUR_WHEELS},
    {"code": "isofix", "label": "Isofix", "cat": "sigurnost", "types": ("car", "van", "camper")},
    {"code": "alarm", "label": "Alarm", "cat": "sigurnost", "types": ALL},
    {
        "code": "parking_senzori",
        "label": "Parking senzori",
        "cat": "sigurnost",
        "types": FOUR_WHEELS,
    },
    {
        "code": "kamera",
        "label": "Kamera za vožnju unatrag",
        "cat": "sigurnost",
        "types": FOUR_WHEELS,
    },
    {"code": "kamera_360", "label": "Kamera 360°", "cat": "sigurnost", "types": FOUR_WHEELS},
    {
        "code": "mrtvi_kut",
        "label": "Asistent za mrtvi kut",
        "cat": "sigurnost",
        "types": FOUR_WHEELS,
    },
    {
        "code": "trake",
        "label": "Asistent za održavanje trake",
        "cat": "sigurnost",
        "types": FOUR_WHEELS,
    },
    {
        "code": "auto_kocenje",
        "label": "Automatsko kočenje u nuždi",
        "cat": "sigurnost",
        "types": FOUR_WHEELS,
    },
    {
        "code": "kontrola_proklizavanja",
        "label": "Kontrola proklizavanja",
        "cat": "sigurnost",
        "types": ALL,
    },
    # Udobnost
    {"code": "klima", "label": "Klima uređaj", "cat": "udobnost", "types": FOUR_WHEELS},
    {
        "code": "automatska_klima",
        "label": "Automatska klima",
        "cat": "udobnost",
        "types": FOUR_WHEELS,
    },
    {"code": "tempomat", "label": "Tempomat", "cat": "udobnost", "types": ALL},
    {
        "code": "adaptivni_tempomat",
        "label": "Adaptivni tempomat",
        "cat": "udobnost",
        "types": FOUR_WHEELS,
    },
    {"code": "grijana_sjedala", "label": "Grijana sjedala", "cat": "udobnost", "types": ALL},
    {"code": "kozna_sjedala", "label": "Kožna sjedala", "cat": "udobnost", "types": FOUR_WHEELS},
    {
        "code": "elektricna_sjedala",
        "label": "Električno podesiva sjedala",
        "cat": "udobnost",
        "types": FOUR_WHEELS,
    },
    {"code": "grijani_volan", "label": "Grijani volan", "cat": "udobnost", "types": FOUR_WHEELS},
    {"code": "keyless", "label": "Ulaz i pokretanje bez ključa", "cat": "udobnost", "types": ALL},
    {"code": "start_stop", "label": "Start-stop sustav", "cat": "udobnost", "types": FOUR_WHEELS},
    {
        "code": "panoramski_krov",
        "label": "Panoramski krov",
        "cat": "udobnost",
        "types": ("car", "camper"),
    },
    {"code": "head_up", "label": "Head-up zaslon", "cat": "udobnost", "types": ("car",)},
    # Multimedija
    {"code": "navigacija", "label": "Navigacija", "cat": "multimedija", "types": ALL},
    {
        "code": "carplay",
        "label": "Apple CarPlay / Android Auto",
        "cat": "multimedija",
        "types": ALL,
    },
    {"code": "bluetooth", "label": "Bluetooth", "cat": "multimedija", "types": ALL},
    {
        "code": "digitalni_instrumenti",
        "label": "Digitalna instrument ploča",
        "cat": "multimedija",
        "types": ALL,
    },
    {
        "code": "premium_zvuk",
        "label": "Premium ozvučenje",
        "cat": "multimedija",
        "types": FOUR_WHEELS,
    },
    {"code": "dab", "label": "DAB radio", "cat": "multimedija", "types": FOUR_WHEELS},
    {
        "code": "bezicno_punjenje",
        "label": "Bežično punjenje mobitela",
        "cat": "multimedija",
        "types": FOUR_WHEELS,
    },
    # Eksterijer
    {"code": "alu_felge", "label": "Alu felge", "cat": "eksterijer", "types": ALL},
    {"code": "led_svjetla", "label": "LED svjetla", "cat": "eksterijer", "types": ALL},
    {"code": "xenon", "label": "Xenon svjetla", "cat": "eksterijer", "types": FOUR_WHEELS},
    {"code": "kuka", "label": "Kuka za vuču", "cat": "eksterijer", "types": FOUR_WHEELS},
    {
        "code": "krovni_nosaci",
        "label": "Krovni nosači",
        "cat": "eksterijer",
        "types": ("car", "van", "camper"),
    },
    {
        "code": "zatamnjena_stakla",
        "label": "Zatamnjena stakla",
        "cat": "eksterijer",
        "types": FOUR_WHEELS,
    },
    # Type specific
    {
        "code": "kofer",
        "label": "Kofer / bočne torbe",
        "cat": "specificno",
        "types": ("motorcycle",),
    },
    {
        "code": "grijane_rucke",
        "label": "Grijane ručke",
        "cat": "specificno",
        "types": ("motorcycle",),
    },
    {
        "code": "quickshifter",
        "label": "Quickshifter",
        "cat": "specificno",
        "types": ("motorcycle",),
    },
    {
        "code": "zastitno_staklo",
        "label": "Zaštitno staklo",
        "cat": "specificno",
        "types": ("motorcycle",),
    },
    {
        "code": "nacini_voznje",
        "label": "Načini vožnje",
        "cat": "specificno",
        "types": ("motorcycle",),
    },
    {"code": "solarni_panel", "label": "Solarni panel", "cat": "specificno", "types": ("camper",)},
    {"code": "tenda", "label": "Tenda", "cat": "specificno", "types": ("camper",)},
    {
        "code": "nosac_bicikala",
        "label": "Nosač bicikala",
        "cat": "specificno",
        "types": ("camper",),
    },
    {"code": "hladnjak", "label": "Hladnjak", "cat": "specificno", "types": ("camper",)},
    {"code": "kuhalo", "label": "Kuhalo", "cat": "specificno", "types": ("camper",)},
    {"code": "satelitska", "label": "Satelitska antena", "cat": "specificno", "types": ("camper",)},
    {
        "code": "pregrada",
        "label": "Pregrada teretnog prostora",
        "cat": "specificno",
        "types": ("van",),
    },
    {
        "code": "obloga_tereta",
        "label": "Obloga teretnog prostora",
        "cat": "specificno",
        "types": ("van",),
    },
    {"code": "klizna_vrata", "label": "Bočna klizna vrata", "cat": "specificno", "types": ("van",)},
    {"code": "retarder", "label": "Retarder", "cat": "specificno", "types": ("truck",)},
    {"code": "hidraulika", "label": "Hidraulika", "cat": "specificno", "types": ("truck",)},
    {"code": "parkirna_klima", "label": "Parkirna klima", "cat": "specificno", "types": ("truck",)},
]
EQUIPMENT_BY_CODE = {item["code"]: item for item in EQUIPMENT}


# ---------------------------------------------------------------------------
# Accessors
# ---------------------------------------------------------------------------
def type_label(vehicle_type: str | None) -> str:
    return VEHICLE_TYPES.get(vehicle_type or "", {}).get("label", vehicle_type or "")


def field_label(field: dict, vehicle_type: str | None = None) -> str:
    return field.get("type_labels", {}).get(vehicle_type or "", field["label"])


def common_fields_for(vehicle_type: str) -> list[dict]:
    return [f for f in COMMON_FIELDS if f.get("types") is None or vehicle_type in f["types"]]


def type_fields(vehicle_type: str) -> list[dict]:
    return TYPE_FIELDS.get(vehicle_type, [])


def schema_for(vehicle_type: str) -> dict:
    """Everything the form/validation needs for one type, grouped by section."""
    if vehicle_type not in VEHICLE_TYPES:
        raise KeyError(vehicle_type)
    sections: dict[str, list[dict]] = {key: [] for key, _label in SECTIONS}
    for field in common_fields_for(vehicle_type):
        sections[field["group"]].append(dict(field, source="column"))
    for field in type_fields(vehicle_type):
        sections[field["group"]].append(dict(field, source="attributes"))
    return {
        "type": vehicle_type,
        **VEHICLE_TYPES[vehicle_type],
        "sections": sections,
        "equipment": equipment_for(vehicle_type),
    }


def equipment_for(vehicle_type: str) -> list[dict]:
    """Equipment categories with the items valid for `vehicle_type`."""
    result = []
    for cat_key, cat_label in EQUIPMENT_CATEGORIES:
        items = [
            {"code": item["code"], "label": item["label"]}
            for item in EQUIPMENT
            if item["cat"] == cat_key and vehicle_type in item["types"]
        ]
        if items:
            result.append({"key": cat_key, "label": cat_label, "items": items})
    return result


def equipment_grouped(codes: list[str], vehicle_type: str) -> list[dict]:
    """Selected equipment grouped by category (public page)."""
    selected = set(codes or [])
    groups = []
    for category in equipment_for(vehicle_type):
        items = [i["label"] for i in category["items"] if i["code"] in selected]
        if items:
            groups.append(
                {
                    "key": category["key"],
                    "label": category["label"],
                    "icon": EQUIPMENT_ICONS.get(category["key"], "check-circle"),
                    "items": items,
                }
            )
    return groups


def option_label(field: dict, value) -> str:
    for code, text in field.get("options", []):
        if code == value:
            return text
    return "" if value is None else str(value)


def label(field_key: str, value, vehicle_type: str | None = None) -> str:
    """Display label for a stored code, e.g. label('fuel', 'dizel') -> 'Dizel'."""
    field = COMMON_BY_KEY.get(field_key)
    if field is None and vehicle_type:
        field = next((f for f in type_fields(vehicle_type) if f["key"] == field_key), None)
    if field is None:
        for fields in TYPE_FIELDS.values():
            field = next((f for f in fields if f["key"] == field_key), None)
            if field:
                break
    if field is None:
        return "" if value is None else str(value)
    return option_label(field, value)


def status_label(status: str) -> str:
    return STATUSES.get(status, status)


def allowed_transitions(status: str) -> list[str]:
    return STATUS_TRANSITIONS.get(status, [])


# ---------------------------------------------------------------------------
# Parsing and validation
# ---------------------------------------------------------------------------
def _parse_int(raw: str) -> int:
    cleaned = raw.replace(".", "").replace(" ", "").replace(" ", "")
    if cleaned.endswith(",00"):
        cleaned = cleaned[:-3]
    return int(cleaned)


def _parse_float(raw: str) -> float:
    return float(raw.replace(" ", "").replace(",", "."))


def _parse_month(raw: str) -> date:
    """Accepts `YYYY-MM` (input type=month) or `MM/YYYY`."""
    raw = raw.strip()
    if "/" in raw:
        month, year = raw.split("/", 1)
    else:
        year, month = raw.split("-", 1)[0], raw.split("-", 1)[1][:2]
    return date(int(year), int(month), 1)


def parse_field(field: dict, raw) -> tuple[object, str | None]:
    """Parse one raw form value according to `field`. Returns (value, error)."""
    kind = field["type"]
    if kind == "bool":
        return str(raw or "").lower() in {"1", "on", "true", "da", "yes"}, None
    text = str(raw or "").strip()
    if text == "":
        return None, None
    try:
        if kind == "int":
            value = _parse_int(text)
        elif kind == "float":
            value = round(_parse_float(text), 2)
        elif kind == "month":
            value = _parse_month(text)
        elif kind == "select":
            codes = [code for code, _ in field.get("options", [])]
            if text not in codes:
                return None, "Odaberite vrijednost s popisa."
            value = text
        elif kind == "url":
            if not text.startswith(("https://", "http://")) or len(text) > 300:
                return None, "Upišite ispravnu poveznicu (https://...)."
            value = text
        else:
            max_length = field.get("max_length", 250)
            value = text[:max_length]
    except (ValueError, IndexError):
        return None, "Neispravna vrijednost."
    if kind in ("int", "float"):
        if "min" in field and value < field["min"]:
            return None, f"Najmanja dopuštena vrijednost je {field['min']}."
        if "max" in field and value > field["max"]:
            return None, f"Najveća dopuštena vrijednost je {field['max']}."
    if kind == "month" and not (1950 <= value.year <= CURRENT_YEAR + 10):
        return None, "Neispravan datum."
    return value, None


def is_required(field: dict, vehicle_type: str, condition: str | None) -> bool:
    if field.get("required"):
        return True
    if vehicle_type in field.get("required_types", ()):
        return True
    return bool(field.get("required_new") and condition == CONDITION_NEW)


def validate_attributes(vehicle_type: str, data) -> tuple[dict, dict]:
    """Validate type-specific fields from a mapping of raw values.

    Keys in `data` may be plain (`body_type`) or prefixed (`attr_body_type`).
    Returns (clean_attributes, errors) — errors keyed by field key.
    """
    clean: dict = {}
    errors: dict = {}
    for field in type_fields(vehicle_type):
        raw = data.get(f"attr_{field['key']}", data.get(field["key"]))
        value, error = parse_field(field, raw)
        if error:
            errors[field["key"]] = error
            continue
        if field["type"] == "bool":
            clean[field["key"]] = bool(value)
            continue
        if value is None:
            if field.get("required"):
                errors[field["key"]] = "Obavezno polje."
            continue
        clean[field["key"]] = value
    return clean, errors


def validate_common(vehicle_type: str, data) -> tuple[dict, dict]:
    """Validate common (column) fields. Returns (clean_columns, errors)."""
    clean: dict = {}
    errors: dict = {}
    condition = str(data.get("condition") or "")
    for field in common_fields_for(vehicle_type):
        value, error = parse_field(field, data.get(field["key"]))
        if error:
            errors[field["key"]] = error
            continue
        if value is None and is_required(field, vehicle_type, condition):
            errors[field["key"]] = "Obavezno polje."
            continue
        clean[field["key"]] = value
    # Price is required unless "price on request".
    if not clean.get("price_on_request") and clean.get("price_eur") is None:
        errors.setdefault("price_eur", "Upišite cijenu ili označite „Cijena na upit”.")
    if clean.get("price_old_eur") and clean.get("price_eur"):
        if clean["price_old_eur"] <= clean["price_eur"]:
            errors.setdefault("price_old_eur", "Stara cijena mora biti veća od nove.")
    if clean.get("vin"):
        vin = str(clean["vin"]).upper().replace(" ", "")
        if len(vin) != 17 or any(c in "IOQ" for c in vin) or not vin.isalnum():
            errors["vin"] = "VIN ima 17 znakova (slova i brojke, bez I, O, Q)."
        else:
            clean["vin"] = vin
    # Fields not valid for this type are cleared (e.g. doors on a motorcycle).
    valid_keys = {f["key"] for f in common_fields_for(vehicle_type)}
    for field in COMMON_FIELDS:
        if field["key"] not in valid_keys:
            clean[field["key"]] = False if field["type"] == "bool" else None
    return clean, errors


def validate_equipment(vehicle_type: str, codes) -> list[str]:
    valid = {i["code"] for c in equipment_for(vehicle_type) for i in c["items"]}
    return sorted({str(code) for code in codes if str(code) in valid})


def power_hp(power_kw: int | None) -> int | None:
    return round(power_kw * 1.35962) if power_kw else None
