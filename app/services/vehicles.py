"""Vehicle business logic shared by admin and public routes.

Admin part (phase 3): title/slug generation with slug history, status
transitions, duplication, deletion, form parsing/validation.
Public part (phase 4): public queries, filters, similar vehicles, view counting.
"""

from __future__ import annotations

import re
import time
import uuid
from datetime import timedelta

from sqlalchemy import and_, case, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.database import utcnow
from app.models import (
    STATUS_ACTIVE,
    STATUS_DRAFT,
    STATUS_RESERVED,
    STATUS_SOLD,
    Make,
    User,
    Vehicle,
    VehicleModel,
    VehicleSlugHistory,
    VehicleView,
)
from app.security import clean_html
from app.services.images import delete_variants
from app.utils import local_today, slugify
from app.vehicle_schema import (
    EQUIPMENT,
    EQUIPMENT_CATEGORIES,
    TYPE_CODES,
    VEHICLE_TYPES,
    allowed_transitions,
    common_fields_for,
    field_options,
    power_hp,
    type_fields,
    validate_attributes,
    validate_common,
    validate_equipment,
)


# ---------------------------------------------------------------------------
# Title and slug
# ---------------------------------------------------------------------------
def build_title(make_name: str, model_name: str | None, variant: str | None) -> str:
    return " ".join(part for part in (make_name, model_name or "", variant or "") if part).strip()


def build_slug(vehicle: Vehicle) -> str:
    """`{make}-{model}-{year}-{id}`, e.g. `bmw-320d-2019-42`."""
    base = slugify(
        f"{vehicle.make.name if vehicle.make else ''} "
        f"{vehicle.model.name if vehicle.model else ''} {vehicle.year or ''}",
        150,
    )
    return f"{base}-{vehicle.id}" if base else f"vozilo-{vehicle.id}"


def refresh_title_and_slug(db: Session, vehicle: Vehicle) -> None:
    """Regenerate title and slug; an old slug is kept in history (-> 301 redirect)."""
    db.flush()
    db.refresh(vehicle, ["make", "model"])
    vehicle.title = build_title(
        vehicle.make.name, vehicle.model.name if vehicle.model else None, vehicle.variant
    )
    new_slug = build_slug(vehicle)
    old_slug = vehicle.slug
    if old_slug == new_slug:
        return
    # If we return to a previous slug, drop it from history.
    db.execute(delete(VehicleSlugHistory).where(VehicleSlugHistory.old_slug == new_slug))
    if old_slug and not old_slug.startswith("tmp-"):
        exists = db.scalar(
            select(VehicleSlugHistory.id).where(VehicleSlugHistory.old_slug == old_slug)
        )
        if not exists:
            db.add(VehicleSlugHistory(vehicle_id=vehicle.id, old_slug=old_slug))
    vehicle.slug = new_slug


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------
def change_status(vehicle: Vehicle, new_status: str) -> str | None:
    """Apply an allowed status transition. Returns an error message or None."""
    if new_status == vehicle.status:
        return None
    if new_status not in allowed_transitions(vehicle.status):
        return "Ta promjena statusa nije dopuštena."
    now = utcnow()
    vehicle.status = new_status
    if new_status == STATUS_ACTIVE and vehicle.published_at is None:
        vehicle.published_at = now
    if new_status == STATUS_SOLD:
        vehicle.sold_at = now
    elif new_status in (STATUS_ACTIVE, STATUS_RESERVED, STATUS_DRAFT):
        vehicle.sold_at = None
    return None


# ---------------------------------------------------------------------------
# Create / duplicate / delete
# ---------------------------------------------------------------------------
def create_vehicle(db: Session, values: dict, user: User) -> Vehicle:
    vehicle = Vehicle(slug=f"tmp-{uuid.uuid4().hex}", created_by=user.id, **values)
    db.add(vehicle)
    db.flush()
    refresh_title_and_slug(db, vehicle)
    return vehicle


