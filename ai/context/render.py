"""Rendering project data into context items.

Project data enters a prompt on exactly the same path as a retrieved document:
it is sanitized, fenced, labelled with its source, and given a reference the
model must cite. Two consequences worth stating:

* **User-authored text is untrusted.** A project name, a requirement or a note
  is text a user typed, and a user can type an instruction. It goes through the
  same injection scan as an NTRS abstract.
* **Project data is not evidence about the world.** It is labelled
  `USER_PROVIDED` or `SIMULATION`, never `PRIMARY_SCIENTIFIC`, so a claim
  resting on it cannot be presented as a scientific fact.
"""

from typing import List, Optional, Sequence

from contracts._time import utc_now
from contracts.ai import ContextItem
from contracts.provenance import FreshnessClass, SourceReference, SourceType

from ..safety.sanitize import sanitize_context_text
from .models import ProjectContext, ProjectContextKind

__all__ = ["render_project_context", "PROJECT_SOURCE", "SIMULATION_SOURCE"]

#: Provenance for user-authored configuration and notes.
PROJECT_SOURCE = SourceReference(
    source_name="user_project",
    source_type=SourceType.USER_PROVIDED,
    attribution="This project's own configuration",
)

#: Provenance for simulator output.
SIMULATION_SOURCE = SourceReference(
    source_name="simulation_engine",
    source_type=SourceType.SIMULATION,
    attribution="LostIntoSpacE educational simulator",
)


def _item(ref, canonical_id, title, content, source, kind, sanitize=True):
    """Build one context item, sanitizing user-authored text."""
    body = content
    if sanitize:
        cleaned = sanitize_context_text(content, location=canonical_id)
        if cleaned.should_quarantine:
            #: Refuse rather than fence: a project note trying to reassign the
            #: model's role has no legitimate reading.
            return None
        body = cleaned.text
    return ContextItem(
        ref=ref,
        canonical_id=canonical_id,
        title=title,
        content=body,
        source=source,
        source_type=source.source_type,
        timestamp=None,
        retrieved_at=utc_now(),
        freshness_class=FreshnessClass.STATIC,
        relevance=1.0,
        #: Project data is current by construction — it was just fetched — but
        #: it describes the user's design, not the world, so it is never
        #: presentable as a live scientific reading.
        may_present_as_live=False,
    )


def render_project_context(
    context: ProjectContext, start_index: int = 1
) -> List[ContextItem]:
    """Turn fetched project data into citable context items."""
    items: List[ContextItem] = []
    index = start_index

    def add(canonical_id, title, content, source):
        nonlocal index
        if not content or not str(content).strip():
            return
        built = _item(
            "P{0}".format(index), canonical_id, title, str(content), source, None
        )
        if built is not None:
            items.append(built)
            index += 1

    project = context.project
    if project is not None:
        lines = []
        if project.name:
            lines.append("Name: {0}".format(project.name))
        if project.description:
            lines.append("Description: {0}".format(project.description))
        if project.target:
            lines.append("Target: {0}".format(project.target))
        if project.requirements:
            lines.append(
                "Requirements:\n" + "\n".join(
                    "  - {0}".format(item) for item in project.requirements
                )
            )
        add("project:{0}".format(project.id or "current"), "Project configuration",
            "\n".join(lines), PROJECT_SOURCE)

    mission = context.mission
    if mission is not None:
        add("mission-config:{0}".format(mission.id or "current"),
            "Mission configuration", mission.describe(), PROJECT_SOURCE)

    vehicle = context.vehicle
    if vehicle is not None:
        add("vehicle-config:{0}".format(vehicle.id or "current"),
            "Vehicle configuration", vehicle.describe(), PROJECT_SOURCE)

    simulation = context.simulation
    if simulation is not None:
        lines = []
        if simulation.status:
            lines.append("Status: {0}".format(simulation.status))
        if simulation.outcome:
            lines.append("Outcome: {0}".format(simulation.outcome))
        if simulation.max_altitude_km is not None:
            lines.append("Max altitude: {0:g} km".format(simulation.max_altitude_km))
        if simulation.max_velocity_ms is not None:
            lines.append("Max velocity: {0:g} m/s".format(simulation.max_velocity_ms))
        if simulation.engine_version:
            lines.append("Engine version: {0}".format(simulation.engine_version))
        add("simulation:{0}".format(simulation.id or "current"),
            "Simulation run (simulator output, not a real flight)",
            "\n".join(lines), SIMULATION_SOURCE)

        for position, event in enumerate(simulation.events[:10]):
            add(
                "simulation-event:{0}:{1}".format(simulation.id or "current", position),
                "Simulation event {0}".format(position + 1),
                _describe_event(event),
                SIMULATION_SOURCE,
            )
        for position, failure in enumerate(simulation.failures[:5]):
            add(
                "simulation-failure:{0}:{1}".format(
                    simulation.id or "current", position
                ),
                "Simulation failure {0}".format(position + 1),
                _describe_event(failure),
                SIMULATION_SOURCE,
            )

    learning = context.learning
    if learning is not None:
        lines = []
        if learning.level:
            lines.append("Level: {0}".format(learning.level))
        if learning.completed_lesson_slugs:
            lines.append("Completed: {0}".format(
                ", ".join(learning.completed_lesson_slugs)
            ))
        if learning.in_progress_lesson_slugs:
            lines.append("In progress: {0}".format(
                ", ".join(learning.in_progress_lesson_slugs)
            ))
        if learning.topic_mastery:
            lines.append("Weakest topics: {0}".format(
                ", ".join(learning.weakest_topics())
            ))
        add("learning-progress:{0}".format(context.user_id or "current"),
            "Learning progress", "\n".join(lines), PROJECT_SOURCE)

    for position, note in enumerate(context.notes[:5]):
        add("user-note:{0}".format(note.id or position),
            note.title or "User note", note.body, PROJECT_SOURCE)

    return items


def _describe_event(event) -> str:
    """Render a simulation event dict without assuming its shape.

    Person 3 owns the event schema; Task 24 binds to it properly. Until then
    this renders whatever keys are present rather than guessing at names that
    may not exist.
    """
    if not isinstance(event, dict):
        return str(event)
    parts = []
    for key in ("time_s", "t", "timestamp", "type", "event_type", "phase",
                "severity", "component", "subsystem", "message", "description",
                "reason", "value", "unit"):
        if key in event and event[key] not in (None, ""):
            parts.append("{0}: {1}".format(key, event[key]))
    if not parts:
        parts = ["{0}: {1}".format(key, value) for key, value in event.items()]
    return "; ".join(parts)
