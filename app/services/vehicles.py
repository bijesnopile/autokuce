"""Vehicle business logic shared by admin and public routes.

Admin part (phase 3): title/slug generation with slug history, status
transitions, duplication, deletion, form parsing/validation.
Public part (phase 4): public queries, filters, similar vehicles, view counting.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

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
)
from app.security import clean_html
from app.services.images import delete_variants
from app.utils import slugify
from app.vehicle_schema import (
    TYPE_CODES,
    allowed_transitions,
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
def parse_vehicle_form(db: Session, form, current: Vehicle | None = None):
    """Validate the admin form. Returns (values_for_model, raw_for_rerender, errors)."""
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

    common, common_errors = validate_common(vehicle_type, form)
    # Type-specific inputs are named "<type>__<key>" (each type has its own fieldset).
    attr_raw = {
        field["key"]: form.get(f"{vehicle_type}__{field['key']}")
        for field in type_fields(vehicle_type)
    }
    attributes, attr_errors = validate_attributes(vehicle_type, attr_raw)
    errors.update(common_errors)
    errors.update({f"{vehicle_type}__{key}": message for key, message in attr_errors.items()})
    values.update(common)
    values["attributes"] = attributes
    values["equipment"] = validate_equipment(vehicle_type, form.getlist("equipment"))
    values["power_hp"] = power_hp(values.get("power_kw"))
    values["description"] = clean_html(str(form.get("description", ""))[:20_000])
    if values.get("price_on_request"):
        values["price_old_eur"] = None
    return values, raw, errors
