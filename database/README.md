<![CDATA[# Database — `database/`

## Owner: P2 (Backend / Database)

> Full setup, verification, and troubleshooting: **[`docs/backend/DATABASE_SETUP.md`](../docs/backend/DATABASE_SETUP.md)**.
> Schema authority: **[`docs/backend/DATABASE_CONTRACT.md`](../docs/backend/DATABASE_CONTRACT.md)**.

## Structure
- `alembic.ini` — Alembic config. Contains **no** database URL and no credentials; `migrations/env.py` reads `DATABASE_URL` from the environment.
- `migrations/` — Alembic revisions. All hand-written (see Rules).
- `seeds/` — **Loader scripts only.** Idempotent Python scripts that read seed *content* and upsert it into Postgres (space objects, lessons, demo data). P2 owns this infrastructure.
- `scripts/` — DB admin scripts (reset, backup, etc.)

## Ownership Boundary: `database/seeds/` vs `data/seeds/`
This directory does **not** own or author seed content. The content itself (space object records, lesson text, fallback datasets) is P4's responsibility and lives in `data/seeds/` and `data/fallback/` (see `data/README.md`). `database/seeds/` scripts read from there and load it into Postgres — they contain loading/upsert logic, not the data. This split exists so content and loading logic don't get duplicated or drift apart between P2 and P4. See `docs/decisions/DECISION_LOG.md` #18.

## Commands

Run from this directory, with the `apps/api` virtualenv active (that is where `alembic` and the models live):

```bash
source ../apps/api/venv/Scripts/activate   # Windows Git Bash
source ../apps/api/venv/bin/activate       # Linux/macOS

alembic upgrade head          # apply everything
alembic current               # what's applied now
alembic history               # the revision chain
alembic downgrade -1          # roll back one revision
alembic upgrade head --sql    # print SQL, no server needed

python seeds/seed_all.py      # structure only until P4 delivers content
```

## Current state

7 revisions, `0001_baseline` → `0007_conversations_messages`, creating **15 tables**.

`vehicle_stages`, `telemetry_points`, and `vehicle_components.stage_id` are **deliberately not created** — their contracts depend on P3 decisions that are still open (`DECISION_LOG` #24, #25, #26). They land together in `0008`. Tests assert they stay absent.

## Rules

- **Never edit a released migration.** Create a new one.
- **Always test on a fresh database** — `upgrade head` then `downgrade base`.
- **Autogenerate output is a draft, not an answer.** It does not reliably detect CHECK constraints, partial indexes, or server defaults. Every revision here was written by hand for that reason; read and correct anything `--autogenerate` produces.
- **Pass CHECK constraint names in short form** (`name="role_valid"`, not `name="ck_users_role_valid"`). The naming convention prefixes them, so a pre-prefixed name becomes `ck_users_ck_users_role_valid` and stops matching the model. A test enforces this — the bug was real, not hypothetical.
- **Both the app and Alembic use `asyncpg`.** There is no psycopg2 in this project; the usual async-app/sync-Alembic split was deliberately eliminated. See the note at the top of `migrations/env.py` before "fixing" it.
- **Seed loaders must be idempotent** — safe to run repeatedly.
]]>
