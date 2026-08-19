"""Metrics for grounded answers.

Retrieval metrics measure whether the right documents came back. These measure
whether the *answer* is honest about them:

* **Groundedness** — every citation resolves to supplied context.
* **Citation correctness** — the cited items are the ones that should have been
  cited, judged against the labelled expected sources.
* **Source authority** — whether a scientific question was answered from an
  authoritative source.
* **Freshness correctness** — whether a time-sensitive answer carried the
  currency caveat it needed.
* **Hallucination rate** — the fraction of answers containing a fabricated
  citation. The single most important number here.
* **Abstention correctness** — declined when it should, answered when it could.
* **Completeness** — a weak lexical check that expected terms appear.

`hallucination_rate` and `false_answer_rate` are reported separately because
they are different failures: the first is citing a source that does not exist,
the second is answering a question the corpus cannot support at all.
"""

from typing import Dict, List, Optional, Sequence, Set

from pydantic import BaseModel, ConfigDict, Field

from contracts.ai import AIResponse, ConfidenceLevel, DataOrigin

__all__ = ["AnswerOutcome", "GroundingSummary", "score_answer", "summarize"]

#: Source types that count as authoritative for a scientific claim.
_AUTHORITATIVE = {"PRIMARY_SCIENTIFIC", "LITERATURE", "AGENCY_PUBLIC_API"}


class AnswerOutcome(BaseModel):
    """How one answer scored."""

    model_config = ConfigDict(extra="forbid")

    question_id: str
    question: str
    #: True when the system declined to answer.
    declined: bool = False
    should_decline: bool = False

    #: Every citation resolved against supplied context.
    grounded: bool = False
    #: A citation referenced context that was never supplied.
    hallucinated_citation: bool = False
    #: At least one expected source appeared in the retrieved context.
    cited_expected_source: bool = False
    #: Expected sources that did appear.
    matched_sources: List[str] = Field(default_factory=list)
    #: An authoritative source backed the answer.
    used_authoritative_source: bool = False
    #: A required currency caveat was present.
    freshness_correct: bool = True
    #: Fraction of expected terms present in the answer text.
    completeness: float = 0.0
    #: Fraction of factual sentences carrying a citation.
    citation_coverage: float = 0.0
    confidence: Optional[str] = None
    data_origin: Optional[str] = None
    notes: List[str] = Field(default_factory=list)

    @property
    def correct_abstention(self) -> bool:
        return self.should_decline and self.declined

    @property
    def false_answer(self) -> bool:
        """Answered a question that should have been declined."""
        return self.should_decline and not self.declined

    @property
    def missed_answer(self) -> bool:
        """Declined a question the corpus can answer."""
        return (not self.should_decline) and self.declined

    def summary(self) -> str:
        if self.should_decline:
            return "{0}: {1}".format(
                self.question_id,
                "declined" if self.declined else "WRONGLY ANSWERED",
            )
        return "{0}: grounded={1} expected_source={2} complete={3:.2f}".format(
            self.question_id, self.grounded, self.cited_expected_source,
            self.completeness,
        )


class GroundingSummary(BaseModel):
    """Aggregate scores over a run."""

    model_config = ConfigDict(extra="forbid")

    total: int = 0
    answerable: int = 0
    unanswerable: int = 0

    groundedness: float = 0.0
    citation_correctness: float = 0.0
    source_authority: float = 0.0
    freshness_correctness: float = 0.0
    completeness: float = 0.0
    citation_coverage: float = 0.0

    hallucination_rate: float = 0.0
    false_answer_rate: float = 0.0
    missed_answer_rate: float = 0.0
    abstention_precision: float = 0.0

    outcomes: List[AnswerOutcome] = Field(default_factory=list)

    def describe(self) -> str:
        return "\n".join([
            "Grounded answering over {0} question(s) "
            "({1} answerable, {2} must decline)".format(
                self.total, self.answerable, self.unanswerable
            ),
            "  groundedness          {0:.3f}".format(self.groundedness),
            "  citation correctness  {0:.3f}".format(self.citation_correctness),
            "  citation coverage     {0:.3f}".format(self.citation_coverage),
            "  source authority      {0:.3f}".format(self.source_authority),
            "  freshness correctness {0:.3f}".format(self.freshness_correctness),
            "  completeness          {0:.3f}".format(self.completeness),
            "  hallucination rate    {0:.3f}".format(self.hallucination_rate),
            "  false answers         {0:.3f}".format(self.false_answer_rate),
            "  missed answers        {0:.3f}".format(self.missed_answer_rate),
            "  abstention precision  {0:.3f}".format(self.abstention_precision),
        ])

    def failures(self) -> List[AnswerOutcome]:
        return [
            outcome for outcome in self.outcomes
            if outcome.false_answer
            or outcome.missed_answer
            or outcome.hallucinated_citation
            or (not outcome.should_decline and not outcome.cited_expected_source)
        ]


