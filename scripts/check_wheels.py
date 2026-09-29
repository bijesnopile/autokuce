"""Provjera: imaju li svi paketi iz requirements.txt binarne wheelove za Docker sliku.

    python scripts/check_wheels.py        # treba internet (pip download u privremenu mapu)

Cilj je `python:3.11-slim-trixie` (Linux x86_64, CPython 3.11, glibc 2.41): pip ondje
prihvaća manylinux2014 i manylinux_2_28/2_34/2_36 wheelove, a Dockerfile instalira s
`--only-binary=:all:` (u slim slici nema kompajlera). Pokreni nakon svake promjene pinova.

Izlazni kod 1 ako se cijeli skup ne može instalirati iz wheelova za tu sliku. Dodatno se
ispisuje koji paketi NEMAJU wheel za stariji manylinux2014 (glibc 2.17) — informativno.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.utils import ensure_utf8_console  # noqa: E402

DOCKER_PLATFORMS = [
    "manylinux2014_x86_64",
    "manylinux_2_28_x86_64",
    "manylinux_2_34_x86_64",
    "manylinux_2_36_x86_64",
]


def pip_download(requirements: list[str], platforms: list[str], dest: Path) -> tuple[bool, str]:
    args = [
        sys.executable, "-m", "pip", "download", "--only-binary=:all:",
        "--python-version", "3.11", "--implementation", "cp",
        "--disable-pip-version-check", "--quiet", "-d", str(dest),
    ]  # fmt: skip
    for platform in platforms:
        args += ["--platform", platform]
    result = subprocess.run(
        [*args, *requirements], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    errors = [line for line in result.stderr.splitlines() if line.startswith("ERROR")]
    return result.returncode == 0, " ".join(errors)


def main() -> int:
    ensure_utf8_console()
    requirements = [
        line.split("#", 1)[0].strip()
        for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.split("#", 1)[0].strip()
    ]
    with tempfile.TemporaryDirectory(prefix="autokuca-wheels-") as tmp:
        ok, error = pip_download(
            ["-r", str(ROOT / "requirements.txt")], DOCKER_PLATFORMS, Path(tmp)
        )
        wheels = sorted(p.name for p in Path(tmp).glob("*.whl"))
        print(
            f"Docker slika (cp311, glibc 2.41): {'OK' if ok else 'GREŠKA'} — {len(wheels)} wheelova"
        )
        if not ok:
            print("  " + error)
        legacy_missing = []
        for requirement in requirements:
            legacy_ok, _ = pip_download(
                [requirement], ["manylinux2014_x86_64"], Path(tmp) / "legacy"
            )
            if not legacy_ok:
                legacy_missing.append(requirement)
    if legacy_missing:
        print(
            "Informativno — bez manylinux2014 (glibc 2.17) wheela, trebaju glibc ≥ 2.28: "
            + ", ".join(legacy_missing)
        )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
