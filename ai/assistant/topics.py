"""Domain topic routing.

The assistant covers space science, planets, spacecraft, missions, rockets,
propulsion, orbital mechanics, engineering and learning. Knowing which of those
a question belongs to changes two things: which sources are authoritative for
it, and what a good answer looks like.

Rule-based and inspectable, for the same reason as intent classification: the
signals are strong, and a misrouted question should be traceable to the word
that caused it.
"""

import re
from enum import Enum
from typing import Dict, List, Optional, Sequence, Set

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["Topic", "TopicAssessment", "classify_topic", "TOPIC_KEYWORDS"]


class Topic(str, Enum):
    """Subject areas the assistant covers."""

    SPACE_SCIENCE = "SPACE_SCIENCE"
    PLANETS = "PLANETS"
    SPACECRAFT = "SPACECRAFT"
    MISSIONS = "MISSIONS"
    ROCKETS = "ROCKETS"
    PROPULSION = "PROPULSION"
    ORBITAL_MECHANICS = "ORBITAL_MECHANICS"
    ENGINEERING = "ENGINEERING"
    LEARNING = "LEARNING"
    #: Recognisably in-domain but not one of the above.
    GENERAL = "GENERAL"
    #: Not a space question at all.
    OUT_OF_DOMAIN = "OUT_OF_DOMAIN"


#: Topic -> terms that indicate it. Matched as whole words.
TOPIC_KEYWORDS: Dict[Topic, Set[str]] = {
    Topic.PLANETS: {
        "planet", "planets", "mars", "venus", "mercury", "jupiter", "saturn",
        "uranus", "neptune", "pluto", "moon", "moons", "dwarf", "asteroid",
        "asteroids", "comet", "comets", "ceres", "bennu", "exoplanet",
        "exoplanets", "atmosphere", "surface", "crater", "terrestrial",
    },
    Topic.SPACECRAFT: {
        "spacecraft", "probe", "probes", "rover", "rovers", "lander", "landers",
        "orbiter", "orbiters", "satellite", "satellites", "iss", "station",
        "telescope", "voyager", "cassini", "galileo", "juno", "curiosity",
        "perseverance",
    },
    Topic.MISSIONS: {
        "mission", "missions", "apollo", "artemis", "chandrayaan", "launch",
        "flyby", "landing", "objective", "objectives", "crew", "crewed",
        "programme", "program", "agency", "nasa", "esa", "isro",
    },
    Topic.ROCKETS: {
        "rocket", "rockets", "launcher", "vehicle", "booster", "stage",
        "staging", "saturn", "falcon", "sls", "lvm3", "payload", "fairing",
        "liftoff", "ascent",
    },
    Topic.PROPULSION: {
        "propulsion", "engine", "engines", "thrust", "isp", "impulse",
        "propellant", "fuel", "oxidiser", "oxidizer", "turbopump", "nozzle",
        "combustion", "cryogenic", "hypergolic", "ion", "burn",
    },
    Topic.ORBITAL_MECHANICS: {
        "orbit", "orbits", "orbital", "eccentricity", "inclination", "apoapsis",
        "periapsis", "perigee", "apogee", "hohmann", "transfer", "delta-v",
        "deltav", "ephemeris", "trajectory", "kepler", "gravity", "assist",
        "decay", "elements", "epoch", "raan", "anomaly", "semi-major",
    },
    Topic.ENGINEERING: {
        "structure", "structural", "load", "loads", "material", "materials",
        "heat", "thermal", "shield", "failure", "tolerance", "margin",
        "pressure", "stress", "design", "subsystem", "component", "telemetry",
        "avionics", "max-q", "maxq", "reentry", "re-entry",
    },
    Topic.LEARNING: {
        "learn", "learning", "lesson", "lessons", "study", "beginner",
        "explain", "understand", "teach", "course", "tutorial", "next",
        "practice", "exercise",
    },
    Topic.SPACE_SCIENCE: {
        "space", "astronomy", "astrophysics", "star", "stars", "galaxy",
        "universe", "cosmic", "solar", "system", "radiation", "magnetosphere",
        "observation", "spectrum", "science", "scientific",
    },
}

_WORD = re.compile(r"[a-z0-9][a-z0-9\-]*")

#: Strong signals that a question is not about space at all. Kept short: the
#: real out-of-domain test is that nothing in the corpus matches, which
#: retrieval already handles. This only catches the obvious.
_OUT_OF_DOMAIN = {
    "tax", "taxes", "recipe", "pizza", "mortgage", "divorce", "stock",
    "cryptocurrency", "medication", "dosage", "lawsuit",
}


class TopicAssessment(BaseModel):
    """Which subject areas a question touches."""

    model_config = ConfigDict(extra="forbid")

    #: The strongest match.
    primary: Topic = Topic.GENERAL
    #: Every topic with at least one matching term, strongest first.
    topics: List[Topic] = Field(default_factory=list)
    confidence: float = 0.0
    matched_terms: List[str] = Field(default_factory=list)

    @property
    def is_in_domain(self) -> bool:
        return self.primary is not Topic.OUT_OF_DOMAIN

    @property
    def is_scientific(self) -> bool:
        """Whether authoritative archive sources should be preferred."""
        return self.primary in (
            Topic.SPACE_SCIENCE, Topic.PLANETS, Topic.ORBITAL_MECHANICS,
            Topic.SPACECRAFT, Topic.MISSIONS,
        )

    @property
    def is_engineering(self) -> bool:
        """Whether written explanation is likely to serve better than archives."""
        return self.primary in (
            Topic.ENGINEERING, Topic.PROPULSION, Topic.ROCKETS, Topic.LEARNING
        )


def classify_topic(text: str) -> TopicAssessment:
    """Route a question to its subject areas."""
    lowered = str(text or "").lower()
    words = set(_WORD.findall(lowered))
    if not words:
        return TopicAssessment()

    if words & _OUT_OF_DOMAIN:
        matched = sorted(words & _OUT_OF_DOMAIN)
        #: Only out-of-domain when nothing in-domain also matched — "the
        #: economics of launch" is a space question with a finance word in it.
        in_domain = any(words & terms for terms in TOPIC_KEYWORDS.values())
        if not in_domain:
            return TopicAssessment(
                primary=Topic.OUT_OF_DOMAIN,
                confidence=0.8,
                matched_terms=matched,
            )

    scores: Dict[Topic, List[str]] = {}
    for topic, terms in TOPIC_KEYWORDS.items():
        hits = sorted(words & terms)
        if hits:
            scores[topic] = hits

    if not scores:
        return TopicAssessment(primary=Topic.GENERAL, confidence=0.2)

    ordered = sorted(
        scores.items(), key=lambda item: (-len(item[1]), item[0].value)
    )
    primary, hits = ordered[0]
    total = sum(len(items) for items in scores.values())
    return TopicAssessment(
        primary=primary,
        topics=[topic for topic, _ in ordered],
        confidence=min(1.0, len(hits) / float(max(1, total)) + 0.3),
        matched_terms=sorted({term for _, items in ordered for term in items}),
    )
