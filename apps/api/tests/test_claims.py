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
API_MESSAGES = ROOT / "apps" / "api" / "src" / "atesta_api" / "messages"
DOCS = [ROOT / "README.md", ROOT / "PRODUCT.md"]
# The assistant's product FAQ (docs/specs/assistant.md): our own words, so the same rules apply.
FAQ = ROOT / "apps" / "web" / "src" / "content" / "assistant-faq.json"

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
    elif isinstance(node, list):
        for n, value in enumerate(node):
            yield from _values(value, f"{path}.{n}")
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
        f"{path.relative_to(ROOT)}:{key}": value
        for path in [*sorted(MESSAGES.glob("*.json")), *sorted(API_MESSAGES.glob("*.json"))]
        for key, value in _values(json.loads(path.read_text()))
    }
    texts.update({path.name: path.read_text() for path in DOCS})
    faq = json.loads(FAQ.read_text())
    texts.update({f"{FAQ.name}:{key}": value for key, value in _values(faq)})
    return texts


def test_no_copy_claims_compliance() -> None:
    texts = _repository_texts()
    assert len(texts) > 300  # every message value was read, not an empty glob
    assert any(key.startswith("assistant-faq.json:entries") for key in texts)
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


# Customer logos and testimonials (landing-legal A3, owner 23/11/2026): never without written
# permission. The data file starts empty; every entry must name the permission it rests on.
CUSTOMERS = ROOT / "apps" / "web" / "src" / "content" / "customers.json"


def customer_problems(entries: list[dict[str, Any]]) -> list[str]:
    problems = []
    for n, entry in enumerate(entries):
        for field in ("name", "permission_ref", "permission_date"):
            if not str(entry.get(field, "")).strip():
                problems.append(f"customers[{n}].{field}")
    return problems


def test_customer_proof_rests_on_written_permission() -> None:
    entries = json.loads(CUSTOMERS.read_text(encoding="utf-8"))
    assert isinstance(entries, list)
    assert customer_problems(entries) == []


def test_a_customer_without_permission_is_caught() -> None:
    assert customer_problems([{"name": "Ejemplo S.L.", "logo": "x.svg"}]) == [
        "customers[0].permission_ref",
        "customers[0].permission_date",
    ]
