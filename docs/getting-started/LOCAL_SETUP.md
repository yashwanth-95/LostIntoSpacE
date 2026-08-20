# Local Setup

Every command here was run against this repository. Nothing is aspirational.

**Prerequisites:** Python 3.11+, Node.js 18+, PostgreSQL 13+.

If you only want to see the product work, steps 1–3 and 6–7 are enough: the
rocket builder, the simulation, mission control, search and the AI assistant all
run with **no database**. The database adds persistence and the object
catalogue.

---

## 1. Clone and configure

```bash
git clone https://github.com/yashwanth-95/LostIntoSpacE.git
cd LostIntoSpacE
cp .env.example .env
```

`.env` is git-ignored. Nothing in it is ever committed.

## 2. Python environment

Two dependency manifests exist, on purpose: `apps/api/pyproject.toml` (the
backend, Python 3.11+) and the root `pyproject.toml` (the data/search/AI trees,
which keep a 3.9 floor). Install both into one environment.

```bash
python3 -m venv .venv
source .venv/bin/activate

pip install -e "apps/api[dev]"
pip install "httpx>=0.27" respx numpy pydantic
```

Verify:

```bash
python -c "import fastapi, sqlalchemy, httpx, numpy; print('ok')"
```

## 3. Start the backend

```bash
cd apps/api
PYTHONPATH=$PWD python -m uvicorn src.main:app --reload --port 8000
```

Check it:

```bash
curl localhost:8000/api/v1/health
curl localhost:8000/api/v1/health/engines
```

`/health/engines` should report `simulation`, `search` and `ai` all available.
If one is `false`, its `reason` names the missing import — that is almost always
a dependency from step 2.

The API deliberately starts **without** a database. `/health` answers, and so do
simulation, search and AI.

## 4. PostgreSQL

Create the role and both databases. The password is passed in at run time, so
the script holds no credentials and is safe to commit:

```bash
psql -h 127.0.0.1 -U postgres -d postgres \
     -v app_password="'choose-a-password-here'" \
     -f database/scripts/setup_local_db.sql
```

The nested quoting on `-v` is required: psql substitutes the value literally, so
it must carry its own single quotes.

Then put that same password into `.env`:

```
DATABASE_URL=postgresql+asyncpg://lostintospace:choose-a-password-here@localhost:5432/lostintospace
```

> The shipped default is literally `password`. Leaving it produces
> `password authentication failed for user "lostintospace"`, and every
> database-backed endpoint returns `503 DATABASE_UNAVAILABLE`.

## 5. Migrations and seed data

```bash
cd database
alembic upgrade head
cd ..
python database/seeds/seed_all.py
```

Both the application and Alembic use asyncpg — one driver, no URL rewriting.

Confirm the connection:

```bash
curl localhost:8000/api/v1/health/ready
# {"status":"success","data":{"state":"ready","database":"reachable"}}
```

## 6. Frontend

```bash
cd apps/web
npm install
npm run dev
```

Open <http://localhost:3000>.

The dev server proxies `/api` to port 8000, so requests are same-origin and CORS
is not involved. Leave `VITE_API_URL` unset unless you are serving the frontend
from a different origin — in which case add that origin to `CORS_ORIGINS`.

## 7. Verify it works

```bash
# From apps/web, with the backend running:
npx tsx e2e/journey.mjs
```

This drives the whole product loop — catalogue, builder, launch, Python
simulation, telemetry, staging, orbit, failure, AI explanation, search — and
prints 56 checks. It is the fastest way to confirm a setup is sound.

Steps 4–5 skipped? Two checks report `HTTP 503` for the database-backed
endpoints and still pass, because that is the documented state.

---

## Running the tests

```bash
# Data, search and AI                (repository root)
pytest

# Backend                            (apps/api)
cd apps/api && PYTHONPATH=$PWD pytest

# Python simulation                  (repository root)
pytest simulation/tests

# TypeScript simulation engine
cd packages/simulation-engine && npx vitest run

# Frontend
cd apps/web && npx vitest run

# End-to-end (needs the API running)
cd apps/web && npx tsx e2e/journey.mjs
```

Expected: 1419, 291, 106, 570, 27, and 56 checks respectively.

Backend tests that need a live database skip unless `TEST_DATABASE_URL` is set.
To run them, uncomment it in `.env` — it points at `lostintospace_test`, which
step 4 created, so tests can never touch development data.

---

## Troubleshooting

**`Failed to resolve import "./App"`** — historical. `App.tsx` did not exist
before the first-prototype integration. If you see this, you are on a commit
before `42c6d05`.

**`Could not reach the API. Is the backend running on port 8000?`** — the
frontend is up but the backend is not. Step 3.

**`503 DATABASE_UNAVAILABLE`** — expected without steps 4–5. Explore, Catalog,
sign-in and the workspace need the database; nothing else does.

**`/health/engines` reports an engine unavailable** — a missing Python
dependency. The `reason` field names the module. Step 2.

**A simulation returns 504** — runs are capped at 30 s wall clock. Shorten the
mission or coarsen the timestep; `GET /api/v1/simulations/limits` publishes
every cap.

**`npm run build` fails on an engine import** — `vite.config.ts` must keep the
`@lostintospace/simulation-engine` alias in step with `tsconfig.json`'s `paths`.
TypeScript resolves those; Rollup does not, unless told.

**Port already in use** — `--port` on uvicorn, `--port` on vite. Change
`CORS_ORIGINS` if you move the frontend.
