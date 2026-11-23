"""Dev-only helpers fail closed, and queued jobs take ids only (scanner-connectors spec)."""

import uuid
from pathlib import Path
from typing import Any

import pytest
from atesta_api.modules.compliance.api import load_catalog_fixture
from atesta_api.modules.identity.api import ensure_dev_organization
from atesta_api.modules.scanning.api import run_fixture_scan
from atesta_api.platform.queue import defer

NOTHING: Any = None  # the guard must refuse before touching the session or connection


@pytest.mark.parametrize("env", [None, "prod", "staging"])
def test_dev_helpers_refuse_outside_dev(monkeypatch: pytest.MonkeyPatch, env: str | None) -> None:
    if env is None:
        monkeypatch.delenv("ATESTA_ENV", raising=False)
    else:
        monkeypatch.setenv("ATESTA_ENV", env)
    with pytest.raises(RuntimeError, match="ATESTA_ENV"):
        load_catalog_fixture(NOTHING, {}, "prowler", "5.52.0")
    with pytest.raises(RuntimeError, match="ATESTA_ENV"):
        ensure_dev_organization(NOTHING, uuid.uuid4(), "x")
    with pytest.raises(RuntimeError, match="ATESTA_ENV"):
        run_fixture_scan(
            NOTHING,
            organization_id=uuid.uuid4(),
            scan_id=uuid.uuid4(),
            connection_id=uuid.uuid4(),
            provider="m365",
            tenant="t",
            store=NOTHING,
            fixtures=Path(),
            expected_root=Path(),
        )


@pytest.mark.parametrize(
    "arguments",
    [{"email": "a@example.com"}, {"scan_id": uuid.uuid4()}, {"Scan_id": "x"}, {"_id": "x"}],
)
def test_jobs_are_deferred_with_id_strings_only(arguments: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="_id strings"):
        defer(NOTHING, "atesta:snapshot_scores", queue="scans", **arguments)