COPY_FIELDS = (
    "vehicle_type",
    "make_id",
    "model_id",
    "variant",
    "condition",
    "year",
    "first_registration",
    "mileage_km",
    "price_eur",
    "price_old_eur",
    "price_on_request",
    "tax_type",
    "fuel",
    "power_kw",
    "power_hp",
    "engine_ccm",
    "transmission",
    "drive",
    "color",
    "color_metallic",
    "doors",
    "seats",
    "euro_norm",
    "fuel_consumption_l100",
    "energy_consumption_kwh100",
    "electric_range_km",
    "battery_kwh",
    "co2_g_km",
    "registered_until",
    "first_owner",
    "service_book",
    "warranty_months",
    "description",
    "equipment",
    "attributes",
    "video_url",
)


def duplicate_vehicle(db: Session, vehicle: Vehicle, user: User) -> Vehicle:
    """Copy as a draft without images, VIN, views or publication dates."""
    values = {name: getattr(vehicle, name) for name in COPY_FIELDS}
    values["equipment"] = list(vehicle.equipment or [])
    values["attributes"] = dict(vehicle.attributes or {})
    values["status"] = STATUS_DRAFT
    return create_vehicle(db, values, user)


def delete_vehicle(db: Session, vehicle: Vehicle) -> None:
    """Delete the vehicle and all image variants from storage."""
    for image in list(vehicle.images):
        delete_variants(image.file_key)
    db.delete(vehicle)


def can_delete(user: User, vehicle: Vehicle) -> bool:
    """Owner+ may delete any vehicle; a salesperson only own drafts."""
    from app.permissions import can

    if can(user, "vehicles.delete_any"):
        return True
    return vehicle.status == STATUS_DRAFT and vehicle.created_by == user.id


# ---------------------------------------------------------------------------
# Form parsing
# ---------------------------------------------------------------------------
NEW_OPTION = "__new__"  # select value of "+ Nova opcija…" (label in "<name>__new")


def _pending_new_options(form, vehicle_type: str) -> tuple[list[dict], dict]:
    """Selects set to "+ Nova opcija…": [{name, key, scope, field, source, label}], errors."""
    from app.services.custom_options import clean_label

    pending, errors = [], {}
    fields = [(f, f["key"], "column") for f in common_fields_for(vehicle_type)]
    fields += [(f, f"{vehicle_type}__{f['key']}", "attributes") for f in type_fields(vehicle_type)]
    for field, name, source in fields:
        if not field.get("extensible") or form.get(name) != NEW_OPTION:
            continue
        label = clean_label(form.get(f"{name}__new", ""))
        if not label:
            errors[name] = "Upišite naziv nove opcije."
            continue
        pending.append(
            {
                "name": name,
                "key": field["key"],
                "scope": field["scope"],
                "field": field,
                "source": source,
                "label": label,
            }
        )
    return pending, errors


def _pending_equipment(form) -> list[tuple[str, str]]:
    """New equipment typed per category ("equipment_new__<cat>", comma separated)."""
    from app.services.custom_options import clean_label

    result = []
    for cat_key, _label in EQUIPMENT_CATEGORIES:
        for part in str(form.get(f"equipment_new__{cat_key}", "")).split(","):
            label = clean_label(part)
            if label and (cat_key, label) not in result:
                result.append((cat_key, label))
    return result[:20]


def _builtin_options(field: dict) -> list[tuple[str, str]]:
    from app.vehicle_schema import COMMON_BY_KEY, TYPE_FIELDS

    if "." in field["scope"]:
        type_code, key = field["scope"].split(".", 1)
        base = next(f for f in TYPE_FIELDS[type_code] if f["key"] == key)
    else:
        base = COMMON_BY_KEY[field["key"]]
    return list(base["options"])


