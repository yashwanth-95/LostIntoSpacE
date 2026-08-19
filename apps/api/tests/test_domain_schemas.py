"""Schema-level contract and security tests. No database, no mocking.

These are the highest-value tests for Phases 6-12: almost every security
property of the new endpoints is enforced by a Pydantic model
(`extra="forbid"` blocking privilege escalation, Literals blocking bad enums,
`ge`/`le` blocking impossible numbers), and all of that is testable with no
PostgreSQL running.
"""

import uuid

import pytest
from pydantic import ValidationError

from src.schemas.common import MAX_PAGE_SIZE, PaginationParams, pagination_meta
from src.schemas.conversation import ConversationCreate, ConversationUpdate, MessageCreate
from src.schemas.learning import ProgressUpdate, ProgressUpsert
from src.schemas.mission import MissionCreate, MissionUpdate
from src.schemas.project import ProjectCreate, ProjectUpdate
from src.schemas.user import PreferencesUpdate, UserProfileUpdate
from src.schemas.vehicle import VehicleComponentCreate, VehicleCreate, VehicleUpdate

# ---------- privilege escalation / mass assignment ----------

# Every one of these would be a real vulnerability if the schema silently
# dropped it instead of rejecting the request.
ESCALATION_ATTEMPTS = [
    (UserProfileUpdate, {"role": "admin"}, "self-promotion to admin"),
    (UserProfileUpdate, {"is_active": True}, "reactivating a disabled account"),
    (UserProfileUpdate, {"password_hash": "x"}, "overwriting the password hash"),
    (UserProfileUpdate, {"id": str(uuid.uuid4())}, "changing own user id"),
    (ProjectUpdate, {"user_id": str(uuid.uuid4())}, "reassigning project ownership"),
    (ProjectUpdate, {"id": str(uuid.uuid4())}, "changing project id"),
    (ProjectUpdate, {"deleted_at": None}, "un-deleting via PATCH"),
    (MissionUpdate, {"project_id": str(uuid.uuid4())}, "moving mission to another project"),
    (VehicleUpdate, {"mission_id": str(uuid.uuid4())}, "moving vehicle to another mission"),
    (VehicleUpdate, {"is_valid": True}, "faking validation state"),
    (VehicleUpdate, {"stability_margin": 99.0}, "faking a derived physics value"),
    (VehicleUpdate, {"total_mass_kg": 1.0}, "faking a derived mass"),
    (ConversationUpdate, {"user_id": str(uuid.uuid4())}, "reassigning a conversation"),
]


@pytest.mark.parametrize(("schema", "payload", "description"), ESCALATION_ATTEMPTS)
def test_forbidden_fields_are_rejected_not_ignored(schema, payload, description) -> None:
    """extra='forbid' turns these into 422s. Pydantic's DEFAULT would silently
    drop them and return 200, making the attempt look successful."""
    with pytest.raises(ValidationError):
        schema(**payload)


# ---------- enum validation ----------


def test_project_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        ProjectCreate(name="x", status="totally-made-up")


def test_project_accepts_every_contracted_status() -> None:
    for status in ("draft", "active", "completed", "archived"):
        assert ProjectCreate(name="x", status=status).status == status


def test_mission_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        MissionCreate(project_id=uuid.uuid4(), name="x", status="launched")


def test_component_rejects_unknown_type() -> None:
    with pytest.raises(ValidationError):
        VehicleComponentCreate(component_type="warp_core", mass_kg=1, position={}, dimensions={})


def test_component_accepts_every_contracted_type() -> None:
    for part in ("nose", "body", "fins", "engine", "payload", "recovery", "avionics"):
        component = VehicleComponentCreate(
            component_type=part, mass_kg=1, position={}, dimensions={}
        )
        assert component.component_type == part


def test_message_rejects_unknown_role() -> None:
    with pytest.raises(ValidationError):
        MessageCreate(role="root", content="hi")


def test_conversation_rejects_unknown_context_type() -> None:
    with pytest.raises(ValidationError):
        ConversationCreate(context_type="jailbreak")


