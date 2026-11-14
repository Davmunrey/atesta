"""Stable error codes for errors the framework raises (identity-auth spec).

The API holds no user-facing prose: the web maps codes to ES/EN texts. Bodies never echo the
submitted input (an email, a token) or exception text.
"""

from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from sqlalchemy.exc import DataError
from starlette.exceptions import HTTPException as StarletteHTTPException

from atesta_api.platform.headers import RESPONSE_HEADERS

# {"code": ...} literals, so the contract export (atesta_api.contract) lists every code.
_HTTP_DETAILS = {404: {"code": "request.not_found"}, 405: {"code": "request.method_not_allowed"}}
_OTHER_HTTP_DETAIL = {"code": "request.error"}


def _field(error: Mapping[str, Any]) -> str:
    if error.get("type") == "json_invalid":
        return "body"  # the location is a character offset, not a field
    return ".".join(str(part) for part in error.get("loc", ()))


async def _invalid_request(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):  # registered for that type only
        return await _server_error(request, exc)
    fields = sorted({_field(e) for e in exc.errors()})
    return JSONResponse(
        status_code=422, content={"detail": {"code": "request.invalid", "fields": fields}}
    )


async def _http_error(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, StarletteHTTPException):  # registered for that type only
        return await _server_error(request, exc)
    if isinstance(exc.detail, dict):  # already {"code": ...} from a handler
        return await http_exception_handler(request, exc)
    detail = _HTTP_DETAILS.get(exc.status_code, _OTHER_HTTP_DETAIL)
    return JSONResponse(
        status_code=exc.status_code, content={"detail": detail}, headers=exc.headers
    )


async def _unstorable_text(request: Request, exc: Exception) -> JSONResponse:
    """PostgreSQL text cannot hold NUL: input that carries one is invalid, not a server fault.

    Any other DataError is re-raised, so it still reaches _server_error and is logged.
    """
    if isinstance(exc, DataError) and "NUL (0x00)" in str(exc.orig):
        return JSONResponse(
            status_code=422, content={"detail": {"code": "request.invalid", "fields": []}}
        )
    raise exc


async def _server_error(request: Request, exc: Exception) -> JSONResponse:
    """Starlette still re-raises the exception after this response, so it is logged.

    This response is sent outside the middleware stack, so it sets the headers itself.
    """
    return JSONResponse(
        status_code=500, content={"detail": {"code": "server.error"}}, headers=RESPONSE_HEADERS
    )


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _invalid_request)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(DataError, _unstorable_text)
    app.add_exception_handler(Exception, _server_error)
