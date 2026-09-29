"""Full demo data set (spec chapter 19) — placeholder content only.

16 vehicles (8 cars, 3 vans, 2 motorcycles, 2 campers, 1 truck; 12 active, 1 reserved,
2 sold — 10 and 45 days ago, 1 draft; 3 featured; one "price on request", one with an
old price, 2 new with consumption/CO2), each with 5–8 generated photos pushed through
app/services/images.py like a real upload; 60 days of views; 10 inquiries with notes;
15 subscribers; 1 sent + 1 draft campaign; demo users; demo audit entries.

Idempotent via the `demo_seeded` settings key; `reset_demo()` wipes demo tables first.
"""

from __future__ import annotations

import logging
import os
import random
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import utcnow
from app.models import (
    ROLE_OWNER,
    ROLE_SALESPERSON,
    AuditLog,
    Campaign,
    CampaignDelivery,
    ContactClick,
    Inquiry,
    InquiryNote,
    Make,
    Page,
    Setting,
    Subscriber,
    User,
    Vehicle,
    VehicleImage,
    VehicleModel,
    VehiclePriceHistory,
    VehicleSlugHistory,
    VehicleView,
)
from app.security import email_hash, hash_token
from app.services import newsletter as nl
from app.services.financing import financeable
from app.services.images import delete_variants, save_vehicle_image
from app.services.placeholder_images import vehicle_placeholder
from app.services.site import get_value, invalidate_site_cache, set_values
from app.services.vehicles import change_status, create_vehicle
from app.utils import local_today, slugify
from app.vehicle_schema import power_hp, validate_attributes, validate_common, validate_equipment

log = logging.getLogger("seed")
MARKER = "demo_seeded"

# Realistic customer messages for the demo inquiries (no personal data: "Ime Prezime").
INQUIRY_MESSAGES = [
    "Poštovani, zanima me je li vozilo još dostupno i je li moguća zamjena za moje vozilo?",
    "Dobar dan, može li se dogovoriti probna vožnja ovaj tjedan? Hvala unaprijed.",
    "Zanima me mogućnost financiranja na 60 rata. Koliko bi iznosilo učešće?",
    "Je li vozilo imalo prometnu nezgodu i je li servisna povijest dostupna na uvid?",
    "Molim vas ponudu uz R1 račun, tražimo vozilo za tvrtku. Je li cijena fiksna?",
]
NOTES = [
    "Nazvao kupca, dogovoren pregled u subotu u 10 h.",
    "Poslana informativna ponuda financiranja emailom.",
    "Kupac dolazi s vozilom na procjenu za zamjenu.",
    "Vozilo prodano drugom kupcu — javljeno, ponuđena slična vozila.",
]


TYPE_TEXT = {
    "car": (
        "Udoban i pouzdan automobil za svakodnevnu vožnju i duža putovanja. Interijer je uredan "
        "i očuvan, a vozilo je prije objave oglasa prošlo servisnu provjeru."
    ),
    "van": (
        "Praktično vozilo za posao i obitelj — prostran teretni prostor, ekonomičan motor i "
        "jednostavno održavanje. Odličan izbor za obrtnike i tvrtke."
    ),
    "motorcycle": (
        "Motocikl je redovno održavan i spreman za sezonu. Uz vozilo dobivate oba ključa i "
        "kompletnu dokumentaciju."
    ),
    "camper": (
        "Kamper je spreman za putovanja: stambeni dio je čist i funkcionalan, a plinska, "
        "električna i vodovodna instalacija provjerene su prije prodaje."
    ),
    "truck": (
        "Gospodarsko vozilo u besprijekornom voznom stanju, redovno servisirano u ovlaštenom "
        "servisu. Pogodno za domaći i međunarodni prijevoz."
    ),
}


def description(spec: dict) -> str:
    """Realistic generic ad text (demo): intro from the vehicle data, highlighted equipment,
    a paragraph per vehicle type and a closing call to action. No company data."""
    from app.vehicle_schema import EQUIPMENT_BY_CODE

    name = f"{spec['make']} {spec['model']} {spec.get('variant', '')}".strip()
    km = f"{spec.get('mileage_km') or 0:,}".replace(",", ".")
    if spec["condition"] == "new":
        intro = f"Novi {name} ({spec['year']}.), nekorišten i spreman za isporuku."
    else:
        intro = f"{name} iz {spec['year']}. godine, {km} km, u odličnom stanju."
        if spec.get("first_owner") and spec.get("service_book"):
            intro += " Vozilo je od prvog vlasnika, s urednom servisnom knjižicom."
        elif spec.get("service_book"):
            intro += " Uz vozilo ide uredna servisna knjižica."
    features = [EQUIPMENT_BY_CODE[c]["label"] for c in spec.get("eq", []) if c in EQUIPMENT_BY_CODE]
    parts = [f"<p>{intro}</p>"]
    if features:
        items = "".join(f"<li>{label}</li>" for label in features[:6])
        parts.append(f"<h3>Istaknuta oprema</h3>\n<ul>{items}</ul>")
    parts.append(f"<p>{TYPE_TEXT[spec['type']]}</p>")
    parts.append(
        "<p>Vozilo je moguće pogledati i isprobati uz prethodni dogovor. Za dodatne informacije, "
        "fotografije ili informativnu ponudu financiranja javite nam se putem obrasca ili "
        "telefonom.</p>"
    )
    return "\n".join(parts)


