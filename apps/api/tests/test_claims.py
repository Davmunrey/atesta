"""Product copy never claims that a customer complies (docs/specs/claims-honesty.md, #130).

Scans every i18n message value and the README and PRODUCT.md. Official framework texts in the
catalog are out of scope: they are the law's own words.
"""

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
MESSAGES = ROOT / "apps" / "web" / "messages"
DOCS = [ROOT / "README.md", ROOT / "PRODUCT.md"]

FORBIDDEN = [
    re.compile(r"\bcumpl(?:e|en|ís|imos)\b", re.I),
    re.compile(r"\bcumplimiento garantizado\b", re.I),
    re.compile(r"\bgarantiza(?:mos)?\b[^.]*\b(?:cumplimiento|certificaci[oó]n)\b", re.I),
    re.compile(r"\bcertificad[oa]s? por atesta\b", re.I),
    re.compile(r"\b(?:complies|comply|compliant|meets|guarantee[sd]?)\b", re.I),
    re.compile(r"\bcertified by atesta\b", re.I),
]


def _values(node: Any, path: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _values(value, f"{path}.{key}" if path else key)
    elif isinstance(node, str):
        yield path, node


def claims(texts: dict[str, str]) -> list[str]:
    return [
        f"{where}: {pattern.pattern}"
        for where, text in sorted(texts.items())
        for pattern in FORBIDDEN
        if pattern.search(text)
    ]


def _repository_texts() -> dict[str, str]:
    texts = {
        f"{path.name}:{key}": value
        for path in sorted(MESSAGES.glob("*.json"))
        for key, value in _values(json.loads(path.read_text()))
    }
    texts.update({path.name: path.read_text() for path in DOCS})
    return texts


def test_no_copy_claims_compliance() -> None:
    texts = _repository_texts()
    assert len(texts) > 300  # every message value was read, not an empty glob
    assert claims(texts) == []


@pytest.mark.parametrize(
    "text",
    [
        "Cumple",
        "No cumple",
        "Los requisitos que cumplen",
        "Cumplimiento garantizado",
        "Garantizamos la certificación ENS",
        "Certificado por Atesta",
        "Meets",
        "Your company is compliant",
        "Test once, comply with many",
        "Certified by Atesta",
    ],
)
def test_a_planted_claim_is_caught(text: str) -> None:
    assert claims({"planted": text}) != []


@pytest.mark.parametrize(
    "text",
    [
        "Atesta organiza evidencias para preparar auditorías. No certifica cumplimiento.",
        "Superado",
        "No implantado",
        "Readiness tool. Atesta does not issue certificates.",
        "Audit readiness across compliance frameworks",
    ],
)
def test_honest_copy_passes(text: str) -> None:
    assert claims({"honest": text}) == []
