"""Provjera kvalitete prije commita / deploya (Windows i Linux).

    python scripts/check.py            # ruff, ruff format --check, pytest, pip-audit
    python scripts/check.py --brzo     # bez pip-audita (radi bez interneta)

pip-audit: ranjivost u paketu koji ide u produkcijsku sliku (requirements.txt i njegove
ovisnosti) ruši provjeru; ranjivost samo u razvojnim alatima (requirements-dev.txt) je
upozorenje. Ako pip-audit ne može doći do baze ranjivosti (nema mreže), to je upozorenje.
Izlazni kod 0 = sve prošlo.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.utils import ensure_utf8_console  # noqa: E402

PY = sys.executable


def run(title: str, args: list[str]) -> bool:
    print(f"\n=== {title} ===", flush=True)
    result = subprocess.run(args, cwd=ROOT)
    ok = result.returncode == 0
    print(f"--- {title}: {'OK' if ok else 'GREŠKA'}", flush=True)
    return ok


def _canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def runtime_packages() -> set[str]:
    """requirements.txt + all their (installed) dependencies, canonical names."""
    names = []
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            names.append(re.split(r"[\[<>=!~; ]", line, maxsplit=1)[0])
    seen: set[str] = set()
    while names:
        name = _canonical(names.pop())
        if name in seen:
            continue
        seen.add(name)
        try:
            requires = metadata.distribution(name).requires or []
        except metadata.PackageNotFoundError:
            continue
        for req in requires:
            if "extra ==" in req:
                continue  # optional extras are not installed in the image
            names.append(re.split(r"[\[<>=!~;( ]", req, maxsplit=1)[0])
    return seen


def pip_audit() -> bool:
    print("\n=== pip-audit ===", flush=True)
    result = subprocess.run(
        [PY, "-m", "pip_audit", "--format", "json", "--progress-spinner", "off"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError:
        print(result.stderr.strip()[-2000:])
        print("--- pip-audit: UPOZORENJE — provjera nije izvedena (mreža?)")
        return True
    runtime = runtime_packages()
    critical, warnings = [], []
    for dep in report.get("dependencies", []):
        for vuln in dep.get("vulns", []):
            line = (
                f"{dep['name']} {dep['version']}: {vuln['id']} "
                f"(popravak: {', '.join(vuln.get('fix_versions') or ['nema'])})"
            )
            (critical if _canonical(dep["name"]) in runtime else warnings).append(line)
    for line in warnings:
        print(f"  upozorenje (samo dev alati): {line}")
    for line in critical:
        print(f"  KRITIČNO (produkcijska slika): {line}")
    ok = not critical
    status = "OK" if ok else "GREŠKA"
    print(f"--- pip-audit: {status} ({len(critical)} kritičnih, {len(warnings)} upozorenja)")
    return ok


def main() -> int:
    ensure_utf8_console()
    parser = argparse.ArgumentParser(description="ruff + pytest + pip-audit")
    parser.add_argument("--brzo", action="store_true", help="preskoči pip-audit")
    args = parser.parse_args()

    results = {
        "ruff check": run("ruff check", [PY, "-m", "ruff", "check", "."]),
        "ruff format": run("ruff format --check", [PY, "-m", "ruff", "format", "--check", "."]),
        "pytest": run("pytest", [PY, "-m", "pytest", "-q"]),
    }
    if not args.brzo:
        results["pip-audit"] = pip_audit()

    print("\n=== Sažetak ===")
    for name, ok in results.items():
        print(f"  {'✔' if ok else '✘'} {name}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
