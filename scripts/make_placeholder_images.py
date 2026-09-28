"""Generate placeholder images (Pillow).

    python scripts/make_placeholder_images.py            # app/static/img/og-default.png
    python scripts/make_placeholder_images.py --demo 8   # + 8 sample photos (data/placeholders/)

The demo seed (python -m app.seed) uses the same generator directly and pushes the
images through app/services/images.py like a real upload.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services.placeholder_images import og_image, vehicle_placeholder  # noqa: E402
from app.utils import ensure_utf8_console  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Placeholder slike")
    parser.add_argument("--demo", type=int, default=0, help="broj primjera fotografija vozila")
    parser.add_argument("--company", default="IME PODUZEĆA")
    args = parser.parse_args()
    ensure_utf8_console()

    target = ROOT / "app" / "static" / "img" / "og-default.png"
    target.write_bytes(og_image(args.company))
    print(f"OG slika: {target}")
    if args.demo:
        folder = ROOT / "data" / "placeholders"
        folder.mkdir(parents=True, exist_ok=True)
        for n in range(1, args.demo + 1):
            path = folder / f"vozilo-{n}.jpg"
            path.write_bytes(vehicle_placeholder(n, args.demo, args.company))
            print(f"Fotografija: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