COMMON_EQ = ["abs", "esp", "zracni_jastuci", "klima", "bluetooth", "alu_felge", "tempomat"]
RICH_EQ = COMMON_EQ + [
    "automatska_klima",
    "navigacija",
    "parking_senzori",
    "kamera",
    "grijana_sjedala",
    "led_svjetla",
    "carplay",
    "start_stop",
    "isofix",
]

# Raw values as they would come from the admin form (validated with the schema).
VEHICLES: list[dict] = [
    # --- 8 cars ---------------------------------------------------------------------------
    dict(
        type="car",
        make="Škoda",
        model="Octavia",
        variant="2.0 TDI Style",
        condition="used",
        status="active",
        year=2020,
        first_registration="2020-06",
        mileage_km=98000,
        price_eur=21900,
        tax_type="marza",
        fuel="dizel",
        transmission="automatski",
        power_kw=110,
        engine_ccm=1968,
        drive="prednji",
        color="siva",
        color_metallic=True,
        doors=5,
        seats=5,
        euro_norm="euro6d",
        first_owner=True,
        service_book=True,
        registered_until="2027-06",
        attrs={"body_type": "karavan"},
        eq=RICH_EQ,
        featured=True,
        images=8,
        published_days=4,
    ),
    dict(
        type="car",
        make="Volkswagen",
        model="Golf",
        variant="1.5 TSI Life",
        condition="new",
        status="active",
        year=2026,
        mileage_km=10,
        price_eur=28450,
        tax_type="pdv",
        fuel="benzin",
        transmission="rucni",
        power_kw=85,
        engine_ccm=1498,
        drive="prednji",
        color="bijela",
        doors=5,
        seats=5,
        euro_norm="euro6e",
        fuel_consumption_l100="5,4",
        co2_g_km=123,
        warranty_months=24,
        attrs={"body_type": "hatchback"},
        eq=RICH_EQ,
        featured=True,
        images=7,
        published_days=2,
    ),
    dict(
        type="car",
        make="BMW",
        model="Serija 3",
        variant="320d xDrive M Sport",
        condition="used",
        status="active",
        year=2019,
        first_registration="2019-03",
        mileage_km=145000,
        price_eur=27900,
        price_old_eur=29900,
        tax_type="marza",
        fuel="dizel",
        transmission="automatski",
        power_kw=140,
        engine_ccm=1995,
        drive="4x4",
        color="crna",
        color_metallic=True,
        doors=4,
        seats=5,
        euro_norm="euro6d_temp",
        service_book=True,
        registered_until="2027-03",
        attrs={"body_type": "limuzina"},
        eq=RICH_EQ + ["kozna_sjedala", "head_up"],
        images=8,
        published_days=11,
    ),
    dict(
        type="car",
        make="Toyota",
        model="RAV4",
        variant="2.5 Hybrid Style",
        condition="used",
        status="reserved",
        year=2021,
        first_registration="2021-09",
        mileage_km=62000,
        price_eur=32500,
        tax_type="pdv",
        fuel="hibrid",
        transmission="automatski",
        power_kw=160,
        engine_ccm=2487,
        drive="4x4",
        color="bijela",
        color_metallic=True,
        doors=5,
        seats=5,
        euro_norm="euro6d",
        first_owner=True,
        service_book=True,
        warranty_months=12,
        attrs={"body_type": "suv"},
        eq=RICH_EQ,
        images=6,
        published_days=18,
    ),
    dict(
        type="car",
        make="Renault",
        model="Clio",
        variant="1.0 TCe Evolution",
        condition="used",
        status="active",
        year=2022,
        first_registration="2022-04",
        mileage_km=28000,
        price_eur=14900,
        tax_type="marza",
        fuel="benzin",
        transmission="rucni",
        power_kw=67,
        engine_ccm=999,
        drive="prednji",
        color="crvena",
        doors=5,
        seats=5,
        euro_norm="euro6d",
        first_owner=True,
        service_book=True,
        attrs={"body_type": "hatchback"},
        eq=COMMON_EQ + ["carplay"],
        images=6,
        published_days=6,
    ),
    dict(
        type="car",
        make="Mercedes-Benz",
        model="E-klasa",
        variant="E 220 d AMG Line",
        condition="used",
        status="active",
        year=2018,
        first_registration="2018-11",
        mileage_km=168000,
        price_on_request=True,
        tax_type="marza",
        fuel="dizel",
        transmission="automatski",
        power_kw=143,
        engine_ccm=1950,
        drive="straznji",
        color="srebrna",
        color_metallic=True,
        doors=4,
        seats=5,
        euro_norm="euro6c",
        service_book=True,
        attrs={"body_type": "limuzina"},
        eq=RICH_EQ + ["kozna_sjedala", "elektricna_sjedala", "premium_zvuk"],
        images=7,
        published_days=25,
    ),
    dict(
        type="car",
        make="Kia",
        model="EV6",
        variant="77 kWh GT-Line AWD",
        condition="new",
        status="active",
        year=2026,
        mileage_km=5,
        price_eur=52990,
        tax_type="pdv",
        fuel="elektricni",
        transmission="automatski",
        power_kw=239,
        drive="4x4",
        color="siva",
        color_metallic=True,
        doors=5,
        seats=5,
        energy_consumption_kwh100="17,2",
        electric_range_km=506,
        battery_kwh="77,4",
        warranty_months=84,
        attrs={"body_type": "suv"},
        eq=RICH_EQ + ["panoramski_krov", "bezicno_punjenje"],
        images=6,
        published_days=9,
    ),
    dict(
        type="car",
        make="Peugeot",
        model="3008",
        variant="1.5 BlueHDi Allure",
        condition="used",
        status="sold",
        sold_days=10,
        year=2019,
        first_registration="2019-04",
        mileage_km=120000,
        price_eur=17500,
        tax_type="marza",
        fuel="dizel",
        transmission="automatski",
        power_kw=96,
        engine_ccm=1499,
        drive="prednji",
        color="plava",
        doors=5,
        seats=5,
        euro_norm="euro6d_temp",
        service_book=True,
        attrs={"body_type": "suv"},
        eq=COMMON_EQ + ["navigacija", "kamera"],
        images=5,
        published_days=40,
    ),
    # --- 3 vans ---------------------------------------------------------------------------
    dict(
        type="van",
        make="Ford",
        model="Transit Custom",
        variant="2.0 EcoBlue Trend",
        condition="used",
        status="active",
        year=2021,
        first_registration="2021-07",
        mileage_km=88000,
        price_eur=24900,
        tax_type="bez_pdv",
        fuel="dizel",
        transmission="rucni",
        power_kw=96,
        engine_ccm=1995,
        drive="prednji",
        color="bijela",
        seats=3,
        euro_norm="euro6d",
        service_book=True,
        attrs={
            "van_type": "furgon",
            "payload_kg": "1100",
            "cargo_volume_m3": "6,0",
            "wheelbase": "kratki",
            "roof_height": "H1",
        },
        eq=["abs", "esp", "klima", "bluetooth", "pregrada", "klizna_vrata", "tempomat"],
        images=6,
        published_days=14,
    ),
    dict(
        type="van",
        make="Volkswagen",
        model="Transporter",
        variant="2.0 TDI Comfortline",
        condition="used",
        status="active",
        year=2019,
        first_registration="2019-02",
        mileage_km=132000,
        price_eur=29900,
        tax_type="pdv",
        fuel="dizel",
        transmission="rucni",
        power_kw=110,
        engine_ccm=1968,
        drive="prednji",
        color="siva",
        color_metallic=True,
        seats=9,
        euro_norm="euro6",
        attrs={"van_type": "putnicki", "wheelbase": "dugi", "roof_height": "H1"},
        eq=["abs", "esp", "klima", "parking_senzori", "tempomat", "kuka", "bluetooth"],
        images=6,
        published_days=20,
    ),
    dict(
        type="van",
        make="Mercedes-Benz",
        model="Sprinter",
        variant="316 CDI",
        condition="used",
        status="draft",
        year=2018,
        first_registration="2018-10",
        mileage_km=190000,
        price_eur=22500,
        tax_type="bez_pdv",
        fuel="dizel",
        transmission="rucni",
        power_kw=120,
        engine_ccm=2143,
        drive="straznji",
        color="bijela",
        seats=3,
        euro_norm="euro6",
        attrs={"van_type": "sasija", "payload_kg": "1450", "wheelbase": "dugi"},
        eq=["abs", "esp", "klima", "kuka"],
        images=5,
        published_days=None,
    ),
    # --- 2 motorcycles --------------------------------------------------------------------
    dict(
        type="motorcycle",
        make="Yamaha",
        model="MT-07",
        variant="ABS",
        condition="used",
        status="active",
        year=2021,
        first_registration="2021-05",
        mileage_km=12500,
        price_eur=6490,
        tax_type="marza",
        fuel="benzin",
        transmission="rucni",
        power_kw=54,
        engine_ccm=689,
        color="plava",
        euro_norm="euro5",
        first_owner=True,
        service_book=True,
        attrs={
            "moto_type": "naked",
            "cylinders": "2",
            "cooling": "tekucina",
            "final_drive": "lanac",
            "abs": "1",
            "a2_suitable": "1",
        },
        eq=["abs", "led_svjetla", "digitalni_instrumenti"],
        images=6,
        published_days=8,
    ),
    dict(
        type="motorcycle",
        make="KTM",
        model="890 Adventure",
        variant="",
        condition="used",
        status="sold",
        sold_days=45,
        year=2022,
        first_registration="2022-03",
        mileage_km=9800,
        price_eur=11900,
        tax_type="marza",
        fuel="benzin",
        transmission="rucni",
        power_kw=77,
        engine_ccm=889,
        color="narancasta",
        euro_norm="euro5",
        attrs={
            "moto_type": "enduro",
            "cylinders": "2",
            "cooling": "tekucina",
            "final_drive": "lanac",
            "abs": "1",
        },
        eq=["abs", "kontrola_proklizavanja", "nacini_voznje", "kofer"],
        images=5,
        published_days=58,
    ),
    # --- 2 campers ------------------------------------------------------------------------
    dict(
        type="camper",
        make="Adria",
        model="Coral",
        variant="670 SL",
        condition="used",
        status="active",
        year=2020,
        first_registration="2020-06",
        mileage_km=42000,
        price_eur=64900,
        tax_type="pdv",
        fuel="dizel",
        transmission="rucni",
        power_kw=103,
        engine_ccm=2287,
        drive="prednji",
        color="bijela",
        seats=4,
        euro_norm="euro6d_temp",
        service_book=True,
        attrs={
            "camper_type": "poluintegrirani",
            "berths": "4",
            "length_m": "7,4",
            "gross_weight_kg": "3500",
            "wc_shower": "1",
            "heating": "plinsko",
        },
        eq=[
            "abs",
            "esp",
            "klima",
            "tempomat",
            "kamera",
            "solarni_panel",
            "tenda",
            "nosac_bicikala",
            "hladnjak",
            "kuhalo",
        ],
        featured=True,
        images=8,
        published_days=5,
    ),
    dict(
        type="camper",
        make="Knaus",
        model="Sky TI",
        variant="700 MEG",
        condition="used",
        status="active",
        year=2019,
        first_registration="2019-09",
        mileage_km=58000,
        price_eur=59900,
        tax_type="marza",
        fuel="dizel",
        transmission="rucni",
        power_kw=118,
        engine_ccm=2287,
        drive="prednji",
        color="bijela",
        seats=4,
        euro_norm="euro6",
        attrs={
            "camper_type": "poluintegrirani",
            "berths": "5",
            "length_m": "7,0",
            "gross_weight_kg": "3500",
            "wc_shower": "1",
            "heating": "dizelsko",
        },
        eq=["abs", "klima", "tempomat", "tenda", "satelitska", "hladnjak", "kuhalo"],
        images=6,
        published_days=30,
    ),
    # --- 1 truck --------------------------------------------------------------------------
    dict(
        type="truck",
        make="MAN",
        model="TGX",
        variant="18.510 4x2 BLS",
        condition="used",
        status="active",
        year=2019,
        first_registration="2019-01",
        mileage_km=520000,
        price_eur=54500,
        tax_type="bez_pdv",
        fuel="dizel",
        transmission="automatski",
        power_kw=375,
        engine_ccm=12419,
        color="bijela",
        euro_norm="euro6",
        attrs={
            "truck_body": "tegljac",
            "gross_weight_kg": "18000",
            "axles": "2",
            "cabin": "spavaca",
            "tachograph": "1",
        },
        eq=["abs", "esp", "klima", "tempomat", "retarder", "parkirna_klima", "navigacija"],
        images=6,
        published_days=16,
    ),
]


