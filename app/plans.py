"""Paketi (Osnovni / Standard / Premium) i funkcije koje otključavaju.

Aktivni paket = `plan_override` iz tablice settings (postavlja ga superadmin na stranici Sustav)
ili env varijabla `PLAN` (default osnovni). Provjera u kodu: `has_feature("whatsapp")`; u
Jinji isto (globalno); rute: `Depends(require_feature("..."))` iz `app.deps` (admin → stranica
403 "Dostupno u paketu Standard", javno → 404).

Nova funkcija u paketu: zapis u FEATURES (kod, naziv, opis, paketi) → provjera u ruti/templateu
→ red u docs/PAKETI.md. `planned=True` = samo zapis za roadmap (nije implementirano, uvijek
zaključano).
"""

from __future__ import annotations

PLAN_OSNOVNI = "osnovni"
PLAN_STANDARD = "standard"
PLAN_PREMIUM = "premium"
PLAN_CODES = (PLAN_OSNOVNI, PLAN_STANDARD, PLAN_PREMIUM)

PLANS: dict[str, dict] = {
    PLAN_OSNOVNI: {
        "label": "Osnovni",
        "order": 1,
        "description": (
            "Web-stranica s oglasima vozila, upiti i mini-CRM, newsletter, statistika, SEO i "
            "GDPR alati. Do 2 korisnika administracije."
        ),
    },
    PLAN_STANDARD: {
        "label": "Standard",
        "order": 2,
        "description": (
            "Sve iz Osnovnog + WhatsApp/Viber, kartica za izlog i PDF ponuda, automatski "
            "odgovor i kalendarski termini, kalkulator rate i upit za financiranje, feed prema "
            "portalima. Do 5 korisnika."
        ),
    },
    PLAN_PREMIUM: {
        "label": "Premium",
        "order": 3,
        "description": (
            "Sve iz Standarda + neograničen broj korisnika i napredne funkcije (ugovori, marža, "
            "poslovnice, više jezika, novosti) kako budu dostupne."
        ),
    },
}

_STANDARD_UP = frozenset({PLAN_STANDARD, PLAN_PREMIUM})
_PREMIUM = frozenset({PLAN_PREMIUM})

FEATURES: dict[str, dict] = {
    "whatsapp": {
        "label": "WhatsApp i Viber gumbi",
        "description": "Kupac jednim dodirom otvara razgovor s pripremljenom porukom o vozilu.",
        "plans": _STANDARD_UP,
    },
    "izlog_kartica": {
        "label": "Kartica za izlog (A4/A5)",
        "description": "Ispis kartice vozila za vjetrobran ili izlog: cijena, podaci, QR kod.",
        "plans": _STANDARD_UP,
    },
    "ponuda_pdf": {
        "label": "Ponuda kupcu (PDF)",
        "description": "Ponuda s podacima tvrtke, vozilom i cijenom — ispis ili spremanje u PDF.",
        "plans": _STANDARD_UP,
    },
    "auto_odgovor": {
        "label": "Automatski odgovor kupcu",
        "description": "Kupac odmah dobiva email potvrdu da je upit zaprimljen.",
        "plans": _STANDARD_UP,
    },
    "kalendar_termin": {
        "label": "Kalendarski pozivi za preglede",
        "description": "Termin pregleda stiže kupcu i prodavaču kao .ics događaj; potvrda termina.",
        "plans": _STANDARD_UP,
    },
    "kalkulator_rate": {
        "label": "Kalkulator rate",
        "description": "Informativni izračun mjesečne rate na oglasu i oznaka 'od … €/mj' u listi.",
        "plans": _STANDARD_UP,
    },
    "upit_financiranje": {
        "label": "Upit za financiranje",
        "description": "Kupac šalje zahtjev za ponudu financiranja s učešćem i rokom.",
        "plans": _STANDARD_UP,
    },
    "feed_portali": {
        "label": "Feed prema portalima",
        "description": (
            "Automatski XML/CSV feed za Njuškalo, Index oglase, mobile.de, AutoScout24 i Meta."
        ),
        "plans": _STANDARD_UP,
    },
    "korisnici_5": {
        "label": "Do 5 korisnika administracije",
        "description": "Osnovni paket: 2 korisnika; Standard: 5; Premium: neograničeno.",
        "plans": _STANDARD_UP,
    },
    # --- Planirano (samo zapisi; nije implementirano, uvijek zaključano) ------------------
    "korisnici_neograniceno": {
        "label": "Neograničen broj korisnika",
        "description": "Bez ograničenja broja korisnika administracije.",
        "plans": _PREMIUM,
    },
    "ugovor_pdf": {
        "label": "Kupoprodajni ugovor (PDF)",
        "description": "Ugovor s podacima kupca i vozila iz upita.",
        "plans": _PREMIUM,
        "planned": True,
    },
    "marza": {
        "label": "Nabavna cijena i marža",
        "description": "Interna nabavna cijena, troškovi i izračun marže po vozilu.",
        "plans": _PREMIUM,
        "planned": True,
    },
    "poslovnice": {
        "label": "Više poslovnica",
        "description": "Vozila, kontakti i radno vrijeme po lokaciji.",
        "plans": _PREMIUM,
        "planned": True,
    },
    "jezici": {
        "label": "Višejezični sadržaj",
        "description": "Oglasi i stranice na više jezika (hreflang).",
        "plans": _PREMIUM,
        "planned": True,
    },
    "blog": {
        "label": "Novosti / blog",
        "description": "Objave s vlastitim stranicama i SEO-om.",
        "plans": _PREMIUM,
        "planned": True,
    },
    "zamagljivanje_tablica": {
        "label": "Automatsko zamagljivanje tablica",
        "description": "Prepoznavanje i zamagljivanje registarskih tablica pri uploadu.",
        "plans": _PREMIUM,
        "planned": True,
    },
}

