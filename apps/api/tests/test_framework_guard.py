"""Rule 9 guard: no framework identifier in code (control-model spec). No allowlist."""

import io
import re
import tokenize
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[3]
GUARDED = ["apps/api/src", "apps/api/migrations", "apps/worker", "packages/core/src"]
DENYLIST = {"ens", "nis2", "iso27001", "27001", "rd311", "dora", "soc2"}
_SPLIT = re.compile(r"[^0-9A-Za-z]+|(?<=[a-z0-9])(?=[A-Z])")


def parts(value: str) -> set[str]:
    return {p.lower() for p in _SPLIT.split(value) if p}


def pack_ids() -> set[str]:
    packs = (REPO / "catalog" / "frameworks").glob("*/pack.yaml")
    return {str(yaml.safe_load(p.read_text())["id"]) for p in packs if p.parent.name != "_template"}


def violations(source: str, packs: set[str]) -> list[str]:
    found = []
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type not in (tokenize.NAME, tokenize.STRING):
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
    ]
    clean = ["max_tokens = 1", "screens_count = 2", "def ensure_tenant(): ..."]
    assert all(violations(s, set()) for s in flagged)
    assert not any(violations(s, set()) for s in clean)
