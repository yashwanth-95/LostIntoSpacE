"""Safety: treating retrieved and user content as untrusted data."""

from .sanitize import (
    CONTEXT_FENCE_CLOSE,
    CONTEXT_FENCE_OPEN,
    InjectionFinding,
    InjectionSeverity,
    SanitizedText,
    sanitize_context_text,
    scan_for_injection,
)

__all__ = [
    "sanitize_context_text",
    "scan_for_injection",
    "SanitizedText",
    "InjectionFinding",
    "InjectionSeverity",
    "CONTEXT_FENCE_OPEN",
    "CONTEXT_FENCE_CLOSE",
]
