"""Minimal gettext-style i18n.

The translation key is the Croatian source text. `app/i18n/{LANGUAGE}.json`
maps source text -> translated text. Missing keys return the source text, so
`hr.json` can stay empty. New language = new JSON file (no code changes);
`scripts/extract_strings.py` collects all `_()` calls into the JSON files.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from app.config import get_settings

I18N_DIR = Path(__file__).resolve().parent
log = logging.getLogger(__name__)


@lru_cache
def load_translations(language: str) -> dict[str, str]:
    path = I18N_DIR / f"{language}.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        log.error("Invalid translation file %s", path)
        return {}
    # Empty values mean "not translated yet" -> fall back to the source text.
    return {key: value for key, value in data.items() if value}


def gettext(text: str, **kwargs) -> str:
    """Translate `text` into the configured language and apply `str.format(**kwargs)`."""
    translated = load_translations(get_settings().LANGUAGE).get(text, text)
    if kwargs:
        try:
            return translated.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text.format(**kwargs)
    return translated


_ = gettext
