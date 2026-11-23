"""Tenant context value type. Any module may read it; only identity sets it (ADR-012)."""

import uuid
from dataclasses import dataclass

# Field of TenantContext -> transaction-local Postgres setting read by the RLS policies.
SETTING_NAMES = (
    ("subject", "app.subject"),
    ("user_id", "app.user_id"),
    ("organization_id", "app.organization_id"),
    ("invitation_token_sha256", "app.invitation_token_sha256"),
    ("training_token_sha256", "app.training_token_sha256"),
    ("api_token_sha256", "app.api_token_sha256"),
)


@dataclass(frozen=True, slots=True)
class TenantContext:
    subject: str | None = None
    user_id: uuid.UUID | None = None
    organization_id: uuid.UUID | None = None
    invitation_token_sha256: str | None = None
    training_token_sha256: str | None = None
    api_token_sha256: str | None = None
