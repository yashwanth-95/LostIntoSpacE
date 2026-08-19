"""Treating retrieved content as data, never as instructions.

A retrieved document is attacker-influenced input. NTRS abstracts, ESA product
descriptions, and anything a user types into a project note all reach the model,
and any of them can contain text shaped like an instruction.

Three layers, because none is sufficient alone:

1. **Structural** — context is fenced in delimiters and labelled as data, and
   the system prompt states that content inside the fence is never an
   instruction. Structure is what actually holds; the rest is defence in depth.
2. **Detection** — recognisable injection patterns are flagged so a document
   attempting one is visible in the response diagnostics and can be
   investigated, rather than silently sanitised away.
3. **Neutralisation** — the specific tokens that let text escape its fence are
   defanged: delimiter sequences, role markers, and anything imitating the
   system's own framing.

What this module deliberately does *not* do is try to detect malice by meaning.
That is unbounded, and a filter that mostly works is worse than a structure that
always does — it invites reliance it cannot support.
"""

import re
from enum import Enum
from typing import List, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "InjectionSeverity",
    "InjectionFinding",
    "SanitizedText",
    "sanitize_context_text",
    "scan_for_injection",
    "CONTEXT_FENCE_OPEN",
    "CONTEXT_FENCE_CLOSE",
]

#: Fence markers. Chosen to be improbable in scientific prose, and any
#: occurrence of them inside content is neutralised before fencing.
CONTEXT_FENCE_OPEN = "<<<RETRIEVED_DATA>>>"
CONTEXT_FENCE_CLOSE = "<<<END_RETRIEVED_DATA>>>"


class InjectionSeverity(str, Enum):
    """How strongly the text looks like an attempt to steer the model."""

    #: Unambiguous: an explicit instruction addressed to an assistant.
    HIGH = "HIGH"
    #: Suspicious: role markers, fence imitation, hidden-text tricks.
    MEDIUM = "MEDIUM"
    #: Worth recording, commonly benign in scientific text.
    LOW = "LOW"


#: `(pattern, severity, description)`. Written against the *lowercased* text.
_PATTERNS: Tuple[Tuple[str, InjectionSeverity, str], ...] = (
    (r"ignore (?:all |any |the )?(?:previous|prior|above|earlier)\s+"
     r"(?:instructions?|prompts?|rules?|directions?)",
     InjectionSeverity.HIGH, "instructs the model to discard its instructions"),
    (r"disregard (?:all |any |the )?(?:previous|prior|above|earlier)\s+"
     r"(?:instructions?|prompts?|rules?)",
     InjectionSeverity.HIGH, "instructs the model to discard its instructions"),
    (r"forget (?:everything|all)(?: you were told| above| previously)?",
     InjectionSeverity.HIGH, "instructs the model to discard context"),
    (r"you are now\b", InjectionSeverity.HIGH, "attempts to reassign the model's role"),
    (r"new instructions?\s*:", InjectionSeverity.HIGH, "declares replacement instructions"),
    (r"system\s*(?:prompt|message)\s*:", InjectionSeverity.HIGH,
     "imitates a system message"),
    (r"\bact as\b.{0,40}\b(?:assistant|ai|model|system)\b", InjectionSeverity.HIGH,
     "attempts to reassign the model's role"),
    (r"do not (?:cite|mention|reveal|include)\b", InjectionSeverity.HIGH,
     "instructs the model to suppress attribution"),
    (r"reveal (?:your |the )?(?:system prompt|instructions|api key|secret)",
     InjectionSeverity.HIGH, "attempts to extract configuration or credentials"),
    (r"(?:print|output|repeat) (?:your |the )?(?:system prompt|instructions)",
     InjectionSeverity.HIGH, "attempts to extract the system prompt"),
    (r"override (?:the )?(?:safety|rules|guidelines)", InjectionSeverity.HIGH,
     "attempts to disable safety rules"),

    (r"^\s*(?:system|assistant|user)\s*:", InjectionSeverity.MEDIUM,
     "imitates a conversation role marker"),
    (r"<<<\s*\w+\s*>>>", InjectionSeverity.MEDIUM, "imitates a context fence"),
    (r"\[/?(?:INST|SYS|SYSTEM)\]", InjectionSeverity.MEDIUM,
     "imitates a chat template token"),
    (r"<\|[a-z_]+\|>", InjectionSeverity.MEDIUM, "imitates a special token"),
    (r"```\s*system", InjectionSeverity.MEDIUM, "imitates a system code fence"),

    (r"\bplease (?:respond|answer|say|reply) (?:only )?(?:with|that)\b",
     InjectionSeverity.LOW, "attempts to dictate the answer"),
    (r"\bthis is (?:very )?important\s*:", InjectionSeverity.LOW,
     "attempts to escalate its own priority"),
)

