"""Evidence file uploads (evidence-file-uploads spec, #222): real PostgreSQL, local store."""

import hashlib
import json
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from atesta_api.main import app
from atesta_api.modules.evidence import files
from atesta_api.modules.evidence.api import LocalEvidenceStore, StoreUnavailableError
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine, text

from .conftest import WEB_ORIGIN, auth
from .test_bff import signed_in
from .test_control_workspace import statement
from .test_control_workspace import workspace as workspace
from .test_members import events, org_with
from .test_rbac import _add, _future

PDF = b"%PDF-1.7\n%synthetic policy for a test\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"synthetic pixels"
JPEG = b"\xff\xd8\xff\xe0" + b"synthetic photo"
OOXML = b"PK\x03\x04" + b"synthetic office document"


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[LocalEvidenceStore]:
    monkeypatch.setenv("ATESTA_ENV", "test")
    local = LocalEvidenceStore(tmp_path / "evidence")
    app.state.evidence_store = local
    yield local
    del app.state.evidence_store


def upload(
    client: TestClient,
    org: str,
    control: str,
    sub: str,
    *,
    name: str = "policy.pdf",
    data: bytes = PDF,
    browser_type: str = "application/pdf",
    **fields: Any,
) -> Response:
    form = {"submission_id": str(uuid.uuid4()), "title": "Synthetic policy", **fields}
    return client.post(
        f"/api/v1/orgs/{org}/controls/{control}/evidence/files",
        data=form,
        files={"file": (name, data, browser_type)},
        headers=auth(sub),
    )


def download(client: TestClient, org: str, evidence_id: str, sub: str) -> Response:
    return client.get(f"/api/v1/orgs/{org}/evidence/{evidence_id}/file", headers=auth(sub))


def code(response: Response) -> str:
    return str(response.json()["detail"]["code"])


def stored_path(store: LocalEvidenceStore, superuser: Engine, evidence_id: str) -> Path:
    with superuser.connect() as conn:
        key = conn.execute(
            text("SELECT storage_key FROM evidence WHERE id = :i"), {"i": evidence_id}
        ).scalar_one()
    return store.root.joinpath(*key.split("/"))


def rows(superuser: Engine, org: str) -> int:
    with superuser.connect() as conn:
        query = text("SELECT count(*) FROM evidence WHERE organization_id = :o")
        return int(conn.execute(query, {"o": org}).scalar_one())


# --- upload, list, download ----------------------------------------------------------------


def test_upload_list_and_download_return_the_same_bytes(
    client: TestClient, superuser: Engine, workspace: str, store: LocalEvidenceStore
) -> None:
    org, subs = org_with(client, superuser, mem="member")
    created = upload(client, org, workspace, subs["mem"], title="  Política de acceso  ")
    assert created.status_code == 201, created.text
    item = created.json()
    digest = hashlib.sha256(PDF).hexdigest()
    assert item["kind"] == "document"
    assert item["title"] == "Política de acceso"
    assert item["file"] == {
        "name": "policy.pdf",
        "media_type": "application/pdf",
        "size_bytes": len(PDF),
        "sha256": digest,
    }
    page = client.get(
        f"/api/v1/orgs/{org}/controls/{workspace}/evidence", headers=auth(subs["mem"])
    ).json()
    assert page["items"] == [item]
    assert page["file_uploads"] == {
        "enabled": True,
        "max_bytes": 25 * 1024 * 1024,
        "extensions": ["csv", "docx", "jpeg", "jpg", "pdf", "png", "txt", "xlsx"],
    }
    assert "storage_key" not in json.dumps(page)
    with superuser.connect() as conn:
        row = conn.execute(
            text(
                "SELECT kind, source_type, sha256, size_bytes, media_type, storage_key"
                " FROM evidence WHERE id = :i"
            ),
            {"i": item["id"]},
        ).one()
    assert tuple(row)[:5] == ("document", "upload", digest, len(PDF), "application/pdf")
    assert row.storage_key == f"{org}/evidence/{item['id']}/policy.pdf"

    got = download(client, org, item["id"], subs["mem"])
    assert got.status_code == 200
    assert got.content == PDF
    assert got.headers["content-type"] == "application/pdf"
    assert got.headers["content-disposition"] == 'attachment; filename="policy.pdf"'
    assert got.headers["x-content-type-options"] == "nosniff"
    assert got.headers["content-security-policy"] == "sandbox; default-src 'none'"
    assert events(superuser, org, "evidence.file_uploaded") == 1
    assert events(superuser, org, "evidence.file_downloaded") == 1


