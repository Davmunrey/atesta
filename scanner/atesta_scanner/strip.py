"""Strip personal-data fields from the OCSF output before it leaves the container (D10).

`resources[].data.metadata` is the full pydantic dump of each resource (users, mailboxes,
transport rules); M365 models declare no redacted fields. The rest of each finding is kept.
"""

import json


class OutputInvalidError(ValueError):
    """The engine output is not an OCSF findings array (wrapper exit 30)."""


def strip_metadata(raw: bytes) -> bytes:
    try:
        findings = json.loads(raw)
    except (ValueError, RecursionError):  # nesting too deep to parse is not OCSF
        raise OutputInvalidError("output is not JSON") from None
    if not isinstance(findings, list):
        raise OutputInvalidError("output is not an array of findings")
    for index, finding in enumerate(findings):
        resources = finding.get("resources", []) if isinstance(finding, dict) else None
        if not isinstance(resources, list):
            raise OutputInvalidError(f"finding {index}: resources is not a list")
        for resource in resources:
            data = resource.get("data") if isinstance(resource, dict) else None
            if data is None:
                continue
            if not isinstance(data, dict):
                raise OutputInvalidError(f"finding {index}: resource data is not an object")
            data.pop("metadata", None)
    return json.dumps(findings, separators=(",", ":")).encode()
