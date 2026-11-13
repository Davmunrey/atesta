"""The job file a run receives (scanner-connectors spec, Scan lifecycle): ids, never a secret."""

import json
import re
from dataclasses import dataclass

from atesta_scanner.invocation import prowler_argv

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_KEYS = frozenset({"organization_id", "scan_id", "attempt", "provider", "tenant", "excluded"})


class JobError(ValueError):
    """job.json is not what the worker writes."""


@dataclass(frozen=True, slots=True)
class Job:
    organization_id: str
    scan_id: str
    attempt: int
    provider: str
    tenant: str
    excluded: tuple[str, ...]


def load_job(raw: bytes) -> Job:
    try:
        data = json.loads(raw)
    except ValueError:
        raise JobError("job.json is not JSON") from None
    if not isinstance(data, dict) or data.keys() != _KEYS:
        raise JobError("job.json has unexpected or missing keys")
    ids = (data["organization_id"], data["scan_id"])
    if not all(isinstance(i, str) and _UUID.fullmatch(i) for i in ids):
        raise JobError("job ids are not UUIDs")
    attempt, tenant, excluded = data["attempt"], data["tenant"], data["excluded"]
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
        raise JobError("job attempt must be 1 or more")
    if not isinstance(tenant, str) or not tenant:
        raise JobError("job has no tenant to pin")
    if not isinstance(excluded, list) or not all(isinstance(c, str) for c in excluded):
        raise JobError("job excluded checks must be a list of check ids")
    try:
        prowler_argv(data["provider"], excluded)  # validates the provider and every check id
    except ValueError as error:
        raise JobError(str(error)) from None
    return Job(*ids, attempt, data["provider"], tenant, tuple(sorted(excluded)))
