"""Files the operator portal's client is generated from (ADR-017, "API conventions"): the OpenAPI
document and the error-code list, kept fresh in `apps/operator/contract/` by the test suite."""

import json

from atesta_operator.errors import STATUS
from atesta_operator.main import create_app

# Raised by the shared kernel (platform.errors) and the token check, as in the customer API.
SHARED_CODES = frozenset(
    {
        "auth.invalid_token",
        "auth.provider_unavailable",
        "request.error",
        "request.invalid",
        "request.method_not_allowed",
        "request.not_found",
        "server.error",
    }
)


def openapi_document() -> str:
    return json.dumps(create_app().openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def error_codes() -> list[str]:
    return sorted(SHARED_CODES | set(STATUS))
