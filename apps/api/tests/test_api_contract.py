"""The web client is generated from files this suite keeps fresh (web-shell spec, Contract).

Regenerate with ATESTA_UPDATE_API_CONTRACT=1 uv run pytest apps/api/tests/test_api_contract.py
"""

import ast
import json
import os
from pathlib import Path

import pytest
from atesta_api.contract import _code_literals, error_codes, openapi_document

ROOT = Path(__file__).resolve().parents[3]
OPENAPI = ROOT / "apps/web/src/lib/api/openapi.json"
ERROR_CODES = ROOT / "apps/web/src/lib/api/error-codes.json"
UPDATE = os.environ.get("ATESTA_UPDATE_API_CONTRACT") == "1"


def _check(path: Path, fresh: str) -> None:
    if UPDATE:
        path.write_text(fresh)
    assert path.read_text() == fresh, f"{path.name} is stale; regenerate (see module docstring)"


def test_openapi_document_is_fresh() -> None:
    _check(OPENAPI, openapi_document())


def test_openapi_serves_only_the_api_prefix() -> None:
    paths = json.loads(openapi_document())["paths"]
    assert "/api/v1/me" in paths
    assert all(p.startswith(("/api/v1/", "/auth/")) or p == "/health" for p in paths)


def test_error_code_list_is_fresh() -> None:
    _check(ERROR_CODES, json.dumps(error_codes(), indent=2) + "\n")


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('raise error(409, "identity.last_owner")', {"identity.last_owner"}),
        ('raise _error(400, "auth.bad_state")', {"auth.bad_state"}),
        ('HTTPException(401, detail={"code": "auth.invalid_token"})', {"auth.invalid_token"}),
        ('error(400, "Not a code")', set()),
        ("error(400, code_variable)", set()),
        ('{"response_type": "code", "code": code}', set()),
        ('other(400, "x.y")', set()),
    ],
)
def test_error_code_extraction(source: str, expected: set[str]) -> None:
    assert _code_literals(ast.parse(source)) == expected