def parse_vehicle_form(
    db: Session,
    form,
    current: Vehicle | None = None,
    user_id: int | None = None,
    created: list | None = None,
):
    """Validate the admin form. Returns (values_for_model, raw_for_rerender, errors).

    New select options ("+ Nova opcija…") and new equipment are created only when the whole
    form is valid; their labels are appended to `created` (for the audit log)."""
    from app.services import custom_options

    custom_options.refresh()  # another worker may have added options a moment ago
    raw = {key: form.get(key) for key in form}
    raw["equipment"] = form.getlist("equipment")
    errors: dict = {}

    vehicle_type = str(form.get("vehicle_type", ""))
    if vehicle_type not in TYPE_CODES:
        errors["vehicle_type"] = "Odaberite vrstu vozila."
        return {}, raw, errors

    values: dict = {"vehicle_type": vehicle_type}

    make = None
    try:
        make = db.get(Make, int(form.get("make_id", "")))
    except (TypeError, ValueError):
        make = None
    if make is None or (not make.is_active and (not current or current.make_id != make.id)):
        errors["make_id"] = "Odaberite marku."
    else:
        values["make_id"] = make.id

    model = None
    try:
        model = db.get(VehicleModel, int(form.get("model_id", "")))
    except (TypeError, ValueError):
        model = None
    if model is None or make is None or model.make_id != make.id:
        errors["model_id"] = "Odaberite model."
    elif model.vehicle_type and model.vehicle_type != vehicle_type:
        errors["model_id"] = "Model ne odgovara odabranoj vrsti vozila."
    else:
        values["model_id"] = model.id

    pending, pending_errors = _pending_new_options(form, vehicle_type)
    # Validate with the "new option" selects left empty; they get their code after saving.
    data = {key: form.get(key) for key in form}
    for name in [item["name"] for item in pending] + list(pending_errors):
        data[name] = ""
    common, common_errors = validate_common(vehicle_type, data)
    # Type-specific inputs are named "<type>__<key>" (each type has its own fieldset).
    attr_raw = {
        field["key"]: data.get(f"{vehicle_type}__{field['key']}")
        for field in type_fields(vehicle_type)
    }
    attributes, attr_errors = validate_attributes(vehicle_type, attr_raw)
    for item in pending:  # "required" is satisfied by the new option
        (common_errors if item["source"] == "column" else attr_errors).pop(item["key"], None)
    errors.update(common_errors)
    errors.update({f"{vehicle_type}__{key}": message for key, message in attr_errors.items()})
    errors.update(pending_errors)  # "Upišite naziv nove opcije" wins over "Obavezno polje"
    values.update(common)
    values["attributes"] = attributes
    values["equipment"] = validate_equipment(vehicle_type, form.getlist("equipment"))
    new_equipment = _pending_equipment(form)
    if not errors:
        for item in pending:
            code, is_new = custom_options.add_option(
                db, item["scope"], item["label"], _builtin_options(item["field"]), user_id
            )
            if item["source"] == "column":
                values[item["key"]] = code
            else:
                values["attributes"][item["key"]] = code
            if is_new and created is not None:
                created.append(item["label"])
        for category, label in new_equipment:
            code, is_new = custom_options.add_equipment(
                db, vehicle_type, category, label, EQUIPMENT, user_id
            )
            if code not in values["equipment"]:
                values["equipment"] = sorted([*values["equipment"], code])
            if is_new and created is not None:
                created.append(label)
    values["power_hp"] = power_hp(values.get("power_kw"))
    values["description"] = clean_html(str(form.get("description", ""))[:20_000])
    if values.get("price_on_request"):
        values["price_old_eur"] = None
    return values, raw, errors


# ===========================================================================
# Public part (phase 4): queries, filters, sorting, similar vehicles, views
# ===========================================================================
PER_PAGE = 12

PUBLIC_SORTS = {
    "najnovije": "Najnovije",
    "cijena_uzlazno": "Cijena: od najniže",
    "cijena_silazno": "Cijena: od najviše",
    "km_uzlazno": "Kilometraža: od najmanje",
    "godina_silazno": "Godina: od najnovije",
}

BOT_MARKERS = ("bot", "crawler", "spider", "preview", "slurp", "facebookexternalhit", "headless")
VIEW_DEDUPE_SECONDS = 6 * 3600


