"""Model registry.

Importing this package imports every model, which is what registers them on
`Base.metadata`. Alembic's env.py imports this module and nothing else - if a
model is not reachable from here, autogenerate will not see it and will happily
propose dropping its table.

Approved MVP entities per docs/backend/DATABASE_CONTRACT.md §2: 15 of 17 tables.
The two absent tables are blocked pending P3 sign-off, NOT forgotten:

    vehicle_stages    - mass semantics (SD-6/#25) and propulsion field authority
                        (SD-7/#26) unresolved
    telemetry_points  - storage representation (SD-5/#24) unresolved

`VehicleComponent.stage_id` is absent for the same reason: it is a foreign key
into vehicle_stages. See src/models/vehicle.py for the full note.
"""

from src.core.database.base import Base
from src.models.content import Lesson, SpaceObject
from src.models.conversation import Conversation, Message, SearchHistory
from src.models.learning import LearningProgress
from src.models.project import Mission, Project
from src.models.simulation import FailureEvent, SimulationEvent, SimulationRun
from src.models.user import RefreshToken, User
from src.models.vehicle import Vehicle, VehicleComponent

__all__ = [
    "Base",
    "Conversation",
    "FailureEvent",
    "LearningProgress",
    "Lesson",
    "Message",
    "Mission",
    "Project",
    "RefreshToken",
    "SearchHistory",
    "SimulationEvent",
    "SimulationRun",
    "SpaceObject",
    "User",
    "Vehicle",
    "VehicleComponent",
]

# Tables intentionally not yet defined, asserted by tests so that adding one
# without updating the contract fails loudly.
DEFERRED_TABLES = ("vehicle_stages", "telemetry_points")