def _form_values(spec: dict) -> dict:
    """Spec -> raw strings (like the admin form) for schema validation."""
    raw = {}
    skip = {
        "type",
        "make",
        "model",
        "attrs",
        "eq",
        "images",
        "published_days",
        "status",
        "sold_days",
        "featured",
    }
    for key, value in spec.items():
        if key in skip:
            continue
        if isinstance(value, bool):
            raw[key] = "1" if value else ""
        else:
            raw[key] = str(value)
    raw["featured"] = "1" if spec.get("featured") else ""
    return raw


def _get_model(db: Session, make_name: str, model_name: str, vehicle_type: str):
    make = db.scalar(select(Make).where(Make.slug == slugify(make_name)))
    if make is None:
        make = Make(name=make_name, slug=slugify(make_name))
        db.add(make)
        db.flush()
    model = db.scalar(
        select(VehicleModel).where(
            VehicleModel.make_id == make.id, VehicleModel.slug == slugify(model_name)
        )
    )
    if model is None:
        model = VehicleModel(
            make_id=make.id, name=model_name, slug=slugify(model_name), vehicle_type=vehicle_type
        )
        db.add(model)
        db.flush()
    return make, model


def seed_vehicles(db: Session, owner: User, company: str, image_size=(1600, 1200)) -> list:
    now = utcnow()
    created = []
    for index, spec in enumerate(VEHICLES):
        make, model = _get_model(db, spec["make"], spec["model"], spec["type"])
        clean, errors = validate_common(spec["type"], _form_values(spec))
        attributes, attr_errors = validate_attributes(spec["type"], spec["attrs"])
        if errors or attr_errors:
            raise ValueError(f"Demo vehicle {spec['make']} {spec['model']}: {errors} {attr_errors}")
        values = dict(clean)
        values.update(
            vehicle_type=spec["type"],
            make_id=make.id,
            model_id=model.id,
            attributes=attributes,
            equipment=validate_equipment(spec["type"], spec["eq"]),
            power_hp=power_hp(clean.get("power_kw")),
            description=description(spec),
            status="draft",
        )
        vehicle = create_vehicle(db, values, owner)
        published_days = spec.get("published_days")
        vehicle.created_at = now - timedelta(days=(published_days or 1) + 1, hours=index)
        if spec["status"] != "draft":
            change_status(vehicle, "active")
            vehicle.published_at = now - timedelta(days=published_days, hours=index * 3)
            if spec["status"] in ("reserved", "sold"):
                change_status(vehicle, spec["status"])
            if spec["status"] == "sold":
                vehicle.sold_at = now - timedelta(days=spec["sold_days"])
        created.append((vehicle, spec["images"]))
    db.flush()

    # Photos go through the real upload pipeline (validation, WebP variants, no EXIF).
    # Generation/encoding is CPU bound and Pillow releases the GIL -> use a thread pool.
    jobs = [
        (vehicle.id, vehicle.vehicle_type, n, count)
        for vehicle, count in created
        for n in range(1, count + 1)
    ]

    def process(job):
        vehicle_id, kind, n, count = job
        data = vehicle_placeholder(n, count, company, size=image_size, kind=kind)
        key, processed = save_vehicle_image(vehicle_id, data)
        return vehicle_id, n, key, processed.width, processed.height

    workers = min(8, (os.cpu_count() or 2))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for vehicle_id, n, key, width, height in pool.map(process, jobs):
            db.add(
                VehicleImage(
                    vehicle_id=vehicle_id,
                    file_key=key,
                    sort_order=n - 1,
                    width=width,
                    height=height,
                )
            )
    db.flush()
    return [vehicle for vehicle, _count in created]