def public_condition():
    """Visible on the website: active, reserved, and sold for SOLD_VISIBLE_DAYS after sale."""
    cutoff = utcnow() - timedelta(days=get_settings().SOLD_VISIBLE_DAYS)
    return or_(
        Vehicle.status.in_((STATUS_ACTIVE, STATUS_RESERVED)),
        and_(Vehicle.status == STATUS_SOLD, Vehicle.sold_at >= cutoff),
    )


def public_query():
    return (
        select(Vehicle)
        .where(public_condition())
        .options(
            selectinload(Vehicle.images), selectinload(Vehicle.make), selectinload(Vehicle.model)
        )
    )


def is_publicly_visible(vehicle: Vehicle) -> bool:
    if vehicle.status in (STATUS_ACTIVE, STATUS_RESERVED):
        return True
    if vehicle.status == STATUS_SOLD and vehicle.sold_at:
        return vehicle.sold_at >= utcnow() - timedelta(days=get_settings().SOLD_VISIBLE_DAYS)
    return False


def _int_param(value, low: int = 0, high: int = 100_000_000) -> int | None:
    try:
        number = int(str(value).replace(".", "").replace(" ", ""))
    except (TypeError, ValueError):
        return None
    return number if low <= number <= high else None


def parse_filters(params) -> dict:
    """Validate public GET filters; invalid values are silently ignored."""
    filters: dict = {}
    if params.get("tip") in VEHICLE_TYPES:
        filters["tip"] = params.get("tip")
    for key in ("marka", "model"):
        value = _int_param(params.get(key), 1, 10_000_000)
        if value:
            filters[key] = value
    for key in ("cijena_od", "cijena_do", "km_do"):
        value = _int_param(params.get(key), 0, 100_000_000)
        if value is not None:
            filters[key] = value
    for key in ("godina_od", "godina_do"):
        value = _int_param(params.get(key), 1900, 2100)
        if value:
            filters[key] = value
    if params.get("gorivo") in dict(field_options("fuel")):
        filters["gorivo"] = params.get("gorivo")
    if params.get("mjenjac") in dict(field_options("transmission")):
        filters["mjenjac"] = params.get("mjenjac")
    if params.get("stanje") in ("novo", "rabljeno"):
        filters["stanje"] = params.get("stanje")
    if params.get("snizeno") in ("1", "on", "da"):
        filters["snizeno"] = 1
    if "model" in filters and "marka" not in filters:
        filters.pop("model")
    return filters


def apply_filters(stmt, filters: dict):
    if "tip" in filters:
        stmt = stmt.where(Vehicle.vehicle_type == filters["tip"])
    if "marka" in filters:
        stmt = stmt.where(Vehicle.make_id == filters["marka"])
    if "model" in filters:
        stmt = stmt.where(Vehicle.model_id == filters["model"])
    if "cijena_od" in filters:
        stmt = stmt.where(Vehicle.price_eur >= filters["cijena_od"], ~Vehicle.price_on_request)
    if "cijena_do" in filters:
        stmt = stmt.where(Vehicle.price_eur <= filters["cijena_do"], ~Vehicle.price_on_request)
    if "godina_od" in filters:
        stmt = stmt.where(Vehicle.year >= filters["godina_od"])
    if "godina_do" in filters:
        stmt = stmt.where(Vehicle.year <= filters["godina_do"])
    if "km_do" in filters:
        stmt = stmt.where(Vehicle.mileage_km <= filters["km_do"])
    if "gorivo" in filters:
        stmt = stmt.where(Vehicle.fuel == filters["gorivo"])
    if "mjenjac" in filters:
        stmt = stmt.where(Vehicle.transmission == filters["mjenjac"])
    if "stanje" in filters:
        stmt = stmt.where(Vehicle.condition == ("new" if filters["stanje"] == "novo" else "used"))
    if "snizeno" in filters:
        from app.services.pricing import active_drops

        dropped = [vid for vid, drop in active_drops().items()]
        stmt = stmt.where(Vehicle.id.in_(dropped or [-1]), ~Vehicle.price_on_request)
    return stmt


