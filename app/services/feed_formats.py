"""Formati feedova po portalu (vidi docs/FEEDOVI.md — izvori, datumi, mapiranje, praznine).

`spec`: "confirmed" = izrađeno prema javnoj specifikaciji portala; "generic" = javna specifikacija
nije dostupna — generički XML koji treba potvrditi s portalom (ne tvrdimo usklađenost).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from xml.etree import ElementTree as ET

from sqlalchemy.orm import Session

from app.services import feeds
from app.services.feeds import csv_bytes, record, sub, xml_bytes

# ---------------------------------------------------------------------------
# Required fields (record key -> label shown in the validation list)
# ---------------------------------------------------------------------------
FIELD_LABELS = {
    "make": "Marka",
    "model": "Model",
    "year": "Godina",
    "mileage_km": "Kilometraža",
    "price_eur": "Cijena (ne „na upit”)",
    "fuel": "Gorivo",
    "transmission": "Mjenjač",
    "body_type": "Karoserija",
    "color": "Boja",
    "images": "Barem jedna slika",
    "description": "Opis",
    "first_registration": "Prva registracija",
    "power_kw": "Snaga",
}

GENERIC_REQUIRED = ["make", "model", "year", "mileage_km", "price_eur", "fuel", "images"]

# ---------------------------------------------------------------------------
# Meta (Facebook/Instagram) vehicle catalog — public spec (docs/FEEDOVI.md)
# Enum fields are case-insensitive; values below are written as in the reference.
# ---------------------------------------------------------------------------
META_FUEL = {
    "benzin": "GASOLINE",
    "dizel": "DIESEL",
    "hibrid": "HYBRID",
    "plugin_hibrid": "HYBRID",  # no separate plug-in value
    "elektricni": "ELECTRIC",
    "lpg": "OTHER",
    "cng": "OTHER",
}
META_TRANSMISSION = {"rucni": "Manual", "automatski": "Automatic"}
META_BODY = {
    "limuzina": "SEDAN",
    "karavan": "WAGON",
    "hatchback": "HATCHBACK",
    "suv": "SUV",
    "coupe": "COUPE",
    "kabriolet": "CONVERTIBLE",
    "monovolumen": "MINIVAN",
    "pickup": "TRUCK",
}
META_BODY_BY_TYPE = {"van": "VAN", "camper": "VAN", "truck": "TRUCK"}
META_DRIVE = {"prednji": "FWD", "straznji": "RWD", "4x4": "4X4"}
META_STATE = {"new": "New", "used": "Used"}
META_COLOR = {
    "bijela": "White",
    "crna": "Black",
    "siva": "Gray",
    "srebrna": "Silver",
    "plava": "Blue",
    "crvena": "Red",
    "zelena": "Green",
    "smeda": "Brown",
    "bez": "Beige",
    "zuta": "Yellow",
    "narancasta": "Orange",
    "ljubicasta": "Purple",
    "zlatna": "Gold",
    "ostalo": "Other",
}
META_REQUIRED = ["make", "model", "year", "mileage_km", "price_eur", "images", "color"]
META_MAX_DESCRIPTION = 5000
META_CSV_IMAGES = 10
META_CSV_HEADER = [
    "vehicle_id",
    "vin",
    "make",
    "model",
    "year",
    "transmission",
    "body_style",
    "fuel_type",
    "drivetrain",
    "description",
    *[f"image[{i}].url" for i in range(META_CSV_IMAGES)],
    "mileage.value",
    "mileage.unit",
    "url",
    "title",
    "price",
    "state_of_vehicle",
    "exterior_color",
    "availability",
    "address",
    "latitude",
    "longitude",
    "trim",
    "dealer_name",
    "dealer_phone",
]


def split_address(address: str) -> dict:
    """ "Ulica i broj 1, 10000 Grad" -> addr1 / postal_code / city (country HR)."""
    street, _, rest = (address or "").partition(",")
    match = re.match(r"\s*(\d{5})\s+(.+)", rest)
    postal, city = (match.group(1), match.group(2).strip()) if match else ("", rest.strip())
    return {"addr1": street.strip(), "city": city, "postal_code": postal, "country": "HR"}


def meta_address(site: dict) -> dict:
    address = split_address(site.get("company_address", ""))
    address["region"] = site.get("feed_region") or address["city"]
    return address


def meta_site_problems(site: dict) -> list[str]:
    """Dealer-level Meta fields (address region, coordinates) set on /admin/feed."""
    problems = []
    if not site.get("feed_region"):
        problems.append("Županija (region) za Meta adresu")
    if not (site.get("feed_latitude") and site.get("feed_longitude")):
        problems.append("Koordinate prodajnog mjesta (latitude/longitude) za Meta")
    return problems


def meta_description(data: dict) -> str:
    """Plain text, no links (Meta rule), at most 5000 characters."""
    text = re.sub(r"https?://\S+|www\.\S+", "", data["description"]).strip() or data["title"]
    return text[:META_MAX_DESCRIPTION]


def meta_row(data: dict, site: dict) -> dict:
    body = META_BODY.get(data["body_type"]) or META_BODY_BY_TYPE.get(data["vehicle_type"], "OTHER")
    row = {
        "vehicle_id": data["id"],
        "vin": data["vin"],
        "make": data["make"],
        "model": data["model"],
        "year": data["year"],
        "transmission": META_TRANSMISSION.get(data["transmission"], ""),
        "body_style": body,
        "fuel_type": META_FUEL.get(data["fuel"], "OTHER" if data["fuel"] else ""),
        "drivetrain": META_DRIVE.get(data["drive"], ""),
        "description": meta_description(data),
        "mileage.value": data["mileage_km"] or 0,
        "mileage.unit": "KM",
        "url": data["url"],
        "title": data["title"],
        "price": f"{data['price_eur']} EUR" if data["price_eur"] else "",
        "state_of_vehicle": META_STATE.get(data["condition"], "Used"),
        "exterior_color": META_COLOR.get(data["color"], ""),
        # Reserved cars stay in the catalog but are not advertised.
        "availability": "not_available" if data["status"] == "reserved" else "available",
        "latitude": site.get("feed_latitude", ""),
        "longitude": site.get("feed_longitude", ""),
        "trim": data["variant"],
        "dealer_name": data["dealer_name"],
        "dealer_phone": data["dealer_phone"],
    }
    return row


def build_meta(records: list[dict], site: dict, fmt: str) -> bytes:
    import json

    address = meta_address(site)
    rows = [(data, meta_row(data, site)) for data in records if data["price_eur"]]
    if fmt == "csv":
        csv_rows = []
        for data, row in rows:
            row = dict(row, address=json.dumps(address, ensure_ascii=False))
            for index, url in enumerate(data["images"][:META_CSV_IMAGES]):
                row[f"image[{index}].url"] = url
            csv_rows.append(row)
        return csv_bytes(META_CSV_HEADER, csv_rows)
    root = ET.Element("listings")
    sub(root, "title", f"{site.get('company_name', '')} – vozila")
    ET.SubElement(root, "link", {"rel": "self", "href": feeds.absolute("/feed/meta.xml")})
    for data, row in rows:
        listing = ET.SubElement(root, "listing")
        for key in ("vehicle_id", "title", "description", "url"):
            sub(listing, key, row[key])
        for url in data["images"]:
            image = ET.SubElement(listing, "image")
            sub(image, "url", url)
        for key in ("make", "model", "year"):
            sub(listing, key, row[key])
        mileage = ET.SubElement(listing, "mileage")
        sub(mileage, "value", row["mileage.value"])
        sub(mileage, "unit", "KM")
        for key in (
            "price",
            "state_of_vehicle",
            "exterior_color",
            "fuel_type",
            "transmission",
            "body_style",
            "drivetrain",
            "trim",
            "vin",
            "availability",
        ):
            sub(listing, key, row[key])
        element = ET.SubElement(listing, "address", {"format": "simple"})
        for part in ("addr1", "city", "region", "postal_code", "country"):
            sub(element, "component", address[part], name=part)
        sub(listing, "latitude", row["latitude"])
        sub(listing, "longitude", row["longitude"])
        sub(listing, "dealer_name", row["dealer_name"])
        sub(listing, "dealer_phone", row["dealer_phone"])
    return xml_bytes(root)


# ---------------------------------------------------------------------------
# Generic XML (portals without a public specification)
# ---------------------------------------------------------------------------
GENERIC_CSV_HEADER = [
    "id",
    "url",
    "naslov",
    "vrsta",
    "marka",
    "model",
    "izvedba",
    "stanje",
    "status",
    "godina",
    "prva_registracija",
    "kilometraza_km",
    "cijena_eur",
    "oporezivanje",
    "odbitni_pdv",
    "gorivo",
    "mjenjac",
    "pogon",
    "karoserija",
    "snaga_kw",
    "snaga_ks",
    "obujam_ccm",
    "boja",
    "vrata",
    "sjedala",
    "euro_norma",
    "co2_g_km",
    "potrosnja_l100",
    "potrosnja_kwh100",
    "domet_km",
    "baterija_kwh",
    "opis",
    "slike",
    "oprema",
    "vin",
    "azurirano",
]


def generic_row(data: dict) -> dict:
    return {
        "id": data["id"],
        "url": data["url"],
        "naslov": data["title"],
        "vrsta": data["vehicle_type"],
        "marka": data["make"],
        "model": data["model"],
        "izvedba": data["variant"],
        "stanje": data["condition"],
        "status": data["status"],
        "godina": data["year"],
        "prva_registracija": data["first_registration"],
        "kilometraza_km": data["mileage_km"],
        "cijena_eur": data["price_eur"],
        "oporezivanje": data["tax_type"],
        "odbitni_pdv": "da" if data["vat_deductible"] else "ne",
        "gorivo": data["fuel"],
        "mjenjac": data["transmission"],
        "pogon": data["drive"],
        "karoserija": data["body_type"],
        "snaga_kw": data["power_kw"],
        "snaga_ks": data["power_hp"],
        "obujam_ccm": data["engine_ccm"],
        "boja": data["color"],
        "vrata": data["doors"],
        "sjedala": data["seats"],
        "euro_norma": data["euro_norm"],
        "co2_g_km": data["co2_g_km"],
        "potrosnja_l100": data["fuel_l100"],
        "potrosnja_kwh100": data["energy_kwh100"],
        "domet_km": data["electric_range_km"],
        "baterija_kwh": data["battery_kwh"],
        "opis": data["description"],
        "slike": " ".join(data["images"]),
        "oprema": ",".join(data["equipment"]),
        "vin": data["vin"],
        "azurirano": data["updated_at"],
    }


# ---------------------------------------------------------------------------
# Portal codes written next to our own codes in the generic feed (attribute `kod`), so an
# integrator can map to the portal's API without guessing. Sources: docs/FEEDOVI.md.
# ---------------------------------------------------------------------------
PORTAL_CODES = {
    "mobile_de": {  # Seller API refdata (services.mobile.de/refdata/...)
        "gorivo": {
            "benzin": "PETROL",
            "dizel": "DIESEL",
            "hibrid": "HYBRID",
            "plugin_hibrid": "HYBRID",
            "elektricni": "ELECTRICITY",
            "lpg": "LPG",
            "cng": "CNG",
        },
        "mjenjac": {"rucni": "MANUAL_GEAR", "automatski": "AUTOMATIC_GEAR"},
        "karoserija": {
            "limuzina": "Limousine",
            "karavan": "EstateCar",
            "hatchback": "SmallCar",
            "suv": "OffRoad",
            "coupe": "SportsCar",
            "kabriolet": "Cabrio",
            "monovolumen": "Van",
            "pickup": "OtherCar",
        },
        "stanje": {"new": "NEW", "used": "USED"},
    },
    "autoscout24": {  # Listing Creation API /references
        "gorivo": {
            "benzin": "B",
            "dizel": "D",
            "hibrid": "2",
            "plugin_hibrid": "2",
            "elektricni": "E",
            "lpg": "L",
            "cng": "C",
        },
        "mjenjac": {"rucni": "M", "automatski": "A"},
        "karoserija": {
            "limuzina": "6",
            "karavan": "5",
            "hatchback": "1",
            "suv": "4",
            "coupe": "3",
            "kabriolet": "2",
            "monovolumen": "12",
            "pickup": "4",
        },
        "stanje": {"new": "N", "used": "U"},
    },
}


def build_generic(portal: str, records: list[dict], site: dict, fmt: str) -> bytes:
    if fmt == "csv":
        return csv_bytes(GENERIC_CSV_HEADER, [generic_row(d) for d in records], delimiter=";")
    root = ET.Element(
        "vozila",
        {
            "format": "autokuca-generic-1",
            "portal": portal,
            "napomena": "Format treba potvrditi s portalom",
            "generirano": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    )
    dealer = ET.SubElement(root, "prodavac")
    sub(dealer, "naziv", site.get("company_name", ""))
    sub(dealer, "adresa", site.get("company_address", ""))
    sub(dealer, "telefon", site.get("company_phone", ""))
    sub(dealer, "email", site.get("company_email", ""))
    portal_codes = PORTAL_CODES.get(portal, {})

    def coded(parent, key, value):
        code = portal_codes.get(key, {}).get(value)
        return sub(parent, key, value, kod=code) if code else sub(parent, key, value)

    for data in records:
        row = generic_row(data)
        vehicle = ET.SubElement(root, "vozilo", {"id": data["id"]})
        for key in (
            "url",
            "naslov",
            "vrsta",
            "marka",
            "model",
            "izvedba",
            "stanje",
            "status",
            "godina",
            "prva_registracija",
        ):
            coded(vehicle, key, row[key])
        sub(vehicle, "kilometraza", row["kilometraza_km"], jedinica="km")
        if data["price_eur"]:
            sub(
                vehicle,
                "cijena",
                data["price_eur"],
                valuta="EUR",
                oporezivanje=data["tax_type"],
                odbitni_pdv=row["odbitni_pdv"],
            )
        else:
            sub(vehicle, "cijena_na_upit", "da")
        for key in ("gorivo", "mjenjac", "pogon", "karoserija"):
            coded(vehicle, key, row[key])
        if data["power_kw"]:
            sub(vehicle, "snaga", data["power_kw"], jedinica="kW", ks=data["power_hp"] or "")
        for key in (
            "obujam_ccm",
            "boja",
            "vrata",
            "sjedala",
            "euro_norma",
            "co2_g_km",
            "potrosnja_l100",
            "potrosnja_kwh100",
            "domet_km",
            "baterija_kwh",
            "opis",
        ):
            sub(vehicle, key, row[key])
        if data["images"]:
            images = ET.SubElement(vehicle, "slike")
            for url in data["images"]:
                sub(images, "slika", url)
        if data["equipment"]:
            equipment = ET.SubElement(vehicle, "oprema")
            for code in data["equipment"]:
                sub(equipment, "stavka", code)
        sub(vehicle, "vin", row["vin"])
        sub(vehicle, "azurirano", row["azurirano"])
    return xml_bytes(root)


# ---------------------------------------------------------------------------
# Portals
# ---------------------------------------------------------------------------
PORTALS: dict[str, dict] = {
    "njuskalo": {
        "label": "Njuškalo",
        "formats": ("xml",),
        "spec": "generic",
        "spec_note": "Specifikacija uvoza nije javno objavljena (partnerski uvoz uz aktivacijski "
        "kod) — generički XML, format treba potvrditi s Njuškalom.",
        "source_url": "",
        "required": GENERIC_REQUIRED,
        "instructions": [
            "Javite se prodaji Njuškala za auto-kuće i zatražite automatski uvoz oglasa (XML).",
            "Pošaljite im XML URL s ove stranice i zatražite njihovu specifikaciju ili potvrdu "
            "da mogu preuzeti ovaj format.",
            "Njuškalo obrađuje uvoz jednom dnevno (noću) — promjene nisu vidljive odmah.",
            "Nakon prvog preuzimanja provjerite oglase na Njuškalu i zadnje preuzimanje ovdje.",
        ],
    },
    "index": {
        "label": "Index oglasi",
        "formats": ("xml",),
        "spec": "generic",
        "spec_note": "Javna specifikacija uvoza nije pronađena — generički XML, format treba "
        "potvrditi s Index oglasima.",
        "source_url": "",
        "required": GENERIC_REQUIRED,
        "instructions": [
            "Kontaktirajte Index oglase (poslovni korisnici) i pitajte za automatski uvoz.",
            "Pošaljite XML URL i zatražite potvrdu formata ili njihovu specifikaciju.",
        ],
    },
    "mobile_de": {
        "label": "mobile.de",
        "formats": ("xml", "csv"),
        "spec": "generic",
        "spec_note": "mobile.de ne preuzima feed s URL-a: oglasi se šalju njihovim Seller API-jem "
        "(za registrirane trgovce) ili CSV+ZIP uploadom. Ovaj feed je izvor podataka za "
        "integratora; XML uz naše kodove nosi i kodove mobile.de (atribut kod).",
        "source_url": "https://services.mobile.de/docs/seller-api.html",
        "required": GENERIC_REQUIRED + ["first_registration", "power_kw"],
        "instructions": [
            "Registrirajte trgovački račun na mobile.de i zatražite pristup Seller API-ju "
            "(service@team.mobile.de) ili odaberite ovlaštenog integratora.",
            "Integratoru dajte XML URL — polja gorivo, mjenjač, karoserija i stanje već imaju "
            "kodove mobile.de.",
        ],
    },
    "autoscout24": {
        "label": "AutoScout24",
        "formats": ("xml", "csv"),
        "spec": "generic",
        "spec_note": "AutoScout24 ne preuzima feed s URL-a: oglasi i slike šalju se Listing "
        "Creation API-jem s pristupnim podacima pružatelja. Ovaj feed je izvor podataka za "
        "integratora; XML nosi i kodove AutoScout24 (atribut kod).",
        "source_url": "https://listing-creation.api.autoscout24.com/docs",
        "required": GENERIC_REQUIRED + ["first_registration", "power_kw"],
        "instructions": [
            "Registrirajte trgovački račun na AutoScout24 i odaberite pružatelja podataka "
            "(integratora) s pristupom Listing Creation API-ju.",
            "Integratoru dajte XML URL i svoj AutoScout24 customerId.",
        ],
    },
    "meta": {
        "label": "Meta (Facebook / Instagram)",
        "formats": ("xml", "csv"),
        "spec": "confirmed",
        "spec_note": "Katalog vozila za Meta oglase (Automotive Inventory Ads), prema javnoj "
        "referenci polja.",
        "source_url": "https://developers.facebook.com/docs/marketing-api/auto-ads/reference/",
        "required": META_REQUIRED,
        "csv_header": META_CSV_HEADER,
        "csv_delimiter": ",",
        "instructions": [
            "Ispod upišite županiju i koordinate prodajnog mjesta (Meta ih traži u adresi).",
            "U Meta Commerce Manageru izradite katalog vrste „Vozila” (Automotive).",
            "Izvori podataka → Zakazani feed → zalijepite XML URL s ove stranice.",
            "Postavite dnevno preuzimanje; greške po vozilu vidjet ćete u Commerce Manageru.",
        ],
    },
}
for _meta in PORTALS.values():
    _meta.setdefault("csv_header", GENERIC_CSV_HEADER)
    _meta.setdefault("csv_delimiter", ";")

BUILDERS = {"meta": lambda records, site, fmt: build_meta(records, site, fmt)}


def parse_feed_settings(form) -> tuple[dict, str | None]:
    """VIN switch + Meta location (region, coordinates). Returns (values, error)."""
    values = {
        "feed_include_vin": "true" if form.get("feed_include_vin") in ("1", "on") else "false",
        "feed_region": " ".join(str(form.get("feed_region", "")).split())[:60],
    }
    for key, limit in (("feed_latitude", 90), ("feed_longitude", 180)):
        raw = str(form.get(key, "")).strip().replace(",", ".")
        if not raw:
            values[key] = ""
            continue
        try:
            number = float(raw)
        except ValueError:
            return values, "Koordinate upišite kao decimalne brojeve, npr. 45.8150 i 15.9819."
        if not -limit <= number <= limit:
            return values, "Koordinate su izvan dopuštenog raspona."
        values[key] = f"{number:.6f}".rstrip("0").rstrip(".")
    return values, None


def build(db: Session, portal: str, fmt: str) -> bytes:
    from app.services.site import get_site

    site = get_site()
    records = [record(v, site) for v in feeds.feed_vehicles(db)]
    builder = BUILDERS.get(portal)
    if builder:
        return builder(records, site, fmt)
    return build_generic(portal, records, site, fmt)


def missing_fields(data: dict, required: list[str]) -> list[str]:
    missing = []
    for key in required:
        if key == "first_registration" and data.get("condition") == "new":
            continue  # new vehicles are not registered yet
        value = data.get(key)
        if value is None or value == "" or value == []:
            missing.append(key)
    return missing


def validate(db: Session) -> list[dict]:
    """Feed vehicles with missing required fields: [{vehicle, missing: [(label, portals)]}]."""
    from app.services.site import get_site

    site = get_site()
    problems = []
    for vehicle in feeds.feed_vehicles(db):
        data = record(vehicle, site)
        by_field: dict[str, list[str]] = {}
        for meta in PORTALS.values():
            for key in missing_fields(data, meta["required"]):
                by_field.setdefault(key, []).append(meta["label"])
        if by_field:
            problems.append(
                {
                    "vehicle": vehicle,
                    "missing": [
                        (FIELD_LABELS.get(k, k), portals) for k, portals in by_field.items()
                    ],
                }
            )
    return problems