_COMPILED = tuple(
    (re.compile(pattern, re.IGNORECASE | re.MULTILINE), severity, description)
    for pattern, severity, description in _PATTERNS
)

#: Zero-width and bidirectional-override characters. These hide text from a
#: human reviewer while the model still reads it, which makes them a delivery
#: mechanism rather than a payload — always stripped.
_INVISIBLE = re.compile(
    "[​‌‍⁠﻿‪‫‬‭‮⁦⁧⁨⁩]"
)


class InjectionFinding(BaseModel):
    """One suspicious pattern found in retrieved content."""

    model_config = ConfigDict(extra="forbid")

    severity: InjectionSeverity
    description: str
    #: The matched text, trimmed. Kept so a human can see what was found.
    excerpt: str = ""
    #: Where it was found — a canonical id or field name.
    location: Optional[str] = None


class SanitizedText(BaseModel):
    """Content after neutralisation, with what was found."""

    model_config = ConfigDict(extra="forbid")

    text: str
    findings: List[InjectionFinding] = Field(default_factory=list)
    #: True when anything was altered.
    modified: bool = False

    @property
    def is_suspicious(self) -> bool:
        return bool(self.findings)

    @property
    def highest_severity(self) -> Optional[InjectionSeverity]:
        order = (
            InjectionSeverity.HIGH, InjectionSeverity.MEDIUM, InjectionSeverity.LOW
        )
        for severity in order:
            if any(finding.severity is severity for finding in self.findings):
                return severity
        return None

    @property
    def should_quarantine(self) -> bool:
        """Whether this content should be withheld from the model entirely.

        Reserved for HIGH severity. A document trying to reassign the model's
        role has no legitimate reading, and fencing it would still put an
        instruction in the context window.
        """
        return self.highest_severity is InjectionSeverity.HIGH


def scan_for_injection(
    text: str, location: Optional[str] = None
) -> List[InjectionFinding]:
    """Report injection-shaped patterns. Does not modify anything."""
    body = str(text or "")
    if not body:
        return []
    findings: List[InjectionFinding] = []
    for pattern, severity, description in _COMPILED:
        match = pattern.search(body)
        if match:
            findings.append(
                InjectionFinding(
                    severity=severity,
                    description=description,
                    excerpt=match.group(0)[:120],
                    location=location,
                )
            )
    if _INVISIBLE.search(body):
        findings.append(
            InjectionFinding(
                severity=InjectionSeverity.MEDIUM,
                description="contains invisible or bidirectional-override "
                            "characters, which hide text from human review",
                excerpt="",
                location=location,
            )
        )
    return findings


def sanitize_context_text(
    text: str, location: Optional[str] = None, max_length: int = 4000
) -> SanitizedText:
    """Neutralise fence-escaping tokens and report what was found.

    Content is *not* rewritten for meaning. Only the tokens that could let text
    escape its delimiters are defanged, so the scientific content a document
    carries survives intact and remains quotable.
    """
    original = str(text or "")
    body = original

    body = _INVISIBLE.sub("", body)

    #: Defang anything imitating the fence or a chat-template token. Replacing
    #: with a visible marker rather than deleting keeps the tampering evident.
    body = body.replace(CONTEXT_FENCE_OPEN, "[fence-token-removed]")
    body = body.replace(CONTEXT_FENCE_CLOSE, "[fence-token-removed]")
    body = re.sub(r"<<<\s*(\w+)\s*>>>", r"[removed-marker:\1]", body)
    body = re.sub(r"<\|([a-z_]+)\|>", r"[removed-token:\1]", body)
    body = re.sub(r"\[/?(INST|SYS|SYSTEM)\]", r"[removed-token:\1]", body,
                  flags=re.IGNORECASE)
    #: Leading role markers only — "System:" starting a line reads as a turn
    #: boundary, while "the system: a rocket" mid-sentence does not.
    body = re.sub(r"(?im)^\s*(system|assistant|user)\s*:", r"\1 -", body)

    if len(body) > max_length:
        body = body[:max_length] + " […truncated]"

    findings = scan_for_injection(original, location)
    return SanitizedText(
        text=body, findings=findings, modified=(body != original)
    )
