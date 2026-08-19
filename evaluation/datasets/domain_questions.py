"""Domain question sets for the full evaluation suite.

Task 29 requires, on top of the 30 search queries and 40 RAG questions already
in place:

* 20 mission questions
* 20 rocket-engineering questions
* 20 space-object questions
* 10 failure-analysis scenarios
* 10 recommendation scenarios

Each set is labelled with what a correct answer *requires* — the evidence, the
origin, the caveats — rather than with expected wording. Asserting phrasing
would test the language model; asserting evidence tests the system.

Same honesty caveat as the retrieval set: these labels were authored by the
same person who built the pipeline, so they measure self-consistency until
someone else reviews them.
"""

from typing import List

from pydantic import BaseModel, ConfigDict, Field

from .rag_questions import QuestionKind, RAGQuestion

__all__ = [
    "MISSION_QUESTIONS",
    "ENGINEERING_QUESTIONS",
    "OBJECT_QUESTIONS",
    "FailureScenario",
    "FAILURE_SCENARIOS",
    "RecommendationScenario",
    "RECOMMENDATION_SCENARIOS",
    "ALL_DOMAIN_QUESTIONS",
]


def _q(id, question, **kwargs):
    return RAGQuestion(id=id, question=question, **kwargs)


# ----------------------------------------------------------------------
# 20 mission questions
# ----------------------------------------------------------------------
MISSION_QUESTIONS: List[RAGQuestion] = [
    _q("mq-01", "Which mission first landed humans on the Moon?",
       kind=QuestionKind.MISSION, expected_sources=["mission:apollo-11"],
       expected_terms=["Apollo"], rationale="canonical fact"),
    _q("mq-02", "Who crewed Apollo 11?",
       kind=QuestionKind.MISSION, expected_sources=["mission:apollo-11"],
       rationale="crew list is on the record"),
    _q("mq-03", "What went wrong on Apollo 13?",
       kind=QuestionKind.MISSION, expected_sources=["mission:apollo-13"],
       expected_terms=["oxygen"], rationale="recorded anomaly"),
    _q("mq-04", "What lessons came out of Apollo 13?",
       kind=QuestionKind.MISSION, expected_sources=["mission:apollo-13"],
       rationale="published lessons on the record"),
    _q("mq-05", "What was Artemis I?",
       kind=QuestionKind.MISSION, expected_sources=["mission:artemis-1"],
       rationale="recent programme"),
    _q("mq-06", "Was Artemis I crewed?",
       kind=QuestionKind.MISSION, expected_sources=["mission:artemis-1"],
       rationale="mission type is on the record"),
    _q("mq-07", "Which mission visited Uranus and Neptune?",
       kind=QuestionKind.MISSION, expected_sources=["mission:voyager-2"],
       rationale="unique fact"),
    _q("mq-08", "Why could Voyager 2 reach so many planets?",
       kind=QuestionKind.MISSION,
       expected_sources=["mission:voyager-2", "concept:gravity-assist"],
       rationale="mission plus the concept explaining it"),
    _q("mq-09", "What did Galileo achieve at Jupiter?",
       kind=QuestionKind.MISSION, expected_sources=["mission:galileo"],
       expected_terms=["Jupiter"], rationale="achievements on the record"),
    _q("mq-10", "What went wrong with Galileo's antenna?",
       kind=QuestionKind.MISSION, expected_sources=["mission:galileo"],
       rationale="recorded anomaly"),
    _q("mq-11", "What is Juno studying?",
       kind=QuestionKind.MISSION, expected_sources=["mission:juno"],
       rationale="objectives on the record"),
    _q("mq-12", "How did Curiosity land on Mars?",
       kind=QuestionKind.MISSION, expected_sources=["mission:curiosity"],
       rationale="landing method in the description"),
    _q("mq-13", "What is Perseverance collecting?",
       kind=QuestionKind.MISSION, expected_sources=["mission:perseverance"],
       rationale="objective on the record"),
    _q("mq-14", "Which ISRO mission landed near the lunar south pole?",
       kind=QuestionKind.MISSION, expected_sources=["mission:chandrayaan-3"],
       rationale="agency-specific"),
    _q("mq-15", "Which mission delivered a probe to Titan?",
       kind=QuestionKind.MISSION, expected_sources=["mission:cassini"],
       rationale="detail in the description"),
    _q("mq-16", "How long did Cassini operate?",
       kind=QuestionKind.MISSION, expected_sources=["mission:cassini"],
       rationale="launch and end dates are recorded"),
    _q("mq-17", "Which missions have explored Jupiter?",
       kind=QuestionKind.MISSION,
       expected_sources=["mission:galileo", "mission:juno", "mission:voyager-2"],
       rationale="several correct answers"),
    _q("mq-18", "Which agency ran Chandrayaan-3?",
       kind=QuestionKind.MISSION, expected_sources=["mission:chandrayaan-3"],
       rationale="agency lookup"),
    _q("mq-19", "What launch vehicle did Apollo 11 use?",
       kind=QuestionKind.MISSION, expected_sources=["mission:apollo-11"],
       rationale="launch vehicle on the record"),
    _q("mq-20", "What was the exact budget of the Cassini mission?",
       kind=QuestionKind.UNANSWERABLE, should_decline=True,
       rationale="mission indexed, budget is not"),
]


