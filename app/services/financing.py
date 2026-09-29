"""Informativni izračun rate (paket Standard, `kalkulator_rate` / `upit_financiranje`).

Anuitet: rata = G · r / (1 − (1 + r)^−n), r = godišnja kamata / 12 / 100, n = broj mjeseci
(r = 0 → G / n). Isti algoritam je u `static/js/public.js` (`financingPayment`) — izračun na
poslužitelju služi kao primjer bez JavaScripta i za oznaku "od … €/mj" na karticama.
Zaokruživanje na cent: floor(x · 100 + 0.5) / 100 (isto u JS-u).
"""

from __future__ import annotations

import math

from app.models import Vehicle

TERM_STEP = 12  # months slider step
MIN_TERM = 12
MAX_DOWN_PERCENT = 90
DOWN_STEP = 5


def round_cents(value: float) -> float:
    return math.floor(value * 100 + 0.5) / 100


def monthly_payment(principal: float, annual_rate_percent: float, months: int) -> float:
    """Annuity payment in EUR rounded to cents (0 for no principal / no term)."""
    if principal <= 0 or months <= 0:
        return 0.0
    rate = annual_rate_percent / 12 / 100
    if rate == 0:
        return round_cents(principal / months)
    return round_cents(principal * rate / (1 - math.pow(1 + rate, -months)))


def _number(value, default: float) -> float:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return default


def config(site: dict | None = None) -> dict:
    """Calculator parameters from the company settings."""
    from app.services.site import get_site

    site = site or get_site()
    max_months = int(_number(site.get("financing_max_months"), 84))
    return {
        "rate": _number(site.get("financing_rate_percent"), 6.9),
        "max_months": max(MIN_TERM, max_months),
        "min_down": int(_number(site.get("financing_min_down_percent"), 20)),
        "max_down": MAX_DOWN_PERCENT,
        "disclaimer": site.get("financing_disclaimer", ""),
        "terms": term_options(max_months),
    }


def term_options(max_months: int) -> list[int]:
    options = list(range(MIN_TERM, max_months + 1, TERM_STEP))
    if options[-1] != max_months:
        options.append(max_months)
    return options


def calculator_enabled(site: dict | None = None) -> bool:
    from app.plans import has_feature
    from app.services.site import get_site

    site = site or get_site()
    return has_feature("kalkulator_rate") and bool(site.get("financing_enabled"))


def financeable(vehicle: Vehicle) -> bool:
    """Only vehicles with a published price (not "price on request")."""
    return bool(vehicle.price_eur) and not vehicle.price_on_request and vehicle.status != "sold"


def example(vehicle: Vehicle, down_percent: float | None = None, months: int | None = None):
    """Representative example (minimum down payment, longest term) or given parameters."""
    cfg = config()
    down_percent = cfg["min_down"] if down_percent is None else down_percent
    months = cfg["max_months"] if months is None else months
    price = float(vehicle.price_eur or 0)
    down = round_cents(price * down_percent / 100)
    principal = round_cents(price - down)
    return {
        "price": price,
        "down_percent": down_percent,
        "down": down,
        "principal": principal,
        "months": months,
        "rate": cfg["rate"],
        "payment": monthly_payment(principal, cfg["rate"], months),
    }


def card_from(vehicle: Vehicle) -> int | None:
    """ "od X €/mj" on list cards: representative example, rounded UP to whole euros."""
    if not calculator_enabled() or not financeable(vehicle):
        return None
    payment = example(vehicle)["payment"]
    return math.ceil(payment) if payment > 0 else None


def format_eur(value: float, decimals: int = 2) -> str:
    """197.54 -> "197,54 €", 10000 -> "10.000,00 €" (hr-HR, same as the JS formatter)."""
    text = f"{value:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{text} €"


def parse_request(form, vehicle: Vehicle) -> tuple[dict, dict]:
    """Financing inquiry fields -> (clean values for `inquiries.extra`, errors)."""
    cfg = config()
    errors: dict = {}
    price = float(vehicle.price_eur or 0)

    def number(key: str) -> float | None:
        raw = str(form.get(key, "")).strip().replace(".", "").replace(",", ".")
        try:
            return float(raw) if raw else None
        except ValueError:
            return None

    down = number("down_payment")
    if down is None or down < 0:
        errors["down_payment"] = "Upišite iznos učešća u eurima."
    elif price and down < round_cents(price * cfg["min_down"] / 100) - 0.5:
        errors["down_payment"] = f"Najmanje učešće je {cfg['min_down']} % cijene."
    elif down >= price:
        errors["down_payment"] = "Učešće mora biti manje od cijene vozila."
    try:
        months = int(str(form.get("months", "")))
    except ValueError:
        months = 0
    if not MIN_TERM <= months <= cfg["max_months"]:
        errors["months"] = f"Rok otplate od {MIN_TERM} do {cfg['max_months']} mjeseci."
    if errors:
        return {}, errors
    principal = round_cents(price - down)
    return {
        "price": price,
        "down_payment": round_cents(down),
        "amount": principal,
        "months": months,
        "rate": cfg["rate"],
        "payment": monthly_payment(principal, cfg["rate"], months),
    }, {}