# Price history for the demo: (make, [(days ago, old price, new price)]). The first row of
# every published vehicle is its starting price; BMW and Škoda get recent drops (Škoda two in a
# row, so its "old price" stays the first one), Toyota an increase (never shown publicly).
DEMO_PRICE_CHANGES = {
    "BMW": [(12, 29900, 27900)],
    "Škoda": [(24, 23900, 22900), (5, 22900, 21900)],
    "Toyota": [(8, None, None)],  # +900 € (filled in from the current price)
}


def seed_price_history(db: Session, vehicles: list, owner: User) -> int:
    from app.services.pricing import effective_price

    now = utcnow()
    count = 0
    for vehicle in vehicles:
        if vehicle.published_at is None:
            continue
        changes = DEMO_PRICE_CHANGES.get(vehicle.make.name if vehicle.make else "", [])
        price = effective_price(vehicle)
        if changes and changes[0][1] is None and price:  # increase scenario
            changes = [(changes[0][0], price - 900, price)]
        start_price = changes[0][1] if changes else price
        db.add(
            VehiclePriceHistory(
                vehicle_id=vehicle.id,
                old_price=None,
                new_price=start_price,
                changed_at=vehicle.published_at,
                user_id=owner.id,
            )
        )
        count += 1
        for days_ago, old, new in changes:
            changed_at = max(
                now - timedelta(days=days_ago), vehicle.published_at + timedelta(hours=6)
            )
            db.add(
                VehiclePriceHistory(
                    vehicle_id=vehicle.id,
                    old_price=old,
                    new_price=new,
                    changed_at=changed_at,
                    user_id=owner.id,
                )
            )
            count += 1
        if changes and changes[-1][2] < changes[0][1] and not vehicle.price_old_eur:
            vehicle.price_old_eur = changes[0][1]  # like the admin does on a price drop
    return count


