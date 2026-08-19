"""Model-level tests that need no database server.

Models are compiled to PostgreSQL DDL with a dialect object rather than a
connection, so these assertions run anywhere. They verify the contract in
docs/backend/DATABASE_CONTRACT.md is actually expressed in the models.
"""

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from src.models import DEFERRED_TABLES, Base

PG = postgresql.dialect()

EXPECTED_TABLES = {
    "conversations",
    "failure_events",
    "learning_progress",
    "lessons",
    "messages",
    "missions",
    "projects",
    "refresh_tokens",
    "search_history",
    "simulation_events",
    "simulation_runs",
    "space_objects",
    "users",
    "vehicle_components",
    "vehicles",
}


def ddl(table_name: str) -> str:
    return str(CreateTable(Base.metadata.tables[table_name]).compile(dialect=PG))


def test_exactly_the_approved_tables_are_defined() -> None:
    """15 of the 17 contracted tables. Guards against a table being added
    without going through the contract."""
    assert set(Base.metadata.tables) == EXPECTED_TABLES


@pytest.mark.parametrize("table", DEFERRED_TABLES)
def test_blocked_tables_are_not_defined(table: str) -> None:
    """vehicle_stages and telemetry_points are blocked pending P3 sign-off
    (DECISION_LOG #24, #25, #26). Defining either would bake an unresolved
    contract question into a migration."""
    assert table not in Base.metadata.tables


def test_vehicle_components_has_no_stage_id() -> None:
    """stage_id is an FK into the blocked vehicle_stages table, so it defers
    with it. Components remain usable: vehicle_id is their real ownership link."""
    assert "stage_id" not in Base.metadata.tables["vehicle_components"].columns


def test_every_table_has_created_at() -> None:
    for name, table in Base.metadata.tables.items():
        assert "created_at" in table.columns, f"{name} is missing created_at"


def test_all_timestamps_are_timezone_aware() -> None:
    """TIMESTAMPTZ everywhere, never TIMESTAMP - mixed timezone handling in a
    launch-time application is a real correctness hazard."""
    for name, table in Base.metadata.tables.items():
        for col in table.columns:
            if isinstance(col.type, postgresql.TIMESTAMP) or col.type.__class__.__name__ in (
                "DateTime",
                "TIMESTAMP",
            ):
                assert getattr(col.type, "timezone", False), f"{name}.{col.name} is not TIMESTAMPTZ"


def test_projects_soft_delete_and_partial_index() -> None:
    """SD-8: projects is the only soft-deleted table, because DELETE cascades
    four levels down to simulation results."""
    assert "deleted_at" in Base.metadata.tables["projects"].columns
    idx = {i.name: i for i in Base.metadata.tables["projects"].indexes}
    assert "idx_projects_user_active" in idx
    where = idx["idx_projects_user_active"].dialect_options["postgresql"]["where"]
    assert "deleted_at IS NULL" in str(where)


def test_projects_is_the_only_soft_deleted_table() -> None:
    soft_deleted = {n for n, t in Base.metadata.tables.items() if "deleted_at" in t.columns}
    assert soft_deleted == {"projects"}


def test_vehicle_mission_is_unique_enforcing_one_to_one() -> None:
    """The 1:1 that GET /missions/{mid}/vehicle assumes must be enforced, not
    merely documented - a plain index would allow two vehicles per mission."""
    assert "UNIQUE" in ddl("vehicles")
    col = Base.metadata.tables["vehicles"].columns["mission_id"]
    assert col.unique is True


def test_simulation_run_vehicle_fk_restricts_delete() -> None:
    """Deleting a vehicle with recorded flight history must be blocked, not
    cascade into destroying results."""
    fks = {fk.column.table.name: fk for fk in Base.metadata.tables["simulation_runs"].foreign_keys}
    assert fks["vehicles"].ondelete == "RESTRICT"
    assert fks["missions"].ondelete == "CASCADE"


