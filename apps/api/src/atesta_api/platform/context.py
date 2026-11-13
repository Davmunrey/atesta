"""Tenant context value type. Any module may read it; only identity sets it (ADR-012)."""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TenantContext:
    subject: str | None = None
    user_id: uuid.UUID | None = None
    organization_id: uuid.UUID | None = None
    invitation_token_sha256: str | None = None
