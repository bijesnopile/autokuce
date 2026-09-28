"""Command line tools.

    python -m app.cli maintenance [--dry-run]
    python -m app.cli create-superadmin --email ... --password ...
    python -m app.cli reset-2fa --email ...

Commands are added phase by phase; see `python -m app.cli --help`.
"""

from __future__ import annotations

import argparse
import logging
import sys

from app.utils import ensure_utf8_console


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Autokuća CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="primijeni Alembic migracije (upgrade head)")

    args = parser.parse_args(argv)
    ensure_utf8_console()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.command == "migrate":
        from app.migrate import upgrade_head

        upgrade_head()
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