# Najviše aktivnih korisnika administracije (bez superadmina — to je operater platforme).
USER_LIMITS: dict[str, int | None] = {PLAN_OSNOVNI: 2, PLAN_STANDARD: 5, PLAN_PREMIUM: None}


def normalize_plan(value: str | None) -> str | None:
    value = (value or "").strip().lower()
    return value if value in PLAN_CODES else None


def configured_plan() -> str:
    from app.config import get_settings

    return normalize_plan(get_settings().PLAN) or PLAN_OSNOVNI


def plan_override() -> str | None:
    from app.services.site import get_site

    return normalize_plan(get_site().get("plan_override"))


def current_plan() -> str:
    return plan_override() or configured_plan()


def plan_label(plan: str | None = None) -> str:
    return PLANS[plan or current_plan()]["label"]


def has_feature(code: str, plan: str | None = None) -> bool:
    feature = FEATURES.get(code)
    if feature is None or feature.get("planned"):
        return False
    return (plan or current_plan()) in feature["plans"]


def required_plan(code: str) -> str:
    """Lowest plan that includes the feature (for the "Standard"/"Premium" badge)."""
    plans = FEATURES[code]["plans"]
    return min(plans, key=lambda p: PLANS[p]["order"])


def lock_badge(code: str) -> str:
    """ "Standard"/"Premium" when the feature is locked in the current plan, else ""."""
    return "" if has_feature(code) else PLANS[required_plan(code)]["label"]


def user_limit(plan: str | None = None) -> int | None:
    return USER_LIMITS[plan or current_plan()]


def feature_table(plan: str | None = None) -> list[dict]:
    """All features with their state in `plan` (Sustav page, docs)."""
    plan = plan or current_plan()
    rows = []
    for code, feature in FEATURES.items():
        rows.append(
            {
                "code": code,
                "label": feature["label"],
                "description": feature["description"],
                "plans": [PLANS[p]["label"] for p in PLAN_CODES if p in feature["plans"]],
                "planned": bool(feature.get("planned")),
                "enabled": has_feature(code, plan),
            }
        )
    return rows


def next_plan_with_more_users(plan: str | None = None) -> str | None:
    plan = plan or current_plan()
    limit = user_limit(plan)
    for code in PLAN_CODES:
        other = USER_LIMITS[code]
        if PLANS[code]["order"] > PLANS[plan]["order"] and (other is None or (limit or 0) < other):
            return code
    return None


def seats_used(db) -> int:
    """Active users that count against the plan limit (superadmins = platform operator)."""
    from sqlalchemy import func, select

    from app.models import ROLE_SUPERADMIN, User

    return (
        db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.is_active.is_(True), User.role != ROLE_SUPERADMIN)
        )
        or 0
    )


def seat_available(db) -> bool:
    limit = user_limit()
    return limit is None or seats_used(db) < limit


def seat_limit_message() -> str:
    plan = current_plan()
    upgrade = next_plan_with_more_users(plan)
    message = f"Paket {PLANS[plan]['label']} dopušta najviše {user_limit(plan)} aktivnih korisnika."
    if upgrade:
        message += (
            f" Deaktivirajte nekog korisnika ili prijeđite na paket {PLANS[upgrade]['label']}."
        )
    return message
