"""API user-facing strings exist in Spanish and English (i18n-complete spec, rule 11)."""

import json
from pathlib import Path

import pytest
from atesta_api.platform.i18n import LOCALES, message

MESSAGES = Path(__file__).resolve().parents[1] / "src" / "atesta_api" / "messages"


def _leaves(tree: dict[str, object], prefix: str = "") -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in tree.items():
        path = f"{prefix}.{key}" if prefix else key
        out.update(_leaves(value, path) if isinstance(value, dict) else {path: value})
    return out


def _load(locale: str) -> dict[str, object]:
    return _leaves(json.loads((MESSAGES / f"{locale}.json").read_text(encoding="utf-8")))


def test_spanish_and_english_have_the_same_keys() -> None:
    assert sorted(_load("es")) == sorted(_load("en"))
    assert sorted(path.stem for path in MESSAGES.glob("*.json")) == sorted(LOCALES)


@pytest.mark.parametrize("locale", LOCALES)
def test_every_message_is_a_non_empty_string(locale: str) -> None:
    for key, value in _load(locale).items():
        assert isinstance(value, str) and value.strip(), key


def test_a_missing_key_is_a_bug() -> None:
    assert message("en", "applicability.yes") == "Yes"
    with pytest.raises(KeyError):
        message("es", "applicability.nope")
    with pytest.raises(KeyError):
        message("es", "applicability")  # a group, not a message
