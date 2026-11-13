"""Files the web client is generated from (web-shell spec): OpenAPI and the error-code list."""

import ast
import json
from pathlib import Path
from typing import TypeGuard

from atesta_api.main import create_app

_SOURCES = Path(__file__).resolve().parent
_RAISERS = {"error", "_error"}


def openapi_document() -> str:
    return json.dumps(create_app().openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _code_literals(tree: ast.AST) -> set[str]:
    """Codes passed as `error(status, "x.y")` / `_error(...)`, or as `{"code": "x.y"}`."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) in _RAISERS:
            args = node.args[1:2]
        elif isinstance(node, ast.Dict):
            args = [v for k, v in zip(node.keys, node.values, strict=True) if _is_str(k, "code")]
        else:
            continue
        found.update(a.value for a in args if isinstance(a, ast.Constant) and _is_code(a.value))
    return found


def _is_str(node: ast.expr | None, value: str) -> bool:
    return isinstance(node, ast.Constant) and node.value == value


def _is_code(value: object) -> TypeGuard[str]:
    return isinstance(value, str) and value.count(".") == 1 and value.replace(".", "_").islower()


def error_codes() -> list[str]:
    codes: set[str] = set()
    for path in sorted(_SOURCES.rglob("*.py")):
        codes |= _code_literals(ast.parse(path.read_text(), filename=str(path)))
    return sorted(codes)
