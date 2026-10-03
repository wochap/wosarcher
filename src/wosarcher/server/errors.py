"""JSON errors: every error response is `{"error": code, "detail": text}`."""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.exceptions import HTTPException

from wosarcher.models import ApiError

# Leading parts of a validation location that name where the value came from, not the field.
LOCATION_ROOTS = {"body", "query", "path", "form"}


class RouteError(Exception):
    def __init__(self, status: int, error: str, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.error = error
        self.detail = detail


def not_found(run_id: str) -> RouteError:
    return RouteError(404, "run_not_found", f"no run {run_id}")


def describe(errors: Sequence[Any], located: bool = False) -> str:
    """`writing.words: Input should be greater than 0`, one line per invalid field.

    `located`: FastAPI errors, whose location starts with where the value came from (`body`, `query`).
    """
    lines: list[str] = []
    for problem in errors:
        parts = [str(part) for part in problem["loc"]]
        if located and parts and parts[0] in LOCATION_ROOTS:
            parts = parts[1:]
        lines.append(f"{'.'.join(parts) or 'request'}: {problem['msg']}")
    return "\n".join(lines)


def invalid(errors: Sequence[Any]) -> RouteError:
    return RouteError(422, "invalid_request", describe(errors))


def body(status: int, error: str, detail: str) -> JSONResponse:
    return JSONResponse(ApiError(error=error, detail=detail).model_dump(), status_code=status)


def install(app: FastAPI, index: Path | None) -> None:
    """Error handlers; with a frontend build, unknown `GET`s outside `/api` answer `index.html`."""

    async def problem(_request: Request, error: Exception) -> Response:
        assert isinstance(error, RouteError)
        return body(error.status, error.error, error.detail)

    async def validation(_request: Request, error: Exception) -> Response:
        assert isinstance(error, RequestValidationError)
        return body(422, "invalid_request", describe(error.errors(), located=True))

    async def http(request: Request, error: Exception) -> Response:
        assert isinstance(error, HTTPException)
        path = request.url.path
        if error.status_code == 404 and index is not None and request.method == "GET" and not is_api(path):
            return FileResponse(index, media_type="text/html")
        code = "not_found" if error.status_code == 404 else f"http_{error.status_code}"
        return body(error.status_code, code, str(error.detail))

    app.add_exception_handler(RouteError, problem)
    app.add_exception_handler(RequestValidationError, validation)
    app.add_exception_handler(HTTPException, http)


def is_api(path: str) -> bool:
    return path == "/api" or path.startswith("/api/")
