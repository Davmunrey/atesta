"""Rule 9 guard: no framework identifier in code (control-model spec). No allowlist."""

import io
import re
import tokenize
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[3]
GUARDED = [
    "apps/api/src",
    "apps/api/migrations",
    "apps/worker",
    "packages/core/src",
    "scanner/atesta_scanner",
    "scanner/tools",
]
DENYLIST = {"ens", "nis2", "iso27001", "27001", "rd311", "dora", "soc2"}
# Splits on non-alphanumerics, camelCase and acronym CapWords: ENSLevel -> ENS, Level.
_SPLIT = re.compile(r"[^0-9A-Za-z]+|(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
# NAME, STRING and the literal text of f-strings (tokenized apart since Python 3.12).
_CHECKED = {tokenize.NAME, tokenize.STRING, tokenize.FSTRING_MIDDLE}


def parts(value: str) -> set[str]:
    return {p.lower() for p in _SPLIT.split(value) if p}


def pack_ids() -> set[str]:
    packs = (REPO / "catalog" / "frameworks").glob("*/pack.yaml")
    return {str(yaml.safe_load(p.read_text())["id"]) for p in packs if p.parent.name != "_template"}


def violations(source: str, packs: set[str]) -> list[str]:
    found = []
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type not in _CHECKED:
            continue
        if parts(tok.string) & DENYLIST or any(p in tok.string for p in packs):
            found.append(tok.string)
    return found


def test_guarded_code_names_no_framework() -> None:
    packs = pack_ids()
    hits = {
        str(path.relative_to(REPO)): violations(path.read_text(), packs)
        for root in GUARDED
        for path in (REPO / root).rglob("*.py")
    }
    assert {k: v for k, v in hits.items() if v} == {}


def test_guard_self_check() -> None:
    flagged = [
        "ENS_MEDIUM = 1",
        'x = "ens"',
        "class EnsLevel: ...",
        'k = "ens-medium"',
        "iso27001_2022 = 1",
        "class ENSLevel: ...",
        "class DORAReport: ...",
        'k = f"ens_{x}"',
        'k = f"{prefix}nis2"',
        'k = rf"ens-medium"',
    ]
    clean = [
        "max_tokens = 1",
        "screens_count = 2",
        "def ensure_tenant(): ...",
        "class HTTPServerError: ...",
        'k = f"{x}_tokens"',
    ]
    assert all(violations(s, set()) for s in flagged)
    assert not any(violations(s, set()) for s in clean)
