"""Evidence file uploads and downloads (evidence-file-uploads spec, #222).

The browser sends the file to the API, the only writer to the store. The type comes from the
file name's extension and the content must match it; the SHA-256 recorded is the one computed
here over the bytes received. Every download recomputes it before a byte is served (#263).
Files are untrusted data: never executed, rendered or parsed (rule 5). A download is served only
once the malware scanner said the file is clean (evidence-malware-scanning spec).
"""

import hashlib
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, BinaryIO, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from atesta_api.modules.compliance.api import control_is_visible
from atesta_api.modules.evidence.api import storage_key_for
from atesta_api.modules.evidence.malware import NOT_SCANNED, PENDING, mark_not_scanned
from atesta_api.modules.evidence.models import Evidence, EvidenceControl, EvidenceFileScan
from atesta_api.modules.evidence.schemas import EvidenceOut, FileOut, FileUploads, ScanStatus
from atesta_api.modules.evidence.store import (
    EvidenceStore,
    ObjectMissingError,
    StoreUnavailableError,
)
from atesta_api.modules.identity.api import Member, require_member
from atesta_api.platform.audit import record
from atesta_api.platform.db import DbSession

MAX_FILE_BYTES = 25 * 1024 * 1024
FORM_OVERHEAD_BYTES = 64 * 1024  # boundaries, part headers, title and submission id
_CHUNK = 1024 * 1024
_CONTROLS = re.compile(r"[\x00-\x1f\x7f]")
_OOXML = "application/vnd.openxmlformats-officedocument."


def _starts(*signatures: bytes) -> Callable[[bytes], bool]:
    return lambda head: head.startswith(signatures)


@dataclass(frozen=True, slots=True)
class FileType:
    media_type: str
    matches: Callable[[bytes], bool] | None  # None: text, which must hold no NUL byte


_ZIP = _starts(b"PK\x03\x04")
FILE_TYPES = {
    "pdf": FileType("application/pdf", _starts(b"%PDF-")),
    "png": FileType("image/png", _starts(b"\x89PNG\r\n\x1a\n")),
    "jpg": FileType("image/jpeg", _starts(b"\xff\xd8\xff")),
    "jpeg": FileType("image/jpeg", _starts(b"\xff\xd8\xff")),
    "txt": FileType("text/plain", None),
    "csv": FileType("text/csv", None),
    "docx": FileType(_OOXML + "wordprocessingml.document", _ZIP),
    "xlsx": FileType(_OOXML + "spreadsheetml.sheet", _ZIP),
}

router = APIRouter(prefix="/api/v1/orgs/{org_id}", tags=["evidence"])


def evidence_store(request: Request) -> EvidenceStore | None:
    return cast(EvidenceStore | None, getattr(request.app.state, "evidence_store", None))


def file_uploads(request: Request) -> FileUploads:
    return FileUploads(
        enabled=evidence_store(request) is not None,
        max_bytes=MAX_FILE_BYTES,
        extensions=sorted(FILE_TYPES),
    )


def file_out(row: Evidence, scan: EvidenceFileScan | None) -> FileOut | None:
    """The file of an uploaded document. Scan outputs keep their metadata private."""
    if row.source_type != "upload" or row.storage_key is None:
        return None
    return FileOut(
        name=row.storage_key.rsplit("/", 1)[1],
        media_type=row.media_type or "",
        size_bytes=row.size_bytes or 0,
        sha256=row.sha256 or "",
        scan_status=cast(ScanStatus, scan.status if scan else PENDING),
    )


def scan_of(session: Session, row: Evidence) -> EvidenceFileScan | None:
    return session.scalar(
        select(EvidenceFileScan).where(
            EvidenceFileScan.organization_id == row.organization_id,
            EvidenceFileScan.evidence_id == row.id,
        )
    )


def _error(status: int, code: str) -> HTTPException:
    return HTTPException(status, detail={"code": code})


def _invalid(*fields: str) -> HTTPException:
    return HTTPException(422, detail={"code": "request.invalid", "fields": sorted(fields)})


def _safe_name(filename: str) -> tuple[str, FileType]:
    """A short name that keeps its extension, and the type that extension stands for."""
    base = re.split(r"[/\\]", filename)[-1]
    stem, dot, extension = base.rpartition(".")
    kind = FILE_TYPES.get(extension.lower())
    if not dot or not stem.strip(" .") or kind is None:
        raise _error(415, "evidence.file_type_not_allowed")
    return f"{stem[:100]}.{extension.lower()}", kind


