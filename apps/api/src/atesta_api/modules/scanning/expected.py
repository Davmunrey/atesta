"""Expected check lists and exclusions (scanner-connectors spec, Image and Coverage).

`scanner/expected/<version>/<provider>.json` is the committed output of
`prowler <provider> --list-checks-json` for the pinned engine: `{"<provider>": [check ids]}`.
`m365-powershell.json` has the same shape and lists the PowerShell-backed M365 checks
(`scanner/tools/powershell_checks.py`). The image build compares both with the image; ingest
reads them as the expected and excluded sets.
"""

import json
import re
from pathlib import Path

from atesta_core.exclusions import excluded_checks

ENGINE_VERSION = "5.52.0"
_FILE = {"m365": "m365", "google_workspace": "googleworkspace"}  # Atesta -> Prowler provider
_CHECK_ID = re.compile(r"[a-z0-9]+(_[a-z0-9]+)+")


def _read(path: Path, key: str) -> list[str]:
    label = f"expected check list {path.name}"
    try:
        data = json.loads(path.read_bytes())
    except ValueError:
        raise ValueError(f"{label} is not JSON") from None
    checks = data.get(key) if isinstance(data, dict) and data.keys() == {key} else None
    if not isinstance(checks, list) or not all(
        isinstance(c, str) and _CHECK_ID.fullmatch(c) for c in checks
    ):
        raise ValueError(f"{label} is malformed")
    if len(set(checks)) != len(checks):
        raise ValueError(f"{label} lists a check twice")
    return sorted(checks)


def expected_checks(root: Path, provider: str, version: str = ENGINE_VERSION) -> list[str]:
    name = _FILE.get(provider)
    if name is None:
        raise ValueError("unknown provider")
    return _read(root / version / f"{name}.json", name)


def powershell_checks(root: Path, version: str = ENGINE_VERSION) -> list[str]:
    return _read(root / version / "m365-powershell.json", "m365")


def exclusions(root: Path, provider: str, version: str = ENGINE_VERSION) -> dict[str, str]:
    """{check id: reason} the scanner skips; each must be in the provider's expected list."""
    powershell = powershell_checks(root, version) if provider == "m365" else []
    excluded = excluded_checks(provider, powershell)
    unknown = sorted(set(excluded) - set(expected_checks(root, provider, version)))
    if unknown:
        raise ValueError(f"excluded checks are not listed: {', '.join(unknown)}")
    return excluded
