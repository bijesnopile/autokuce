"""Dependency pins and the Docker build contract (network-free checks).

The network check itself — does every pin have a cp311 Linux wheel for the Docker image — is
`python scripts/check_wheels.py` (pip download). These tests keep the preconditions in place.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(\[[a-z,]+\])?==\d[\w.]*$")


def requirement_lines(name: str) -> list[str]:
    lines = (ROOT / name).read_text(encoding="utf-8").splitlines()
    return [line.split("#", 1)[0].strip() for line in lines if line.split("#", 1)[0].strip()]


def test_every_requirement_is_pinned_exactly():
    for name in ("requirements.txt", "requirements-dev.txt"):
        for line in requirement_lines(name):
            if line.startswith("-r "):
                continue
            assert PIN_RE.match(line), f"{name}: '{line}' mora biti pinan s =="


def test_dockerfile_installs_only_binary_wheels_on_a_fixed_base():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "pip install --only-binary=:all: -r requirements.txt" in dockerfile
    bases = re.findall(r"^FROM\s+(\S+)", dockerfile, re.M)
    # Debian trixie (glibc 2.41) accepts manylinux_2_28 wheels (Pillow 12.3 ships only those).
    assert bases and all(base == "python:3.11-slim-trixie" for base in bases)


def test_pillow_is_not_downgraded_below_the_security_release():
    pins = dict(line.split("==") for line in requirement_lines("requirements.txt"))
    major, minor, *_ = (int(part) for part in pins["pillow"].split("."))
    assert (major, minor) >= (12, 3), "Pillow < 12.3 ima poznate ranjivosti (PRETPOSTAVKE.md)"
