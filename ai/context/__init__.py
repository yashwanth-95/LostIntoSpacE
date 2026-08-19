"""Project context: reading the user's own data through Person 2's API.

P4 never touches PostgreSQL. Every read goes through P2's documented HTTP
endpoints using the caller's own bearer token, so P2's ownership checks are the
authorization boundary and P4 holds no privileged credential.
"""

from .client import (
    OwnershipViolation,
    ProjectAccessDenied,
    ProjectAPIError,
    ProjectDataClient,
    ProjectNotFound,
)
from .models import (
    LearningProgress,
    MissionConfiguration,
    ProjectContext,
    ProjectContextKind,
    ProjectSummary,
    SimulationSummary,
    UserNote,
    VehicleComponent,
    VehicleConfiguration,
    VehicleStage,
)
from .render import PROJECT_SOURCE, SIMULATION_SOURCE, render_project_context
from .selection import PERSONAL_MARKERS, ContextRequest, select_project_context

__all__ = [
    "ProjectDataClient",
    "ProjectAPIError",
    "ProjectAccessDenied",
    "ProjectNotFound",
    "OwnershipViolation",
    "ProjectContext",
    "ProjectContextKind",
    "ProjectSummary",
    "MissionConfiguration",
    "VehicleConfiguration",
    "VehicleStage",
    "VehicleComponent",
    "SimulationSummary",
    "LearningProgress",
    "UserNote",
    "select_project_context",
    "ContextRequest",
    "PERSONAL_MARKERS",
    "render_project_context",
    "PROJECT_SOURCE",
    "SIMULATION_SOURCE",
]
