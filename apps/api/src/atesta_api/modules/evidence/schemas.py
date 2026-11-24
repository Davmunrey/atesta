"""Bounded public evidence fields, without storage keys or document downloads."""

import re
import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, field_validator

from atesta_api.modules.evidence.links import carries_credential

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Statement = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)]
_CONTROLS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class StatementIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    submission_id: uuid.UUID
    title: Title
    statement: Statement
    reference_url: Annotated[str, Field(max_length=2048)] | None = None

    @field_validator("title", "statement")
    @classmethod
    def safe_text(cls, value: str) -> str:
        if _CONTROLS.search(value):
            raise ValueError("control characters are not allowed")
        return value

    @field_validator("reference_url")
    @classmethod
    def safe_reference(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        parsed = HttpUrl(value)
        if (
            parsed.scheme != "https"
            or parsed.username
            or parsed.password
            or any(ord(c) < 33 or ord(c) == 127 for c in value)
            or carries_credential(value)
        ):
            raise ValueError("reference must be HTTPS without credentials or whitespace")
        return value


ScanStatus = Literal[
    "pending",
    "no_threats_found",
    "threats_found",
    "unsupported",
    "access_denied",
    "failed",
    "not_scanned",
]


class FileOut(BaseModel):
    """An uploaded document (evidence-file-uploads spec). The storage key stays in the API.

    scan_status: the malware scan (evidence-malware-scanning spec); only `no_threats_found`, or
    `not_scanned` in local development, can be downloaded."""

    name: str
    media_type: str
    size_bytes: int
    sha256: str
    scan_status: ScanStatus


class FileUploads(BaseModel):
    """What the upload form may offer: nothing when no store is configured."""

    enabled: bool
    max_bytes: int
    extensions: list[str]


class EvidenceOut(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    statement: str | None
    reference_url: str | None
    created_by: uuid.UUID | None
    created_at: datetime
    collected_at: datetime
    file: FileOut | None = None


class EvidencePage(BaseModel):
    total: int
    items: list[EvidenceOut]
    file_uploads: FileUploads