def apply_sort(stmt, sort: str):
    """Available vehicles first (sold at the end), then the chosen order."""
    sold_last = case((Vehicle.status == STATUS_SOLD, 1), else_=0)
    if sort == "cijena_uzlazno":
        order = [Vehicle.price_on_request.asc(), Vehicle.price_eur.asc()]
    elif sort == "cijena_silazno":
        order = [Vehicle.price_on_request.asc(), Vehicle.price_eur.desc()]
    elif sort == "km_uzlazno":
        order = [Vehicle.mileage_km.asc()]
    elif sort == "godina_silazno":
        order = [Vehicle.year.desc()]
    else:
        order = [Vehicle.published_at.desc()]
    return stmt.order_by(sold_last, *order, Vehicle.id.desc())


def filter_options(db: Session) -> dict:
    """Options for the public filter form, computed from currently visible vehicles."""
    visible = select(Vehicle.id).where(public_condition())
    makes = db.execute(
        select(Make.id, Make.name, func.count(Vehicle.id))
        .join(Vehicle, Vehicle.make_id == Make.id)
        .where(Vehicle.id.in_(visible))
        .group_by(Make.id, Make.name)
        .order_by(Make.name)
    ).all()
    types = dict(
        db.execute(
            select(Vehicle.vehicle_type, func.count(Vehicle.id))
            .where(Vehicle.id.in_(visible))
            .group_by(Vehicle.vehicle_type)
        ).all()
    )
    ranges = db.execute(
        select(
            func.min(Vehicle.year),
            func.max(Vehicle.year),
            func.min(Vehicle.price_eur),
            func.max(Vehicle.price_eur),
        ).where(Vehicle.id.in_(visible))
    ).one()
    fuels = sorted(
        {
            fuel
            for (fuel,) in db.execute(select(Vehicle.fuel).where(Vehicle.id.in_(visible)))
            if fuel
        }
    )
    return {
        "makes": [{"id": m[0], "name": m[1], "count": m[2]} for m in makes],
        "types": types,
        "total": sum(types.values()),
        "year_min": ranges[0],
        "year_max": ranges[1],
        "price_min": ranges[2],
        "price_max": ranges[3],
        "fuels": fuels,
    }


def similar_vehicles(db: Session, vehicle: Vehicle, n: int = 4) -> list[Vehicle]:
    """Same type; same make first, then closest price. Only available vehicles."""
    price = vehicle.price_eur or 0
    stmt = (
        public_query()
        .where(
            Vehicle.vehicle_type == vehicle.vehicle_type,
            Vehicle.id != vehicle.id,
            Vehicle.status.in_((STATUS_ACTIVE, STATUS_RESERVED)),
        )
        .order_by(
            case((Vehicle.make_id == vehicle.make_id, 0), else_=1),
            func.abs(func.coalesce(Vehicle.price_eur, 0) - price),
            Vehicle.id.desc(),
        )
        .limit(n)
    )
    return list(db.scalars(stmt))


def is_bot(user_agent: str | None) -> bool:
    ua = (user_agent or "").lower()
    return not ua or any(marker in ua for marker in BOT_MARKERS)


def count_view(db: Session, vehicle: Vehicle, request) -> bool:
    """Count a detail-page view (daily table + total). Bots and repeat views (6 h) are skipped.

    Deduplication uses the signed client-state cookie (vehicle IDs + time; no personal data,
    no cross-site tracking)."""
    if is_bot(request.headers.get("user-agent")):
        return False
    now = int(time.time())
    seen = {
        str(key): value
        for key, value in dict(request.session.get("seen", {})).items()
        if isinstance(value, int) and now - value < VIEW_DEDUPE_SECONDS
    }
    if str(vehicle.id) in seen:
        return False
    seen[str(vehicle.id)] = now
    request.session["seen"] = dict(list(seen.items())[-50:])

    today = local_today()
    updated = db.execute(
        update(VehicleView)
        .where(VehicleView.vehicle_id == vehicle.id, VehicleView.date == today)
        .values(count=VehicleView.count + 1)
    ).rowcount
    if not updated:
        db.add(VehicleView(vehicle_id=vehicle.id, date=today, count=1))
    # updated_at is kept unchanged: a view is not an edit.
    db.execute(
        update(Vehicle)
        .where(Vehicle.id == vehicle.id)
        .values(views_total=Vehicle.views_total + 1, updated_at=Vehicle.updated_at)
    )
    try:
        db.commit()
    except IntegrityError:  # concurrent insert of today's row -> retry as update
        db.rollback()
        db.execute(
            update(VehicleView)
            .where(VehicleView.vehicle_id == vehicle.id, VehicleView.date == today)
            .values(count=VehicleView.count + 1)
        )
        db.commit()
    return True