# ----------------------------------------------------------------------
# 20 rocket-engineering questions
# ----------------------------------------------------------------------
ENGINEERING_QUESTIONS: List[RAGQuestion] = [
    _q("eq-01", "How does staging improve rocket performance?",
       kind=QuestionKind.ENGINEERING, expected_sources=["concept:staging"],
       expected_terms=["mass"], rationale="core concept"),
    _q("eq-02", "Why are rockets built in multiple stages?",
       kind=QuestionKind.ENGINEERING, expected_sources=["concept:staging"],
       rationale="paraphrase"),
    _q("eq-03", "What is specific impulse?",
       kind=QuestionKind.ENGINEERING,
       expected_sources=["concept:specific-impulse"],
       expected_terms=["propellant"], rationale="definition"),
    _q("eq-04", "Why can't ion thrusters launch a rocket?",
       kind=QuestionKind.ENGINEERING,
       expected_sources=["concept:specific-impulse"],
       rationale="thrust versus efficiency, in the body"),
    _q("eq-05", "How do liquid rocket engines work?",
       kind=QuestionKind.ENGINEERING,
       expected_sources=["concept:liquid-propulsion"],
       rationale="core concept"),
    _q("eq-06", "What is a turbopump for?",
       kind=QuestionKind.ENGINEERING,
       expected_sources=["concept:liquid-propulsion"],
       rationale="single term in the body"),
    _q("eq-07", "What is regenerative cooling?",
       kind=QuestionKind.ENGINEERING,
       expected_sources=["concept:liquid-propulsion"],
       rationale="detail in the body"),
    _q("eq-08", "Why use hypergolic propellants?",
       kind=QuestionKind.ENGINEERING,
       expected_sources=["concept:liquid-propulsion"],
       rationale="ignition without an igniter"),
    _q("eq-09", "What causes Max-Q?",
       kind=QuestionKind.ENGINEERING, expected_sources=["concept:max-q"],
       expected_terms=["pressure"], rationale="core concept"),
    _q("eq-10", "Why do rockets throttle down during ascent?",
       kind=QuestionKind.ENGINEERING, expected_sources=["concept:max-q"],
       rationale="paraphrase with no title overlap"),
    _q("eq-11", "What is dynamic pressure?",
       kind=QuestionKind.ENGINEERING, expected_sources=["concept:max-q"],
       rationale="the equation's subject"),
    _q("eq-12", "Why do spacecraft heat up during re-entry?",
       kind=QuestionKind.ENGINEERING,
       expected_sources=["concept:reentry-heating"],
       expected_terms=["shock"], rationale="common misconception"),
    _q("eq-13", "Why are re-entry vehicles blunt?",
       kind=QuestionKind.ENGINEERING,
       expected_sources=["concept:reentry-heating"],
       rationale="design rationale"),
    _q("eq-14", "What is an ablative heat shield?",
       kind=QuestionKind.ENGINEERING,
       expected_sources=["concept:reentry-heating"],
       rationale="detail in the body"),
    _q("eq-15", "How much delta-v does it take to reach low Earth orbit?",
       kind=QuestionKind.ENGINEERING,
       expected_sources=["concept:delta-v-budget"],
       expected_terms=["km/s"], rationale="numeric detail"),
    _q("eq-16", "What are gravity losses?",
       kind=QuestionKind.ENGINEERING,
       expected_sources=["concept:delta-v-budget"],
       rationale="term defined in the body"),
    _q("eq-17", "What is the rocket equation?",
       kind=QuestionKind.ENGINEERING,
       expected_sources=["concept:staging", "concept:specific-impulse"],
       rationale="appears in two records"),
    _q("eq-18", "What is a Hohmann transfer?",
       kind=QuestionKind.ENGINEERING,
       expected_sources=["concept:hohmann-transfer"],
       rationale="named manoeuvre"),
    _q("eq-19", "When is a bi-elliptic transfer better than a Hohmann?",
       kind=QuestionKind.ENGINEERING,
       expected_sources=["concept:hohmann-transfer"],
       rationale="the ratio threshold is in the body"),
    _q("eq-20", "What is the exact Cd of a Falcon 9 first stage?",
       kind=QuestionKind.UNANSWERABLE, should_decline=True,
       rationale="vehicle-specific figure not in the corpus"),
]