def seed_views(db: Session, vehicles: list, rng: random.Random) -> int:
    today = local_today()
    total = 0
    for vehicle in vehicles:
        if vehicle.published_at is None:
            continue
        start = max(today - timedelta(days=59), vehicle.published_at.date())
        end = today
        if vehicle.sold_at:
            end = min(today, vehicle.sold_at.date() + timedelta(days=5))
        vehicle_total = 0
        day = start
        while day <= end:
            base = rng.randint(0, 40)
            if day.weekday() >= 5:
                base = int(base * 0.6)
            if vehicle.featured:
                base = int(base * 1.5)
            if base:
                db.add(VehicleView(vehicle_id=vehicle.id, date=day, count=base))
                vehicle_total += base
            day += timedelta(days=1)
        vehicle.views_total = vehicle_total
        total += vehicle_total
    return total


def _demo_financing(vehicle) -> dict:
    """Financing request parameters as the public form stores them (30 % down, 60 months)."""
    from app.services.financing import config, monthly_payment, round_cents

    price = float(vehicle.price_eur)
    down = round(price * 0.3, -2)
    amount = round_cents(price - down)
    rate = config()["rate"]
    return {
        "price": price,
        "down_payment": down,
        "amount": amount,
        "months": 60,
        "rate": rate,
        "payment": monthly_payment(amount, rate, 60),
    }


