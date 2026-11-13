"""Immutable local projection of validated draft content; never a release command."""

from typing import Any, cast

from sqlalchemy import Connection, Table, select
from sqlalchemy.dialects.postgresql import insert

from atesta_api.modules.compliance.catalog import Catalog
from atesta_api.modules.compliance.models import (
    Check,
    Control,
    ControlCheck,
    Framework,
    Mapping,
    Requirement,
)
from atesta_api.platform.db import Base
from atesta_api.platform.devenv import require_dev


def _store(conn: Connection, model: type[Base], rows: list[dict[str, Any]]) -> None:
    table = cast(Table, model.__table__)
    for row in rows:
        conn.execute(insert(table).values(**row).on_conflict_do_nothing())
        query = select(table).where(*(c == row[c.name] for c in table.primary_key))
        existing = conn.execute(query).mappings().one()
        if any(existing[key] != value for key, value in row.items()) or existing.get("retired_at"):
            raise ValueError(
                f"catalog content conflict in {table.name}; explicit migration required"
            )


def import_preview(conn: Connection, catalog: Catalog) -> list[str]:
    """Add drafts atomically; exact reimports are no-ops and conflicts preserve existing data."""
    require_dev("catalog preview")
    if conn.exec_driver_sql("SELECT current_user").scalar_one() != "atesta_owner":
        raise RuntimeError("catalog preview requires the catalog owner role")
    with conn.begin_nested():
        conn.exec_driver_sql("SELECT pg_advisory_xact_lock(hashtext('atesta.catalog.preview'))")
        for pack in catalog.packs:
            metadata = pack.metadata
            fingerprint = catalog.fingerprint(pack)
            _store(
                conn,
                Framework,
                [
                    {
                        "key": metadata.id,
                        **metadata.model_dump(exclude={"id", "attributes"}),
                        "attributes": {
                            **metadata.attributes.model_dump(mode="json"),
                            "preview_fingerprint": fingerprint,
                        },
                        "catalog_version": fingerprint,
                    }
                ],
            )
            controls = catalog.used_controls(pack)
            _store(
                conn,
                Control,
                [
                    {
                        "key": c.id,
                        **c.model_dump(exclude={"id", "prowler_checks", "atesta_checks"}),
                    }
                    for c in controls
                ],
            )
            checks = sorted({check for c in controls for check in c.prowler_checks})
            _store(
                conn,
                Check,
                [
                    {
                        "engine": "prowler",
                        "check_id": check,
                        "engine_version": catalog.engine_version,
                    }
                    for check in checks
                ],
            )
            _store(
                conn,
                ControlCheck,
                [
                    {"control_key": c.id, "engine": "prowler", "check_id": check}
                    for c in controls
                    for check in c.prowler_checks
                ],
            )
            _store(
                conn,
                Requirement,
                [
                    {
                        "framework_key": metadata.id,
                        "code": r.id,
                        **r.model_dump(exclude={"id"}),
                    }
                    for r in pack.requirements
                ],
            )
            _store(
                conn,
                Mapping,
                [
                    {
                        "framework_key": metadata.id,
                        "requirement_code": m.requirement_id,
                        "control_key": m.control_id,
                        **m.model_dump(exclude={"requirement_id", "control_id"}),
                    }
                    for m in pack.mappings
                ],
            )
    return [p.metadata.id for p in catalog.packs]