def test_stage_less_components_survive_stage_deletion() -> None:
    """parent_id uses SET NULL so removing an assembly does not delete children."""
    fks = {fk.parent.name: fk for fk in Base.metadata.tables["vehicle_components"].foreign_keys}
    assert fks["parent_id"].ondelete == "SET NULL"
    assert fks["vehicle_id"].ondelete == "CASCADE"


def test_messages_have_no_user_id() -> None:
    """Ownership is inherited through conversation_id (DATABASE_CONTRACT §2.6).
    A denormalized owner column could contradict its parent."""
    assert "user_id" not in Base.metadata.tables["messages"].columns


def test_search_history_user_is_nullable_for_anonymous_search() -> None:
    """API.md marks /search auth as Optional."""
    assert Base.metadata.tables["search_history"].columns["user_id"].nullable is True


def test_learning_progress_upsert_key_and_consistency_checks() -> None:
    table = Base.metadata.tables["learning_progress"]
    unique_indexes = {i.name for i in table.indexes if i.unique}
    assert "uq_progress_user_lesson" in unique_indexes
    # Names are expanded by the naming convention in core.database.base:
    # "status_valid" -> "ck_learning_progress_status_valid".
    checks = {c.name for c in table.constraints if c.__class__.__name__ == "CheckConstraint"}
    assert {
        "ck_learning_progress_status_valid",
        "ck_learning_progress_percent_range",
        "ck_learning_progress_completed_consistent",
    } <= checks


def test_enum_columns_have_check_constraints() -> None:
    """Enums are VARCHAR + CHECK, not PostgreSQL ENUM types: a CHECK is a
    one-line drop-and-recreate, ALTER TYPE is not."""
    # Constraint names below are the convention-expanded forms
    # (ck_<table>_<name>), which is what actually lands in PostgreSQL.
    expected = {
        "users": "ck_users_role_valid",
        "projects": "ck_projects_status_valid",
        "missions": "ck_missions_status_valid",
        "simulation_runs": "ck_simulation_runs_status_valid",
        "simulation_events": "ck_simulation_events_event_type_valid",
        "messages": "ck_messages_role_valid",
        "conversations": "ck_conversations_context_type_valid",
    }
    for table_name, constraint in expected.items():
        checks = {
            c.name
            for c in Base.metadata.tables[table_name].constraints
            if c.__class__.__name__ == "CheckConstraint"
        }
        assert constraint in checks, f"{table_name} missing CHECK {constraint}"


def test_simulation_event_vocabulary_matches_simulation_md() -> None:
    """SIMULATION.md is the authority; DATABASE.md carried a stale list with
    `landing` and without `liftoff`/`supersonic` (KNOWN_ISSUES P-9)."""
    sql = ddl("simulation_events")
    for event in (
        "ignition",
        "liftoff",
        "max_q",
        "meco",
        "staging",
        "apogee",
        "supersonic",
        "impact",
    ):
        assert f"'{event}'" in sql, f"{event} missing from event_type CHECK"
    assert "landing" not in sql
    assert "failure" in sql  # failure_* family allowed by LIKE


def test_mass_cannot_be_negative() -> None:
    """Physical impossibility belongs in the database - 'never trust frontend
    validation' means the last line of defence is here."""
    assert "mass_kg >= 0" in ddl("vehicle_components")


def test_full_text_search_vectors_are_generated_columns() -> None:
    """Generated, not trigger-maintained: no trigger function to keep in sync."""
    for table in ("space_objects", "lessons"):
        sql = ddl(table)
        assert "GENERATED ALWAYS AS" in sql, f"{table}.search_vector is not generated"
        assert "STORED" in sql


def test_seed_idempotency_index_exists() -> None:
    """Partial unique on (source, source_id) is what makes re-running a seed
    loader an upsert rather than a duplicate insert."""
    idx = {i.name: i for i in Base.metadata.tables["space_objects"].indexes}
    assert idx["idx_spaceobj_source"].unique is True


def test_all_tables_compile_to_postgresql_ddl() -> None:
    """Catches dialect-level mistakes (bad server_default, unsupported type)
    without needing a server."""
    for name in Base.metadata.tables:
        assert ddl(name).strip().startswith("CREATE TABLE")
