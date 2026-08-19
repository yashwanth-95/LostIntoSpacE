"""The standard response envelope defined in docs/api/API.md.

Pure dict builders - no FastAPI dependency - so both route handlers and
exception handlers can share the exact same shape.
"""

from collections.abc import Sequence
from typing import Any


def success_envelope(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"status": "success", "data": data}
    if meta is not None:
        body["meta"] = meta
    return body


def error_envelope(code: str, message: str, details: Sequence[Any] | None = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return {"status": "error", "error": error}