# ----------------------------------------------------------------------
# 20 space-object questions
# ----------------------------------------------------------------------
OBJECT_QUESTIONS: List[RAGQuestion] = [
    _q("oq-01", "Tell me about Ceres.",
       kind=QuestionKind.OBJECT, expected_sources=["asteroid:1"],
       rationale="archive record"),
    _q("oq-02", "What is the mass of Ceres?",
       kind=QuestionKind.OBJECT, expected_sources=["asteroid:1"],
       rationale="measured value from JPL"),
    _q("oq-03", "How big is Ceres?",
       kind=QuestionKind.OBJECT, expected_sources=["asteroid:1"],
       rationale="radius from the archive"),
    _q("oq-04", "What is Bennu?",
       kind=QuestionKind.OBJECT, expected_sources=["asteroid:101955"],
       rationale="archive record"),
    _q("oq-05", "What kind of orbit does Bennu have?",
       kind=QuestionKind.OBJECT, expected_sources=["asteroid:101955"],
       rationale="orbit class from SBDB"),
    _q("oq-06", "What is Kepler-22 b?",
       kind=QuestionKind.OBJECT,
       expected_sources=["exoplanet:kepler-22-b", "star:kepler-22"],
       rationale="exoplanet from the archive"),
    _q("oq-07", "How long is Kepler-22 b's year?",
       kind=QuestionKind.OBJECT, expected_sources=["exoplanet:kepler-22-b"],
       rationale="orbital period from the archive"),
    _q("oq-08", "What star does Kepler-22 b orbit?",
       kind=QuestionKind.OBJECT,
       expected_sources=["star:kepler-22", "exoplanet:kepler-22-b"],
       rationale="host star relationship"),
    _q("oq-09", "What is the International Space Station?",
       kind=QuestionKind.OBJECT, expected_sources=["space-station:25544"],
       rationale="alias lookup"),
    _q("oq-10", "What orbit is the ISS in?",
       kind=QuestionKind.OBJECT, expected_sources=["space-station:25544"],
       rationale="operational element set"),
    _q("oq-11", "What is the ISS's inclination?",
       kind=QuestionKind.OBJECT, expected_sources=["space-station:25544"],
       rationale="single orbital element"),
    _q("oq-12", "What is NORAD 25544?",
       kind=QuestionKind.OBJECT, expected_sources=["space-station:25544"],
       rationale="identifier paste-in"),
    _q("oq-13", "Where is the ISS right now?",
       kind=QuestionKind.TIME_SENSITIVE,
       expected_sources=["space-station:25544"],
       requires_freshness_caveat=True,
       rationale="must not answer from stored elements as current"),
    _q("oq-14", "What are the ISS's current orbital elements?",
       kind=QuestionKind.TIME_SENSITIVE,
       expected_sources=["space-station:25544"],
       requires_freshness_caveat=True, rationale="explicitly current"),
    _q("oq-15", "What GPS satellites are in orbit?",
       kind=QuestionKind.OBJECT, expected_sources=[],
       rationale="constellation records are indexed"),
    _q("oq-16", "What natural events is NASA tracking?",
       kind=QuestionKind.OBJECT, expected_sources=[],
       rationale="EONET events are indexed"),
    _q("oq-17", "What is a dwarf planet?",
       kind=QuestionKind.UNANSWERABLE, should_decline=True,
       rationale="the corpus holds Ceres but no definition of the class; "
                 "answering from unrelated records is the failure this "
                 "labels"),
    _q("oq-18", "Which asteroids does the corpus cover?",
       kind=QuestionKind.OBJECT,
       expected_sources=["asteroid:1", "asteroid:101955"],
       rationale="browse over object records"),
    _q("oq-19", "What is the surface temperature of Kepler-22 b?",
       kind=QuestionKind.UNANSWERABLE, should_decline=True,
       rationale="record exists, this field does not"),
    _q("oq-20", "How many craters does Bennu have?",
       kind=QuestionKind.UNANSWERABLE, should_decline=True,
       rationale="not in the archive record"),
]


