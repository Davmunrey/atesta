"""Synthetic catalog fixtures for dev tooling (scanner-connectors spec, Local development).

Loads test content only (rule 10), never a pack from catalog/frameworks/. Runs on a connection
already acting as atesta_owner, since catalog tables are read-only for atesta_app. Idempotent:
existing rows are kept as they are.
"""

from collections.abc import Mapping
from typing import Any

from sqlalchemy import Connection
from sqlalchemy.dialects.postgresql import insert

from atesta_api.modules.compliance.models import (
    Check,
    Control,
    ControlCheck,
    Framework,
    Requirement,
)
from atesta_api.modules.compliance.models import Mapping as MappingRow
from atesta_api.platform.devenv import require_dev

_SYNTHETIC = "synthetic test content"


def _add(connection: Connection, model: type[Any], rows: list[dict[str, Any]]) -> None:
    if rows:
        connection.execute(insert(model).on_conflict_do_nothing(), rows)


def load_catalog_fixture(
    connection: Connection, data: Mapping[str, Any], engine: str, engine_version: str
) -> list[str]:
    """Insert the fixture's frameworks (as drafts), controls and checks; return framework keys."""
    require_dev("load_catalog_fixture")
    version, frameworks = str(data["catalog_version"]), list(data["frameworks"])
    controls: Mapping[str, list[str]] = data["controls"]
    checks = sorted({check for ids in controls.values() for check in ids})
    _add(
        connection,
        Framework,
        [
            {
                "key": f["key"],
                "name": f["name"],
                "version": "1",
                "jurisdiction": "none",
                "source": _SYNTHETIC,
                "license_notes": _SYNTHETIC,
                "status": "draft",
                "catalog_version": version,
            }
            for f in frameworks
        ],
    )
    _add(
        connection,
        Control,
        [
            {
                "key": key,
                "title_es": key,
                "title_en": key,
                "description_es": key,
                "description_en": key,
                "manual": not ids,
            }
            for key, ids in controls.items()
        ],
    )
    _add(
        connection,
        Check,
        [{"engine": engine, "check_id": c, "engine_version": engine_version} for c in checks],
    )
    _add(
        connection,
        ControlCheck,
        [
            {"control_key": key, "engine": engine, "check_id": c}
            for key, ids in controls.items()
            for c in ids
        ],
    )
    requirements = [
        (f["key"], code, keys) for f in frameworks for code, keys in f["requirements"].items()
    ]
    _add(
        connection,
        Requirement,
        [
            {"framework_key": fw, "code": code, "title_es": code, "source": _SYNTHETIC}
            for fw, code, _ in requirements
        ],
    )
    _add(
        connection,
        MappingRow,
        [
            {
                "framework_key": fw,
                "requirement_code": code,
                "control_key": key,
                "rationale": _SYNTHETIC,
                "source": _SYNTHETIC,
            }
            for fw, code, keys in requirements
            for key in keys
        ],
    )
    return [f["key"] for f in frameworks]
