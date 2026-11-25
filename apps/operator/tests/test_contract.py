"""The operator portal's client is generated from files this suite keeps fresh (ADR-017, "API
conventions"), and every `operator.*` code has its ES and EN text.

Regenerate with ATESTA_UPDATE_API_CONTRACT=1 uv run pytest apps/operator/tests/test_contract.py
"""

import ast
import json
import os
import re
from pathlib import Path

from atesta_operator.contract import error_codes, openapi_document
from atesta_operator.errors import STATUS

APP = Path(__file__).resolve().parents[1]
CONTRACT = APP / "contract"
UPDATE = os.environ.get("ATESTA_UPDATE_API_CONTRACT") == "1"


def _check(path: Path, fresh: str) -> None:
    if UPDATE:
        path.write_text(fresh)
    assert path.read_text() == fresh, f"{path.name} is stale; regenerate (see module docstring)"


def test_openapi_document_is_fresh() -> None:
    _check(CONTRACT / "openapi.json", openapi_document())


def test_error_code_list_is_fresh() -> None:
    _check(CONTRACT / "error-codes.json", json.dumps(error_codes(), indent=2) + "\n")


def test_openapi_serves_only_the_api_prefix() -> None:
    paths = json.loads(openapi_document())["paths"]
    assert "/api/v1/me" in paths
    assert all(p.startswith(("/api/v1/", "/auth/")) or p == "/health" for p in paths)


def test_every_code_the_source_raises_is_listed() -> None:
    """`operator_error("x")` with a code outside STATUS would reach the portal with no text."""
    found: set[str] = set()
    for path in (APP / "src").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "operator_error":
                first = node.args[0] if node.args else None
                assert isinstance(first, ast.Constant), f"{path.name}: code must be a literal"
                found.add(str(first.value))
    assert found and found <= set(STATUS)


def test_every_operator_code_has_spanish_and_english_text() -> None:
    codes = {c.split(".", 1)[1] for c in STATUS}
    for language in ("es", "en"):
        texts = json.loads((CONTRACT / "messages" / f"{language}.json").read_text())
        operator = texts["errors"]["operator"]
        assert set(operator) == codes, language
        assert all(isinstance(t, str) and t.strip() for t in operator.values())


def test_every_code_the_session_returns_is_listed() -> None:
    """The portal shows a text only for listed codes; a write without its origin is 403
    `auth.bad_origin`, which the portal must explain (#487)."""
    source = (APP / "src" / "atesta_operator" / "session.py").read_text()
    raised = set(re.findall(r'"(auth\.[a-z_]+)"', source))
    assert raised and raised <= set(error_codes())
