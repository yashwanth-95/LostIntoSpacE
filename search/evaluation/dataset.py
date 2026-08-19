"""The labelled evaluation set.

Thirty-six queries: thirty-one answerable from the indexed corpus, five that
deliberately are not. The unanswerable ones matter as much as the rest — a
retriever that never abstains scores well on precision while being unusable in
front of an AI layer that must not invent answers.

**Honesty note.** These labels were authored by the same person who wrote the
retriever and the seed content, so they measure self-consistency, not truth.
That limitation is recorded in `docs/PERSON4_DATA_ARCHITECTURE.md` §7.6 and the
set should be reviewed by someone else before the numbers are quoted anywhere
that matters.

Relevance is a *set*, because more than one record is often genuinely relevant:
"How does a gravity assist work?" is answered by the concept, and also by
Cassini and Voyager 2, whose descriptions explain their use of the technique.
Insisting on a single right answer would measure a labelling opinion.
"""

from typing import List, Set

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["EvaluationQuery", "EVALUATION_QUERIES", "answerable", "unanswerable"]


class EvaluationQuery(BaseModel):
    """One labelled query."""

    model_config = ConfigDict(extra="forbid")

    id: str
    text: str
    #: Canonical ids that count as a correct hit. Empty means the system should
    #: abstain.
    relevant: List[str] = Field(default_factory=list)
    #: Why this query is in the set.
    rationale: str = ""
    #: True when the corpus genuinely cannot answer it.
    expects_no_answer: bool = False


def _q(id, text, relevant=(), rationale="", expects_no_answer=False):
    return EvaluationQuery(
        id=id,
        text=text,
        relevant=list(relevant),
        rationale=rationale,
        expects_no_answer=expects_no_answer,
    )


#: The task's five named questions come first, so a regression in them is
#: immediately visible in the report.
EVALUATION_QUERIES: List[EvaluationQuery] = [
    # -- the named questions ---------------------------------------------
    _q("named-01", "How does staging improve rocket performance?",
       ["concept:staging"], "named in the task"),
    _q("named-02", "What causes Max-Q?",
       ["concept:max-q"], "named in the task"),
    _q("named-03", "Which spacecraft explored Jupiter?",
       ["mission:galileo", "mission:juno", "mission:voyager-2"],
       "named in the task; three missions are genuinely relevant"),
    _q("named-04", "What causes orbital decay?",
       ["concept:orbital-decay"], "named in the task"),
    _q("named-05", "How does a gravity assist work?",
       ["concept:gravity-assist", "mission:cassini", "mission:voyager-2"],
       "named in the task; the concept and its canonical examples"),

    # -- conceptual questions ---------------------------------------------
    _q("concept-01", "What is specific impulse?",
       ["concept:specific-impulse"], "definition lookup"),
    _q("concept-02", "How do liquid rocket engines work?",
       ["concept:liquid-propulsion"], "concept, phrased as a question"),
    _q("concept-03", "What is a Hohmann transfer orbit?",
       ["concept:hohmann-transfer"], "concept with a proper noun"),
    _q("concept-04", "Why do spacecraft heat up during re-entry?",
       ["concept:reentry-heating"], "causal question, no title-word overlap"),
    _q("concept-05", "What are the six orbital elements?",
       ["concept:orbital-mechanics"], "content buried in the body"),
    _q("concept-06", "How much delta-v does it take to reach orbit?",
       ["concept:delta-v-budget"], "numeric detail inside the body"),
    _q("concept-07", "Why do rockets throttle down during ascent?",
       ["concept:max-q"], "paraphrase with no title-word overlap"),
    _q("concept-08", "What is dynamic pressure?",
       ["concept:max-q"], "the equation's subject, not the title"),
    _q("concept-09", "Why are rockets built in multiple stages?",
       ["concept:staging"], "paraphrase of the staging question"),
    _q("concept-10", "What is the rocket equation?",
       ["concept:staging", "concept:specific-impulse"],
       "equation appears in two concepts"),
    _q("concept-11", "How does atmospheric drag affect satellites?",
       ["concept:orbital-decay"], "mechanism phrased differently"),
    _q("concept-12", "What is a turbopump used for?",
       ["concept:liquid-propulsion"], "single technical term in the body"),
    _q("concept-13", "Why are re-entry capsules blunt rather than pointed?",
       ["concept:reentry-heating"], "design rationale in the body"),
    _q("concept-14", "What is a heat shield for?",
       ["concept:reentry-heating"], "short conceptual query"),
    _q("concept-15", "How do you change a satellite's orbit efficiently?",
       ["concept:hohmann-transfer", "concept:orbital-mechanics"],
       "two concepts are relevant"),

    # -- mission questions -------------------------------------------------
    _q("mission-01", "Which mission first landed humans on the Moon?",
       ["mission:apollo-11"], "factual mission lookup"),
    _q("mission-02", "Apollo 13",
       ["mission:apollo-13"], "bare title lookup"),
    _q("mission-03", "Which Mars rovers are there?",
       ["mission:curiosity", "mission:perseverance"], "two relevant missions"),
    _q("mission-04", "What was the first Artemis flight?",
       ["mission:artemis-1"], "programme question"),
    _q("mission-05", "Which mission visited Uranus and Neptune?",
       ["mission:voyager-2"], "unique fact in the description"),
    _q("mission-06", "Which ISRO mission landed near the lunar south pole?",
       ["mission:chandrayaan-3"], "agency plus location"),
    _q("mission-07", "Which spacecraft orbited Saturn?",
       ["mission:cassini"], "target-based lookup"),
    _q("mission-08", "Which Apollo mission suffered an oxygen tank failure?",
       ["mission:apollo-13"], "anomaly recorded in the outcome"),
    _q("mission-09", "Which mission carried an atmospheric probe to a giant planet?",
       ["mission:galileo"], "achievement in the outcome"),
    _q("mission-10", "sample return mission to Mars",
       ["mission:perseverance"], "keyword-style query, no question form"),

    # -- object and archive questions --------------------------------------
    _q("object-01", "Ceres",
       ["asteroid:1"], "bare identifier for an ingested archive record"),
    _q("object-02", "International Space Station",
       ["space-station:25544"], "alias lookup on operational data"),

    # -- queries the corpus cannot answer ----------------------------------
    _q("abstain-01", "What is the airspeed velocity of an unladen swallow?",
       [], "nonsense; must abstain", expects_no_answer=True),
    _q("abstain-02", "How do I file my tax return?",
       [], "entirely out of domain", expects_no_answer=True),
    _q("abstain-03", "What is the best pizza topping?",
       [], "out of domain and opinion-based", expects_no_answer=True),
    _q("abstain-04", "zzqqxx wvvbb kkjjhh",
       [], "gibberish", expects_no_answer=True),
    _q("abstain-05", "What did the Beagle 2 lander discover on Mars?",
       [], "plausible and in-domain, but absent from the corpus",
       expects_no_answer=True),
]


def answerable() -> List[EvaluationQuery]:
    return [query for query in EVALUATION_QUERIES if not query.expects_no_answer]


def unanswerable() -> List[EvaluationQuery]:
    return [query for query in EVALUATION_QUERIES if query.expects_no_answer]
