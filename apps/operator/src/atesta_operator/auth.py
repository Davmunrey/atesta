"""Staff authentication and authorization (ADR-017, "Staff identity"; spec, "API").

- **Token:** an access token of the staff pool's app client, checked like the customer API's
  (issuer, `token_use`, `client_id`, scopes) and carrying `auth_time`. A customer-pool token has
  another issuer and app client, so it gets 401 `auth.invalid_token`.
- **Staff row:** the role comes from `operator_staff`, never from the token. No enabled row is
  403 `operator.forbidden`.
- **Matrix:** `authorize` applies `policy.POLICY` to the matched route.

Nothing here logs a token.
"""

import time
import uuid
from dataclasses import dataclass
from typing import Annotated

from atesta_api.modules.identity.api import (
    InvalidTokenError,
    ProviderUnavailableError,
    StaffRole,
    TokenVerifier,
    enabled_staff,
)
from atesta_api.platform.db import DbSession
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from atesta_operator.errors import operator_error
from atesta_operator.policy import POLICY, RECENT_SIGN_IN_SECONDS

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class Staff:
    id: uuid.UUID
    email: str
    role: StaffRole
    auth_time: int


def _invalid() -> HTTPException:
    return HTTPException(status_code=401, detail={"code": "auth.invalid_token"})


def authenticate(
    request: Request,
    session: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Staff:
    if credentials is None:
        raise _invalid()
    verifier: TokenVerifier = request.app.state.token_verifier
    try:
        token = verifier.verify(credentials.credentials)
    except ProviderUnavailableError:
        raise HTTPException(503, detail={"code": "auth.provider_unavailable"}) from None
    except InvalidTokenError:
        raise _invalid() from None
    if token.auth_time is None:  # every staff-pool access token carries it
        raise _invalid()
    member = enabled_staff(session, token.sub)
    if member is None:
        raise operator_error("operator.forbidden")
    return Staff(member.id, member.email, member.role, token.auth_time)


def authorize(request: Request, staff: Annotated[Staff, Depends(authenticate)]) -> Staff:
    """Deny by default: a route missing from POLICY is refused to every role."""
    route = request.scope.get("route")
    rule = POLICY.get((request.method, getattr(route, "path", "")))
    if rule is None or staff.role not in rule.roles:
        raise operator_error("operator.forbidden")
    if rule.recent_sign_in and time.time() - staff.auth_time > RECENT_SIGN_IN_SECONDS:
        raise operator_error("operator.recent_auth_required")
    return staff


CurrentStaff = Annotated[Staff, Depends(authorize)]
