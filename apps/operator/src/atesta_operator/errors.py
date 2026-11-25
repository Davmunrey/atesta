"""The operator API's error codes (operator-portal spec, "API"), in the console's envelope:
`{"detail": {"code": "operator.<code>"}}`. The API holds no prose; the portal maps each code to
its ES and EN text (`apps/operator/contract/messages`).

Module functions refuse with `identity.api.OperatorError` and a bare code; `refusal` maps it here,
so every code and its status is listed once and the contract exports this list.
"""

from atesta_api.modules.identity.api import OperatorError
from fastapi import HTTPException

STATUS: dict[str, int] = {
    "operator.forbidden": 403,
    "operator.recent_auth_required": 401,
    "operator.not_found": 404,
    "operator.no_billing_profile": 404,
    "operator.invalid_plan": 422,
    "operator.invalid_field": 422,
    "operator.name_mismatch": 422,
    "operator.already_suspended": 409,
    "operator.not_suspended": 409,
    "operator.closure_exists": 409,
    "operator.closure_by_owner": 409,
    "operator.no_closure": 409,
    "operator.erasure_pending": 409,
    "operator.same_approver": 409,
    "operator.cooling_off": 409,
    "operator.erasure_expired": 409,
    "operator.erasure_approved": 409,
    "operator.erasure_cancelled": 409,
    "operator.erasure_executed": 409,
    "operator.last_admin": 409,
    "operator.self_change": 409,
}


def operator_error(code: str, **extra: str) -> HTTPException:
    """`code` is a full `operator.*` code from STATUS; extra keys (a field name) join the body."""
    return HTTPException(status_code=STATUS[code], detail={"code": code, **extra})


def refusal(error: OperatorError) -> HTTPException:
    code = f"operator.{error.code}"
    return HTTPException(status_code=STATUS[code], detail={"code": code})