def seed_inquiries(db: Session, vehicles: list, seller: User, owner: User, policy: str) -> int:
    now = utcnow()
    public = [v for v in vehicles if v.status in ("active", "reserved")]
    plan = [
        # (type, status, days ago, vehicle index or None, assigned)
        ("vehicle", "new", 0.2, 0, False),
        ("viewing", "new", 1, 2, False),
        ("vehicle", "new", 3, 4, False),
        ("general", "new", 4, None, False),
        ("vehicle", "contacted", 6, 1, True),
        ("viewing", "contacted", 9, 9, True),
        ("vehicle", "contacted", 13, 3, True),
        ("general", "contacted", 17, None, False),
        ("vehicle", "closed", 22, 5, False),
        ("viewing", "closed", 28, 7, False),
        # Paket Standard: upit za financiranje (parametri u `extra`).
        ("financing", "new", 0.5, 1, False),
    ]
    for n, (kind, status, days_ago, vehicle_index, assigned) in enumerate(plan, start=1):
        created_at = now - timedelta(days=days_ago, hours=n)
        vehicle = public[vehicle_index] if vehicle_index is not None else None
        extra = None
        if kind == "financing":
            vehicle = next(v for v in public[vehicle_index:] + public if financeable(v))
            extra = {"financing": _demo_financing(vehicle)}
        inquiry = Inquiry(
            type=kind,
            vehicle_id=vehicle.id if vehicle else None,
            name="Ime Prezime",
            email=f"kupac{n}@primjer.hr",
            phone="+385XXXXXXXXXX",
            message=INQUIRY_MESSAGES[n % len(INQUIRY_MESSAGES)],
            preferred_date=(now + timedelta(days=2 + n % 5)).replace(
                hour=9 + n % 6, minute=0, second=0, microsecond=0
            )
            if kind == "viewing"
            else None,
            status=status,
            extra=extra,
            assigned_to=seller.id if assigned else None,
            consent_at=created_at,
            consent_ip="192.0.2.10",
            consent_user_agent="Mozilla/5.0 (demo)",
            consent_policy_version=policy,
            source_url=f"/vozila/{vehicle.slug}" if vehicle else "/kontakt",
            created_at=created_at,
            contacted_at=created_at + timedelta(hours=3 + n) if status != "new" else None,
            closed_at=created_at + timedelta(days=2) if status == "closed" else None,
        )
        if n == 6:  # confirmed viewing (calendar invitation sent, same UID as the request)
            inquiry.scheduled_at = inquiry.preferred_date + timedelta(hours=1)
            inquiry.extra = {"schedule_seq": 1}
        db.add(inquiry)
        db.flush()
        if n in (5, 6, 7, 9):
            author = seller if n != 9 else owner
            db.add(
                InquiryNote(
                    inquiry_id=inquiry.id,
                    user_id=author.id,
                    body=NOTES[(5, 6, 7, 9).index(n)],
                    created_at=created_at + timedelta(hours=4),
                )
            )
    return len(plan)


