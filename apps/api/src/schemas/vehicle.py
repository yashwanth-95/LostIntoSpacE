"""Vehicle and component schemas - the P2/P3 serialization boundary.

TERMINOLOGY (DECISION_LOG #20): the entity is VEHICLE everywhere in the
backend, database, and API. The UI may render it as "Rocket". No field is
renamed for P3's convenience and none of P3's names are renamed for ours.

FIELD NAMES ARE P3's CONTRACT. `component_type`, `mass_kg`, `position`,
`dimensions`, `properties` come from docs/architecture/DATABASE.md and
docs/rkt_spec/RKT_SPEC.md and are passed through verbatim. Renaming any of
them would silently break the builder's save/load round-trip.

READ-ONLY DERIVED FIELDS. `total_mass_kg`, `cg_position`, `cp_position`,
`stability_margin`, `is_valid`, `validation_errors` are caches of values P3's
engine computes - they appear in responses but are rejected in requests
(extra="forbid"). The backend does not compute them: that is physics, and
DATABASE_CONTRACT.md §4.10 is explicit that P3 owns it. Until P3 wires in a
recompute call these stay null/false, which is honest rather than wrong.

STAGES ARE ABSENT. `vehicle_stages` is still blocked pending P3 sign-off on
SD-6 (mass semantics) and SD-7 (propulsion over-determination) - see
DECISION_LOG #25/#26. `VehicleComponent.stage_id` is an FK into that table so
it defers with it. Components remain fully usable: `vehicle_id` is their real
ownership link.
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# From docs/architecture/DATABASE.md's vehicle_components.component_type
# comment. Kept as a Literal so an unknown part type is a 422 rather than a
# row that no builder or simulation knows how to interpret.
ComponentType = Literal["nose", "body", "fins", "engine", "payload", "recovery", "avionics"]


class VehicleComponentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    component_type: ComponentType
    name: str | None = Field(default=None, max_length=100)
    # >= 0, matching the ck_vehicle_components_mass_non_negative DB CHECK.
    # A negative mass is physically impossible, so it is rejected at both ends.
    mass_kg: float = Field(ge=0)
    position: dict[str, Any]
    dimensions: dict[str, Any]
    properties: dict[str, Any] = Field(default_factory=dict)
    parent_id: UUID | None = None
    sort_order: int = Field(default=0, ge=0)


class VehicleComponentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    component_type: ComponentType | None = None
    name: str | None = Field(default=None, max_length=100)
    mass_kg: float | None = Field(default=None, ge=0)
    position: dict[str, Any] | None = None
    dimensions: dict[str, Any] | None = None
    properties: dict[str, Any] | None = None
    parent_id: UUID | None = None
    sort_order: int | None = Field(default=None, ge=0)

    def changed_fields(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True)


class VehicleComponentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    vehicle_id: UUID
    component_type: str
    name: str | None
    mass_kg: float
    position: dict[str, Any]
    dimensions: dict[str, Any]
    properties: dict[str, Any]
    parent_id: UUID | None
    sort_order: int
    created_at: datetime


class VehicleCreate(BaseModel):
    """A vehicle belongs to exactly one mission (1:1, UNIQUE on mission_id).

    `components` may be supplied inline so the builder can save a whole design
    in one request rather than N+1 round-trips.
    """

    model_config = ConfigDict(extra="forbid")

    mission_id: UUID
    name: str = Field(min_length=1, max_length=200)
    total_height_m: float | None = Field(default=None, gt=0)
    components: list[VehicleComponentCreate] = Field(default_factory=list)


class VehicleCreateNested(BaseModel):
    """Body for `POST /missions/{mission_id}/vehicle` - `mission_id` comes
    from the path, so it is absent here."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    total_height_m: float | None = Field(default=None, gt=0)
    components: list[VehicleComponentCreate] = Field(default_factory=list)


class VehicleUpdate(BaseModel):
    """`mission_id` is deliberately absent: moving a vehicle between missions
    would break the 1:1 UNIQUE and is not a builder operation."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    total_height_m: float | None = Field(default=None, gt=0)

    def changed_fields(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True)


class VehicleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    mission_id: UUID
    name: str
    # Derived/read-only - see module docstring.
    total_mass_kg: float | None
    total_height_m: float | None
    cg_position: dict[str, Any] | None
    cp_position: dict[str, Any] | None
    stability_margin: float | None
    is_valid: bool
    validation_errors: list[Any]
    created_at: datetime
    updated_at: datetime


class VehicleDetailResponse(VehicleResponse):
    """Vehicle plus its components - the save/load payload P3's builder round-trips."""

    components: list[VehicleComponentResponse] = Field(default_factory=list)