# ----------------------------------------------------------------------
# 10 failure-analysis scenarios
# ----------------------------------------------------------------------
class FailureScenario(BaseModel):
    """One simulation run, and what its analysis must contain."""

    model_config = ConfigDict(extra="forbid")

    id: str
    #: Key into `ai.tests.fixtures.simulation_runs.ALL_RUNS`.
    run: str
    #: Documented failure rule the analysis should identify, if any.
    expected_rule: str = ""
    expected_subsystem: str = ""
    #: Concepts the explanation should retrieve.
    expected_references: List[str] = Field(default_factory=list)
    #: Whether an analysis is expected at all.
    expects_cause: bool = True
    #: Whether mitigations should be offered.
    expects_mitigations: bool = True
    rationale: str = ""


FAILURE_SCENARIOS: List[FailureScenario] = [
    FailureScenario(
        id="fs-01", run="twr", expected_rule="insufficient_twr",
        expected_subsystem="PROPULSION",
        expected_references=["concept:staging", "concept:specific-impulse"],
        rationale="the simplest fatal failure",
    ),
    FailureScenario(
        id="fs-02", run="max_q", expected_rule="excessive_q",
        expected_subsystem="AERODYNAMICS",
        expected_references=["concept:max-q"],
        rationale="aerodynamic limit, with an impact aftermath",
    ),
    FailureScenario(
        id="fs-03", run="structural", expected_rule="structural_overload",
        expected_subsystem="STRUCTURE",
        expected_references=["concept:max-q", "concept:staging"],
        rationale="named component in the event",
    ),
    FailureScenario(
        id="fs-04", run="fuel", expected_rule="fuel_exhaustion",
        expected_subsystem="PROPULSION",
        expected_references=["concept:delta-v-budget"],
        rationale="delta-v shortfall",
    ),
    FailureScenario(
        id="fs-05", run="instability", expected_rule="instability",
        expected_subsystem="STABILITY",
        rationale="negative static margin",
    ),
    FailureScenario(
        id="fs-06", run="success", expects_cause=False,
        expects_mitigations=False,
        rationale="a successful run must not acquire an invented failure",
    ),
    FailureScenario(
        id="fs-07", run="undocumented",
        expects_cause=False, expects_mitigations=False,
        rationale="an unknown failure identifier must not be attributed; "
                  "refusing to name a cause is the correct outcome",
    ),
    FailureScenario(
        id="fs-08", run="malformed",
        expects_cause=False, expects_mitigations=False,
        rationale="an unexpected payload shape must degrade rather than raise. "
                  "Its events arrive under a key the parser does not know, so "
                  "no failure is read and no cause is claimed — which is right: "
                  "inventing one from an unparsed payload would be worse than "
                  "reporting that nothing could be read.",
    ),
    FailureScenario(
        id="fs-09", run="max_q", expected_rule="excessive_q",
        expected_subsystem="AERODYNAMICS",
        expected_references=["concept:max-q"],
        rationale="repeat of fs-02 to check determinism",
    ),
    FailureScenario(
        id="fs-10", run="structural", expected_rule="structural_overload",
        expected_subsystem="STRUCTURE",
        rationale="repeat of fs-03 to check determinism",
    ),
]