def seed_subscribers(db: Session, policy: str) -> list[Subscriber]:
    now = utcnow()
    confirmed = []
    sources = ["footer", "home", "vehicle", "footer", "home"]
    for n in range(1, 11):
        address = f"citatelj{n}@primjer.hr"
        sub = Subscriber(
            email=address,
            email_hash=email_hash(address),
            status="pending",
            source=sources[n % 5],
            consent_at=now - timedelta(days=50 - n * 4),
            consent_ip="192.0.2.20",
            consent_user_agent="Mozilla/5.0 (demo)",
            consent_policy_version=policy,
            created_at=now - timedelta(days=50 - n * 4),
        )
        db.add(sub)
        db.flush()
        sub.status = "confirmed"
        sub.confirmed_at = sub.created_at + timedelta(minutes=20)
        sub.unsubscribe_token_hash = hash_token(nl.unsubscribe_token(sub))
        confirmed.append(sub)
    for n in range(11, 14):
        address = f"citatelj{n}@primjer.hr"
        db.add(
            Subscriber(
                email=address,
                email_hash=email_hash(address),
                status="pending",
                source="footer",
                consent_at=now - timedelta(days=n - 10),
                consent_ip="192.0.2.21",
                consent_policy_version=policy,
                confirm_sent_at=now - timedelta(days=n - 10),
                confirm_token_hash=email_hash(f"demo-token-{n}"),
                created_at=now - timedelta(days=n - 10),
            )
        )
    for n in range(14, 16):
        db.add(
            Subscriber(
                email=None,
                email_hash=email_hash(f"citatelj{n}@primjer.hr"),
                status="unsubscribed",
                source="home",
                consent_at=now - timedelta(days=80),
                consent_policy_version=policy,
                confirmed_at=now - timedelta(days=79),
                unsubscribed_at=now - timedelta(days=15 + n),
                created_at=now - timedelta(days=80),
            )
        )
    db.flush()
    return confirmed


def seed_campaigns(db: Session, owner: User, subscribers: list, vehicles: list) -> None:
    now = utcnow()
    cards = "".join(nl.vehicle_card_html(v) for v in vehicles[:2])
    sent = Campaign(
        subject="Nova vozila u ponudi",
        body_html=nl.clean_campaign_html(
            "<p>Pozdrav!</p><p>Ovaj tjedan u ponudu su stigla nova vozila — izdvojili smo "
            f"nekoliko najzanimljivijih.</p>{cards}<p>Vozila možete pogledati i isprobati uz "
            "prethodni dogovor. Javite nam se odgovorom na ovaj email.</p>"
        ),
        status="sent",
        recipients_count=len(subscribers),
        sent_at=now - timedelta(days=12),
        created_by=owner.id,
        created_at=now - timedelta(days=13),
    )
    db.add(sent)
    db.flush()
    for index, sub in enumerate(subscribers):
        failed = index == len(subscribers) - 1
        db.add(
            CampaignDelivery(
                campaign_id=sent.id,
                subscriber_id=sub.id,
                status="failed" if failed else "sent",
                error="Brevo HTTP 400: invalid recipient (demo)" if failed else None,
                created_at=sent.sent_at,
            )
        )
    db.add(
        Campaign(
            subject="Proljetna akcija — besplatan servis uz kupnju",
            body_html=(
                "<h2>Proljetna akcija</h2><p>Uz svako vozilo kupljeno do kraja mjeseca "
                "poklanjamo prvi redovni servis. Pogledajte ponudu na našoj stranici.</p>"
            ),
            status="draft",
            created_by=owner.id,
            created_at=now - timedelta(days=10),
        )
    )


