"""Scientific claim classification.

The product must distinguish seven kinds of statement: observation, measured
value, derived value, estimate, theory, simulation, and AI inference. They are
in `ClaimType`, but an enum nothing assigns is decoration — this module does the
assigning, and checks the result.

Why it matters concretely: "the vehicle broke up at 91 m/s²" is a simulation
result; "Ceres has a mass of 9.38×10²⁰ kg" is a measured value with a published
uncertainty; "staging improves performance because the rocket equation is
logarithmic in mass ratio" is theory. Rendering all three identically invites a
reader to treat the first as a fact about a real vehicle.

Classification uses the **source** first and the wording second. Source is
strong evidence — anything from the simulator is a simulation, full stop — while
wording is a weaker signal used only to distinguish an estimate from a
measurement within the same source.
"""

import re
from typing import Dict, List, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from contracts.ai import Citation, ClaimType, ContextItem
from contracts.provenance import SourceType

__all__ = [
    "ClaimAssessment",
    "classify_claim",
    "check_claim_discipline",
    "CLAIM_LABELS",
    "HEDGE_PATTERNS",
]

#: How each claim type should be described to a user. A UI renders these; the
#: text is here so the wording cannot drift between surfaces.
CLAIM_LABELS: Dict[ClaimType, str] = {
    ClaimType.OBSERVATION: "observed",
    ClaimType.MEASURED_VALUE: "measured value",
    ClaimType.DERIVED_VALUE: "derived from measurements",
    ClaimType.ESTIMATE: "estimate",
    ClaimType.THEORY: "established theory",
    ClaimType.SIMULATION: "simulation result — not a real-world observation",
    ClaimType.AI_INFERENCE: "AI inference — not from a cited source",
}

#: Source type decides the claim type outright where it can.
_BY_SOURCE: Dict[SourceType, ClaimType] = {
    SourceType.SIMULATION: ClaimType.SIMULATION,
    SourceType.CALCULATED: ClaimType.DERIVED_VALUE,
    SourceType.EDITORIAL: ClaimType.THEORY,
    SourceType.PRIMARY_SCIENTIFIC: ClaimType.MEASURED_VALUE,
    SourceType.BUNDLED_REFERENCE: ClaimType.MEASURED_VALUE,
    SourceType.LITERATURE: ClaimType.OBSERVATION,
    SourceType.SECONDARY_OPERATIONAL: ClaimType.OBSERVATION,
    SourceType.EO_CATALOGUE: ClaimType.OBSERVATION,
    SourceType.AGENCY_PUBLIC_API: ClaimType.OBSERVATION,
    SourceType.USER_PROVIDED: ClaimType.ESTIMATE,
}

#: Wording that marks a figure as approximate. Used to demote a measured value
#: to an estimate — never to promote anything.
HEDGE_PATTERNS = (
    r"\babout\b", r"\bapproximately\b", r"\broughly\b", r"\baround\b",
    r"\bnearly\b", r"\bestimated?\b", r"\border of magnitude\b",
    r"\bon the order of\b", r"~", r"\bsome\s+\d", r"\bin the region of\b",
)

_HEDGE = re.compile("|".join(HEDGE_PATTERNS), re.IGNORECASE)

#: Wording that presents something as a settled fact about the world. Combined
#: with a simulation source, this is the dangerous case.
_ASSERTIVE = re.compile(
    r"\b(?:is|are|was|were|will be|has|have|does|do)\b", re.IGNORECASE
)

#: Words that would wrongly describe a simulation as reality.
_REALITY_WORDS = re.compile(
    r"\b(?:in reality|actually|in fact|really|the real|real[- ]world|"
    r"would happen|will happen|proves|demonstrates that)\b",
    re.IGNORECASE,
)


class ClaimAssessment(BaseModel):
    """What kind of claim a statement is, and why."""

    model_config = ConfigDict(extra="forbid")

    claim_type: ClaimType
    label: str
    #: What decided it.
    basis: str
    #: True when the statement's wording overstates its evidence.
    overstated: bool = False
    warning: Optional[str] = None


def classify_claim(
    statement: str, item: Optional[ContextItem] = None
) -> ClaimAssessment:
    """Classify one statement, using its source first and wording second."""
    text = str(statement or "")

    if item is None:
        #: No source means the model said it unaided. An unsourced statement
        #: worded as a fact is the overstatement that matters most, so the
        #: check runs here too rather than only on the sourced path.
        overstated = bool(_ASSERTIVE.search(text))
        return ClaimAssessment(
            claim_type=ClaimType.AI_INFERENCE,
            label=CLAIM_LABELS[ClaimType.AI_INFERENCE],
            basis="no supporting source was cited",
            overstated=overstated,
            warning=(
                "This statement is asserted as fact but has no cited source."
                if overstated else None
            ),
        )

    claim_type = _BY_SOURCE.get(item.source_type, ClaimType.OBSERVATION)
    basis = "source type {0}".format(item.source_type.value)

    #: Hedged wording demotes a measurement to an estimate. It never promotes:
    #: an estimate stated confidently is still an estimate, and that case is
    #: caught below as overstatement.
    if claim_type is ClaimType.MEASURED_VALUE and _HEDGE.search(text):
        claim_type = ClaimType.ESTIMATE
        basis += "; wording is hedged, so the figure is treated as an estimate"

    overstated = False
    warning = None

    if claim_type is ClaimType.SIMULATION and _REALITY_WORDS.search(text):
        overstated = True
        warning = (
            "This statement rests on simulator output but is worded as a claim "
            "about the real world. Simulator results describe a model."
        )
    elif claim_type is ClaimType.AI_INFERENCE and _ASSERTIVE.search(text):
        overstated = True
        warning = (
            "This statement is asserted as fact but has no cited source."
        )

    return ClaimAssessment(
        claim_type=claim_type,
        label=CLAIM_LABELS[claim_type],
        basis=basis,
        overstated=overstated,
        warning=warning,
    )


def check_claim_discipline(
    citations: Sequence[Citation], items: Sequence[ContextItem]
) -> List[str]:
    """Find citations whose claim type disagrees with their source.

    Returns human-readable problems. The important one is a claim resting on
    simulator output that is not typed as a simulation — that is how a model
    result becomes "a fact" in a rendered answer.
    """
    by_ref = {item.ref: item for item in items}
    problems: List[str] = []

    for citation in citations:
        item = by_ref.get(citation.ref)
        if item is None:
            problems.append(
                "citation {0} has no supplied context to check against".format(
                    citation.ref
                )
            )
            continue

        expected = _BY_SOURCE.get(item.source_type, ClaimType.OBSERVATION)

        if item.source_type is SourceType.SIMULATION and (
            citation.claim_type is not ClaimType.SIMULATION
        ):
            problems.append(
                "citation {0} rests on simulator output but is typed {1}; "
                "simulation results must never be typed as observations or "
                "measurements".format(citation.ref, citation.claim_type.value)
            )
            continue

        #: A measured value demoted to an estimate is fine — that is the
        #: hedging rule working. The reverse is not.
        if (
            expected is ClaimType.ESTIMATE
            and citation.claim_type is ClaimType.MEASURED_VALUE
        ):
            problems.append(
                "citation {0} is typed as a measured value but its source is "
                "{1}".format(citation.ref, item.source_type.value)
            )

        assessment = classify_claim(citation.claim, item)
        if assessment.overstated and assessment.warning:
            problems.append(
                "citation {0}: {1}".format(citation.ref, assessment.warning)
            )

    return problems
