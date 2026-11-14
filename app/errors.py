"""Shared API error responses without exposing database or validation internals."""
import sqlite3

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


def install_error_handlers(app):
    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        body = dict(exc.detail) if isinstance(exc.detail, dict) else {"detail": str(exc.detail)}
        if not isinstance(body.get("detail"), str):
            body["detail"] = body.pop("message", "The request could not be completed.")
        body.setdefault("code", "REQUEST_ERROR")
        return JSONResponse(body, status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request, exc):
        issue = exc.errors()[0]
        field = ".".join(str(part) for part in issue["loc"] if part not in ("body", "query", "path"))
        return JSONResponse({"detail": issue["msg"].removeprefix("Value error, "),
                             "code": "INVALID_INPUT", "field": field or None}, status_code=422)

    @app.exception_handler(sqlite3.Error)
    async def database_error(request, exc):
        return JSONResponse({"detail": "Storage is temporarily unavailable. Please retry; keep your entered values.",
                             "code": "DATABASE_UNAVAILABLE"}, status_code=503)