def youtube_id(url: str | None) -> str | None:
    """Extract the video ID from common YouTube URL formats."""
    if not url:
        return None
    match = YOUTUBE_RE.search(url)
    return match.group(1) if match else None


YOUTUBE_RE = re.compile(
    r"(?:youtube(?:-nocookie)?\.com/(?:watch\?(?:.*&)?v=|embed/|shorts/|live/)|youtu\.be/)"
    r"([A-Za-z0-9_-]{11})"
)


# ---------------------------------------------------------------------------
# Presentation helpers for the public detail page
# ---------------------------------------------------------------------------
PUBLIC_SPEC_SECTIONS = ("osnovno", "motor", "karoserija", "stanje")
SPEC_SECTION_ICONS = {"osnovno": "info", "motor": "zap", "stanje": "file"}
HIDDEN_ON_PUBLIC = {
    "vin",
    "featured",
    "video_url",
    "price_eur",
    "price_old_eur",
    "price_on_request",
    "tax_type",
    "color_metallic",
    "power_kw",
}


def format_value(field: dict, value) -> str:
    """Human readable value of a schema field ('' = do not show)."""
    from app.templating import format_number
    from app.vehicle_schema import option_label

    if value is None or value == "" or value is False:
        return ""
    kind = field["type"]
    if kind == "bool":
        return "Da"
    if kind == "select":
        return option_label(field, value)
    if kind == "month":
        return value.strftime("%m/%Y")
    if kind in ("int", "float") and field.get("plain"):
        text = str(value)
    elif kind in ("int", "float"):
        decimals = 1 if isinstance(value, float) and value % 1 else 0
        text = format_number(value, decimals)
    else:
        text = str(value)
    return f"{text} {field['unit']}" if field.get("unit") else text


def energy_metrics(vehicle: Vehicle) -> dict | None:
    """WLTP block (detail page, window card, offer): fuel -> l/100 km + CO2; electric ->
    kWh/100 km, range, 0 g/km; plug-in hybrid -> both. None when nothing is filled in."""
    from app.templating import format_number
    from app.vehicle_schema import ELECTRIC_FUELS, PLUGIN_FUELS

    def num(value, decimals=1):
        return format_number(value, decimals if value % 1 else 0)

    electric = vehicle.fuel in ELECTRIC_FUELS
    plugin = vehicle.fuel in PLUGIN_FUELS
    rows: list[tuple[str, str, str]] = []
    if not electric and vehicle.fuel_consumption_l100 is not None:
        rows.append(("Potrošnja goriva", num(vehicle.fuel_consumption_l100), "l/100 km"))
    if (electric or plugin) and vehicle.energy_consumption_kwh100 is not None:
        rows.append(("Potrošnja energije", num(vehicle.energy_consumption_kwh100), "kWh/100 km"))
    if (electric or plugin) and vehicle.electric_range_km is not None:
        rows.append(("Električni domet", num(vehicle.electric_range_km, 0), "km"))
    if not rows and vehicle.co2_g_km is None:
        return None
    if electric:
        rows.append(("Emisija CO2", "0", "g/km"))  # no tailpipe emissions
    elif vehicle.co2_g_km is not None:
        rows.append(("Emisija CO2", str(vehicle.co2_g_km), "g/km"))
    title = "Potrošnja energije i domet" if electric else "Potrošnja goriva i emisija CO2"
    return {"title": title, "rows": rows, "electric": electric}