def score_answer(question, response: AIResponse) -> AnswerOutcome:
    """Score one answer against its label."""
    declined = response.insufficient_evidence
    outcome = AnswerOutcome(
        question_id=question.id,
        question=question.question,
        declined=declined,
        should_decline=question.should_decline,
        confidence=response.confidence.value,
        data_origin=response.data_origin.value,
        citation_coverage=float(
            response.diagnostics.get("citation_coverage", 0.0) or 0.0
        ),
    )

    if declined:
        #: A declined answer is scored only on whether declining was right.
        #: Grading its (absent) citations would reward silence.
        outcome.freshness_correct = True
        return outcome

    outcome.hallucinated_citation = bool(response.unverified_citations) or any(
        limitation.kind == "unverified_citation"
        for limitation in response.limitations
    )
    outcome.grounded = response.is_grounded and not outcome.hallucinated_citation

    retrieved = {item.canonical_id for item in response.context_items}
    expected = set(question.expected_sources)
    if expected:
        outcome.matched_sources = sorted(retrieved & expected)
        outcome.cited_expected_source = bool(outcome.matched_sources)
    else:
        outcome.cited_expected_source = True

    outcome.used_authoritative_source = any(
        item.source_type.value in _AUTHORITATIVE for item in response.context_items
    )

    if question.requires_freshness_caveat:
        has_caveat = any(
            limitation.kind in ("not_current", "stale_data")
            for limitation in response.limitations
        ) or response.data_origin is DataOrigin.LIVE
        outcome.freshness_correct = has_caveat
        if not has_caveat:
            outcome.notes.append(
                "time-sensitive answer carried no currency caveat"
            )

    if question.expected_terms:
        lowered = response.answer.lower()
        hits = [term for term in question.expected_terms if term.lower() in lowered]
        outcome.completeness = len(hits) / float(len(question.expected_terms))
    else:
        outcome.completeness = 1.0

    return outcome


def _mean(values: Sequence[float]) -> float:
    return sum(values) / float(len(values)) if values else 0.0


def summarize(outcomes: Sequence[AnswerOutcome]) -> GroundingSummary:
    """Aggregate per-question outcomes."""
    answered = [o for o in outcomes if not o.should_decline and not o.declined]
    answerable = [o for o in outcomes if not o.should_decline]
    must_decline = [o for o in outcomes if o.should_decline]

    summary = GroundingSummary(
        total=len(outcomes),
        answerable=len(answerable),
        unanswerable=len(must_decline),
        outcomes=list(outcomes),
    )

    if answered:
        summary.groundedness = _mean([1.0 if o.grounded else 0.0 for o in answered])
        summary.citation_correctness = _mean(
            [1.0 if o.cited_expected_source else 0.0 for o in answered]
        )
        summary.source_authority = _mean(
            [1.0 if o.used_authoritative_source else 0.0 for o in answered]
        )
        summary.freshness_correctness = _mean(
            [1.0 if o.freshness_correct else 0.0 for o in answered]
        )
        summary.completeness = _mean([o.completeness for o in answered])
        summary.citation_coverage = _mean([o.citation_coverage for o in answered])
        summary.hallucination_rate = _mean(
            [1.0 if o.hallucinated_citation else 0.0 for o in answered]
        )

    if must_decline:
        correct = sum(1 for o in must_decline if o.declined)
        summary.abstention_precision = correct / float(len(must_decline))
        summary.false_answer_rate = 1.0 - summary.abstention_precision

    if answerable:
        summary.missed_answer_rate = _mean(
            [1.0 if o.missed_answer else 0.0 for o in answerable]
        )

    return summary
