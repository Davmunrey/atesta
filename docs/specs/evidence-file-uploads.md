# Spec: evidence file uploads

- Issues: #222 (API, stores, infra), #400 (console screen). Builds on `control-evidence-statements.md`, `hosted-environment.md` (`s3-evidence`,
  #263) and `rbac.md`.
- Status: draft

## Problem

Evidence is statements and links today. The documents an auditor asks for (an approved policy, the
minutes of a committee, a signed supplier agreement, a screenshot of a setting) live in the
customer's own drives, so the evidence register only points at them. A link can stop working, can
change after the fact and cannot be handed to an auditor as part of a pack. The person preparing
the audit needs to put the file itself beside the control, and the auditor needs to know the file
they open is the file that was recorded.

## Acceptance criteria

**Upload (members)**
- [ ] **Endpoint:** `POST /api/v1/orgs/{org_id}/controls/{control_key}/evidence/files`,
  `multipart/form-data` with `submission_id` (UUID), `title` (1 to 200 characters, no control
  characters) and one `file`. Any member may upload; an auditor's write is refused (403) as
  everywhere. Cookie writes keep the same-origin check. The control must be visible, as for
  statements (404 `evidence.control_not_found`).
- [ ] **Through the API, not straight to the bucket:** the browser sends the file to the API on
  the app's own origin, and the API is the only writer to the evidence store (decision D1).
- [ ] **Size:** at most 25 MiB, at least one byte. A request with no `Content-Length` is refused
  (411) and one whose declared length is over the limit is refused (413
  `evidence.file_too_large`) before any of its body is read. The stored size is the size
  counted, not the size declared.
- [ ] **Type:** the type comes from the file name's extension, never from the browser's
  declared content type: `pdf`, `png`, `jpg`/`jpeg`, `txt`, `csv`, `docx`, `xlsx`. Anything else
  is refused (415 `evidence.file_type_not_allowed`). The content must match the type: the
  format's signature for binary types, and no NUL byte for `txt` and `csv` (422
  `evidence.file_content_mismatch`).
- [ ] **What it writes:** one evidence row of kind `document`, source `upload`, with the title,
  the author, the canonical media type, the counted size and the SHA-256 the API computed over
  the bytes it received; its link to the control; and the audit event
  `evidence.file_uploaded`. The object key is built by the server under
  `<organization_id>/evidence/<evidence_id>/`, from a sanitized file name. Audit metadata holds
  identifiers, size and media type, never the title or the file name.
- [ ] **Idempotent:** `submission_id` is the evidence id. The same submission again with the
  same bytes, title and control returns the first record (200) and writes nothing; with
  anything different it is a conflict (409 `evidence.submission_conflict`), concurrent requests
  included. A first write returns 201.
- [ ] **Store failures:** when the store is not configured or does not accept the write, the
  answer is 503 `evidence.storage_unavailable` and no row is written.

**Read (members and auditors)**
- [ ] **List:** each item of `GET .../controls/{control_key}/evidence` gains `file`: `null`, or
  the file name, media type, size and SHA-256 of an uploaded document. Storage keys never leave
  the API. The page also carries `file_uploads`: whether uploads are enabled, the size limit and
  the accepted extensions, so the screen offers only what works.
- [ ] **Download:** `GET /api/v1/orgs/{org_id}/evidence/{evidence_id}/file` returns the bytes as
  an attachment (`Content-Disposition: attachment`, the stored media type, `nosniff`,
  `Content-Security-Policy: sandbox`). Only uploaded documents of the caller's organization;
  anything else is 404 `evidence.file_not_found`. Scan outputs are not downloadable here.
