"""Migration consistency checks that need no database server.

These migrations are hand-written (autogenerate needs a live connection, and
per DATABASE_CONTRACT.md §10 it does not reliably detect CHECK constraints or
partial indexes anyway). The risk that creates is drift: a model gains a table
or index and the migration is forgotten. These tests close that gap by parsing
the revision files and comparing against Base.metadata.

They do NOT prove the migrations run. That requires PostgreSQL — see
docs/backend/DATABASE_SETUP.md for the verification command.
"""

import re
from pathlib import Path

import pytest

from src.models import DEFERRED_TABLES, Base

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "database" / "migrations" / "versions"

CREATE_TABLE_RE = re.compile(r'op\.create_table\(\s*"([^"]+)"')
DROP_TABLE_RE = re.compile(r'op\.drop_table\(\s*"([^"]+)"')
CREATE_INDEX_RE = re.compile(r'op\.create_index\(\s*"([^"]+)"')
REVISION_RE = re.compile(r'^revision: str = "([^"]+)"', re.M)
DOWN_REVISION_RE = re.compile(r"^down_revision: str \| None = (?:\"([^\"]+)\"|None)", re.M)


def migration_files() -> list[Path]:
    return sorted(p for p in MIGRATIONS_DIR.glob("*.py") if not p.name.startswith("__"))


def all_migration_source() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in migration_files())


def test_migrations_directory_exists_and_is_populated() -> None:
    assert MIGRATIONS_DIR.is_dir(), f"missing {MIGRATIONS_DIR}"
    assert migration_files(), "no migration revisions found"


def test_revision_chain_is_linear_and_rooted() -> None:
    """One root, no branches, no gaps - a broken chain fails at deploy time,
    which is the worst time to find out."""
    revisions: dict[str, str | None] = {}
    for path in migration_files():
        src = path.read_text(encoding="utf-8")
        rev = REVISION_RE.search(src)
        assert rev, f"{path.name} has no revision id"
        down_match = DOWN_REVISION_RE.search(src)
        assert down_match, f"{path.name} has no down_revision"
        revisions[rev.group(1)] = down_match.group(1)

    roots = [r for r, down in revisions.items() if down is None]
    assert len(roots) == 1, f"expected exactly one root revision, got {roots}"

    # Every down_revision must name a revision that exists.
    for rev, down in revisions.items():
        if down is not None:
            assert down in revisions, f"{rev} points at unknown down_revision {down}"

    # No two revisions may share a parent (that would be a branch).
    parents = [d for d in revisions.values() if d is not None]
    assert len(parents) == len(set(parents)), "revision chain branches"

    # Walking from the root must reach every revision.
    children = {down: rev for rev, down in revisions.items() if down is not None}
    seen, cursor = 1, roots[0]
    while cursor in children:
        cursor = children[cursor]
        seen += 1
    assert seen == len(revisions), "revision chain is not fully connected"


def test_every_model_table_is_created_by_a_migration() -> None:
    """The drift guard: add a model without a migration and this fails."""
    created = set(CREATE_TABLE_RE.findall(all_migration_source()))
    missing = set(Base.metadata.tables) - created
    assert not missing, f"tables in models but never created by a migration: {sorted(missing)}"


def test_migrations_create_no_table_outside_the_models() -> None:
    created = set(CREATE_TABLE_RE.findall(all_migration_source()))
    extra = created - set(Base.metadata.tables)
    assert not extra, f"tables created by migrations but absent from models: {sorted(extra)}"


@pytest.mark.parametrize("table", DEFERRED_TABLES)
def test_blocked_tables_are_not_created_by_any_migration(table: str) -> None:
    """vehicle_stages / telemetry_points must not sneak in before P3 signs off."""
    created = set(CREATE_TABLE_RE.findall(all_migration_source()))
    assert table not in created


def test_every_model_index_is_created_by_a_migration() -> None:
    created = set(CREATE_INDEX_RE.findall(all_migration_source()))
    model_indexes = {ix.name for t in Base.metadata.tables.values() for ix in t.indexes}
    missing = model_indexes - created
    assert not missing, f"indexes in models but not in any migration: {sorted(missing)}"


def test_every_created_table_is_dropped_in_a_downgrade() -> None:
    """A downgrade that forgets a table leaves the database un-rollbackable."""
    src = all_migration_source()
    created = set(CREATE_TABLE_RE.findall(src))
    dropped = set(DROP_TABLE_RE.findall(src))
    assert created == dropped, f"asymmetric up/down: {sorted(created ^ dropped)}"


def test_check_constraint_names_are_short_form() -> None:
    """Regression guard.

    The `ck` naming convention is `ck_%(table_name)s_%(constraint_name)s`, so a
    migration that passes an already-prefixed name produces a double-prefixed
    constraint (`ck_users_ck_users_role_valid`) that does not match the model.
    Migrations must pass the SHORT name and let the convention expand it, exactly
    as the models do. FK/PK/UQ conventions have no %(constraint_name)s token, so
    only CHECK constraints are affected.
    """
    table_names = "|".join(sorted(Base.metadata.tables, key=len, reverse=True))
    bad = re.findall(rf'name="ck_(?:{table_names})_[a-z_]+"', all_migration_source())
    assert not bad, (
        f"migrations use pre-prefixed CHECK names (will double-prefix): {sorted(set(bad))}"
    )


def test_check_constraint_names_match_the_models() -> None:
    """Every CHECK in the models must be created by a migration under the same
    name, so a hand-written migration cannot drift from the model it mirrors."""
    src = all_migration_source()
    for table_name, table in Base.metadata.tables.items():
        for constraint in table.constraints:
            if constraint.__class__.__name__ != "CheckConstraint":
                continue
            # Model name is convention-expanded (ck_<table>_<short>); the
            # migration carries the short form.
            short = constraint.name.removeprefix(f"ck_{table_name}_")
            assert f'name="{short}"' in src, (
                f"{table_name}: CHECK '{constraint.name}' has no migration "
                f'declaring name="{short}"'
            )


def test_migration_modules_are_importable() -> None:
    """Catches syntax errors without a database."""
    import importlib.util

    for path in migration_files():
        spec = importlib.util.spec_from_file_location(path.stem, path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert hasattr(module, "upgrade") and hasattr(module, "downgrade")