def test_audit_metadata_carries_no_title_or_file_name(
    client: TestClient, superuser: Engine, workspace: str, store: LocalEvidenceStore
) -> None:
    org, subs = org_with(client, superuser)
    item = upload(
        client, org, workspace, subs["owner"], name="secret-plan.pdf", title="Secret title"
    ).json()
    download(client, org, item["id"], subs["owner"])
    with superuser.connect() as conn:
        found = conn.execute(
            text(
                "SELECT action, target_id, metadata FROM audit_events WHERE organization_id = :o"
                " AND action LIKE 'evidence.file%' ORDER BY action"
            ),
            {"o": org},
        ).all()
    assert [(a, t) for a, t, _ in found] == [
        ("evidence.file_downloaded", item["id"]),
        ("evidence.file_uploaded", item["id"]),
    ]
    assert found[1].metadata == {
        "control_key": workspace,
        "media_type": "application/pdf",
        "size_bytes": len(PDF),
    }
    assert "ecret" not in json.dumps([m for _, _, m in found])


@pytest.mark.parametrize(
    ("name", "data", "media_type"),
    [
        ("scan.PNG", PNG, "image/png"),
        ("photo.jpg", JPEG, "image/jpeg"),
        ("photo.jpeg", JPEG, "image/jpeg"),
        ("notes.txt", "Acta nº 12: aprobada".encode("cp1252"), "text/plain"),
        ("users.csv", b"user;mfa\nana;yes\n", "text/csv"),
        (
            "minutes.docx",
            OOXML,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        (
            "inventory.xlsx",
            OOXML,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
    ],
)
def test_each_accepted_type_is_stored_with_its_canonical_media_type(
    client: TestClient,
    superuser: Engine,
    workspace: str,
    store: LocalEvidenceStore,
    name: str,
    data: bytes,
    media_type: str,
) -> None:
    org, subs = org_with(client, superuser)
    # The browser's declared type is ignored: the extension decides, the content must match.
    created = upload(
        client, org, workspace, subs["owner"], name=name, data=data, browser_type="text/html"
    )
    assert created.status_code == 201, created.text
    assert created.json()["file"]["media_type"] == media_type
    got = download(client, org, created.json()["id"], subs["owner"])
    assert (got.content, got.headers["content-type"].split(";")[0]) == (data, media_type)


def test_a_file_larger_than_the_in_memory_spool_round_trips(
    client: TestClient, superuser: Engine, workspace: str, store: LocalEvidenceStore
) -> None:
    """Above 1 MiB the upload spools to a temporary file (the hosted API's /tmp volume)."""
    org, subs = org_with(client, superuser)
    big = b"%PDF-1.7\n" + bytes(range(256)) * (3 * 1024 * 4)  # about 3 MiB
    created = upload(client, org, workspace, subs["owner"], data=big)
    assert created.status_code == 201, created.text
    assert created.json()["file"]["size_bytes"] == len(big)
    assert created.json()["file"]["sha256"] == hashlib.sha256(big).hexdigest()
    assert download(client, org, created.json()["id"], subs["owner"]).content == big


def test_file_names_become_safe_keys_and_keep_their_extension(
    client: TestClient, superuser: Engine, workspace: str, store: LocalEvidenceStore
) -> None:
    org, subs = org_with(client, superuser)
    for name, expected in [
        ("C:\\fakepath\\..\\política de acceso.pdf", "pol_tica_de_acceso.pdf"),
        ("../../etc/passwd.pdf", "passwd.pdf"),
        ("x" * 300 + ".pdf", "x" * 100 + ".pdf"),
    ]:
        created = upload(client, org, workspace, subs["owner"], name=name)
        assert created.status_code == 201, created.text
        assert created.json()["file"]["name"] == expected
        assert stored_path(store, superuser, created.json()["id"]).read_bytes() == PDF


# --- who may do what -----------------------------------------------------------------------


def test_roles_tenants_and_hidden_controls(
    client: TestClient, superuser: Engine, workspace: str, store: LocalEvidenceStore
) -> None:
    org, subs = org_with(client, superuser, mem="member")
    _, others = org_with(client, superuser)
    auditor = _add(superuser, client, org, "auditor", _future())
    item = upload(client, org, workspace, subs["mem"]).json()

    refused = upload(client, org, workspace, auditor)
    assert (refused.status_code, code(refused)) == (403, "identity.forbidden")
    assert download(client, org, item["id"], auditor).content == PDF  # auditors read

    stranger = upload(client, org, workspace, others["owner"])
    assert (stranger.status_code, code(stranger)) == (404, "identity.not_found")
    assert download(client, org, item["id"], others["owner"]).status_code == 404

    hidden = upload(client, org, "no_such_control", subs["owner"])
    assert (hidden.status_code, code(hidden)) == (404, "evidence.control_not_found")
    assert rows(superuser, org) == 1


def test_another_organization_cannot_download_by_id(
    client: TestClient, superuser: Engine, workspace: str, store: LocalEvidenceStore
) -> None:
    org, subs = org_with(client, superuser)
    other, others = org_with(client, superuser)
    item = upload(client, org, workspace, subs["owner"]).json()
    leaked = download(client, other, item["id"], others["owner"])
    assert (leaked.status_code, code(leaked)) == (404, "evidence.file_not_found")
    assert PDF not in leaked.content
    assert events(superuser, other, "evidence.file_downloaded") == 0


def test_only_uploaded_documents_are_downloadable(
    client: TestClient, superuser: Engine, workspace: str, store: LocalEvidenceStore
) -> None:
    org, subs = org_with(client, superuser)
    recorded = client.post(
        f"/api/v1/orgs/{org}/controls/{workspace}/evidence",
        headers=auth(subs["owner"]),
        json=statement(),
    ).json()
    assert recorded["file"] is None
    for evidence_id in (recorded["id"], str(uuid.uuid4())):
        missing = download(client, org, evidence_id, subs["owner"])
        assert (missing.status_code, code(missing)) == (404, "evidence.file_not_found")


def test_a_cookie_upload_needs_the_web_origin(
    client: TestClient, superuser: Engine, workspace: str, store: LocalEvidenceStore
) -> None:
    org, subs = org_with(client, superuser)
    browser = signed_in(client, subs["owner"])
    path = f"/api/v1/orgs/{org}/controls/{workspace}/evidence/files"
    form = {"submission_id": str(uuid.uuid4()), "title": "Synthetic policy"}
    attached = {"file": ("policy.pdf", PDF, "application/pdf")}
    foreign = browser.post(
        path, data=form, files=attached, headers={"Origin": "https://evil.example"}
    )
    assert (foreign.status_code, code(foreign)) == (403, "auth.bad_origin")
    own = browser.post(path, data=form, files=attached, headers={"Origin": WEB_ORIGIN})
    assert own.status_code == 201, own.text


# --- refused uploads -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "data", "status", "expected"),
    [
        ("run.exe", b"MZ\x90\x00", 415, "evidence.file_type_not_allowed"),
        ("page.html", b"<script>alert(1)</script>", 415, "evidence.file_type_not_allowed"),
        ("image.svg", b"<svg onload=alert(1)>", 415, "evidence.file_type_not_allowed"),
        ("macro.docm", OOXML, 415, "evidence.file_type_not_allowed"),
        ("archive.zip", OOXML, 415, "evidence.file_type_not_allowed"),
        ("no-extension", PDF, 415, "evidence.file_type_not_allowed"),
        (".pdf", PDF, 415, "evidence.file_type_not_allowed"),
        ("policy.pdf", b"MZ\x90\x00 not a pdf", 422, "evidence.file_content_mismatch"),
        ("policy.pdf", b"<html>%PDF-1.7", 422, "evidence.file_content_mismatch"),
        ("scan.png", JPEG, 422, "evidence.file_content_mismatch"),
        ("photo.jpg", PNG, 422, "evidence.file_content_mismatch"),
        ("minutes.docx", PDF, 422, "evidence.file_content_mismatch"),
        ("notes.txt", b"text\x00binary", 422, "evidence.file_content_mismatch"),
        ("users.csv", b"a;b\n" + b"\x00" * 4, 422, "evidence.file_content_mismatch"),
        ("policy.pdf", b"", 422, "evidence.file_empty"),
    ],
)
def test_types_outside_the_allowlist_and_mismatched_content_are_refused(
    client: TestClient,
    superuser: Engine,
    workspace: str,
    store: LocalEvidenceStore,
    name: str,
    data: bytes,
    status: int,
    expected: str,
) -> None:
    org, subs = org_with(client, superuser)
    refused = upload(client, org, workspace, subs["owner"], name=name, data=data)
    assert (refused.status_code, code(refused)) == (status, expected)
    assert rows(superuser, org) == 0
    assert not any(p.is_file() for p in store.root.rglob("*"))


@pytest.mark.parametrize(
    "fields",
    [
        {"title": " "},
        {"title": "x" * 201},
        {"title": "null\x00title"},
        {"submission_id": "not-a-uuid"},
    ],
)
def test_invalid_fields_are_refused(
    client: TestClient,
    superuser: Engine,
    workspace: str,
    store: LocalEvidenceStore,
    fields: dict[str, str],
) -> None:
    org, subs = org_with(client, superuser)
    refused = upload(client, org, workspace, subs["owner"], **fields)
    assert (refused.status_code, code(refused)) == (422, "request.invalid")
    assert rows(superuser, org) == 0


def test_a_request_without_its_fields_or_file_is_refused(
    client: TestClient, superuser: Engine, workspace: str, store: LocalEvidenceStore
) -> None:
    org, subs = org_with(client, superuser)
    path = f"/api/v1/orgs/{org}/controls/{workspace}/evidence/files"
    headers = auth(subs["owner"])
    form = {"submission_id": str(uuid.uuid4()), "title": "Synthetic policy"}
    attached = ("policy.pdf", PDF, "application/pdf")
    attempts = [
        client.post(path, data=form, headers=headers),  # no file
        client.post(path, data={"title": "x"}, files={"file": attached}, headers=headers),
        client.post(path, data={**form, "file": "text, not a file"}, headers=headers),
        client.post(path, json=form, headers=headers),  # not multipart
        client.post(
            path, data=form, files=[("file", attached), ("file", attached)], headers=headers
        ),
    ]
    assert [(r.status_code, code(r)) for r in attempts] == [(422, "request.invalid")] * 5
    assert rows(superuser, org) == 0


def test_size_limits_are_enforced_before_and_while_reading(
    client: TestClient,
    superuser: Engine,
    workspace: str,
    store: LocalEvidenceStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(files, "MAX_FILE_BYTES", 1000)
    monkeypatch.setattr(files, "FORM_OVERHEAD_BYTES", 2000)
    org, subs = org_with(client, superuser)
    fits = upload(client, org, workspace, subs["owner"], data=b"%PDF-" + b"x" * 995)
    assert fits.status_code == 201, fits.text
    # One byte over the limit still fits the declared length allowance: the counted size decides.
    counted = upload(client, org, workspace, subs["owner"], data=b"%PDF-" + b"x" * 996)
    assert (counted.status_code, code(counted)) == (413, "evidence.file_too_large")
    # Far over: refused on the declared length, before the body is parsed.
    declared = upload(client, org, workspace, subs["owner"], data=b"%PDF-" + b"x" * 5000)
    assert (declared.status_code, code(declared)) == (413, "evidence.file_too_large")
    assert rows(superuser, org) == 1


def test_a_body_without_a_declared_length_is_refused(
    client: TestClient, superuser: Engine, workspace: str, store: LocalEvidenceStore
) -> None:
    org, subs = org_with(client, superuser)
    chunked = client.post(
        f"/api/v1/orgs/{org}/controls/{workspace}/evidence/files",
        content=iter([b"--b\r\n", b"--b--\r\n"]),  # a generator body is sent chunked
        headers={**auth(subs["owner"]), "Content-Type": "multipart/form-data; boundary=b"},
    )
    assert (chunked.status_code, code(chunked)) == (411, "evidence.length_required")


# --- retries -------------------------------------------------------------------------------


def test_a_retry_returns_the_first_record_and_a_changed_retry_conflicts(
    client: TestClient, superuser: Engine, workspace: str, store: LocalEvidenceStore
) -> None:
    org, subs = org_with(client, superuser, mem="member")
    submission = str(uuid.uuid4())
    first = upload(client, org, workspace, subs["owner"], submission_id=submission)
    again = upload(client, org, workspace, subs["owner"], submission_id=submission)
    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json() == first.json()
    assert first.json()["id"] == submission
    changed = [
        upload(client, org, workspace, subs["owner"], submission_id=submission, data=PDF + b"x"),
        upload(client, org, workspace, subs["owner"], submission_id=submission, title="Other"),
        upload(client, org, workspace, subs["mem"], submission_id=submission),
    ]
    assert [(r.status_code, code(r)) for r in changed] == [
        (409, "evidence.submission_conflict")
    ] * 3
    assert rows(superuser, org) == 1
    assert events(superuser, org, "evidence.file_uploaded") == 1
    assert stored_path(store, superuser, submission).read_bytes() == PDF


def test_a_submission_id_cannot_take_another_organizations_evidence_id(
    client: TestClient, superuser: Engine, workspace: str, store: LocalEvidenceStore
) -> None:
    org, subs = org_with(client, superuser)
    other, others = org_with(client, superuser)
    taken = upload(client, org, workspace, subs["owner"]).json()["id"]
    clash = upload(client, other, workspace, others["owner"], submission_id=taken)
    assert (clash.status_code, code(clash)) == (409, "evidence.submission_conflict")
    assert rows(superuser, other) == 0
    assert download(client, org, taken, subs["owner"]).content == PDF


def test_concurrent_uploads_of_one_submission_write_one_record(
    client: TestClient, superuser: Engine, workspace: str, store: LocalEvidenceStore
) -> None:
    org, subs = org_with(client, superuser)
    submission = str(uuid.uuid4())
    variants = [PDF, PDF, PDF + b"a", PDF + b"b"]

    def send(data: bytes) -> int:
        return upload(
            client, org, workspace, subs["owner"], submission_id=submission, data=data
        ).status_code

    with ThreadPoolExecutor(max_workers=4) as pool:
        statuses = sorted(pool.map(send, variants))
    assert statuses.count(201) == 1
    assert set(statuses) <= {200, 201, 409}
    assert rows(superuser, org) == 1
    assert events(superuser, org, "evidence.file_uploaded") == 1
    # Whatever won, the record and the stored object agree.
    assert download(client, org, submission, subs["owner"]).status_code == 200


# --- the store is missing or failing -------------------------------------------------------


def test_without_a_store_uploads_are_disabled_and_said_so(
    client: TestClient, superuser: Engine, workspace: str
) -> None:
    org, subs = org_with(client, superuser)
    page = client.get(
        f"/api/v1/orgs/{org}/controls/{workspace}/evidence", headers=auth(subs["owner"])
    ).json()
    assert page["file_uploads"]["enabled"] is False
    refused = upload(client, org, workspace, subs["owner"])
    assert (refused.status_code, code(refused)) == (503, "evidence.storage_unavailable")
    assert rows(superuser, org) == 0


def test_a_failing_store_writes_no_record_and_serves_nothing(
    client: TestClient,
    superuser: Engine,
    workspace: str,
    store: LocalEvidenceStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org, subs = org_with(client, superuser)
    item = upload(client, org, workspace, subs["owner"]).json()

    def fail(*args: object, **kwargs: object) -> None:
        raise StoreUnavailableError("synthetic outage")

    monkeypatch.setattr(store, "write", fail)
    monkeypatch.setattr(store, "read", fail)
    refused = upload(client, org, workspace, subs["owner"])
    assert (refused.status_code, code(refused)) == (503, "evidence.storage_unavailable")
    assert rows(superuser, org) == 1
    unavailable = download(client, org, item["id"], subs["owner"])
    assert (unavailable.status_code, code(unavailable)) == (503, "evidence.storage_unavailable")
    # An outage is not an integrity failure: nothing is recorded against the file.
    assert events(superuser, org, "evidence.file_integrity_failed") == 0


# --- integrity on every read (#263) --------------------------------------------------------


@pytest.mark.parametrize(
    ("tamper", "reason"),
    [
        (lambda path: path.write_bytes(PDF[:-1] + b"X"), "sha256"),  # same size, other bytes
        (lambda path: path.write_bytes(PDF[:-5]), "size"),  # truncated
        (lambda path: path.write_bytes(PDF + b"appended"), "size"),
        (lambda path: path.unlink(), "missing"),
    ],
    ids=["changed bytes", "truncated", "appended", "missing"],
)
def test_a_stored_object_that_no_longer_matches_is_never_served(
    client: TestClient,
    superuser: Engine,
    workspace: str,
    store: LocalEvidenceStore,
    tamper: Any,
    reason: str,
) -> None:
    org, subs = org_with(client, superuser)
    item = upload(client, org, workspace, subs["owner"]).json()
    tamper(stored_path(store, superuser, item["id"]))
    refused = download(client, org, item["id"], subs["owner"])
    assert (refused.status_code, code(refused)) == (409, "evidence.file_integrity_failed")
    assert b"PDF" not in refused.content and b"appended" not in refused.content
    assert "content-disposition" not in refused.headers
    with superuser.connect() as conn:
        recorded = conn.execute(
            text(
                "SELECT target_id, metadata FROM audit_events WHERE organization_id = :o"
                " AND action = 'evidence.file_integrity_failed'"
            ),
            {"o": org},
        ).all()
    assert [tuple(r) for r in recorded] == [(item["id"], {"reason": reason})]
    assert events(superuser, org, "evidence.file_downloaded") == 0