def spec_sections(vehicle: Vehicle) -> list[dict]:
    """Specification table grouped by schema sections (only filled, public fields)."""
    from app.vehicle_schema import SECTION_LABELS, field_label, schema_for

    schema = schema_for(vehicle.vehicle_type)
    attributes = vehicle.attributes or {}
    result = []
    for key in PUBLIC_SPEC_SECTIONS:
        rows = []
        if key == "motor" and vehicle.power_kw:
            rows.append(("Snaga", f"{vehicle.power_kw} kW ({vehicle.power_hp} KS)"))
        for field in schema["sections"][key]:
            if field.get("admin_only") or field["key"] in HIDDEN_ON_PUBLIC:
                continue
            if field["source"] == "attributes":
                value = attributes.get(field["key"])
            else:
                value = getattr(vehicle, field["key"], None)
            text = format_value(field, value)
            if field["key"] == "color" and text and vehicle.color_metallic:
                text += " metalik"
            if text:
                rows.append((field_label(field, vehicle.vehicle_type), text))
        if rows:
            icon = SPEC_SECTION_ICONS.get(key) or VEHICLE_TYPES[vehicle.vehicle_type]["icon"]
            result.append({"key": key, "label": SECTION_LABELS[key], "icon": icon, "rows": rows})
    return result


def split_columns(groups: list[dict], weight) -> list[list[dict]]:
    """Two balanced columns of cards: each group goes to the currently shorter column
    (keeps the order within a column; on mobile the columns simply stack)."""
    columns: list[list[dict]] = [[], []]
    heights = [0.0, 0.0]
    for index, group in enumerate(groups):
        target = 0 if heights[0] <= heights[1] else 1
        # `order` restores the original sequence when the columns collapse on mobile.
        columns[target].append({**group, "order": index})
        heights[target] += weight(group)
    return [column for column in columns if column]


def spec_columns(specs: list[dict]) -> list[list[dict]]:
    return split_columns(specs, lambda g: 1.5 + len(g["rows"]))


def equipment_columns(groups: list[dict]) -> list[list[dict]]:
    return split_columns(groups, lambda g: 2 + (len(g["items"]) + 1) // 2)


def highlights(vehicle: Vehicle) -> list[dict]:
    """Selling points shown as chips above the specification (only what is recorded)."""
    items = []
    if vehicle.first_owner:
        items.append({"icon": "user", "text": "Prvi vlasnik"})
    if vehicle.service_book:
        items.append({"icon": "wrench", "text": "Servisna knjižica"})
    if vehicle.warranty_months:
        items.append({"icon": "shield-check", "text": f"Garancija {vehicle.warranty_months} mj."})
    if vehicle.registered_until and vehicle.registered_until >= local_today().replace(day=1):
        items.append(
            {
                "icon": "calendar",
                "text": f"Registriran do {vehicle.registered_until.strftime('%m/%Y')}",
            }
        )
    if vehicle.tax_type == "pdv":
        items.append({"icon": "file", "text": "Moguć R1 račun"})
    if vehicle.condition == "new" and vehicle.mileage_km is not None and vehicle.mileage_km < 100:
        items.append({"icon": "award", "text": "Nekorišteno vozilo"})
    return items


def key_facts(vehicle: Vehicle) -> list[dict]:
    from app.templating import km
    from app.vehicle_schema import label

    facts = [
        {"icon": "calendar", "label": "Godina", "value": str(vehicle.year or "—")},
        {"icon": "gauge", "label": "Kilometraža", "value": km(vehicle.mileage_km) or "—"},
        {"icon": "fuel", "label": "Gorivo", "value": label("fuel", vehicle.fuel) or "—"},
        {
            "icon": "zap",
            "label": "Snaga",
            "value": f"{vehicle.power_kw} kW / {vehicle.power_hp} KS" if vehicle.power_kw else "—",
        },
        {
            "icon": "gearbox",
            "label": "Mjenjač",
            "value": label("transmission", vehicle.transmission) or "—",
        },
        {
            "icon": "check-circle",
            "label": "Stanje",
            "value": "Novo" if vehicle.condition == "new" else "Rabljeno",
        },
    ]
    return facts