def _measure(body: BinaryIO, kind: FileType) -> tuple[str, int]:
    """SHA-256 and size of the bytes received, refusing content that is not the declared type."""
    digest, size, head, text_file = hashlib.sha256(), 0, b"", kind.matches is None
    body.seek(0)
    while chunk := body.read(_CHUNK):
        if size == 0:
            head = chunk[:16]
        size += len(chunk)
        if size > MAX_FILE_BYTES:
            raise _error(413, "evidence.file_too_large")
        if text_file and b"\x00" in chunk:
            raise _error(422, "evidence.file_content_mismatch")
        digest.update(chunk)
    if size == 0:
        raise _error(422, "evidence.file_empty")
    if kind.matches is not None and not kind.matches(head):
        raise _error(422, "evidence.file_content_mismatch")
    return digest.hexdigest(), size


def _output(row: Evidence, scan: EvidenceFileScan | None) -> EvidenceOut:
    return EvidenceOut(
        id=row.id,
        kind=row.kind,
        title=row.title,
        created_by=row.created_by,
        created_at=row.created_at.astimezone(UTC),
        collected_at=row.collected_at.astimezone(UTC),
        statement=None,
        reference_url=None,
        file=file_out(row, scan),
    )


def _same_upload(
    session: Session, row: Evidence, member: Member, control_key: str, title: str, digest: str
) -> bool:
    linked = session.scalar(
        select(EvidenceControl.control_key).where(
            EvidenceControl.organization_id == row.organization_id,
            EvidenceControl.evidence_id == row.id,
            EvidenceControl.control_key == control_key,
        )
    )
    return (
        linked is not None
        and row.source_type == "upload"
        and row.sha256 == digest
        and row.title == title
        and row.created_by == member.user_id
    )


def _record_upload(
    session: Session,
    store: EvidenceStore,
    member: Member,
    control_key: str,
    evidence_id: uuid.UUID,
    title: str,
    upload: UploadFile,
) -> tuple[EvidenceOut, bool]:
    """Store the file, then its record. Returns the evidence and whether it is new."""
    name, kind = _safe_name(upload.filename or "")
    digest, size = _measure(upload.file, kind)
    org = member.organization_id
    # Serialize one submission, so a conflicting concurrent retry gets 409.
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"evidence:{org}:{evidence_id}"},
    )
    existing = session.scalar(
        select(Evidence).where(Evidence.organization_id == org, Evidence.id == evidence_id)
    )
    if existing is not None:
        if not _same_upload(session, existing, member, control_key, title, digest):
            raise _error(409, "evidence.submission_conflict")
        return _output(existing, scan_of(session, existing)), False
    key = storage_key_for(org, evidence_id, name)
    row = Evidence(
        id=evidence_id,
        organization_id=org,
        kind="document",
        title=title,
        storage_key=key,
        sha256=digest,
        media_type=kind.media_type,
        size_bytes=size,
        source_type="upload",
        created_by=member.user_id,
        collected_at=datetime.now(UTC),
    )
    try:  # another organization's evidence id: refused before anything is stored
        with session.begin_nested():
            session.add(row)
            session.flush()
    except IntegrityError:
        raise _error(409, "evidence.submission_conflict") from None
    upload.file.seek(0)
    try:
        store.write(key, upload.file, sha256=digest, media_type=kind.media_type, size=size)
    except StoreUnavailableError:
        raise _error(503, "evidence.storage_unavailable") from None
    if not store.scanned:
        mark_not_scanned(session, row)
    session.add(
        EvidenceControl(organization_id=org, evidence_id=evidence_id, control_key=control_key)
    )
    record(
        session,
        organization_id=org,
        action="evidence.file_uploaded",
        target_type="evidence",
        target_id=str(evidence_id),
        actor_user_id=member.user_id,
        metadata={"control_key": control_key, "media_type": kind.media_type, "size_bytes": size},
    )
    session.refresh(row)
    return _output(row, scan_of(session, row)), True


def _visible(session: Session, control_key: str) -> None:
    if not control_is_visible(session, control_key):
        raise _error(404, "evidence.control_not_found")


_UPLOAD_BODY = {
    "required": True,
    "content": {
        "multipart/form-data": {
            "schema": {
                "type": "object",
                "required": ["submission_id", "title", "file"],
                "properties": {
                    "submission_id": {"type": "string", "format": "uuid"},
                    "title": {"type": "string", "minLength": 1, "maxLength": 200},
                    "file": {"type": "string", "format": "binary"},
                },
            }
        }
    },
}


