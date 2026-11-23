"""User-facing API strings in Spanish and English (i18n-complete spec, rule 11).

Code stays in English; the words a person reads come from `atesta_api/messages/{es,en}.json`,
the API's counterpart of the web message files. Spanish is the default language.
"""

import json
from functools import cache
from pathlib import Path
from typing import Literal

type Locale = Literal["es", "en"]
LOCALES: tuple[Locale, ...] = ("es", "en")
_DIR = Path(__file__).resolve().parent.parent / "messages"


@cache
def _catalog(locale: Locale) -> dict[str, object]:
    loaded: dict[str, object] = json.loads((_DIR / f"{locale}.json").read_text(encoding="utf-8"))
    return loaded


def message(locale: Locale, key: str) -> str:
    """The message at a dotted key; a missing key is a bug, so it raises."""
    node: object = _catalog(locale)
    for part in key.split("."):
        if not isinstance(node, dict):
            raise KeyError(key)
        node = node[part]
    if not isinstance(node, str):
        raise KeyError(key)
    return node


def accepted_locale(header: str | None) -> Locale:
    """The caller's preferred locale from an Accept-Language header; Spanish when none fits."""
    ranked: list[tuple[float, int, Locale]] = []
    for position, part in enumerate((header or "").split(",")):
        tag, _, params = part.strip().partition(";")
        primary = tag.strip().lower().split("-")[0]
        if primary not in LOCALES:
            continue
        weight = 1.0
        if params.strip().startswith("q="):
            try:
                weight = float(params.strip()[2:])
            except ValueError:
                continue
        if weight > 0:
            ranked.append((-weight, position, "en" if primary == "en" else "es"))
    return min(ranked)[2] if ranked else "es"
