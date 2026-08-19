"""Safety: treating retrieved and user content as untrusted data."""

from .claims import (
    CLAIM_LABELS,
    ClaimAssessment,
    check_claim_discipline,
    classify_claim,
)
from .source_validation import (
    SOURCE_HOSTS,
    SourceCheck,
    UrlVerdict,
    verify_context_items,
    verify_source_reference,
)
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
    "verify_source_reference",
    "verify_context_items",
    "SourceCheck",
    "UrlVerdict",
    "SOURCE_HOSTS",
    "classify_claim",
    "check_claim_discipline",
    "ClaimAssessment",
    "CLAIM_LABELS",
]
