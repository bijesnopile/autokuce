"""Collect all `_("...")` strings from Python code and templates into i18n JSON files.

    python scripts/extract_strings.py            # update every language file except hr.json
    python scripts/extract_strings.py --lang de  # create/update app/i18n/de.json

The key is the Croatian source text. Existing translations are kept; new keys
are added with an empty value (empty = not translated, the source text is shown).
`hr.json` stays empty because Croatian is the source language.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.utils import ensure_utf8_console  # noqa: E402

APP = ROOT / "app"
I18N = APP / "i18n"

# _("text") or _('text'), also gettext("text"); supports escaped quotes.
PATTERN = re.compile(r"""(?:\b_|\bgettext)\(\s*(?P<q>["'])(?P<text>(?:\\.|(?!(?P=q)).)*?)(?P=q)""")


def collect() -> list[str]:
    found: set[str] = set()
    files = list(APP.rglob("*.py")) + list((APP / "templates").rglob("*.html"))
    for path in files:
        content = path.read_text(encoding="utf-8")
        for match in PATTERN.finditer(content):
            text = (
                match.group("text")
                .encode("utf-8")
                .decode("unicode_escape")
                .encode("latin-1")
                .decode("utf-8")
            )
            if text.strip():
                found.add(text)
    return sorted(found)


def update(lang: str, strings: list[str]) -> tuple[int, int]:
    path = I18N / f"{lang}.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    added = 0
    for text in strings:
        if text not in data:
            data[text] = ""
            added += 1
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    translated = sum(1 for value in data.values() if value)
    return added, translated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lang", action="append", help="jezik (npr. en); može više puta")
    args = parser.parse_args()
    ensure_utf8_console()
    strings = collect()
    languages = args.lang or [p.stem for p in I18N.glob("*.json") if p.stem != "hr"]
    print(f"Pronađeno {len(strings)} stringova.")
    for lang in languages:
        if lang == "hr":
            print("hr.json se ne mijenja (izvorni jezik).")
            continue
        added, translated = update(lang, strings)
        print(f"{lang}.json: +{added} novih, prevedeno {translated}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