# ---------- physical / numeric bounds ----------


def test_component_rejects_negative_mass() -> None:
    """Matches the ck_vehicle_components_mass_non_negative DB CHECK - rejected
    at the edge so it never becomes an opaque IntegrityError."""
    with pytest.raises(ValidationError):
        VehicleComponentCreate(component_type="nose", mass_kg=-1.0, position={}, dimensions={})


def test_component_allows_zero_mass() -> None:
    # >= 0, not > 0: a massless reference marker is legitimate.
    assert (
        VehicleComponentCreate(component_type="nose", mass_kg=0, position={}, dimensions={}).mass_kg
        == 0
    )


def test_vehicle_rejects_non_positive_height() -> None:
    for bad_height in (0, -1.5):
        with pytest.raises(ValidationError):
            VehicleCreate(mission_id=uuid.uuid4(), name="v", total_height_m=bad_height)


def test_progress_percent_must_be_0_to_100() -> None:
    for bad in (-1, 101, 1000):
        with pytest.raises(ValidationError):
            ProgressUpsert(lesson_id=uuid.uuid4(), progress_percent=bad)
    for good in (0, 50, 100):
        upsert = ProgressUpsert(lesson_id=uuid.uuid4(), progress_percent=good)
        assert upsert.progress_percent == good


def test_progress_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        ProgressUpdate(status="mastered")


# ---------- PATCH semantics ----------


def test_changed_fields_omits_unset_fields() -> None:
    """PATCH must not overwrite fields the client didn't send."""
    assert ProjectUpdate(name="new").changed_fields() == {"name": "new"}


def test_changed_fields_keeps_explicit_nulls() -> None:
    """Explicit null means 'clear this', which is different from omitting it -
    exclude_unset preserves that distinction."""
    changes = ProjectUpdate(description=None).changed_fields()
    assert changes == {"description": None}


# ---------- pagination ----------


def test_pagination_offset_and_limit() -> None:
    assert PaginationParams(page=1, per_page=20).offset == 0
    assert PaginationParams(page=3, per_page=20).offset == 40
    assert PaginationParams(page=2, per_page=50).limit == 50


def test_pagination_rejects_out_of_range() -> None:
    for bad in ({"page": 0}, {"page": -1}, {"per_page": 0}, {"per_page": MAX_PAGE_SIZE + 1}):
        with pytest.raises(ValidationError):
            PaginationParams(**bad)


def test_pagination_meta_matches_documented_envelope() -> None:
    """docs/api/API.md publishes exactly {page, per_page, total}."""
    meta = pagination_meta(PaginationParams(page=2, per_page=10), total=57)
    assert meta == {"page": 2, "per_page": 10, "total": 57}


# ---------- preferences bounds ----------


def test_preferences_accepts_flat_object() -> None:
    prefs = PreferencesUpdate(preferences={"theme": "dark", "units": "metric"}).preferences
    assert prefs["theme"] == "dark"


def test_preferences_allows_one_level_of_nesting() -> None:
    assert PreferencesUpdate(preferences={"panels": ["a", "b"]}).preferences["panels"] == ["a", "b"]


def test_preferences_rejects_deep_nesting() -> None:
    with pytest.raises(ValidationError, match="nested too deeply"):
        PreferencesUpdate(preferences={"a": {"b": {"c": 1}}})


def test_preferences_rejects_bad_key_characters() -> None:
    with pytest.raises(ValidationError):
        PreferencesUpdate(preferences={"has spaces": 1})


def test_preferences_rejects_too_many_keys() -> None:
    with pytest.raises(ValidationError, match="preference keys"):
        PreferencesUpdate(preferences={f"key_{i}": i for i in range(200)})


def test_preferences_rejects_oversized_payload() -> None:
    """Key count alone isn't enough - a few enormous values must also fail."""
    with pytest.raises(ValidationError, match="bytes"):
        PreferencesUpdate(preferences={"blob": "x" * 20_000})
