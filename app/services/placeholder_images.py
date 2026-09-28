"""Generated placeholder images (Pillow): vehicle photos for the demo seed and the
default Open Graph image. No real photos are ever used.

Fonts: Pillow's built-in font has no Croatian letters (č ć š ž đ), so a system TTF
is used when available (DejaVu in Docker via `fonts-dejavu-core`, Arial/Segoe UI on
Windows, Liberation/Noto on Linux). If none is found, text is transliterated to ASCII.
"""

from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.utils import slugify

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
]


@lru_cache
def _font_path() -> str | None:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    return None


def font(size: int) -> ImageFont.FreeTypeFont:
    path = _font_path()
    if path:
        return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def safe_text(text: str) -> str:
    """Transliterate when only the built-in (ASCII) font is available."""
    if _font_path():
        return text
    return slugify(text).replace("-", " ").upper() if text.isupper() else text


def _gradient(size: tuple[int, int], top: tuple, bottom: tuple) -> Image.Image:
    width, height = size
    base = Image.new("RGB", (1, height))
    for y in range(height):
        t = y / max(1, height - 1)
        base.putpixel(
            (0, y), tuple(round(a + (b - a) * t) for a, b in zip(top, bottom, strict=True))
        )
    return base.resize(size)


def _centered(draw: ImageDraw.ImageDraw, text: str, y: int, width: int, fnt, fill) -> None:
    box = draw.textbbox((0, 0), text, font=fnt)
    draw.text(((width - (box[2] - box[0])) / 2 - box[0], y), text, font=fnt, fill=fill)


def _wheel(draw, cx: float, ground: float, radius: float, shade: int) -> None:
    draw.ellipse(
        [
            cx - radius,
            ground - 2 * radius + 44 * radius / 82,
            cx + radius,
            ground + 44 * radius / 82,
        ],
        fill=(shade - 140,) * 3,
    )
    inner = radius * 0.49
    cy = ground - radius + 44 * radius / 82
    draw.ellipse([cx - inner, cy - inner, cx + inner, cy + inner], fill=(shade - 50,) * 3)


def _silhouette(draw, kind: str, width: int, height: int, shade: int) -> None:
    """Simple flat silhouette per vehicle type so galleries read as "vehicle photos"."""
    u = height / 1200
    ground = int(height * 0.76)
    body = (shade - 78, shade - 76, shade - 70)
    glass = (shade - 30, shade - 26, shade - 14)
    light = (shade + 10, shade + 8, shade - 20)
    draw.ellipse(
        [width * 0.14, ground - 16 * u, width * 0.86, ground + 26 * u], fill=(shade - 46,) * 3
    )

    if kind == "motorcycle":
        r = 120 * u
        rear, front = width * 0.33, width * 0.67
        axle = ground - r + 20 * u
        draw.polygon(
            [
                (rear, axle),
                (width * 0.43, ground - 250 * u),
                (width * 0.58, ground - 250 * u),
                (front, axle),
                (width * 0.55, axle),
                (width * 0.47, ground - 140 * u),
            ],
            fill=body,
        )
        draw.rounded_rectangle(
            [width * 0.37, ground - 300 * u, width * 0.50, ground - 262 * u],
            radius=18 * u,
            fill=body,
        )
        draw.ellipse([width * 0.47, ground - 330 * u, width * 0.60, ground - 240 * u], fill=body)
        draw.line([(width * 0.60, ground - 300 * u), (front, axle)], fill=body, width=int(22 * u))
        draw.line(
            [(width * 0.585, ground - 360 * u), (width * 0.64, ground - 330 * u)],
            fill=body,
            width=int(18 * u),
        )
        for cx in (rear, front):
            draw.ellipse([cx - r, axle - r, cx + r, axle + r], fill=(shade - 140,) * 3)
            draw.ellipse(
                [cx - r * 0.62, axle - r * 0.62, cx + r * 0.62, axle + r * 0.62],
                fill=(shade - 50,) * 3,
            )
        return

    if kind == "van":
        draw.rounded_rectangle(
            [width * 0.15, ground - 360 * u, width * 0.74, ground - 45 * u],
            radius=36 * u,
            fill=body,
        )
        draw.polygon(
            [
                (width * 0.72, ground - 360 * u),
                (width * 0.80, ground - 205 * u),
                (width * 0.86, ground - 175 * u),
                (width * 0.86, ground - 45 * u),
                (width * 0.72, ground - 45 * u),
            ],
            fill=body,
        )
        draw.polygon(
            [
                (width * 0.70, ground - 330 * u),
                (width * 0.765, ground - 205 * u),
                (width * 0.70, ground - 205 * u),
            ],
            fill=glass,
        )
        draw.rectangle([width * 0.56, ground - 320 * u, width * 0.67, ground - 215 * u], fill=glass)
        draw.rounded_rectangle(
            [width * 0.83, ground - 150 * u, width * 0.855, ground - 120 * u], radius=6, fill=light
        )
        for cx in (width * 0.28, width * 0.72):
            _wheel(draw, cx, ground, 82 * u, shade)
        return

    if kind == "camper":
        draw.rounded_rectangle(
            [width * 0.12, ground - 420 * u, width * 0.72, ground - 45 * u],
            radius=40 * u,
            fill=body,
        )
        draw.rounded_rectangle(
            [width * 0.60, ground - 420 * u, width * 0.80, ground - 300 * u],
            radius=40 * u,
            fill=body,
        )
        draw.polygon(
            [
                (width * 0.72, ground - 300 * u),
                (width * 0.80, ground - 200 * u),
                (width * 0.87, ground - 170 * u),
                (width * 0.87, ground - 45 * u),
                (width * 0.72, ground - 45 * u),
            ],
            fill=body,
        )
        draw.polygon(
            [
                (width * 0.73, ground - 290 * u),
                (width * 0.785, ground - 205 * u),
                (width * 0.73, ground - 205 * u),
            ],
            fill=glass,
        )
        for x0 in (0.18, 0.40):
            draw.rounded_rectangle(
                [width * x0, ground - 330 * u, width * (x0 + 0.12), ground - 240 * u],
                radius=14 * u,
                fill=glass,
            )
        draw.rounded_rectangle(
            [width * 0.56, ground - 330 * u, width * 0.63, ground - 70 * u],
            radius=10 * u,
            outline=glass,
            width=int(8 * u),
        )
        for cx in (width * 0.27, width * 0.75):
            _wheel(draw, cx, ground, 82 * u, shade)
        return

    if kind == "truck":
        draw.rounded_rectangle(
            [width * 0.10, ground - 470 * u, width * 0.66, ground - 110 * u],
            radius=16 * u,
            fill=body,
        )
        draw.rectangle([width * 0.10, ground - 110 * u, width * 0.86, ground - 70 * u], fill=body)
        draw.rounded_rectangle(
            [width * 0.68, ground - 430 * u, width * 0.87, ground - 70 * u],
            radius=30 * u,
            fill=body,
        )
        draw.rounded_rectangle(
            [width * 0.72, ground - 400 * u, width * 0.86, ground - 270 * u],
            radius=16 * u,
            fill=glass,
        )
        draw.rounded_rectangle(
            [width * 0.84, ground - 170 * u, width * 0.865, ground - 135 * u], radius=6, fill=light
        )
        for cx in (width * 0.20, width * 0.33, width * 0.77):
            _wheel(draw, cx, ground, 78 * u, shade)
        return

    # Default: passenger car.
    draw.polygon(
        [
            (width * 0.31, ground - 175 * u),
            (width * 0.39, ground - 285 * u),
            (width * 0.63, ground - 285 * u),
            (width * 0.73, ground - 175 * u),
        ],
        fill=body,
    )
    draw.rounded_rectangle(
        [width * 0.17, ground - 185 * u, width * 0.83, ground - 45 * u], radius=48 * u, fill=body
    )
    draw.polygon(
        [
            (width * 0.345, ground - 180 * u),
            (width * 0.405, ground - 265 * u),
            (width * 0.505, ground - 265 * u),
            (width * 0.505, ground - 180 * u),
        ],
        fill=glass,
    )
    draw.polygon(
        [
            (width * 0.52, ground - 180 * u),
            (width * 0.52, ground - 265 * u),
            (width * 0.615, ground - 265 * u),
            (width * 0.69, ground - 180 * u),
        ],
        fill=glass,
    )
    draw.rounded_rectangle(
        [width * 0.78, ground - 150 * u, width * 0.825, ground - 120 * u], radius=8, fill=light
    )
    for cx in (width * 0.32, width * 0.68):
        _wheel(draw, cx, ground, 82 * u, shade)