# ----------------------------------------------------------------------
# 10 recommendation scenarios
# ----------------------------------------------------------------------
class RecommendationScenario(BaseModel):
    """One user situation, and what a good recommendation set looks like."""

    model_config = ConfigDict(extra="forbid")

    id: str
    level: str = "BEGINNER"
    current_topic: str = ""
    completed_ids: List[str] = Field(default_factory=list)
    topic_mastery: dict = Field(default_factory=dict)
    project_context: str = ""
    project_subsystems: List[str] = Field(default_factory=list)
    #: At least one of these should appear.
    expected_any: List[str] = Field(default_factory=list)
    #: None of these may appear.
    forbidden: List[str] = Field(default_factory=list)
    rationale: str = ""


RECOMMENDATION_SCENARIOS: List[RecommendationScenario] = [
    RecommendationScenario(
        id="rs-01", level="BEGINNER", current_topic="propulsion",
        topic_mastery={"propulsion": 0.1},
        expected_any=["concept:specific-impulse", "concept:liquid-propulsion",
                      "concept:staging"],
        rationale="a beginner weak in propulsion",
    ),
    RecommendationScenario(
        id="rs-02", level="BEGINNER", current_topic="propulsion",
        completed_ids=["concept:liquid-propulsion"],
        forbidden=["concept:liquid-propulsion"],
        rationale="completed material must not be recommended back",
    ),
    RecommendationScenario(
        id="rs-03", level="INTERMEDIATE", current_topic="structures",
        project_context="vehicle exceeded its structural limit",
        project_subsystems=["STRUCTURE", "AERODYNAMICS"],
        expected_any=["concept:max-q", "concept:staging",
                      "concept:reentry-heating"],
        rationale="an engineer after a structural failure",
    ),
    RecommendationScenario(
        id="rs-04", level="RESEARCHER", current_topic="max-q",
        rationale="a researcher wants sources, not tutorials",
    ),
    RecommendationScenario(
        id="rs-05", level="INTERMEDIATE", current_topic="dynamic pressure",
        project_context="airframe exceeded dynamic pressure limit",
        project_subsystems=["AERODYNAMICS"],
        expected_any=["concept:max-q"],
        rationale="project-driven, directly relevant",
    ),
    RecommendationScenario(
        id="rs-06", level="BEGINNER", current_topic="orbital mechanics",
        topic_mastery={"orbital mechanics": 0.2},
        expected_any=["concept:orbital-mechanics", "concept:hohmann-transfer",
                      "concept:orbital-decay", "concept:gravity-assist"],
        rationale="a beginner weak in orbital mechanics",
    ),
    RecommendationScenario(
        id="rs-07", level="ADVANCED", current_topic="gravity assist",
        expected_any=["concept:gravity-assist", "mission:voyager-2",
                      "mission:cassini"],
        rationale="advanced users can be shown missions",
    ),
    RecommendationScenario(
        id="rs-08", level="BEGINNER", current_topic="",
        rationale="a new user with no history must still get something",
    ),
    RecommendationScenario(
        id="rs-09", level="BEGINNER", current_topic="staging",
        completed_ids=["concept:specific-impulse"],
        expected_any=["concept:staging"],
        rationale="prerequisite met, so staging becomes appropriate",
    ),
    RecommendationScenario(
        id="rs-10", level="INTERMEDIATE", current_topic="re-entry",
        project_context="capsule returning from orbit",
        expected_any=["concept:reentry-heating", "concept:orbital-decay"],
        rationale="re-entry planning",
    ),
]


#: The three question sets that run through the RAG runner.
ALL_DOMAIN_QUESTIONS: List[RAGQuestion] = (
    MISSION_QUESTIONS + ENGINEERING_QUESTIONS + OBJECT_QUESTIONS
)
