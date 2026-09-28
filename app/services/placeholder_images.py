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


def vehicle_placeholder(
    index: int, total: int, company: str = "IME PODUZEĆA", size=(1600, 1200)
) -> bytes:
    """Neutral light-grey 4:3 image with 'FOTOGRAFIJA VOZILA n/N' (shade varies per image)."""
    width, height = size
    shade = 232 - (index * 9) % 40
    tint = (index * 23) % 12
    top = (shade + 8, shade + 8 + tint // 3, min(255, shade + 12 + tint))
    bottom = (shade - 26, shade - 24, shade - 18 + tint // 2)
    image = _gradient(size, top, bottom)
    draw = ImageDraw.Draw(image)
    # Simple car silhouette so the gallery reads as "vehicle photos".
    ground = int(height * 0.76)
    body_color = (shade - 78, shade - 76, shade - 70)
    glass = (shade - 30, shade - 26, shade - 14)
    draw.ellipse([width * 0.16, ground - 16, width * 0.84, ground + 26], fill=(shade - 46,) * 3)
    cabin = [
        (width * 0.31, ground - 175),
        (width * 0.39, ground - 285),
        (width * 0.63, ground - 285),
        (width * 0.73, ground - 175),
    ]
    draw.polygon(cabin, fill=body_color)
    draw.rounded_rectangle(
        [width * 0.17, ground - 185, width * 0.83, ground - 45], radius=48, fill=body_color
    )
    draw.polygon(
        [
            (width * 0.345, ground - 180),
            (width * 0.405, ground - 265),
            (width * 0.505, ground - 265),
            (width * 0.505, ground - 180),
        ],
        fill=glass,
    )
    draw.polygon(
        [
            (width * 0.52, ground - 180),
            (width * 0.52, ground - 265),
            (width * 0.615, ground - 265),
            (width * 0.69, ground - 180),
        ],
        fill=glass,
    )
    draw.rounded_rectangle(
        [width * 0.78, ground - 150, width * 0.825, ground - 120],
        radius=8,
        fill=(shade + 10, shade + 8, shade - 20),
    )
    for cx in (width * 0.32, width * 0.68):
        draw.ellipse([cx - 82, ground - 120, cx + 82, ground + 44], fill=(shade - 140,) * 3)
        draw.ellipse([cx - 40, ground - 78, cx + 40, ground + 2], fill=(shade - 50,) * 3)
    title_font = font(int(height * 0.075))
    small_font = font(int(height * 0.035))
    _centered(
        draw,
        f"FOTOGRAFIJA VOZILA {index}/{total}",
        int(height * 0.16),
        width,
        title_font,
        (70, 76, 88),
    )
    _centered(draw, safe_text(company), int(height * 0.28), width, small_font, (100, 106, 118))
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