@router.post(
    "/controls/{control_key}/evidence/files",
    status_code=201,
    openapi_extra={"requestBody": _UPLOAD_BODY},
)
async def upload_file(
    control_key: str,
    request: Request,
    response: Response,
    member: Annotated[Member, Depends(require_member)],
    session: DbSession,
) -> EvidenceOut:
    """Authentication first, then the declared length, and only then the body."""
    declared = request.headers.get("content-length", "")
    if not declared.isdigit():
        raise _error(411, "evidence.length_required")
    if int(declared) > MAX_FILE_BYTES + FORM_OVERHEAD_BYTES:
        raise _error(413, "evidence.file_too_large")
    await run_in_threadpool(_visible, session, control_key)
    store = evidence_store(request)
    if store is None:
        raise _error(503, "evidence.storage_unavailable")
    if not request.headers.get("content-type", "").startswith("multipart/form-data"):
        raise _invalid("body")
    try:
        form = await request.form(max_files=1, max_fields=2)
    except StarletteHTTPException:
        raise _invalid("body") from None
    try:
        title = form.get("title")
        upload = form.get("file")
        try:
            evidence_id = uuid.UUID(str(form.get("submission_id")))
        except ValueError:
            raise _invalid("submission_id") from None
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 200:
            raise _invalid("title")
        if _CONTROLS.search(title):
            raise _invalid("title")
        if not isinstance(upload, UploadFile):
            raise _invalid("file")
        result, created = await run_in_threadpool(
            _record_upload, session, store, member, control_key, evidence_id, title.strip(), upload
        )
    finally:
        await form.close()  # removes the spooled upload
    if not created:
        response.status_code = 200
    return result


def _integrity_failure(session: Session, row: Evidence, member: Member, reason: str) -> Response:
    """Returned, not raised: the audit event must commit with the refusal."""
    record(
        session,
        organization_id=row.organization_id,
        action="evidence.file_integrity_failed",
        target_type="evidence",
        target_id=str(row.id),
        actor_user_id=member.user_id,
        metadata={"reason": reason},
    )
    return JSONResponse({"detail": {"code": "evidence.file_integrity_failed"}}, status_code=409)


def _refused_detail(status: str, store: EvidenceStore) -> dict[str, str] | None:
    """Fail closed: only a clean result, or the development store's not_scanned, is served."""
    if status == "no_threats_found" or (status == NOT_SCANNED and not store.scanned):
        return None
    if status == PENDING:
        return {"code": "evidence.file_scan_pending"}
    if status == "threats_found":
        return {"code": "evidence.file_malware_found"}
    return {"code": "evidence.file_not_scanned"}


def _download_refused(
    session: Session, row: Evidence, member: Member, status: str, detail: dict[str, str]
) -> Response:
    """Returned, not raised: the audit event must commit with the refusal."""
    record(
        session,
        organization_id=row.organization_id,
        action="evidence.file_download_refused",
        target_type="evidence",
        target_id=str(row.id),
        actor_user_id=member.user_id,
        metadata={"scan_status": status},
    )
    return JSONResponse({"detail": detail}, status_code=409)


@router.get("/evidence/{evidence_id}/file", response_class=Response)
def download_file(
    evidence_id: uuid.UUID,
    request: Request,
    member: Annotated[Member, Depends(require_member)],
    session: DbSession,
) -> Response:
    row = session.scalar(
        select(Evidence).where(
            Evidence.organization_id == member.organization_id,
            Evidence.id == evidence_id,
            Evidence.kind == "document",
            Evidence.source_type == "upload",
        )
    )
    if row is None or row.storage_key is None or row.size_bytes is None:
        raise _error(404, "evidence.file_not_found")
    store = evidence_store(request)
    if store is None:
        raise _error(503, "evidence.storage_unavailable")
    scan = scan_of(session, row)
    status = scan.status if scan else PENDING
    refused = _refused_detail(status, store)
    if refused is not None:  # decided before a byte is read from the store
        return _download_refused(session, row, member, status, refused)
    version = scan.object_version if scan else None  # the version that was scanned (D5)
    try:
        data = store.read(row.storage_key, row.size_bytes + 1, version)
    except ObjectMissingError:
        return _integrity_failure(session, row, member, "missing")
    except StoreUnavailableError:
        raise _error(503, "evidence.storage_unavailable") from None
    if len(data) != row.size_bytes:
        return _integrity_failure(session, row, member, "size")
    if hashlib.sha256(data).hexdigest() != row.sha256:
        return _integrity_failure(session, row, member, "sha256")
    record(
        session,
        organization_id=row.organization_id,
        action="evidence.file_downloaded",
        target_type="evidence",
        target_id=str(row.id),
        actor_user_id=member.user_id,
    )
    name = row.storage_key.rsplit("/", 1)[1]  # [A-Za-z0-9_.-] only: safe in a quoted string
    return Response(
        data,
        media_type=row.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Content-Security-Policy": "sandbox; default-src 'none'",
        },
    )
