"""Role/permission matrix (specification chapter 10) and the admin navigation.

To change who can do what, edit PERMISSIONS. Routes use
`Depends(require_permission("..."))` from `app.deps`; templates use `can()`.
"""

from __future__ import annotations

from app.models import ROLE_OWNER, ROLE_SALESPERSON, ROLE_SUPERADMIN

ALL_ROLES = frozenset({ROLE_SUPERADMIN, ROLE_OWNER, ROLE_SALESPERSON})
OWNER_PLUS = frozenset({ROLE_SUPERADMIN, ROLE_OWNER})
SUPERADMIN_ONLY = frozenset({ROLE_SUPERADMIN})

PERMISSIONS: dict[str, frozenset[str]] = {
    "dashboard": ALL_ROLES,
    "vehicles": ALL_ROLES,
    "vehicles.delete_any": OWNER_PLUS,  # salesperson: only own drafts
    "catalog": ALL_ROLES,
    "inquiries": ALL_ROLES,
    "inquiries.delete": OWNER_PLUS,
    "inquiries.export": OWNER_PLUS,
    "newsletter.view": ALL_ROLES,
    "newsletter.manage": OWNER_PLUS,
    "stats": ALL_ROLES,
    "stats.export": OWNER_PLUS,
    "users": OWNER_PLUS,
    "settings": OWNER_PLUS,
    "pages": OWNER_PLUS,
    "gdpr": OWNER_PLUS,
    "audit": OWNER_PLUS,
    "system": SUPERADMIN_ONLY,
}

ROLE_LABELS = {
    ROLE_SUPERADMIN: "Superadmin",
    ROLE_OWNER: "Vlasnik",
    ROLE_SALESPERSON: "Prodavač",
}


def can(user, permission: str) -> bool:
    if user is None or not getattr(user, "is_active", False):
        return False
    return user.role in PERMISSIONS.get(permission, frozenset())


# Sidebar: (label, url, permission, icon name, section key for highlighting)
ADMIN_NAV = [
    {"label": "Nadzorna ploča", "url": "/admin", "perm": "dashboard", "icon": "home", "key": ""},
    {"label": "Vozila", "url": "/admin/vozila", "perm": "vehicles", "icon": "car", "key": "vozila"},
    {
        "label": "Katalog marki",
        "url": "/admin/katalog/marke",
        "perm": "catalog",
        "icon": "tag",
        "key": "katalog",
    },
    {"label": "Upiti", "url": "/admin/upiti", "perm": "inquiries", "icon": "inbox", "key": "upiti"},
    {
        "label": "Newsletter",
        "url": "/admin/newsletter/pretplatnici",
        "perm": "newsletter.view",
        "icon": "mail",
        "key": "newsletter",
    },
    {
        "label": "Statistika",
        "url": "/admin/statistika",
        "perm": "stats",
        "icon": "chart",
        "key": "statistika",
    },
    {
        "label": "Korisnici",
        "url": "/admin/korisnici",
        "perm": "users",
        "icon": "users",
        "key": "korisnici",
    },
    {
        "label": "Postavke",
        "url": "/admin/postavke",
        "perm": "settings",
        "icon": "settings",
        "key": "postavke",
    },
    {
        "label": "Stranice",
        "url": "/admin/stranice",
        "perm": "pages",
        "icon": "file",
        "key": "stranice",
    },
    {
        "label": "Prava ispitanika",
        "url": "/admin/gdpr",
        "perm": "gdpr",
        "icon": "shield",
        "key": "gdpr",
    },
    {"label": "Audit log", "url": "/admin/audit", "perm": "audit", "icon": "list", "key": "audit"},
    {
        "label": "Sustav",
        "url": "/admin/sustav",
        "perm": "system",
        "icon": "server",
        "key": "sustav",
    },
]


def nav_for(user) -> list[dict]:
    """Navigation items visible to `user` (all items when no user — phase 1 skeleton)."""
    if user is None:
        return ADMIN_NAV
    return [item for item in ADMIN_NAV if can(user, item["perm"])]
