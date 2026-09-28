"""Secure image processing. EVERY upload (vehicle photos, logo) goes through here.

- size limit (MAX_UPLOAD_MB), content check with Pillow (not the extension)
- only JPEG / PNG / WebP by actual content; SVG, GIF, HTML, PDF... are rejected
- max 12 000 px per side and 64 MP total (decompression-bomb protection)
- EXIF orientation applied, then re-encoded to WebP (quality 82) WITHOUT metadata
  -> EXIF/GPS and any hidden payload are gone
- random file names, stored through the storage backend (local or S3)
"""

from __future__ import annotations

import io
import uuid
from dataclasses import dataclass, field

from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import get_settings
from app.services.storage import get_storage

settings = get_settings()

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_SIDE = 12_000
MAX_PIXELS = 64_000_000
VEHICLE_SIZES = (400, 1000, 1600)
LOGO_SIZES = (200, 400)
WEBP_QUALITY = 82

# Pillow raises DecompressionBombError above 2x this value; we check explicitly as well.
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


class ImageError(ValueError):
    """User-facing error (Croatian message)."""


@dataclass
class ProcessedImage:
    width: int
    height: int
    variants: dict[int, bytes] = field(default_factory=dict)


def _open_checked(data: bytes, max_bytes: int) -> Image.Image:
    if not data:
        raise ImageError("Datoteka je prazna.")
    if len(data) > max_bytes:
        raise ImageError(f"Datoteka je veća od {max_bytes // (1024 * 1024)} MB.")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = probe.format
            width, height = probe.size
            probe.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        raise ImageError("Datoteka nije ispravna slika (dopušteno: JPEG, PNG, WebP).") from None
    if fmt not in ALLOWED_FORMATS:
        raise ImageError("Dopušteni formati su JPEG, PNG i WebP.")
    if width > MAX_SIDE or height > MAX_SIDE or width * height > MAX_PIXELS:
        raise ImageError("Slika je prevelika (najviše 12.000 px po stranici).")
    if width < 1 or height < 1:
        raise ImageError("Datoteka nije ispravna slika.")
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (OSError, ValueError, Image.DecompressionBombError):
        raise ImageError("Slika je oštećena i ne može se obraditi.") from None
    return image


def _to_rgb(image: Image.Image, keep_alpha: bool = False) -> Image.Image:
    """Apply EXIF orientation; flatten transparency onto white (logos keep alpha)."""
    image = ImageOps.exif_transpose(image)
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        if keep_alpha:
            return rgba
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.split()[-1])
        return background
    return image.convert("RGB")


def _encode_webp(image: Image.Image, width: int) -> bytes:
    if image.width > width:
        height = round(image.height * width / image.width)
        image = image.resize((width, height), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    # No `exif`/`icc_profile` arguments -> the output carries no metadata.
    image.save(buffer, format="WEBP", quality=WEBP_QUALITY, method=4)
    return buffer.getvalue()


def process_image(
    data: bytes, sizes=VEHICLE_SIZES, max_bytes: int | None = None, keep_alpha: bool = False
) -> ProcessedImage:
    """Validate and re-encode an uploaded image into WebP variants of the given widths."""
    max_bytes = max_bytes or settings.MAX_UPLOAD_MB * 1024 * 1024
    image = _to_rgb(_open_checked(data, max_bytes), keep_alpha)
    result = ProcessedImage(width=image.width, height=image.height)
    for size in sizes:
        result.variants[size] = _encode_webp(image, size)
    return result


def store_variants(prefix: str, processed: ProcessedImage) -> str:
    """Save all variants under a random key; returns the base file key."""
    storage = get_storage()
    base_key = f"{prefix}/{uuid.uuid4().hex}"
    for size, payload in processed.variants.items():
        storage.save(f"{base_key}_{size}.webp", payload, "image/webp")
    return base_key


def delete_variants(base_key: str, sizes=VEHICLE_SIZES) -> None:
    storage = get_storage()
    for size in sizes:
        storage.delete(f"{base_key}_{size}.webp")


def save_vehicle_image(vehicle_id: int, data: bytes) -> tuple[str, ProcessedImage]:
    processed = process_image(data, VEHICLE_SIZES)
    key = store_variants(f"vehicles/{vehicle_id}", processed)
    return key, processed


def save_logo(data: bytes) -> str:
    """Company logo: PNG/WebP/JPEG, max 2 MB, variants 200/400 px (WebP)."""
    processed = process_image(data, LOGO_SIZES, max_bytes=2 * 1024 * 1024, keep_alpha=True)
    return store_variants("branding", processed)
