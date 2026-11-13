"""Scan ingest (scanner-connectors spec, Ingest and Coverage).

One transaction: lock the scan, check the manifest and every file it lists, parse the OCSF output
strictly, pin every finding to the connected tenant, compute coverage, then insert findings and
one result per listed check, register the manifest and the OCSF file as evidence of every control
the scan gives a result for, and close the scan. Everything is checked before anything is
written, so a rejected scan has no rows. The output is untrusted data (rule 5); errors carry
codes, never values from it (rule 2).
"""

import hashlib
import uuid
from collections.abc import Iterable, Mapping, Sequence

from atesta_core.controls import control_results
from atesta_core.coverage import CheckResult, UnexpectedCheckError, coverage, silent_services
from atesta_core.manifest import ManifestError, verify_manifest
from atesta_core.ocsf import OcsfError, OcsfFinding, TenantMismatchError, parse_findings, pin_tenant
from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from atesta_api.modules.compliance.api import active_control_checks
from atesta_api.modules.evidence.api import ScanOutputFile, register_scan_output
from atesta_api.modules.scanning.models import Finding, Scan, ScanCheckResult
from atesta_api.modules.scanning.runners import MANIFEST_FILE, OCSF_FILE, ScanStore
from atesta_api.platform.audit import record
from atesta_api.platform.queue import defer

ENGINE = "prowler"
SNAPSHOT_TASK = "atesta:snapshot_scores"  # the worker's namespaced name; a worker test pins it
OCSF_MAX_BYTES = 100_000_000  # ATESTA_OCSF_MAX_BYTES default; revisit after the live golden


class ScanNotFoundError(LookupError):
    """No such scan in the current org context."""


def _read_output(
    scan: Scan, store: ScanStore, max_bytes: int
) -> tuple[list[ScanOutputFile], list[OcsfFinding]]:
    """The verified manifest and OCSF file, and the findings parsed from that file."""
    prefix = scan.output_prefix
    if prefix is None:
        raise ManifestError("collected scan has no output prefix")
    manifest = store.read(prefix + MANIFEST_FILE)
    if len(manifest) > max_bytes:
        raise ManifestError("manifest is over the size limit")
    files = verify_manifest(manifest, lambda name: store.read(prefix + name), max_bytes)
    if OCSF_FILE not in files:
        raise ManifestError("manifest does not list the OCSF output")
    kept = [(MANIFEST_FILE, manifest), (OCSF_FILE, files[OCSF_FILE])]
    outputs = [
        ScanOutputFile(
            prefix + name, hashlib.sha256(data).hexdigest(), len(data), "application/json"
        )
        for name, data in kept
    ]
    return outputs, parse_findings(files[OCSF_FILE])


def _register_evidence(
    session: Session, scan: Scan, outputs: list[ScanOutputFile], results: list[CheckResult]
) -> None:
    checks = [(ENGINE, r.check_id, r.status) for r in results]
    controls = control_results(active_control_checks(session), checks)
    register_scan_output(
        session,
        organization_id=scan.organization_id,
        scan_id=scan.id,
        files=outputs,
        control_keys=[c.control_id for c in controls],
        collected_at=scan.started_at or session.execute(select(func.now())).scalar_one(),
    )


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
        outputs, findings = _read_output(scan, store, max_bytes)
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
    _register_evidence(session, scan, outputs, results)
    scan.manifest_sha256 = outputs[0].sha256
    scan.expected_checks = sum(r.expected for r in results)
    scan.evaluated_checks = sum(r.evaluated for r in results)
    scan.ingested_at = func.now()
    status = "partial" if silent_services(results) else "succeeded"
    counts = {"expected_checks": scan.expected_checks, "evaluated_checks": scan.evaluated_checks}
    _finish(session, scan, status, counts)
    ids = {"organization_id": str(scan.organization_id), "scan_id": str(scan.id)}
    defer(session, SNAPSHOT_TASK, queue="scans", **ids)  # commits with the ingest
    return status


def _reject(session: Session, scan: Scan, code: str) -> str:
    """The whole scan is rejected: no rows, the code on the scan, nothing from the output."""
    scan.error_code = code
    return _finish(session, scan, "failed", {"error_code": code})
