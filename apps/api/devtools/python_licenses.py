"""Python dependency licences (ADR-006): no GPL or AGPL; LGPL only for the libraries listed.

Reads the licence metadata of every installed distribution (`uv sync` first). Exit 1 on a GPL
or AGPL licence, on an LGPL library not in LGPL_ALLOWED, or on an undeclared licence not in
KNOWN. Usage: uv run python -m apps.api.devtools.python_licenses
"""

import re
import sys
from collections.abc import Iterable
from importlib import metadata

WORKSPACE = {"atesta-api", "atesta-core", "atesta-scanner", "atesta-worker"}
# Unmodified LGPL libraries allowed by ADR-006 amendment 1, as listed in THIRD_PARTY_NOTICES.md.
LGPL_ALLOWED = {"psycopg", "psycopg-binary", "psycopg-pool"}
# Distributions whose metadata declares no licence: name -> licence read at the source, and where.
KNOWN: dict[str, str] = {}

_AGPL = re.compile(r"\bAGPL|Affero General Public", re.I)
_LGPL = re.compile(r"\bLGPL|Lesser General Public|Library General Public", re.I)
_GPL = re.compile(r"(?<![LA])GPL|(?<!Lesser )(?<!Library )(?<!Affero )General Public License", re.I)


def licence_text(meta: metadata.PackageMetadata) -> str:
    """Every licence statement a distribution makes, joined."""
    parts = [meta.get("License-Expression") or ""]
    declared = meta.get("License") or ""
    parts.append(declared.splitlines()[0] if declared.strip() else "")
    classifiers = meta.get_all("Classifier") or []
    parts += [c for c in classifiers if c.startswith("License ::")]
    return " ; ".join(part.strip() for part in parts if part.strip())


def classify(name: str, text: str) -> str | None:
    """Why this distribution's licence is refused, or None when it is allowed."""
    if name in WORKSPACE:
        return None
    if not text:
        return None if name in KNOWN else f"{name}: no licence declared; look it up, add to KNOWN"
    if _AGPL.search(text):
        return f"{name}: AGPL ({text})"
    without_lgpl = _LGPL.sub("", text)
    if _GPL.search(without_lgpl):
        return f"{name}: GPL ({text})"
    if _LGPL.search(text) and name not in LGPL_ALLOWED:
        return f"{name}: LGPL not listed in LGPL_ALLOWED ({text})"
    return None


def problems(distributions: Iterable[tuple[str, str]]) -> list[str]:
    found = (classify(name, text) for name, text in distributions)
    return sorted(problem for problem in found if problem)


def main() -> int:
    installed = [
        (d.metadata["Name"].lower(), licence_text(d.metadata)) for d in metadata.distributions()
    ]
    refused = problems(installed)
    for problem in refused:
        print(f"FAILED {problem}")
    if not refused:
        print(f"passed: {len(installed)} distributions, no GPL or AGPL, LGPL only where allowed")
    return 1 if refused else 0


if __name__ == "__main__":
    sys.exit(main())
