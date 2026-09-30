"""Errors the client may see: a code, one safe sentence, and a request id.

Details (Postgres messages, provider responses, stack traces) go only to the
server log, tagged with the same request id, so a user can report the id and
we can find the details, without leaking internals.
"""

import logging
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

log = logging.getLogger("querylens")


class PublicError(Exception):
    def __init__(
        self, status_code: int, code: str, message: str, headers: dict[str, str] | None = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers or {}


def request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "unknown"))


def _error_body(code: str, message: str, rid: str) -> dict[str, dict[str, str]]:
    return {"error": {"code": code, "message": message, "request_id": rid}}


def install_error_handling(app: FastAPI) -> None:
    @app.middleware("http")
    async def add_request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = uuid.uuid4().hex[:12]
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(PublicError)
    async def public_error(request: Request, error: PublicError) -> JSONResponse:
        rid = request_id(request)
        return JSONResponse(
            status_code=error.status_code,
            content=_error_body(error.code, error.message, rid),
            headers={**error.headers, "X-Request-ID": rid},
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception) -> JSONResponse:
        rid = request_id(request)
        log.exception("unexpected error, request %s", rid)
        return JSONResponse(
            status_code=500,
            content=_error_body("internal_error", "Something went wrong on our side.", rid),
            headers={"X-Request-ID": rid},
        )
