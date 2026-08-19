"""Deciding which project data a question needs.

"Use project information only when relevant" is a privacy requirement as much
as a quality one. Every field pulled into a prompt is a field that could be
echoed back, logged, or sent to a vendor — so the default is to fetch nothing,
and each kind must be justified by the question.

The mapping is explicit and inspectable rather than learned:

    "Why did my rocket fail?"   -> simulation result, failure event,
                                   vehicle config, mission config
    "What should I learn next?" -> learning progress, project context
    "What causes Max-Q?"        -> nothing; it is a general question

That last case matters most. A general question about physics must not drag a
user's private vehicle design into the prompt, however convenient that might be.
"""

import re
from typing import Dict, List, Optional, Sequence, Set

from pydantic import BaseModel, ConfigDict, Field

from .models import ProjectContextKind

__all__ = ["ContextRequest", "select_project_context", "PERSONAL_MARKERS"]

#: Words that make a question about *the user's own work* rather than about
#: space in general. Without one of these, no project data is fetched at all.
PERSONAL_MARKERS = (
    r"\bmy\b", r"\bmine\b", r"\bour\b", r"\bi\s+(?:built|made|designed|ran|"
    r"created|configured)\b", r"\bthis (?:project|mission|rocket|vehicle|"
    r"design|simulation|run)\b", r"\bthe (?:simulation|run) i\b",
)

_PERSONAL = re.compile("|".join(PERSONAL_MARKERS), re.IGNORECASE)

#: Topic -> the kinds it justifies. Ordered by how directly each is needed.
_TOPIC_KINDS: Dict[str, List[ProjectContextKind]] = {
    "failure": [
        ProjectContextKind.SIMULATION_RESULT,
        ProjectContextKind.FAILURE_EVENT,
        ProjectContextKind.VEHICLE_CONFIG,
        ProjectContextKind.MISSION_CONFIG,
    ],
    "simulation": [
        ProjectContextKind.SIMULATION_RESULT,
        ProjectContextKind.TELEMETRY,
        ProjectContextKind.VEHICLE_CONFIG,
    ],
    "vehicle": [
        ProjectContextKind.VEHICLE_CONFIG,
        ProjectContextKind.MISSION_CONFIG,
    ],
    "mission": [
        ProjectContextKind.MISSION_CONFIG,
        ProjectContextKind.PROJECT,
    ],
    "learning": [
        ProjectContextKind.LEARNING_PROGRESS,
        ProjectContextKind.PROJECT,
    ],
    "requirements": [
        ProjectContextKind.REQUIREMENTS,
        ProjectContextKind.PROJECT,
    ],
}

_TOPIC_PATTERNS: Dict[str, str] = {
    "failure": r"\b(?:fail|failed|failure|crash|crashed|explode|exploded|blew|"
               r"anomaly|abort|aborted|lost|broke|broken|went wrong|"
               r"didn'?t work)\b",
    "simulation": r"\b(?:simulat\w*|run|telemetry|trajectory|flight|launch"
                  r"ed?)\b",
    "vehicle": r"\b(?:rocket|vehicle|stage|stages|engine|engines|booster|"
               r"payload|thrust|propellant|tank|component)\b",
    "mission": r"\b(?:mission|orbit|target|objective|destination|apogee|"
               r"altitude)\b",
    "learning": r"\b(?:learn|learning|lesson|study|next|progress|practice|"
                r"understand|teach|beginner|level)\b",
    "requirements": r"\b(?:requirement|requirements|spec|specs|constraint|"
                    r"goal|goals)\b",
}

_COMPILED_TOPICS = {
    name: re.compile(pattern, re.IGNORECASE)
    for name, pattern in _TOPIC_PATTERNS.items()
}


class ContextRequest(BaseModel):
    """What project data to fetch, and why."""

    model_config = ConfigDict(extra="forbid")

    kinds: List[ProjectContextKind] = Field(default_factory=list)
    #: True when the question refers to the user's own work.
    is_personal: bool = False
    #: Which topic rules fired.
    matched_topics: List[str] = Field(default_factory=list)
    reason: str = ""

    @property
    def needs_project_data(self) -> bool:
        return bool(self.kinds)

    def includes(self, kind: ProjectContextKind) -> bool:
        return kind in self.kinds


def select_project_context(
    question: str,
    has_project: bool = True,
    has_simulation: bool = False,
) -> ContextRequest:
    """Decide which project data, if any, this question justifies.

    `has_project` and `has_simulation` describe what the caller *could* supply.
    Asking for a simulation when none is in scope would produce a guaranteed
    skip, and the reason belongs in the request rather than in the fetch.
    """
    text = str(question or "")
    if not text.strip():
        return ContextRequest(reason="empty question")

    is_personal = bool(_PERSONAL.search(text))
    if not is_personal:
        return ContextRequest(
            is_personal=False,
            reason=(
                "the question is not about the user's own work, so no project "
                "data is fetched"
            ),
        )

    if not has_project:
        return ContextRequest(
            is_personal=True,
            reason="the question is personal but no project is in scope",
        )

    matched: List[str] = []
    kinds: List[ProjectContextKind] = []
    for name, pattern in _COMPILED_TOPICS.items():
        if pattern.search(text):
            matched.append(name)
            for kind in _TOPIC_KINDS[name]:
                if kind not in kinds:
                    kinds.append(kind)

    if not matched:
        #: Personal but unclassifiable — fetch the project itself and nothing
        #: more. Broadening the fetch "just in case" is what turns a general
        #: question into an unnecessary disclosure.
        return ContextRequest(
            kinds=[ProjectContextKind.PROJECT],
            is_personal=True,
            matched_topics=[],
            reason="personal question with no specific topic; project summary only",
        )

    if not has_simulation:
        dropped = [
            kind for kind in kinds
            if kind in (
                ProjectContextKind.SIMULATION_RESULT,
                ProjectContextKind.FAILURE_EVENT,
                ProjectContextKind.TELEMETRY,
            )
        ]
        kinds = [kind for kind in kinds if kind not in dropped]

    return ContextRequest(
        kinds=kinds,
        is_personal=True,
        matched_topics=sorted(matched),
        reason="matched {0}".format(", ".join(sorted(matched))),
    )