def seed_audit(db: Session, admin: User, owner: User, seller: User, vehicles: list) -> None:
    now = utcnow()
    entries = [
        (admin, "user.login", "user", admin.id, None, 30),
        (owner, "user.login", "user", owner.id, None, 20),
        (owner, "settings.update", "settings", None, {"keys": ["company_phone"]}, 19),
        (owner, "vehicle.create", "vehicle", vehicles[0].id, {"type": "car"}, 18),
        (seller, "vehicle.images", "vehicle", vehicles[0].id, {"added": 8}, 18),
        (
            seller,
            "vehicle.status",
            "vehicle",
            vehicles[3].id,
            {"from": "active", "to": "reserved"},
            12,
        ),
        (owner, "campaign.send", "campaign", 1, {"recipients": 10}, 12),
        (seller, "inquiry.status", "inquiry", 5, {"from": "new", "to": "contacted"}, 6),
        (seller, "inquiry.note", "inquiry", 5, {"note_id": 1}, 6),
        (owner, "page.update", "page", "o-nama", {"version": 2}, 3),
    ]
    for user, action, entity_type, entity_id, details, days_ago in entries:
        db.add(
            AuditLog(
                user_id=user.id,
                action=action,
                entity_type=entity_type,
                entity_id=str(entity_id) if entity_id is not None else None,
                details=details,
                ip="192.0.2.1",
                created_at=now - timedelta(days=days_ago, hours=2),
            )
        )


def _ensure_user(db: Session, email: str, name: str, role: str) -> User:
    from app.security import hash_password

    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            email=email,
            name=name,
            role=role,
            password_hash=hash_password(get_settings().SEED_PASSWORD),
        )
        db.add(user)
        db.flush()
    return user


def seed_demo(db: Session, image_size=(1600, 1200)) -> dict:
    """Create the demo data set once (idempotent via the `demo_seeded` marker)."""
    if db.get(Setting, MARKER) is not None:
        return {"skipped": True}
    from app.seed import SUPERADMIN_EMAIL

    admin = db.scalar(select(User).where(User.email == SUPERADMIN_EMAIL))
    owner = _ensure_user(db, "vlasnik@domena.com", "Ime Prezime", ROLE_OWNER)
    seller = _ensure_user(db, "prodavac1@domena.com", "Prodavač 1", ROLE_SALESPERSON)
    company = get_value(db, "company_name")
    policy = get_value(db, "privacy_policy_version")
    rng = random.Random(42)

    # Demo WhatsApp number (paket Standard); placeholder, replaced by the dealer in settings.
    if not get_value(db, "whatsapp_number"):
        set_values(db, {"whatsapp_number": "+385XXXXXXXXXX"})
    vehicles = seed_vehicles(db, owner, company, image_size)
    seed_price_history(db, vehicles, owner)
    views = seed_views(db, vehicles, rng)
    inquiries = seed_inquiries(db, vehicles, seller, owner, policy)
    subscribers = seed_subscribers(db, policy)
    public = [v for v in vehicles if v.status == "active"]
    seed_campaigns(db, owner, subscribers, public)
    seed_audit(db, admin or owner, owner, seller, vehicles)
    db.add(Setting(key=MARKER, value=date.today().isoformat()))
    db.commit()
    invalidate_site_cache()
    return {
        "vehicles": len(vehicles),
        "views": views,
        "inquiries": inquiries,
        "subscribers": 15,
        "campaigns": 2,
    }


def reset_demo(db: Session) -> None:
    """Delete demo content (vehicles + photos, inquiries, newsletter, views, demo users)."""
    for image in db.scalars(select(VehicleImage)):
        delete_variants(image.file_key)
    for model in (
        VehiclePriceHistory,
        ContactClick,
        CampaignDelivery,
        Campaign,
        InquiryNote,
        Inquiry,
        Subscriber,
        VehicleView,
        VehicleImage,
        VehicleSlugHistory,
        Vehicle,
        AuditLog,
    ):
        db.execute(delete(model))
    db.execute(delete(User).where(User.email.in_(["vlasnik@domena.com", "prodavac1@domena.com"])))
    db.execute(delete(Setting).where(Setting.key == MARKER))
    reset_demo_content(db)
    db.commit()


# Marketing texts restored by --reset-demo (company data and legal pages are never touched).
DEMO_CONTENT_SETTINGS = ("hero_title", "hero_subtitle", "footer_text", "why_us")
DEMO_CONTENT_PAGES = ("o-nama", "usluge")


def reset_demo_content(db: Session) -> None:
    """Restore the demo marketing texts (home, footer, "why us", O nama, Usluge) to defaults."""
    from app.seed_content import PAGES
    from app.services.site import DEFAULTS, invalidate_site_cache, set_values

    set_values(db, {key: DEFAULTS[key] for key in DEMO_CONTENT_SETTINGS})
    defaults = {page["slug"]: page for page in PAGES}
    for page in db.scalars(select(Page).where(Page.slug.in_(DEMO_CONTENT_PAGES))):
        page.title = defaults[page.slug]["title"]
        page.body_html = defaults[page.slug]["body_html"]
        page.version = (page.version or 0) + 1
        page.is_published = True
    invalidate_site_cache()
