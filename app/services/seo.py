"""SEO helpers: page meta (title, description, canonical, Open Graph) and JSON-LD.

JSON-LD is emitted as `<script type="application/ld+json">` — a data block
that browsers never execute, so it is compatible with the strict CSP.
"""

from __future__ import annotations

from app.config import get_settings
from app.templating import jsonld, km, media_url  # noqa: F401 (jsonld re-exported)
from app.vehicle_schema import VEHICLE_TYPES, label

settings = get_settings()

FUEL_SCHEMA = {
    "benzin": "Gasoline",
    "dizel": "Diesel",
    "hibrid": "Hybrid",
    "plugin_hibrid": "PluginHybrid",
    "elektricni": "Electric",
    "lpg": "LPG",
    "cng": "CNG",
}
TRANSMISSION_SCHEMA = {"rucni": "ManualTransmission", "automatski": "AutomaticTransmission"}


def absolute(path: str) -> str:
    if path.startswith(("http://", "https://")):
        return path
    return f"{settings.base_url}{path}"


def og_default_image() -> str:
    """Per-client override: overrides/static/og-default.png, else the bundled placeholder."""
    if (settings.OVERRIDES_DIR / "static" / "og-default.png").is_file():
        return absolute("/static/custom/og-default.png")
    return absolute("/static/img/og-default.png")


def page_meta(
    title: str,
    description: str,
    path: str,
    image: str | None = None,
    og_type: str = "website",
    noindex: bool = False,
) -> dict:
    return {
        "title": title,
        "description": description[:300],
        "canonical": absolute(path),
        "image": image or og_default_image(),
        "og_type": og_type,
        "noindex": noindex,
    }


def vehicle_meta(vehicle, site: dict) -> dict:
    parts = [vehicle.title]
    if vehicle.year:
        parts.append(str(vehicle.year))
    if vehicle.mileage_km is not None:
        parts.append(km(vehicle.mileage_km))
    title = f"{', '.join(parts)} – {site['company_name']}"
    facts = [
        label("fuel", vehicle.fuel) if vehicle.fuel else "",
        label("transmission", vehicle.transmission) if vehicle.transmission else "",
        f"{vehicle.power_kw} kW ({vehicle.power_hp} KS)" if vehicle.power_kw else "",
    ]
    price = (
        "Cijena na upit"
        if vehicle.price_on_request or vehicle.price_eur is None
        else f"Cijena: {vehicle.price_eur:,} €".replace(",", ".")
    )
    description = (
        f"{', '.join(parts)}. {', '.join(f for f in facts if f)}. {price}. "
        f"{site['company_name']}, {site['company_address']}."
    )
    image = absolute(media_url(vehicle.images[0], 1600)) if vehicle.images else None
    return page_meta(title, description, f"/vozila/{vehicle.slug}", image, og_type="product")


# ---------------------------------------------------------------------------
# JSON-LD
# ---------------------------------------------------------------------------
def organization_jsonld(site: dict) -> dict:
    data = {
        "@context": "https://schema.org",
        "@type": "AutoDealer",
        "name": site["company_name"],
        "url": settings.base_url + "/",
        "email": site["company_email"],
        "telephone": site["company_phone"],
        "address": {
            "@type": "PostalAddress",
            "streetAddress": site["company_address"],
            "addressCountry": "HR",
        },
        "openingHours": site["working_hours"],
        "image": og_default_image(),
    }
    same_as = [u for u in (site.get("facebook_url"), site.get("instagram_url")) if u]
    if same_as:
        data["sameAs"] = same_as
    if site.get("logo_url"):
        data["logo"] = absolute(site["logo_url"])
    return data


def vehicle_jsonld(vehicle, site: dict) -> dict:
    schema_type = VEHICLE_TYPES.get(vehicle.vehicle_type, {}).get("schema_org", "Vehicle")
    data: dict = {
        "@context": "https://schema.org",
        "@type": schema_type,
        "name": vehicle.title,
        "url": absolute(f"/vozila/{vehicle.slug}"),
        "brand": {"@type": "Brand", "name": vehicle.make.name},
        "model": vehicle.model.name if vehicle.model else None,
        "vehicleModelDate": str(vehicle.year) if vehicle.year else None,
        "itemCondition": "https://schema.org/NewCondition"
        if vehicle.condition == "new"
        else "https://schema.org/UsedCondition",
        "image": [absolute(media_url(img, 1600)) for img in vehicle.images[:10]],
    }
    if vehicle.mileage_km is not None:
        data["mileageFromOdometer"] = {
            "@type": "QuantitativeValue",
            "value": vehicle.mileage_km,
            "unitCode": "KMT",
        }
    if vehicle.fuel:
        data["fuelType"] = FUEL_SCHEMA.get(vehicle.fuel, label("fuel", vehicle.fuel))
    if vehicle.transmission:
        data["vehicleTransmission"] = TRANSMISSION_SCHEMA.get(vehicle.transmission)
    if vehicle.color:
        data["color"] = label("color", vehicle.color)
    if vehicle.power_kw:
        data["vehicleEngine"] = {
            "@type": "EngineSpecification",
            "enginePower": {
                "@type": "QuantitativeValue",
                "value": vehicle.power_kw,
                "unitCode": "KWT",
            },
        }
    if vehicle.first_registration:
        data["dateVehicleFirstRegistered"] = vehicle.first_registration.isoformat()
    offer: dict = {
        "@type": "Offer",
        "url": data["url"],
        "priceCurrency": "EUR",
        "availability": "https://schema.org/SoldOut"
        if vehicle.status == "sold"
        else "https://schema.org/InStock",
        "seller": {"@type": "AutoDealer", "name": site["company_name"]},
    }
    if not vehicle.price_on_request and vehicle.price_eur is not None:
        offer["price"] = vehicle.price_eur
    data["offers"] = offer
    return {key: value for key, value in data.items() if value not in (None, [], "")}


def breadcrumbs_jsonld(items: list[tuple[str, str]]) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i, "name": name, "item": absolute(path)}
            for i, (name, path) in enumerate(items, start=1)
        ],
    }