def vehicle_placeholder(
    index: int,
    total: int,
    company: str = "IME PODUZEĆA",
    size=(1600, 1200),
    kind: str = "car",
) -> bytes:
    """Neutral light-grey 4:3 image with 'FOTOGRAFIJA VOZILA n/N' (shade varies per image).

    `kind` is the vehicle type (car/van/motorcycle/camper/truck) and selects the silhouette.
    """
    width, height = size
    shade = 232 - (index * 9) % 40
    tint = (index * 23) % 12
    top = (shade + 8, shade + 8 + tint // 3, min(255, shade + 12 + tint))
    bottom = (shade - 26, shade - 24, shade - 18 + tint // 2)
    image = _gradient(size, top, bottom)
    draw = ImageDraw.Draw(image)
    _silhouette(draw, kind, width, height, shade)
    title_font = font(int(height * 0.075))
    small_font = font(int(height * 0.035))
    _centered(
        draw,
        f"FOTOGRAFIJA VOZILA {index}/{total}",
        int(height * 0.19),
        width,
        title_font,
        (70, 76, 88),
    )
    _centered(draw, safe_text(company), int(height * 0.285), width, small_font, (100, 106, 118))
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=88)
    return buffer.getvalue()


def og_image(company: str = "IME PODUZEĆA", size=(1200, 630)) -> bytes:
    """Default Open Graph image with LOGO box and company name (PNG)."""
    width, height = size
    image = _gradient(size, (21, 38, 92), (30, 64, 175))
    draw = ImageDraw.Draw(image)
    for x in range(0, width, 56):
        draw.line([(x, 0), (x, height)], fill=(40, 62, 130), width=1)
    for y in range(0, height, 56):
        draw.line([(0, y), (width, y)], fill=(40, 62, 130), width=1)
    logo_font = font(64)
    box = draw.textbbox((0, 0), "LOGO", font=logo_font)
    logo_w, logo_h = box[2] - box[0], box[3] - box[1]
    pad_x, pad_y = 34, 22
    left = (width - logo_w - 2 * pad_x) / 2
    top = 150
    draw.rounded_rectangle(
        [left, top, left + logo_w + 2 * pad_x, top + logo_h + 2 * pad_y],
        radius=8,
        outline=(255, 255, 255),
        width=6,
    )
    draw.text(
        (left + pad_x - box[0], top + pad_y - box[1]), "LOGO", font=logo_font, fill=(255, 255, 255)
    )
    _centered(draw, safe_text(company), 340, width, font(78), (255, 255, 255))
    _centered(draw, "Rabljena i nova vozila", 450, width, font(36), (199, 210, 254))
    buffer = io.BytesIO()
    image.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()
