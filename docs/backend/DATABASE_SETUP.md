# Database Setup

**Phase:** 4 — Database Foundation
**Owner:** Person 2

How to get a working LostIntoSpacE database locally, and how to verify it.

---

## Requirements

**PostgreSQL 13 or newer.** The schema depends on two core features:

- `gen_random_uuid()` — built into core since **PG 13** (no `pgcrypto` extension needed)
- `STORED` generated columns — since **PG 12**, used for the full-text `search_vector` columns

`ARCHITECTURE.md` targets PostgreSQL 15+, which comfortably satisfies both. Migration `0001_baseline` checks the server version and fails with a clear message rather than letting a later migration break in a confusing way.

---

## Setup

```bash
# 1. Create the database
createdb lostintospace

# 2. Point the app at it (repo root .env, copied from .env.example)
#    DATABASE_URL=postgresql+asyncpg://<user>:<password>@localhost:5432/lostintospace
cp .env.example .env      # then edit DATABASE_URL

# 3. Apply migrations
cd database
alembic upgrade head

# 4. Seed (structure only in Phase 4 — see "Seeding" below)
python seeds/seed_all.py
```

The `apps/api` virtualenv must be active for steps 3–4: `alembic` and the models both come from it.

```bash
source apps/api/venv/Scripts/activate   # Windows Git Bash
source apps/api/venv/bin/activate       # Linux/macOS
```

### Credentials

`DATABASE_URL` is read from the environment only. `alembic.ini` contains **no** URL and no credentials — `migrations/env.py` pulls it from the app's `Settings`. Nothing about your database is committed to git.

---

## Migrations

```bash
cd database

alembic upgrade head          # apply everything
alembic current               # what's applied now
alembic history               # the revision chain
alembic downgrade -1          # roll back one revision
alembic upgrade head --sql    # print SQL without touching a database
```

`alembic upgrade head --sql` is useful for review and works with **no server running** — it is how the Phase 4 schema was verified on a machine without PostgreSQL.

### Single driver, deliberately

Both the application and the migrations run on **`asyncpg`**. The more commonly documented setup is asyncpg for the app plus `psycopg2` for Alembic, and `KNOWN_ISSUES.md` D-5 originally planned for that split. Using Alembic's native async support instead removes the split entirely: one dependency, no URL rewriting between drivers, and no chance of the two URLs being "helpfully" reconciled later and breaking one of them.

### Rules

- **Never edit a released migration.** Create a new one.
- **Always test on a fresh database** before committing (`createdb` a scratch DB, `upgrade head`, `downgrade base`).
- **Autogenerate output is a draft.** `alembic revision --autogenerate` does not reliably detect CHECK constraints, partial indexes, or server defaults. Read and correct every generated revision by hand. All Phase 4 migrations were written by hand for this reason.
- **CHECK constraint names must be short form.** The naming convention is `ck_%(table_name)s_%(constraint_name)s`, so passing `name="ck_users_role_valid"` produces `ck_users_ck_users_role_valid`. Pass `name="role_valid"`. A test enforces this (`tests/test_migrations.py::test_check_constraint_names_are_short_form`) — it exists because this exact bug was introduced and caught during Phase 4.

---

## Current schema

15 tables, from `docs/backend/DATABASE_CONTRACT.md` §2.

| Revision | Tables |
|---|---|
| `0001_baseline` | *(none — version guard)* |
| `0002_users_and_refresh_tokens` | `users`, `refresh_tokens` |
| `0003_project_spine` | `projects`, `missions`, `vehicles`, `vehicle_components` |
| `0004_simulation_results` | `simulation_runs`, `simulation_events`, `failure_events` |
| `0005_catalogs` | `space_objects`, `lessons`, `search_history` |
| `0006_learning_progress` | `learning_progress` |
| `0007_conversations_messages` | `conversations`, `messages` |

### Not yet created — blocked on P3

| Table | Blocked by |
|---|---|
| `vehicle_stages` | Mass representation (`DECISION_LOG` #25) and propulsion field authority (#26) are unresolved |
| `telemetry_points` | Storage representation — flat `float8` vs JSONB, and whether attitude persists (#24) |
| `vehicle_components.stage_id` | A foreign key *into* `vehicle_stages`, so it cannot exist before that table |

These land together in migration `0008` once P3 answers. `vehicle_components` is fully usable without `stage_id`: `vehicle_id` is a component's real ownership link.

---

## Test database

Tests that need a live server read **`TEST_DATABASE_URL`**, never `DATABASE_URL`, so a test run cannot touch development data even by misconfiguration. When `TEST_DATABASE_URL` is unset those tests **skip** rather than fail:

```bash
createdb lostintospace_test
export TEST_DATABASE_URL="postgresql+asyncpg://<user>:<password>@localhost:5432/lostintospace_test"
cd apps/api && python -m pytest
```

Most of the suite needs no database at all — models are compiled to PostgreSQL DDL with a dialect object rather than a connection, so `pytest` is green on a machine with no PostgreSQL installed.

---

## Seeding

`database/seeds/` holds **loading logic only**. The seed *content* — space object records, lesson text, fallback datasets — is authored by P4 in `data/seeds/` and `data/fallback/` (`DECISION_LOG` #18).

Phase 4 ships the structure, not the loaders: there is no content to load yet. `seed_all.py` reports each seeder as skipped while `data/seeds/` is empty, and raises `NotImplementedError` if content appears without a loader — so seeding can never silently no-op once P4 delivers.

Every loader must be **idempotent**. For `space_objects` the partial unique index on `(source, source_id)` is what turns a re-run into an upsert instead of duplicate rows.

---

## Verification

What was verified for Phase 4 **without** a PostgreSQL server:

- `alembic history` / `heads` — one linear chain, single head
- `alembic upgrade head --sql` — all 7 revisions emit valid DDL end to end
- 40 tests pass, including model↔migration consistency checks
- Generated DDL inspected for: partial indexes, `DESC` indexes, GIN indexes, `GENERATED ALWAYS AS … STORED`, `ON DELETE RESTRICT`/`SET NULL`, and every CHECK constraint
- Migration and model constraint names compared programmatically — exact match, 14/14
- App boots and `/api/v1/health` returns 200 with no database running (the engine is created lazily)

**Not yet verified — requires a real server.** Run these once PostgreSQL is available:

```bash
createdb lostintospace_verify
DATABASE_URL="postgresql+asyncpg://<user>:<pw>@localhost:5432/lostintospace_verify" \
  alembic upgrade head        # must succeed on a fresh database
DATABASE_URL="..." alembic downgrade base   # must cleanly reverse
dropdb lostintospace_verify
```

Until that runs, treat the migrations as reviewed-and-consistent rather than proven-to-apply.
