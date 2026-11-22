"""Every lint or type suppression in shipped code says why (issue #121)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SHIPPED = [
    "apps/api/src",
    "apps/worker/src",
    "apps/api/devtools",
    "packages/core/src",
    "scanner/atesta_scanner",
]
# A suppression followed by nothing but its codes: no reason given.
BARE = re.compile(
    r"#\s*(?:noqa(?::\s*[A-Z]+\d+(?:,\s*[A-Z]+\d+)*)?|type:\s*ignore(?:\[[\w\-, ]+\])?)\s*$"
)


def bare_suppressions(files: dict[str, str]) -> list[str]:
    return [
        f"{name}:{number}"
        for name, text in sorted(files.items())
        for number, line in enumerate(text.splitlines(), 1)
        if BARE.search(line)
    ]


def test_every_suppression_in_shipped_code_has_a_reason() -> None:
    files = {
        str(path.relative_to(ROOT)): path.read_text()
        for base in SHIPPED
        for path in (ROOT / base).rglob("*.py")
    }
    assert bare_suppressions(files) == []


def test_a_bare_suppression_is_caught() -> None:
    planted = {
        "a.py": "x = 1  # noqa: S105\ny = 2  # type: ignore[attr-defined]\nz = 3  # noqa\n",
        "b.py": "w = 4  # noqa: S105 - status value, not a password\n",
    }
    assert bare_suppressions(planted) == ["a.py:1", "a.py:2", "a.py:3"]
