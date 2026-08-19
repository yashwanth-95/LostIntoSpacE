"""Labelled question set for the grounded assistant.

Forty questions: thirty-two the corpus can answer and eight it cannot. The
unanswerable ones are not padding — an assistant that never declines is the
specific failure this product must avoid, and it cannot be measured without
questions that *should* be declined.

Each question declares what a correct answer requires, not what it should say.
Asserting exact wording would test the language model's phrasing; asserting the
evidence, the origin and the caveats tests the system.
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "QuestionKind",
    "RAGQuestion",
    "RAG_QUESTIONS",
    "answerable_questions",
    "unanswerable_questions",
]


class QuestionKind(str, Enum):
    """What the question is testing."""

    FACTUAL = "FACTUAL"
    CONCEPTUAL = "CONCEPTUAL"
    MISSION = "MISSION"
    ENGINEERING = "ENGINEERING"
    OBJECT = "OBJECT"
    TIME_SENSITIVE = "TIME_SENSITIVE"
    #: Should be declined.
    UNANSWERABLE = "UNANSWERABLE"
    OUT_OF_DOMAIN = "OUT_OF_DOMAIN"


class RAGQuestion(BaseModel):
    """One labelled question."""

    model_config = ConfigDict(extra="forbid")

    id: str
    question: str
    kind: QuestionKind = QuestionKind.FACTUAL
    #: Canonical ids that ought to appear in the retrieved context. At least
    #: one must be present for the answer to count as grounded in the right
    #: place.
    expected_sources: List[str] = Field(default_factory=list)
    #: Terms a correct answer is very likely to contain. Used as a weak
    #: completeness signal, never as a pass/fail on wording alone.
    expected_terms: List[str] = Field(default_factory=list)
    #: True when the system should decline.
    should_decline: bool = False
    #: True when the answer must carry a currency caveat.
    requires_freshness_caveat: bool = False
    rationale: str = ""

    @property
    def is_answerable(self) -> bool:
        return not self.should_decline


def _q(id, question, **kwargs):
    return RAGQuestion(id=id, question=question, **kwargs)


RAG_QUESTIONS: List[RAGQuestion] = [
    # -- conceptual / engineering -----------------------------------------
    _q("rag-01", "How does staging improve rocket performance?",
       kind=QuestionKind.CONCEPTUAL,
       expected_sources=["concept:staging"],
       expected_terms=["mass", "stage"],
       rationale="core concept, direct phrasing"),
    _q("rag-02", "What causes Max-Q?",
       kind=QuestionKind.CONCEPTUAL,
       expected_sources=["concept:max-q"],
       expected_terms=["pressure"],
       rationale="core concept"),
    _q("rag-03", "Why do rockets throttle down during ascent?",
       kind=QuestionKind.CONCEPTUAL,
       expected_sources=["concept:max-q"],
       expected_terms=["pressure"],
       rationale="paraphrase with no title-word overlap"),
    _q("rag-04", "What causes orbital decay?",
       kind=QuestionKind.CONCEPTUAL,
       expected_sources=["concept:orbital-decay"],
       expected_terms=["drag"],
       rationale="core concept"),
    _q("rag-05", "How does a gravity assist work?",
       kind=QuestionKind.CONCEPTUAL,
       expected_sources=["concept:gravity-assist", "mission:cassini",
                         "mission:voyager-2"],
       expected_terms=["planet"],
       rationale="concept with canonical mission examples"),
    _q("rag-06", "What is specific impulse?",
       kind=QuestionKind.CONCEPTUAL,
       expected_sources=["concept:specific-impulse"],
       expected_terms=["propellant"],
       rationale="definition lookup"),
    _q("rag-07", "How do liquid rocket engines work?",
       kind=QuestionKind.ENGINEERING,
       expected_sources=["concept:liquid-propulsion"],
       expected_terms=["propellant"],
       rationale="engineering explanation"),
    _q("rag-08", "What is a Hohmann transfer?",
       kind=QuestionKind.CONCEPTUAL,
       expected_sources=["concept:hohmann-transfer"],
       expected_terms=["orbit"],
       rationale="named manoeuvre"),
    _q("rag-09", "Why do spacecraft heat up during re-entry?",
       kind=QuestionKind.ENGINEERING,
       expected_sources=["concept:reentry-heating"],
       expected_terms=["shock", "air"],
       rationale="common misconception — friction versus compression"),
    _q("rag-10", "What is a turbopump for?",
       kind=QuestionKind.ENGINEERING,
       expected_sources=["concept:liquid-propulsion"],
       rationale="single technical term buried in the body"),
    _q("rag-11", "How much delta-v is needed to reach low Earth orbit?",
       kind=QuestionKind.ENGINEERING,
       expected_sources=["concept:delta-v-budget"],
       expected_terms=["km/s"],
       rationale="numeric detail inside the body"),
    _q("rag-12", "What are the six orbital elements?",
       kind=QuestionKind.CONCEPTUAL,
       expected_sources=["concept:orbital-mechanics"],
       expected_terms=["eccentricity", "inclination"],
       rationale="enumerable content"),
    _q("rag-13", "Why are re-entry vehicles blunt rather than pointed?",
       kind=QuestionKind.ENGINEERING,
       expected_sources=["concept:reentry-heating"],
       rationale="design rationale"),
    _q("rag-14", "What is the rocket equation?",
       kind=QuestionKind.CONCEPTUAL,
       expected_sources=["concept:staging", "concept:specific-impulse"],
       expected_terms=["mass"],
       rationale="equation appearing in two records"),
    _q("rag-15", "How does atmospheric drag affect a satellite's orbit?",
       kind=QuestionKind.CONCEPTUAL,
       expected_sources=["concept:orbital-decay"],
       rationale="mechanism, different phrasing"),

    # -- missions ---------------------------------------------------------
    _q("rag-16", "Which mission first landed humans on the Moon?",
       kind=QuestionKind.MISSION,
       expected_sources=["mission:apollo-11"],
       expected_terms=["Apollo"],
       rationale="canonical mission fact"),
    _q("rag-17", "What went wrong on Apollo 13?",
       kind=QuestionKind.MISSION,
       expected_sources=["mission:apollo-13"],
       expected_terms=["oxygen"],
       rationale="anomaly recorded in the mission outcome"),
    _q("rag-18", "Which spacecraft explored Jupiter?",
       kind=QuestionKind.MISSION,
       expected_sources=["mission:galileo", "mission:juno", "mission:voyager-2"],
       rationale="several correct answers"),
    _q("rag-19", "Which mission visited Uranus and Neptune?",
       kind=QuestionKind.MISSION,
       expected_sources=["mission:voyager-2"],
       rationale="unique fact"),
    _q("rag-20", "What was Artemis I?",
       kind=QuestionKind.MISSION,
       expected_sources=["mission:artemis-1"],
       rationale="recent programme"),
    _q("rag-21", "Which ISRO mission landed near the lunar south pole?",
       kind=QuestionKind.MISSION,
       expected_sources=["mission:chandrayaan-3"],
       expected_terms=["Chandrayaan"],
       rationale="agency-specific"),
    _q("rag-22", "Which mission delivered a probe to Titan?",
       kind=QuestionKind.MISSION,
       expected_sources=["mission:cassini"],
       rationale="detail in the description"),
    _q("rag-23", "Which rovers are exploring Mars?",
       kind=QuestionKind.MISSION,
       expected_sources=["mission:curiosity", "mission:perseverance"],
       rationale="two correct answers"),
    _q("rag-24", "What is the Galileo mission known for?",
       kind=QuestionKind.MISSION,
       expected_sources=["mission:galileo"],
       expected_terms=["Jupiter"],
       rationale="achievements in the outcome"),
    _q("rag-25", "Which mission is collecting samples for return from Mars?",
       kind=QuestionKind.MISSION,
       expected_sources=["mission:perseverance"],
       rationale="objective-based"),

    # -- objects ----------------------------------------------------------
    _q("rag-26", "Tell me about Ceres.",
       kind=QuestionKind.OBJECT,
       expected_sources=["asteroid:1"],
       rationale="archive record, bare lookup"),
    _q("rag-27", "What is Bennu?",
       kind=QuestionKind.OBJECT,
       expected_sources=["asteroid:101955"],
       rationale="archive record"),
    _q("rag-28", "What is Kepler-22 b?",
       kind=QuestionKind.OBJECT,
       expected_sources=["exoplanet:kepler-22-b", "star:kepler-22"],
       rationale="exoplanet from the archive"),
    _q("rag-29", "What is the International Space Station?",
       kind=QuestionKind.OBJECT,
       expected_sources=["space-station:25544"],
       rationale="operational record, alias lookup"),
    _q("rag-30", "What orbit is the ISS in?",
       kind=QuestionKind.OBJECT,
       expected_sources=["space-station:25544"],
       rationale="orbital data from an operational feed"),

    # -- time-sensitive ---------------------------------------------------
    _q("rag-31", "Where is the ISS right now?",
       kind=QuestionKind.TIME_SENSITIVE,
       expected_sources=["space-station:25544"],
       requires_freshness_caveat=True,
       rationale="must not answer from stored elements as though current"),
    _q("rag-32", "What are the ISS's current orbital elements?",
       kind=QuestionKind.TIME_SENSITIVE,
       expected_sources=["space-station:25544"],
       requires_freshness_caveat=True,
       rationale="explicitly asks for current values"),

    # -- must decline -----------------------------------------------------
    _q("rag-33", "What did the Beagle 2 lander discover on Mars?",
       kind=QuestionKind.UNANSWERABLE, should_decline=True,
       rationale="in-domain, plausible, absent from the corpus"),
    _q("rag-34", "How many moons does Kepler-22 b have?",
       kind=QuestionKind.UNANSWERABLE, should_decline=True,
       rationale="the record exists but does not contain this"),
    _q("rag-35", "What was the exact cost of the Artemis I mission?",
       kind=QuestionKind.UNANSWERABLE, should_decline=True,
       rationale="mission is indexed, budget is not"),
    _q("rag-36", "Who was the flight director for Chandrayaan-3?",
       kind=QuestionKind.UNANSWERABLE, should_decline=True,
       rationale="personnel detail not in the corpus"),
    _q("rag-37", "How do I file my tax return?",
       kind=QuestionKind.OUT_OF_DOMAIN, should_decline=True,
       rationale="entirely out of domain"),
    _q("rag-38", "What is the best pizza topping?",
       kind=QuestionKind.OUT_OF_DOMAIN, should_decline=True,
       rationale="out of domain and subjective"),
    _q("rag-39", "zzqqxx wvvbb kkjjhh",
       kind=QuestionKind.OUT_OF_DOMAIN, should_decline=True,
       rationale="gibberish"),
    _q("rag-40", "What will the ISS's orbit be in the year 2400?",
       kind=QuestionKind.UNANSWERABLE, should_decline=True,
       rationale="unanswerable in principle from stored elements"),
]


def answerable_questions() -> List[RAGQuestion]:
    return [item for item in RAG_QUESTIONS if item.is_answerable]


def unanswerable_questions() -> List[RAGQuestion]:
    return [item for item in RAG_QUESTIONS if item.should_decline]
