"""Citation validation.

The model writes `[S1]`-style references. This module checks each one against
the context that was actually supplied, and it is the last line of defence
against the failure the product cares most about: a confident answer citing a
source that does not exist.

Three distinct problems, kept distinct because they need different responses:

* **Fabricated** — cites `[S9]` when only S1-S3 were supplied. The citation is
  removed and the answer's confidence drops; it cannot be shown as grounded.
* **Missing** — the answer asserts something factual and cites nothing at all.
* **Unsupported** — the citation exists, but the claim's content has no overlap
  with the cited item. Detected weakly (lexical overlap) and reported as a
  warning, never used to silently rewrite the answer.

A validator that quietly deleted bad citations would hide the model
misbehaving. Everything found is reported.
"""

import re
from enum import Enum
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from pydantic import BaseModel, ConfigDict, Field

from contracts.ai import Citation, ClaimType, ContextItem

__all__ = [
    "CitationProblem",
    "CitationIssue",
    "ValidationResult",
    "CitationValidator",
    "CITATION_PATTERN",
]

#: Matches `[S1]`, `[S12]`, and grouped forms like `[S1, S2]` or `[S1][S2]`.
CITATION_PATTERN = re.compile(r"\[(S\d+(?:\s*,\s*S\d+)*)\]", re.IGNORECASE)

_REF = re.compile(r"S\d+", re.IGNORECASE)

#: Sentences making a factual assertion usually contain one of these. Used only
#: to decide whether a *missing* citation is worth reporting — a hedged or
#: conversational sentence needs no source.
_FACTUAL_MARKERS = re.compile(
    r"\b(?:is|are|was|were|has|have|orbits?|measures?|contains?|reached|"
    r"launched|discovered|equals?|weighs?|spans?|occurred|causes?|"
    r"\d+(?:\.\d+)?)\b",
    re.IGNORECASE,
)

#: Openers that mark a sentence as the system speaking about itself rather than
#: asserting a fact about the world. These need no citation.
_META_OPENERS = (
    "i cannot", "i don't", "i do not", "there is insufficient",
    "the available sources", "no source", "this answer", "note that",
    "based on the retrieved", "the indexed corpus", "insufficient evidence",
)


class CitationProblem(str, Enum):
    """What is wrong with a citation."""

    #: Refers to context that was never supplied. The serious one.
    FABRICATED = "FABRICATED"
    #: A factual claim carries no citation at all.
    MISSING = "MISSING"
    #: The cited item exists but does not appear to support the claim.
    UNSUPPORTED = "UNSUPPORTED"
    #: Cites an item that was supplied but withheld from the model.
    QUARANTINED_SOURCE = "QUARANTINED_SOURCE"


class CitationIssue(BaseModel):
    """One problem found during validation."""

    model_config = ConfigDict(extra="forbid")

    problem: CitationProblem
    detail: str
    ref: Optional[str] = None
    claim: Optional[str] = None

    @property
    def is_fatal(self) -> bool:
        """Whether this makes the answer unfit to present as grounded."""
        return self.problem is CitationProblem.FABRICATED


class ValidationResult(BaseModel):
    """Outcome of validating an answer against its context."""

    model_config = ConfigDict(extra="forbid")

    #: Citations that checked out, in the order they appear in the answer.
    citations: List[Citation] = Field(default_factory=list)
    issues: List[CitationIssue] = Field(default_factory=list)
    #: Refs the model used that were never supplied.
    fabricated_refs: List[str] = Field(default_factory=list)
    #: Supplied refs the answer never used. Not a problem — just unused.
    unused_refs: List[str] = Field(default_factory=list)
    #: Sentences making factual claims with no citation.
    uncited_claims: List[str] = Field(default_factory=list)
    #: The answer with fabricated references stripped.
    cleaned_answer: str = ""

    @property
    def is_grounded(self) -> bool:
        """True when every citation resolved and at least one exists."""
        return bool(self.citations) and not self.fabricated_refs

    @property
    def has_fatal_issues(self) -> bool:
        return any(issue.is_fatal for issue in self.issues)

    @property
    def citation_coverage(self) -> float:
        """Fraction of factual sentences carrying a citation."""
        total = len(self.uncited_claims) + len(self.citations)
        if total == 0:
            return 0.0
        return len(self.citations) / float(total)

    def summary(self) -> str:
        return (
            "{0} citation(s), {1} fabricated, {2} uncited claim(s), "
            "grounded={3}".format(
                len(self.citations), len(self.fabricated_refs),
                len(self.uncited_claims), self.is_grounded,
            )
        )


