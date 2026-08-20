"""Centralized error handling - every error response uses the same envelope."""

import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import InterfaceError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.core.envelope import error_envelope
from src.core.exceptions import AppError

logger = logging.getLogger(__name__)


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_envelope(exc.code, exc.message, exc.details),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # exc.errors() can embed the raw ValueError/AssertionError a custom
    # field_validator raised, under each error's ctx["error"] - plain
    # json.dumps cannot serialize an exception object and would 500 instead
    # of returning the intended 422. jsonable_encoder converts it (and
    # anything else non-JSON-native, e.g. bytes/Decimal) to a plain string
    # first. Found via a real 500 while testing a custom validator, not
    # hypothetical - see tests/test_auth_validation.py.
    details = jsonable_encoder(exc.errors())
    return JSONResponse(
        status_code=422,
        content=error_envelope("VALIDATION_ERROR", "Request validation failed", details),
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "HTTP error"
    return JSONResponse(
        status_code=exc.status_code,
        content=error_envelope(f"HTTP_{exc.status_code}", detail),
    )


async def database_unavailable_handler(request: Request, exc: Exception) -> JSONResponse:
    """An unreachable database is 503, not 500.

    500 tells a client "this server has a bug"; an unconfigured or unreachable
    PostgreSQL is neither the client's fault nor a defect in the code, and
    /health/ready already reports exactly this condition as 503. Without this
    handler the two disagreed: readiness said "not ready" while every data
    endpoint said "internal error", which sends anyone debugging a fresh
    checkout looking for a bug that is not there.

    Scoped to connection-level SQLAlchemy errors only. OperationalError and
    InterfaceError mean "could not talk to the database"; a ProgrammingError or
    IntegrityError means the query itself was wrong, which *is* a server bug and
    must keep its 500.

    The exception text is deliberately never echoed - asyncpg puts the user and
    connection details in it.
    """
    logger.error(
        "Database unavailable",
        exc_info=exc,
        extra={"request_id": _request_id(request)},
    )
    return JSONResponse(
        status_code=503,
        content=error_envelope(
            "DATABASE_UNAVAILABLE",
            "The database is not reachable. See docs/getting-started/LOCAL_SETUP.md.",
        ),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "Unhandled exception",
        exc_info=exc,
        extra={"request_id": _request_id(request)},
    )
    return JSONResponse(
        status_code=500,
        content=error_envelope("INTERNAL_ERROR", "An unexpected error occurred"),
    )


def register_exception_handlers(app: FastAPI) -> None:
    # mypy can't express "handler type varies by registered exception key" for
    # add_exception_handler; each handler is only ever called for its own
    # registered type, so the narrower parameter types are safe at runtime.
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    # Registered before the catch-all so a connection failure resolves to 503
    # rather than being swallowed by the generic Exception handler.
    app.add_exception_handler(OperationalError, database_unavailable_handler)  # type: ignore[arg-type]
    app.add_exception_handler(InterfaceError, database_unavailable_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
