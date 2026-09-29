"""Administracija kao aplikacija na telefonu (PWA, faza 10 E).

- Manifest i ikone generiraju se iz postavki (naziv, primarna boja, logotip).
- Ikone: logotip na jednobojnoj pozadini primarne boje s marginom za "maskable" (sigurna zona
  80 %), inače veliko početno slovo. Keš na disku u DATA_DIR/pwa/ — naziv datoteke sadrži hash
  logotipa, boje i slova, pa se promjenom logotipa ili boje automatski izrađuje nova ikona.
- Service worker je minimalan: admin stranice i API idu uvijek na mrežu (sadrže osobne podatke i
  sesije); keširati se smiju samo /static/* datoteke.
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

from PIL import Image, ImageDraw

from app.config import get_settings

ICON_SIZES = (180, 192, 512)
SAFE_ZONE = 0.62  # logo width relative to the icon (inside the 80 % maskable circle)
PLACEHOLDER_NAME = "IME PODUZEĆA"
STATIC_CACHE = "ak-admin-static-v1"


def short_name(company: str, limit: int = 12) -> str:
    """Whole words that fit in `limit` characters ("Auto Horvat Zagreb" -> "Auto Horvat")."""
    words = (company or "Admin").split()
    result = ""
    for word in words:
        candidate = f"{result} {word}".strip()
        if len(candidate) > limit:
            break
        result = candidate
    return result or words[0][:limit]


def manifest(site: dict) -> dict:
    from app.templating import css_color

    color = css_color(site.get("primary_color"), "#1e40af")
    company = site.get("company_name", "")
    icons = [
        {"src": f"/admin/pwa-icon-{size}.png", "sizes": f"{size}x{size}", "type": "image/png"}
        for size in (192, 512)
    ]
    icons.append(
        {
            "src": "/admin/pwa-icon-512.png",
            "sizes": "512x512",
            "type": "image/png",
            "purpose": "maskable",
        }
    )
    return {
        "name": f"{company} – Admin",
        "short_name": short_name(company),
        "description": "Administracija oglasa, upita i newslettera.",
        "start_url": "/admin/",
        "scope": "/admin/",
        "display": "standalone",
        "theme_color": color,
        "background_color": "#ffffff",
        "lang": "hr",
        "icons": icons,
    }


def _rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _letter(company: str) -> str:
    """Initial of the company; the placeholder name gets "L" (like the LOGO placeholder)."""
    if not company or company.strip().upper() == PLACEHOLDER_NAME:
        return "L"
    for char in company:
        if char.isalnum():
            return char.upper()
    return "L"


def _logo_bytes(site: dict) -> bytes | None:
    from app.services.storage import get_storage

    key = site.get("logo_key")
    if not key:
        return None
    try:
        return get_storage().read(f"{key}_400.webp")
    except Exception:  # noqa: BLE001 - missing file: fall back to the letter icon
        return None


def render_icon(size: int, color: str, logo: bytes | None, letter: str) -> bytes:
    background = _rgb(color)
    icon = Image.new("RGB", (size, size), background)
    if logo:
        with Image.open(io.BytesIO(logo)) as source:
            mark = source.convert("RGBA")
            box = int(size * SAFE_ZONE)
            mark.thumbnail((box, box), Image.Resampling.LANCZOS)
            # White rounded plate so dark logos stay visible on the brand colour.
            pad = max(4, size // 24)
            plate = Image.new("RGBA", (mark.width + 2 * pad, mark.height + 2 * pad), (0, 0, 0, 0))
            ImageDraw.Draw(plate).rounded_rectangle(
                (0, 0, plate.width - 1, plate.height - 1), radius=pad * 2, fill=(255, 255, 255, 255)
            )
            plate.alpha_composite(mark, (pad, pad))
            icon.paste(plate, ((size - plate.width) // 2, (size - plate.height) // 2), plate)
    else:
        from app.services.placeholder_images import font

        draw = ImageDraw.Draw(icon)
        text_font = font(int(size * 0.52))
        box = draw.textbbox((0, 0), letter, font=text_font)
        x = (size - (box[2] - box[0])) / 2 - box[0]
        y = (size - (box[3] - box[1])) / 2 - box[1]
        draw.text((x, y), letter, font=text_font, fill=(255, 255, 255))
    buffer = io.BytesIO()
    icon.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def icon_png(size: int, site: dict) -> bytes:
    """Cached on disk; the file name changes with logo/colour/letter (= invalidation)."""
    from app.templating import css_color

    color = css_color(site.get("primary_color"), "#1e40af")
    logo = _logo_bytes(site)
    letter = _letter(site.get("company_name", ""))
    digest = hashlib.sha256(
        b"|".join([color.encode(), letter.encode(), logo or b"-", str(size).encode()])
    ).hexdigest()[:16]
    folder = Path(get_settings().DATA_DIR) / "pwa"
    path = folder / f"icon-{size}-{digest}.png"
    if path.is_file():
        return path.read_bytes()
    data = render_icon(size, color, logo, letter)
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob(f"icon-{size}-*.png"):
        old.unlink(missing_ok=True)
    path.write_bytes(data)
    return data


SERVICE_WORKER = """/* Autokuća admin — service worker (network-only for admin pages).
   Admin pages and API responses contain personal data and sessions: they are NEVER cached.
   Only static assets (/static/...) may be served from the cache. */
const STATIC_CACHE = "__CACHE__";

self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(names.filter((n) => n !== STATIC_CACHE).map((n) => caches.delete(n)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  const isStatic = request.method === "GET" && url.origin === self.location.origin &&
    url.pathname.startsWith("/static/");
  if (!isStatic) {
    event.respondWith(fetch(request));  // straight to the network, nothing stored
    return;
  }
  event.respondWith(
    caches.open(STATIC_CACHE).then((cache) =>
      cache.match(request).then((hit) => hit || fetch(request).then((response) => {
        if (response.ok) cache.put(request, response.clone());
        return response;
      }))
    )
  );
});
""".replace("__CACHE__", STATIC_CACHE)
