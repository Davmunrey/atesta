"""Expected check lists (scanner-connectors spec, Image and Coverage).

`scanner/expected/<version>/<provider>.json` is the committed output of
`prowler <provider> --list-checks-json` for the pinned engine: `{"<provider>": [check ids]}`.
The image build compares it with the image (PR 5); ingest reads it as the expected set.
"""

import json
import re
from pathlib import Path

ENGINE_VERSION = "5.49.0"
_FILE = {"m365": "m365", "google_workspace": "googleworkspace"}  # Atesta -> Prowler provider
_CHECK_ID = re.compile(r"[a-z0-9]+(_[a-z0-9]+)+")


def expected_checks(root: Path, provider: str, version: str = ENGINE_VERSION) -> list[str]:
    name = _FILE.get(provider)
    if name is None:
        raise ValueError("unknown provider")
    try:
        data = json.loads((root / version / f"{name}.json").read_bytes())
    except ValueError:
        raise ValueError(f"expected check list for {provider} is not JSON") from None
    checks = data.get(name) if isinstance(data, dict) and data.keys() == {name} else None
    if not isinstance(checks, list) or not all(
        isinstance(c, str) and _CHECK_ID.fullmatch(c) for c in checks
    ):
        raise ValueError(f"expected check list for {provider} is malformed")
    if len(set(checks)) != len(checks):
        raise ValueError(f"expected check list for {provider} lists a check twice")
    return sorted(checks)