class CitationValidator:
    """Checks an answer's citations against the context supplied to the model."""

    def __init__(
        self,
        require_citations: bool = True,
        overlap_threshold: float = 0.08,
        check_support: bool = True,
    ):
        #: Whether a factual answer with no citations is an issue.
        self.require_citations = require_citations
        #: Minimum lexical overlap before a claim counts as supported. Low on
        #: purpose: this is a weak signal, and a high threshold would produce
        #: confident false accusations against correctly-cited paraphrases.
        self.overlap_threshold = overlap_threshold
        self.check_support = check_support

    # -- parsing -----------------------------------------------------------
    def extract_refs(self, text: str) -> List[str]:
        """Every reference used in the answer, in order, deduplicated."""
        found: List[str] = []
        for match in CITATION_PATTERN.finditer(str(text or "")):
            for ref in _REF.findall(match.group(1)):
                upper = ref.upper()
                if upper not in found:
                    found.append(upper)
        return found

    def _sentences(self, text: str) -> List[str]:
        parts = re.split(r"(?<=[.!?])\s+|\n+", str(text or ""))
        return [part.strip() for part in parts if part.strip()]

    def _is_factual(self, sentence: str) -> bool:
        lowered = sentence.strip().lower()
        if any(lowered.startswith(opener) for opener in _META_OPENERS):
            return False
        if len(lowered.split()) < 4:
            return False
        return bool(_FACTUAL_MARKERS.search(sentence))

    def _overlap(self, claim: str, content: str) -> float:
        """Fraction of the claim's distinctive words present in the content."""
        def words(text):
            return {
                word for word in re.findall(r"[a-z0-9]+", text.lower())
                if len(word) > 3
            }

        claim_words = words(claim)
        if not claim_words:
            return 1.0
        return len(claim_words & words(content)) / float(len(claim_words))

    # -- validation --------------------------------------------------------
    def validate(
        self,
        answer: str,
        context_items: Sequence[ContextItem],
        quarantined_refs: Optional[Sequence[str]] = None,
    ) -> ValidationResult:
        """Validate `answer` against the context it was given."""
        text = str(answer or "")
        supplied = {item.ref.upper(): item for item in context_items}
        quarantined = {ref.upper() for ref in (quarantined_refs or [])}
        result = ValidationResult(cleaned_answer=text)

        used = self.extract_refs(text)

        for ref in used:
            if ref in quarantined:
                result.fabricated_refs.append(ref)
                result.issues.append(
                    CitationIssue(
                        problem=CitationProblem.QUARANTINED_SOURCE,
                        ref=ref,
                        detail="cites {0}, which was withheld from the model for "
                               "attempted prompt injection".format(ref),
                    )
                )
                continue
            if ref not in supplied:
                result.fabricated_refs.append(ref)
                result.issues.append(
                    CitationIssue(
                        problem=CitationProblem.FABRICATED,
                        ref=ref,
                        detail="cites {0}, which was never supplied; supplied "
                               "references were {1}".format(
                                   ref, sorted(supplied) or "none"
                               ),
                    )
                )
                continue

            item = supplied[ref]
            claim = self._claim_for(text, ref)
            citation = Citation(
                ref=ref,
                canonical_id=item.canonical_id,
                claim=claim,
                claim_type=_claim_type_for(item),
                source=item.source,
                url=item.url,
                verified=True,
            )

            if self.check_support and claim:
                overlap = self._overlap(claim, item.content)
                if overlap < self.overlap_threshold:
                    result.issues.append(
                        CitationIssue(
                            problem=CitationProblem.UNSUPPORTED,
                            ref=ref,
                            claim=claim,
                            detail="the cited item shares little wording with this "
                                   "claim (overlap {0:.2f}); verify manually".format(
                                       overlap
                                   ),
                        )
                    )
            result.citations.append(citation)

        result.unused_refs = sorted(set(supplied) - set(used))

        for sentence in self._sentences(text):
            if CITATION_PATTERN.search(sentence):
                continue
            if self._is_factual(sentence):
                result.uncited_claims.append(sentence)

        if self.require_citations and not used and result.uncited_claims:
            result.issues.append(
                CitationIssue(
                    problem=CitationProblem.MISSING,
                    detail="the answer makes {0} factual claim(s) but cites "
                           "nothing".format(len(result.uncited_claims)),
                    claim=result.uncited_claims[0],
                )
            )

        result.cleaned_answer = self._strip_refs(text, result.fabricated_refs)
        return result

    def _claim_for(self, text: str, ref: str) -> str:
        """The sentence a reference appears in."""
        for sentence in self._sentences(text):
            if ref.upper() in [item.upper() for item in self.extract_refs(sentence)]:
                return sentence
        return ""

    def _strip_refs(self, text: str, refs: Sequence[str]) -> str:
        """Remove fabricated references, leaving the prose intact.

        The claim itself is left standing — deleting it would be rewriting the
        model's answer, and the caller needs to see what was actually said in
        order to judge it. The issue list records what was removed.
        """
        if not refs:
            return text
        targets = {ref.upper() for ref in refs}

        def replace(match):
            kept = [
                item for item in _REF.findall(match.group(1))
                if item.upper() not in targets
            ]
            return "[{0}]".format(", ".join(kept)) if kept else ""

        return re.sub(r"\s*" + CITATION_PATTERN.pattern, replace, text,
                      flags=re.IGNORECASE).strip()


def _claim_type_for(item: ContextItem) -> ClaimType:
    """Infer what kind of claim a source supports.

    Conservative: an editorial concept is `THEORY` (an explanatory framework),
    an archive record is a `MEASURED_VALUE`, and anything unrecognised is an
    `OBSERVATION` rather than something stronger.
    """
    from contracts.provenance import SourceType

    mapping = {
        SourceType.EDITORIAL: ClaimType.THEORY,
        SourceType.PRIMARY_SCIENTIFIC: ClaimType.MEASURED_VALUE,
        SourceType.LITERATURE: ClaimType.OBSERVATION,
        SourceType.SECONDARY_OPERATIONAL: ClaimType.OBSERVATION,
        SourceType.CALCULATED: ClaimType.DERIVED_VALUE,
        SourceType.BUNDLED_REFERENCE: ClaimType.MEASURED_VALUE,
    }
    return mapping.get(item.source_type, ClaimType.OBSERVATION)
