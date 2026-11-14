"""Bounded public evidence fields, without storage keys or document downloads."""

import re
import uuid
from datetime import datetime
from typing import Annotated
from urllib.parse import parse_qsl, urlsplit

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, field_validator

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Statement = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)]
_CONTROLS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
# Parameters that make a link a credential (Azure SAS, S3 and GCS signed URLs, OAuth tokens,
# API keys). Statements are append-only, so such a link could never be purged (rule 2).
_CREDENTIAL_PARAMETERS = frozenset(
    {
        "sig",
        "signature",
        "x-amz-signature",
        "x-amz-credential",
        "x-amz-security-token",
        "x-goog-signature",
        "x-goog-credential",
        "token",
        "access_token",
        "id_token",
        "refresh_token",
        "code",
        "key",
        "apikey",
        "api_key",
        "password",
        "secret",
    }
)


def _carries_credential(url: str) -> bool:
    parts = urlsplit(url)
    names = {
        name.lower()
        for part in (parts.query, parts.fragment)
        for name, _ in parse_qsl(part, keep_blank_values=True)
    }
    return bool(names & _CREDENTIAL_PARAMETERS)


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
            or _carries_credential(value)
        ):
            raise ValueError("reference must be HTTPS without credentials or whitespace")
        return value


class EvidenceOut(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    statement: str | None
    reference_url: str | None
    created_by: uuid.UUID | None
    created_at: datetime
    collected_at: datetime


class EvidencePage(BaseModel):
    total: int
    items: list[EvidenceOut]