- [ ] **Integrity on every read (#263):** the API recomputes the SHA-256 of the stored object
  and compares it and the size with the evidence row before a single byte is served. On a
  mismatch, or when the object is missing, it answers 409 `evidence.file_integrity_failed`,
  writes the audit event `evidence.file_integrity_failed` and serves nothing. A download that
  passes writes `evidence.file_downloaded`.

**Store**
- [ ] `ATESTA_EVIDENCE_STORE` selects the store: `s3` with `ATESTA_EVIDENCE_BUCKET` (hosted), or
  `local` with `ATESTA_EVIDENCE_STORE_DIR`, which starts only in a development `ATESTA_ENV`.
  Unset, uploads are disabled and the API still starts. Any other value stops the start.
- [ ] The S3 store sends the SHA-256 with the write, so S3 refuses bytes that changed on the way,
  and relies on the bucket's default encryption and Object Lock. The API's task role may put and
  get objects only under `*/evidence/*` of the evidence bucket and use the evidence key.

**Screen (#400, second pull request)**
- [ ] **Where:** the evidence panel beside each control, next to "Registrar evidencia". "Subir
  archivo" appears only when `file_uploads.enabled` is true.
- [ ] **Form:** a file and a title that defaults to the file name. The accepted types and the
  size limit are stated before a file is chosen, from `file_uploads`, with the note that each
  file is analysed for malware before it can be downloaded (D2) and that the record cannot be
  edited.
- [ ] **Before sending:** a type outside the list, an empty file or a file over the limit is
  refused in the form with the API's own ES/EN text, and nothing is sent. The API still decides.
- [ ] **Sending:** the form is busy while the file travels; a refusal shows the API's text and
  keeps the input; a retry of the same file and title reuses its `submission_id`.
- [ ] **List:** an uploaded item shows its file name, type and size, and a "Descargar" button.
  The download asks the API, which verifies the file first; an integrity failure is shown as
  such beside the item, never as a missing file.
- [ ] **One product:** the form and the list reuse the panel's existing form, buttons, messages
  and tokens (DESIGN.md); the file picker is the native control, as on the policies and access
  review screens. Checked in the rendered app at 1280 and 375 pixels, light and dark, with the
  polish bar (`tests/e2e/polish.ts`) and no CSP violation.

## Decisions

- **D1. Uploads go through the API; no presigned URLs.** #222 sketched presigned uploads. They
  were not taken, for four reasons. The app is single-origin by design (`connect-src 'self'`,
  `form-action 'self'`; web-shell spec), and a browser write to the bucket's endpoint would open
  that policy and need CORS on the bucket. The recorded SHA-256 must be computed by Atesta over
  the bytes it stored, not declared by a browser. Every object version in the bucket is locked
  for 365 days (#263), so size and type have to be enforced before the bytes land, by the only
  writer. And at 25 MiB the API can carry the body. A direct multipart upload for larger files
  can be added later without changing the record.
- **D2. Malware scanning (owner decision on #401, 2026-11-24).** Every uploaded file is scanned
  by Amazon GuardDuty Malware Protection for S3 in eu-south-2, and a download is refused until
  the file is known to be clean. The design, the statuses and the verified AWS facts are in
  `evidence-malware-scanning.md`. This replaces the first increment's decision to ship without
  scanning. Atesta still never opens, renders or parses an uploaded file, and the type allowlist
  and the download headers stay as they are.
- **D3. The submission id is the evidence id.** It avoids a table that would only map one to
  the other. The id is a random UUID chosen by the client; a collision with another
  organization's evidence id is answered as a conflict and reveals nothing readable.
- **D4. No new table and no migration.** `evidence` already describes a stored file (key, hash,
  type, size) with CHECKs that hold the key under the organization's prefix.

## Out of scope

- Uploads through API keys or the MCP server, and attaching one file to several controls.
- Replacing or deleting a file: evidence is append-only and the bucket is locked. A newer
  upload is a new record.
- Previews, text extraction, or giving documents to the assistant (rule 5 applies when that
  comes).
- Files in the organization export and the auditor dossier. When they are added, they read
  through the same integrity check.
- Downloading scan outputs, and erasing an organization's files on closure (an owner step under
  Object Lock, hosted-environment spec).
- A per-organization storage quota. Malware scanning moved to `evidence-malware-scanning.md` (D2).
- Citing an uploaded file in a requirement assessment. A manual control review can already
  cite it, as it cites any evidence linked to its control; the requirement register accepts
  statements only (`compliance/register.py`), and widening that belongs to its own spec.

## Design notes

- **Module:** evidence. `files.py` holds the router and the validation, `store.py` the
  `EvidenceStore` protocol with `LocalEvidenceStore` (dev only) and `S3EvidenceStore` (boto3),
  and `wire_evidence(app)` in `api.py` builds the store from the environment at start.
- **Reading the body:** the handler authenticates first, checks `Content-Length`, and only then
  parses the form (`max_files=1`). The file is hashed and counted in one pass over the spooled
  upload, then handed to the store as a seekable file.
  Above 1 MiB the upload spools to a temporary file: in the hosted API that is the `/tmp`
  volume, its only writable path (`infra/modules/ecs`).
- **Order of writes:** the row is inserted first, inside the request's transaction, so an id
  that belongs to another organization is refused before anything is stored. The object is
  written next, and the transaction commits only if the store accepted it. If the commit fails
  after that, the object stays (it cannot be deleted under the lock) with no record, and a retry
  writes a new version under the same key. A recorded row therefore always had its object.
- **Download errors and audit:** the integrity refusal is returned, not raised, so the audit
  event commits with it.
- **Vendor behavior, checked against AWS documentation on 2026-11-24:**

| Fact | Source |
| --- | --- |
| `ChecksumSHA256` is "the Base64 encoded, 256-bit SHA256 digest of the object", "to verify that the data received is the same data that was originally sent" | https://docs.aws.amazon.com/AmazonS3/latest/API/API_PutObject.html |
| "The Content-MD5 or x-amz-sdk-checksum-algorithm header is required for any request to upload an object with a retention period configured using Amazon S3 Object Lock" | same page |
| "Amazon S3 never adds partial objects; if you receive a success response, Amazon S3 added the entire object" | same page |
| A put on an existing locked key "creates a new version of that object. The existing protected version of the object remains locked" | https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html |
| SSE-KMS: a put needs `kms:GenerateDataKey` on the key and a download needs `kms:Decrypt` | https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingKMSEncryption.html |
| boto3 reads its region from `AWS_DEFAULT_REGION` | https://docs.aws.amazon.com/boto3/latest/guide/configuration.html |
| boto3 `put_object`: `Body` is "bytes or seekable file-like object"; `get_object` returns a `StreamingBody` and raises `NoSuchKey` | https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/put_object.html and `get_object.html` |

- **New dependencies:** `python-multipart` (already locked for tests, Apache-2.0) moves to the
  API's runtime dependencies; `boto3` (Apache-2.0) is added for the S3 store.
- **Security:** file names are sanitized into keys by the existing `storage_key_for` and held
  under the tenant prefix by the table's CHECK; RLS scopes every read; titles and file names
  never reach logs or audit metadata (rule 2); files are untrusted data and are never executed,
  rendered or parsed (rule 5).

## Test plan

- **HTTP, real PostgreSQL, local store:** upload then list then download returns the same
  bytes; the row holds the counted size and computed hash; member uploads, auditor is refused,
  a stranger gets 404; hidden control 404; no `Content-Length` 411; declared and actual
  oversize 413; empty file, unknown extension, wrong signature, NUL in text; a browser content
  type that lies is ignored; retry returns the first record, a changed retry and concurrent
  different submissions conflict; store unset and store failing give 503 and no row; audit
  metadata carries no title or name; another organization cannot download; a statement or scan
  output is not downloadable; a tampered object, a truncated object and a missing object each
  give 409, an audit event and no bytes; download headers.
- **Store:** the local store refuses to start outside development, refuses unsafe keys and is
  write-once per call; the S3 store sends bucket, key, type and the Base64 SHA-256, maps a
  missing key and client errors, and reads at most the expected size plus one byte (botocore
  stubber, no network).
- **Configuration and infra:** each `ATESTA_EVIDENCE_STORE` value; the API role's policy names
  only `*/evidence/*` and the evidence key.
- **Web (#400):** unit tests for each criterion above with a stubbed API; one browser test that
  uploads through the real file chooser, checks the multipart body carries the file name, downloads
  the file, and shows an integrity failure, at 375 and 1280 pixels in light and dark.
- **Not covered here:** a real S3 bucket, Object Lock and KMS, which need the hosted environment.
