"""Scan ingest (scanner-connectors spec, Ingest and Coverage).

One transaction: lock the scan, check the manifest and every file it lists, parse the OCSF output
strictly, pin every finding to the connected tenant, compute coverage, then insert findings and
one result per listed check and close the scan. Everything is checked before anything is
written, so a rejected scan has no rows. The output is untrusted data (rule 5); errors carry
codes, never values from it (rule 2).
"""

import hashlib
import uuid
from collections.abc import Iterable, Mapping, Sequence

from atesta_core.coverage import UnexpectedCheckError, coverage, silent_services
from atesta_core.manifest import ManifestError, verify_manifest
from atesta_core.ocsf import OcsfError, OcsfFinding, TenantMismatchError, parse_findings, pin_tenant
from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from atesta_api.modules.scanning.models import Finding, Scan, ScanCheckResult
from atesta_api.modules.scanning.runners import MANIFEST_FILE, OCSF_FILE, ScanStore
from atesta_api.platform.audit import record

ENGINE = "prowler"
OCSF_MAX_BYTES = 100_000_000  # ATESTA_OCSF_MAX_BYTES default; revisit after the live golden


class ScanNotFoundError(LookupError):
    """No such scan in the current org context."""


def _read_output(scan: Scan, store: ScanStore, max_bytes: int) -> tuple[str, list[OcsfFinding]]:
    prefix = scan.output_prefix
    if prefix is None:
        raise ManifestError("collected scan has no output prefix")
    manifest = store.read(prefix + MANIFEST_FILE)
    if len(manifest) > max_bytes:
        raise ManifestError("manifest is over the size limit")
    files = verify_manifest(manifest, lambda name: store.read(prefix + name), max_bytes)
    if OCSF_FILE not in files:
        raise ManifestError("manifest does not list the OCSF output")
    return hashlib.sha256(manifest).hexdigest(), parse_findings(files[OCSF_FILE])


def _insert(
    session: Session, model: type[Finding | ScanCheckResult], rows: Sequence[Mapping[str, object]]
) -> None:
    if rows:
        session.execute(insert(model), rows)


def _finish(session: Session, scan: Scan, status: str, metadata: Mapping[str, str | int]) -> str:
    scan.status = status
    scan.finished_at = func.now()
    record(
        session,
        organization_id=scan.organization_id,
        action=f"scan.{status}",
        target_type="scan",
        target_id=str(scan.id),
        metadata={"provider": scan.provider, **metadata},
    )
    session.flush()
    return status


def ingest_scan(
    session: Session,
    scan_id: uuid.UUID,
    *,
    store: ScanStore,
    tenant: str,
    listed: Iterable[str],
    excluded: Mapping[str, str],
    max_bytes: int = OCSF_MAX_BYTES,
) -> str:
    """Ingest a collected scan and return its status. A retried ingest changes nothing."""
    scan = session.scalars(
        select(Scan)
        .where(Scan.id == scan_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one_or_none()
    if scan is None:
        raise ScanNotFoundError(str(scan_id))
    if scan.status != "collected":  # ingested_at is set with the terminal status, never alone
        return scan.status
    try:
        manifest_sha256, findings = _read_output(scan, store, max_bytes)
        pin_tenant(findings, scan.provider, tenant)
        results = coverage(findings, listed, excluded)
    except TenantMismatchError:
        return _reject(session, scan, "scanning.tenant_mismatch")
    except (FileNotFoundError, ManifestError, OcsfError, UnexpectedCheckError):
        return _reject(session, scan, "scanning.output_invalid")

    org, engine = scan.organization_id, ENGINE
    _insert(
        session,
        Finding,
        [
            {
                "organization_id": org,
                "scan_id": scan.id,
                "engine": engine,
                "check_id": f.check_id,
                "status": f.status,
                "muted": f.muted,
                "severity": f.severity,
                "service": f.service,
                "resource_type": f.resource_type,
                "resource_uid": f.resource_uid,
                "resource_name": f.resource_name,
                "region": f.region,
                "message": f.message,
            }
            for f in findings
        ],
    )
    _insert(
        session,
        ScanCheckResult,
        [
            {
                "organization_id": org,
                "scan_id": scan.id,
                "engine": engine,
                "check_id": r.check_id,
                "status": r.status,
                "reason": r.reason,
                "pass_count": r.pass_count,
                "fail_count": r.fail_count,
                "manual_count": r.manual_count,
            }
            for r in results
        ],
    )
    scan.manifest_sha256 = manifest_sha256
    scan.expected_checks = sum(r.expected for r in results)
    scan.evaluated_checks = sum(r.evaluated for r in results)
    scan.ingested_at = func.now()
    status = "partial" if silent_services(results) else "succeeded"
    counts = {"expected_checks": scan.expected_checks, "evaluated_checks": scan.evaluated_checks}
    return _finish(session, scan, status, counts)


def _reject(session: Session, scan: Scan, code: str) -> str:
    """The whole scan is rejected: no rows, the code on the scan, nothing from the output."""
    scan.error_code = code
    return _finish(session, scan, "failed", {"error_code": code})
