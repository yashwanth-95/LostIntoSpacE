# Backend State

**Owner:** Person 2 (Backend / Database / Auth)
**Last audit:** 2026-08-18 (Checkpoint 0/1) · **Last updated:** 2026-08-19 (Phases 6-15)
**Branch audited:** `person/person-2-database` (clean, 2 commits: `267e0f3` "Initial commit", `c43e080` "Initial Architechture Setup")
**Remotes:** `origin` = sarathchandra-4543/LostIntoSpacE (fork), `upstream` = yashwanth-95/LostIntoSpacE

This document is the living record of what actually exists in the backend vs. what is designed/planned. Update it at every checkpoint. For problems, gaps, and risks, see [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) — this file is inventory and architecture, that one is the issues backlog.

---

## 1. Headline Finding

*(As of the original Checkpoint 0 audit, 2026-08-18. Superseded in part by Phase 2, §12 — kept as-is below for historical accuracy of what the audit found, with the update noted explicitly.)*

**At audit time, the entire repository was a documentation + directory scaffold. Zero application code existed anywhere** — not just in the backend. Every module directory (`apps/api/src/*`, `apps/web/src/*`, `simulation/*`, `scientific/*`, `ai/*`, `search/*`, `data/*`, `database/*`, `deployment/*`) contained only `.gitkeep` placeholder files. There were no `.py`, `.ts`, `.tsx`, `.json` (config), `.toml`, `.ini`, or `.yml` files anywhere except the two `.gitkeep`-adjacent root files (`.env.example`, `.gitignore`) and Markdown docs.

**Update (Phase 2, same day):** this is no longer true for `apps/api/` specifically — a real, tested, running FastAPI foundation now exists there (see §12). It is still true for every other module directory listed above (frontend, simulation, scientific, ai, search, data, database, deployment all remain scaffold-only).

What *does* exist beyond code is an unusually thorough and internally-consistent set of planning docs (architecture, DB schema, API contract, RKT file format, decision log) written by the team lead (`yashwanth-95`) in the second commit. This audit treats those docs as the design spec to build against, not as implemented fact.

This was good news for sequencing: there was no legacy code to reconcile, no migration debt, no conflicting implementations. The job was to build the first layer correctly, not to untangle anything — Phase 2 did exactly that for the backend foundation.

---

## 2. Current Architecture (as designed — the foundation layer is built as of Phase 2, §12; domain modules below are still design-only)

Source: `docs/architecture/ARCHITECTURE.md`, `apps/api/README.md`.

**Style:** Modular monolith. One FastAPI process, one Postgres database. No microservices for MVP (explicit rule, `DECISION_LOG.md` #10).

**Layering:**
```
Frontend (React/R3F) → API Layer (FastAPI) → Domain Services → Data Layer (Postgres/Redis) → External Sources (NASA/AI)
```

**Planned backend module boundaries** (`apps/api/src/`), each an independent sub-package with its own `router.py` + `service.py`:

| Module | Depends on | Notes |
|---|---|---|
| `core/` | — | config, db session, security, middleware, exceptions — shared kernel |
| `auth` | `database` | JWT issuance/verification, password hashing |
| `users` | `auth`, `database` | |
| `projects` | `auth`, `users` | |
| `missions` | `projects`, `vehicles` | |
| `vehicles` | `projects` | stages + components live under here |
| `simulation` (backend module) | `missions`, `vehicles` | thin wrapper — calls root `simulation/` engine as a **pure Python library import**, never re-implements physics |
| `space_data` | `database`, root `data/` | |
| `search` (backend module) | `space_data`, `learning` | intended to wrap root `search/` the same way `simulation` wraps its engine (see [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) §4 D-2/D-3 for the still-open ambiguity here) |
| `learning` | `database` | |
| `ai` (backend module) | `search`, `simulation` | wraps root `ai/` provider abstraction |
| `reports` | `simulation`, `missions` | |
| `models/` | — | all SQLAlchemy ORM models, cross-module |
| `schemas/` | — | all Pydantic request/response schemas, cross-module |

**Critical cross-team interface pattern:** three domains (`simulation`, `search`, `ai`) each have *two* homes — a root-level pure-library folder (owned by P3/P4) and a thin `apps/api/src/<name>/` wrapper (owned by P2, this role) that exposes it over HTTP and touches the DB. Backend must never duplicate physics/ranking/LLM logic inside its own module; it only orchestrates. `simulation/README.md` states this explicitly ("Prohibited Dependencies: NO database imports, NO API framework imports"); `search/README.md` and `ai/README.md` do not yet state the equivalent constraint — worth raising with P3/P4.

**Full designed DB schema** (13 tables) — see `docs/architecture/DATABASE.md` for exact DDL: `users`, `projects`, `missions`, `vehicles`, `vehicle_stages`, `vehicle_components`, `simulation_runs`, `telemetry_points`, `simulation_events`, `failure_events`, `space_objects`, `lessons`, `search_history`. All use UUID PKs except `telemetry_points` (BIGSERIAL — deliberate, high-volume time-series table). Relational FKs used throughout for real relationships; JSONB reserved for genuinely variable-shape data (component dimensions, mission environment, simulation config/results). This matches the "relational where relationships matter, JSONB where flexibility is useful" architectural rule.

**Full designed API surface** — see `docs/api/API.md`: `/api/v1` base, standard `{status, data, meta}` / `{status, error}` envelopes, Bearer JWT auth on protected routes. Covers auth, projects, missions, vehicles (+ stages + components), space-objects, search, lessons/learning-progress, simulation (incl. one WebSocket route), AI, reports, and `.rkt` import/export/validate.

---

## 3. Directory-by-Directory Status

### 3.1 `apps/api/` — Backend (mine)

```
apps/api/
├── README.md                          (module structure spec, now includes verified Local Development steps)
├── pyproject.toml                     (deps + ruff/mypy/pytest config — Phase 2)
├── venv/                              (gitignored, created locally, not in git)
├── tests/                             (263 tests: 214 passing, 49 skip without TEST_DATABASE_URL — see §7)
│   ├── conftest.py                    (client fixture; db_session + live_client skip without TEST_DATABASE_URL)
│   ├── test_health.py, test_error_handling.py, test_config.py        (Phase 2)
│   ├── test_models.py, test_migrations.py                            (Phase 4)
│   ├── test_security.py, test_auth_validation.py, test_auth_service.py (Phase 5, no DB)
│   ├── test_auth_live.py              (Phase 5 — skips, PENDING live PostgreSQL)
│   ├── test_domain_schemas.py         (Phases 6-12 — schema/security, no DB)
│   ├── test_domain_endpoints.py       (Phases 6-12 — auth boundary on all 33 protected routes)
│   └── test_integration_live.py       (Phases 13/15 — ownership isolation etc; skips, PENDING)
└── src/
    ├── __init__.py                    (Phase 2)
    ├── main.py                        (Phase 2 — app entrypoint; Phase 4 added lifespan/engine disposal)
    ├── api_router.py                  (mounts every domain router; /health + /health/ready)
    ├── ai/                          (Phase 12 — conversation/message persistence)
    │   ├── service.py, router.py    (P4 posts AI output here; no model is called)
    ├── auth/                          (Phase 5)
    │   ├── service.py                 (register/authenticate/rotate/revoke — DB-touching logic)
    │   ├── dependencies.py            (get_current_user)
    │   └── router.py                  (5 routes: register, login, me, refresh, logout)
    ├── core/
    │   ├── __init__.py                (Phase 2)
    │   ├── config/        __init__.py (Phase 2; Phase 4 added test_database_url)
    │   ├── logging/       __init__.py (Phase 2 — structured JSON logging)
    │   ├── envelope/      __init__.py (Phase 2 — success/error envelope builders)
    │   ├── exceptions/    __init__.py, handlers.py (Phase 2; Phase 5 added UnauthorizedError/
    │   │                                ConflictError + fixed a real jsonable_encoder bug)
    │   ├── middleware/    __init__.py, request_logging.py (Phase 2)
    │   ├── database/      __init__.py, base.py (Phase 4 — lazy async engine, session
    │   │                                        factory, get_db, DeclarativeBase, mixins)
    │   └── security/      __init__.py (Phase 5 — bcrypt hashing, JWT access tokens,
    │                                    opaque refresh token generation/hashing)
    ├── models/                        (Phase 4 — 15 tables, see §14)
    │   ├── __init__.py                (registry Alembic imports; DEFERRED_TABLES)
    │   ├── user.py                    (User, RefreshToken)
    │   ├── project.py                 (Project, Mission)
    │   ├── vehicle.py                 (Vehicle, VehicleComponent)
    │   ├── simulation.py              (SimulationRun, SimulationEvent, FailureEvent)
    │   ├── content.py                 (SpaceObject, Lesson)
    │   ├── learning.py                (LearningProgress)
    │   └── conversation.py            (Conversation, Message, SearchHistory)
    ├── learning/          .gitkeep
    ├── missions/          .gitkeep
    ├── projects/          .gitkeep
    ├── reports/           .gitkeep
    ├── schemas/                       (Phase 5)
    │   └── auth.py                    (RegisterRequest, LoginRequest, RefreshRequest,
    │                                    LogoutRequest, UserResponse, AuthResponse, LogoutResponse)
    ├── search/            .gitkeep
    ├── simulation/        .gitkeep
    ├── space_data/        .gitkeep
    ├── users/             .gitkeep    (still empty — /auth/me covers current-user reads;
    │                                   general user-profile endpoints are Phase 6+)
    └── vehicles/          .gitkeep
```

`src/models/` holds ORM models only. Pydantic request/response schemas live in `src/schemas/` — database concerns and API contracts do not share files.

`core/logging/` and `core/envelope/` are two new subpackages added beyond the original five (`config`, `database`, `exceptions`, `middleware`, `security`) — structured logging and the response envelope both needed a home and didn't fit inside the existing ones. See §12 for the full Phase 2 summary.

### 3.2 `database/` (mine)

```
database/
├── README.md
├── alembic.ini                        (Phase 4 — no credentials; URL comes from env)
├── migrations/
│   ├── env.py                         (Phase 4 — async, imports src.models)
│   ├── script.py.mako
│   └── versions/                      (Phase 4 — 7 hand-written revisions)
│       ├── 0001_baseline.py           (PG version guard, no schema)
│       ├── 0002_users_and_refresh_tokens.py
│       ├── 0003_project_spine.py      (projects, missions, vehicles, vehicle_components)
│       ├── 0004_simulation_results.py (simulation_runs, simulation_events, failure_events)
│       ├── 0005_catalogs.py           (space_objects, lessons, search_history)
│       ├── 0006_learning_progress.py
│       └── 0007_conversations_messages.py
├── scripts/      .gitkeep
└── seeds/                             (Phase 4 — structure only, no content)
    ├── __init__.py                    (ownership boundary vs data/seeds)
    └── seed_all.py                    (skips while data/seeds is empty)
```

Alembic runs on **asyncpg**, the same driver as the app — see §14. Migration `0008` will add `vehicle_stages`, `telemetry_points`, and `vehicle_components.stage_id` once P3 signs off.

### 3.3 `deployment/` (mine)

```
deployment/
├── README.md   (references deployment/docker/docker-compose.dev.yml — does not exist)
├── docker/     .gitkeep
├── nginx/      .gitkeep
└── scripts/    .gitkeep
```

### 3.4 Non-owned areas (verified empty, for awareness only — not to be touched)

- `apps/web/src/**` — full React directory shape exists (components/ui, components/layout, components/features/{auth,dashboard,explore,learn,reports,search,simulate}, hooks, lib, pages, services, stores, styles, types, assets) — all `.gitkeep` only, no `package.json`.
- `simulation/`, `scientific/` — P3's physics engine, all `.gitkeep`.
- `ai/`, `search/`, `data/` — P4's domain, all `.gitkeep`.
- `packages/contracts/src/`, `packages/shared/src/`, `packages/ui/src/` — **empty**. None of the promised contract files (`api.ts`, `simulation.py`, `ai.py`, `rkt.py`/`rkt.ts`, `websocket.ts`, `events.py`) exist yet. This is a cross-team blocker worth flagging in standup, not something backend can unblock alone.
- `assets/`, `tests/` (root, cross-cutting) — all `.gitkeep`.

### 3.5 Root-level files

`README.md`, `LICENSE` (MIT), `.env.example`, `.gitignore`, `.github/ISSUE_TEMPLATE/.gitkeep`, `.github/workflows/.gitkeep` (no CI defined). `README.md` and several docs are wrapped in a stray `<![CDATA[ ... ]]>` block — cosmetic only, renders fine as Markdown, but worth cleaning up whenever those files are next touched.

---

## 4. Configuration Status

- **`.env.example`** exists and is reasonable: app env/debug/log level, API host/port, JWT secret/algorithm/expiries, `CORS_ORIGINS` (added Phase 2), `DATABASE_URL` (Postgres, `asyncpg` driver), Redis URL (optional), NASA API key, AI provider stub, upload settings.
- **`Settings`** (`apps/api/src/core/config`, Phase 2) loads all of the above via `pydantic-settings`, reading `.env` from the repo root regardless of cwd (via `find_dotenv(usecwd=True)`). Refuses to boot if `APP_ENV=production` with the still-default `SECRET_KEY` — closes `KNOWN_ISSUES.md` §5 D-2.
- **`.gitignore`** is thorough and correct for a Python+Node monorepo (venvs, `__pycache__`, `.env*` except example, coverage, `*.db`/`*.sqlite3`, build outputs, deployment secrets).
- **`apps/api/pyproject.toml`** (Phase 2) is now the dependency/tooling manifest — no `requirements.txt` (deliberately; see `apps/api/README.md`). Still **no** `alembic.ini`, `docker-compose.yml`, or `Dockerfile` anywhere in the repo — out of Phase 2 scope.
- **No CI/CD**: `.github/workflows/` is empty. `DECISION_LOG.md` explicitly lists "CI/CD platform" as an **unresolved decision owned by P2**. Local lint/format/type-check/test commands exist and are verified (§12) but nothing runs them automatically yet.

## 5. Documented Module Layout vs. Actual Scaffold — RESOLVED 2026-08-18

Previously: `apps/api/README.md` documented `core/` as flat files while the scaffold had sub-package directories. **Resolved** in the pre-Phase-2 architecture correction — the sub-package structure (`core/config/`, `core/database/`, `core/exceptions/`, `core/middleware/`, `core/security/`, each a package that can grow into multiple files without restructuring) is now the documented source of truth in `apps/api/README.md`. This was a doc-consistency fix, not a new architectural choice, so it isn't tracked as its own row in `docs/decisions/DECISION_LOG.md`.

## 6. Dependency Status

Declared and installed as of Phase 2, in `apps/api/pyproject.toml` (version ranges, not exact pins — see §12 for why that's an intentional MVP simplification):

| Layer | Installed | Status |
|---|---|---|
| Language/runtime | Python 3.11+ (verified against 3.14.4) | ✅ |
| Framework | `fastapi` | ✅ app boots, verified live |
| Server | `uvicorn[standard]` | ✅ verified live |
| Validation/config | `pydantic`, `pydantic-settings`, `python-dotenv` | ✅ |
| Dev tooling | `pytest`, `pytest-asyncio`, `httpx`, `ruff`, `mypy` | ✅ all verified passing, §14 |
| ORM | `sqlalchemy[asyncio]` 2.0 | ✅ Phase 4 — 15 models |
| Migrations | `alembic` | ✅ Phase 4 — 7 revisions, single linear chain |
| DB driver | `asyncpg` | ✅ Phase 4 — used by **both** app and Alembic |
| DB driver (migrations) | ~~`psycopg2-binary`~~ | ❌ **not needed.** Alembic's native async support removes the two-driver split — see §14 and `KNOWN_ISSUES.md` §5 D-5 |
| Password hashing | `bcrypt` | ✅ Phase 5 — **not** `passlib[bcrypt]` as `ARCHITECTURE.md` documents; verified broken, see `DECISION_LOG` #30 |
| JWT | `python-jose[cryptography]` | ✅ Phase 5, as documented |
| Email validation | `email-validator` | ✅ Phase 5 — required by Pydantic's `EmailStr` |

## 7. Test Status

Backend tests live in **`apps/api/tests/`** (co-located with the app, not root `tests/unit/`) — resolved in Phase 2: root `tests/{integration,e2e,performance,scientific,fixtures}` remain for cross-cutting/whole-stack tests later; `apps/api/tests/` holds tests for the backend app itself, runnable standalone via `cd apps/api && python -m pytest`.

**263 tests: 214 passing, 49 correctly skipped** (need a live database; see §15). Phase 2 covered the foundation layer (health endpoint, error-envelope shape, CORS on errors, config/production-safety). Phase 4 added:

- `test_models.py` — compiles models to PostgreSQL DDL with a dialect object (no connection) and asserts the contract holds: exactly the 15 approved tables, deferred tables absent, TIMESTAMPTZ everywhere, soft delete only on `projects`, `vehicles.mission_id` UNIQUE, RESTRICT/SET NULL delete behaviour, `messages` without `user_id`, generated FTS columns, enum CHECKs.
- `test_migrations.py` — drift guards: every model table and index is created by some migration, no migration creates a table absent from the models, the revision chain is linear with one root, every created table is dropped in a downgrade, and CHECK names match the models exactly.

Phase 5 added three more, split by what's genuinely runnable without PostgreSQL — full breakdown in §15:

- `test_security.py` — pure unit tests of hashing/JWT, no mocking.
- `test_auth_validation.py` + `test_auth_service.py` — Pydantic-level and mocked-session tests; no real DB connection.
- `test_auth_live.py` — full HTTP-level flows against a real database, all 18 skipped here, ready to run once PostgreSQL exists.

**No live-database tests yet.** The `db_session` fixture exists and skips unless `TEST_DATABASE_URL` is set, so the suite stays green on a machine without PostgreSQL while still running for real where one exists. `tests/README.md`'s `test_<module>_<function>_<scenario>.py` convention is not strictly followed (kept to `test_<topic>.py`); revisit if it matters as the suite grows.

## 8. Person 2 Scope vs. Reality

| Owned responsibility | Status |
|---|---|
| FastAPI backend | Foundation implemented 2026-08-19 (Phase 2): app boots, `/api/v1` routing, config, structured logging, centralized error handling, CORS. No domain endpoints yet — see §12. |
| PostgreSQL | Schema defined and migrations written (Phase 4). **Never applied to a live server** — none installed on this machine; see §14 Known limitation. |
| SQLAlchemy/ORM | Implemented (Phase 4): 15 of 17 contracted models. `vehicle_stages` + `telemetry_points` blocked on P3. |
| Alembic migrations | Implemented (Phase 4): 7 revisions, one linear chain, async (`asyncpg`) `env.py`, no credentials in `alembic.ini`. |
| Authentication | Implemented 2026-08-19 (Phase 5): register/login/refresh/logout/me, bcrypt hashing, JWT access tokens, refresh-token rotation + reuse-detection lockout. Live-DB behavior unverified — see §15. |
| Authorization | Implemented across every owned resource (Phases 6-12): `core/authz.py` resolves ownership by walking FKs to `users.id`, returns 404-not-403, and hides soft-deleted projects. All 33 protected routes test-verified to reject anonymous and forged-token callers. Isolation between two real users is PENDING live PostgreSQL. |
| User/Project/Rocket(Vehicle)/Mission persistence | Full CRUD implemented (Phases 6-8, 10): users profile/preferences, projects (soft delete), missions, vehicles + components. Vehicle field names are P3's contract, passed through verbatim. |
| Learning progress persistence | Implemented (Phase 9): lessons read API + progress upsert via ON CONFLICT, status/percent/completed_at kept consistent. |
| Conversation/message persistence | Implemented (Phase 12): conversation CRUD + message storage with `grounding` provenance. P2 stores, P4 generates — no model is called here. |
| Space-object API boundary | Implemented (Phase 11): public list/detail/categories with filtering, FTS search, and allow-listed sorting. Read-only — P4 owns ingestion. |
| API validation, error handling, logging | Structured logging (Phase 2) + centralized error handling now proven against real request bodies (Phase 5: `RegisterRequest`/`LoginRequest`/etc. with custom validators). Found and fixed a real bug where custom-validator failures 500'd instead of 422'ing — see §15. Database-level CHECKs remain the last line of defence (Phase 4). |
| Backend tests | 118 total: 100 passing, 18 correctly skipped pending live PostgreSQL (Phase 2 foundation + Phase 4 model/migration + Phase 5 auth suites). No live-database integration run yet — see §7 and §15. |
| Security baseline | Auth is now real (Phase 5): password hashing, JWT, refresh rotation with reuse detection, production-safety config check (`KNOWN_ISSUES.md` §5 D-2, closed Phase 2). **Still open:** rate limiting on `/auth/register`/`/auth/login` (D-3) and a CORS-origin production hardening review — see [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) §5 |
| Shared API contracts | Minimum surface identified 2026-08-18 (`docs/backend/API_CONTRACT.md`); actual `packages/contracts/` package still blocked on P4/team review — see §11 |

## 9. What Must Be Preserved

- All existing docs (`docs/architecture/*`, `docs/api/API.md`, `docs/rkt_spec/RKT_SPEC.md`, `docs/decisions/DECISION_LOG.md`, `docs/setup/SETUP.md`, every module `README.md`) — they are detailed, mutually consistent, and represent team agreement. Treat as the spec; don't casually diverge without updating the doc and flagging the change (contracts rule: "Any change to a contract requires agreement from all affected team members").
- The directory scaffold and naming (`apps/api/src/<module>/router.py` + `service.py` pattern, `models/` and `schemas/` as shared cross-module folders).
- The "Allowed Imports" boundaries stated in each module README (e.g., `apps/web` must never import `apps/api`; `apps/api` must never import `apps/web`; `simulation/` must stay framework/DB-free).
- `.env.example` variable names — other team members' tooling (mock servers, scripts) may already assume these names.
- `.gitignore` as-is; it's correct for this stack.
- The RKT file format spec and its validation rules — used by both frontend export/import UX and backend validation.

## 10. Recommended Build Order (backend-only, dependency-respecting)

Derived from `ARCHITECTURE.md` §7's project-wide dependency graph, narrowed to what P2 actually builds, and matching the "don't build the whole backend at once" instruction. Each step should be its own PLAN→IMPLEMENT→TEST→VERIFY→DOCUMENT→CHECKPOINT cycle:

1. ~~**Project bootstrap**~~ — **DONE (Phase 2).** `pyproject.toml`, `src/main.py`, `core/config/`, `/health`.
2. ~~**Database wiring**~~ — **DONE (Phase 4).** `core/database/` (lazy async engine, session factory, `get_db`), Alembic initialized against `database/migrations/`, `0001_baseline`. The driver question resolved to **asyncpg for both** app and migrations — the split was eliminated, not configured.
3. ~~**Core models + migrations**~~ — **DONE (Phase 4), except the two blocked tables.** 15 tables across 7 revisions in FK order. `vehicle_stages` and `telemetry_points` (and `vehicle_components.stage_id`, an FK into the former) are deferred to `0008` pending P3 — see §14.
4. ~~**Auth module**~~ — **DONE (Phase 5).** Password hashing (`bcrypt`), JWT issue/verify, `register`/`login`/`me`, `get_current_user` dependency, `refresh_tokens` rotation + reuse-detection lockout per decision #16 for `/auth/refresh` and `/auth/logout`. Live-DB behavior unverified — see §15.
5. **Users + Projects modules** ← **NEXT.** First authenticated CRUD, establishes the router/service/schema pattern the rest of the modules copy. `users/` is still an empty scaffold dir — `/auth/me` covers current-user reads, but there's no general profile-update endpoint yet.
6. **Missions + Vehicles (+ stages/components)** — bulk of relational CRUD.
7. **Space data + Learning modules** — mostly read APIs against P4-seeded tables; seed-loading boundary with P4 is now defined (`database/README.md`/`data/README.md`, decision #18) — write the `database/seeds/` loader scripts against P4's `data/seeds/`/`data/fallback/` content once it exists.
8. **Simulation integration** — thin `apps/api/src/simulation/` wrapper calling P3's `simulation.engine.run_simulation()` as a library call once that exists; persist `simulation_runs`/`telemetry_points`/`simulation_events`.
9. **Search integration** — thin wrapper once P4's `search/` interface is defined; resolve the DB-ownership boundary first ([`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) §4 D-2/D-3 — still open, not addressed by the pre-Phase-2 correction).
10. **AI integration + Reports + RKT import/export** — last, since they depend on nearly everything else being real. AI wrapper persists to `conversations`/`messages` per `docs/api/API.md`.
11. **Security/test hardening pass** — rate limiting on auth routes, wider test coverage sweep. (Structured logging, centralized error-handling middleware, and CORS were pulled forward and implemented in Phase 2 — see §12 — since they're foundation-layer, not auth-specific.)

Do not start step *n+1* before step *n* is tested and the project still runs end-to-end (`uvicorn` boots, `/health` returns 200) — matches the "keep the project runnable after every milestone" rule.

---

## 11. Pre-Phase-2 Architecture Correction (2026-08-18)

Following the audit at Checkpoint 0, a documentation-only correction pass resolved four of the findings before any implementation starts. No application code was written; only architecture/schema/API docs changed.

- **Auth/logout gap (KNOWN_ISSUES D-1 security):** added `refresh_tokens` table to `DATABASE.md` (hashed token, `revoked_at`, `replaced_by` for rotation). Access tokens stay stateless; refresh tokens are now revocable. `API.md`'s auth section and `DECISION_LOG.md` #7/#16 updated to match. `/auth/logout` and `/auth/refresh` now have a real mechanism behind them.
- **Missing conversation/message schema:** added `conversations` (with JSONB `context_ref` soft-link, not FK) and `messages` tables to `DATABASE.md`. `API.md`'s AI section got two new read endpoints. Decision recorded as #17.
- **`core/` doc/scaffold mismatch (§5, KNOWN_ISSUES P-1):** resolved — sub-package structure is now the documented source of truth in `apps/api/README.md`, with the flat-file draft explicitly marked superseded.
- **Seed ownership ambiguity (KNOWN_ISSUES D-1 in §4):** resolved — `database/README.md` and `data/README.md` now state the boundary explicitly (P2 = loader scripts in `database/seeds/`, P4 = content in `data/seeds/`/`data/fallback/`). Decision recorded as #18.
- **Minimum pre-parallel-dev contracts identified**, not implemented: `docs/backend/API_CONTRACT.md` (new) names the envelope, auth, `Project`, `MissionSummary`, `SpaceObject`, and search shapes needed before Phase 2, and explicitly defers simulation/AI/WebSocket/RKT contracts to their later phases. Decision recorded as #19.

**Not addressed by this pass** (still open, tracked in `KNOWN_ISSUES.md`): the `search`/`ai` DB-access boundary ambiguity (D-2/D-3 in §4), CI/CD platform choice, rate limiting, CORS policy, `SECURITY_CHECKLIST.md`, backend test-location decision, async/sync DB driver split documentation, dual onboarding docs (P-2), missing dev scripts (P-3), stray CDATA wrapper (P-4). None of these block starting Phase 2 work on Projects/Dashboard/Space Data/Search — they're independent of what was corrected here.

## 12. Phase 2 — Backend Foundation (2026-08-19)

First application code in the repo. Scope: FastAPI setup, `/api/v1` routing, config management, env loading, health endpoint, structured logging, centralized error handling, CORS, linting/formatting/type-checking, testing setup, reproducible local startup. Explicitly excluded (per Phase 2 instructions): DB models, auth, any domain CRUD, learning, AI, search, simulation physics — none of that was touched.

**What was built** (`apps/api/src/`): `main.py` (entrypoint), `api_router.py` (`/api/v1` router, health check only), `core/config` (Settings + prod-safety check), `core/logging` (new — structured JSON logs), `core/envelope` (new — `success_envelope`/`error_envelope`), `core/exceptions` (`AppError` hierarchy + centralized handlers for app errors, validation errors, HTTP errors, and unhandled exceptions — all through the one envelope), `core/middleware` (CORS + per-request logging with `X-Request-ID` correlation). `apps/api/pyproject.toml` added as the single dependency/tooling manifest (ruff, mypy, pytest configured there).

**Verified, not just written** (see full command output in the session that produced this checkpoint): `pip install -e ".[dev]"` succeeds from a clean venv; `pytest` → 9/9 passing; `ruff check` and `ruff format --check` → clean; `mypy` → 0 errors across 26 source files; the server was actually booted with `python -m uvicorn src.main:app --port 8000` (not just tested in-process) and hit with real HTTP requests — `GET /api/v1/health` → 200 with the correct envelope, `GET /api/v1/does-not-exist` → 404 with a structured error envelope (not FastAPI's default `{"detail": ...}` shape), an `OPTIONS` CORS preflight → correct `access-control-allow-origin`, and `/docs`/`openapi.json` both serve. Structured JSON log lines were confirmed in the server's stdout with matching `request_id` correlation to the response header.

**Decisions made that were previously open items:**
- Backend tests live in `apps/api/tests/`, not root `tests/unit/` (closes the open item in old §7 / `KNOWN_ISSUES.md` §3).
- `KNOWN_ISSUES.md` §5 D-2 (no safeguard against booting in production with the default `SECRET_KEY`) is now closed — `Settings.validate_production_safety()` raises on that combination, called at startup in `main.py`.
- Internal imports across `apps/api/src/` are rooted at `src.` (e.g. `from src.core.config import get_settings`), not bare (`from core.config import ...`) — the bare form only worked by accident of `sys.path` under some invocations and broke under `python -m uvicorn`. Documented in `apps/api/README.md`.

**Explicitly not done** (out of Phase 2 scope, unchanged from before): no DB connection wired up (`core/database/` still empty — the health check is liveness-only, does not check DB reachability), no auth (`core/security/` still empty), no domain routers/models/schemas, no CI workflow (checks are documented and verified locally, nothing runs them automatically yet), no Docker.

Non-critical issues found during implementation are recorded in `KNOWN_ISSUES.md` rather than blocking this phase — see its Checkpoint 2 entry for the two found this round (a `starlette`/`httpx` deprecation warning in tests, and version ranges vs. an exact lockfile).

## 13. Phase 3 — Database Contract Finalization (2026-08-19)

Documentation only; no models, no migrations, no endpoints. Produced [`DATABASE_CONTRACT.md`](DATABASE_CONTRACT.md) (normative spec for Phase 4) and [`SCHEMA_DECISIONS.md`](SCHEMA_DECISIONS.md) (decision record SD-1…SD-8). `DATABASE_DESIGN.md` is now marked superseded so it can't compete as a source of truth.

**Six decisions closed:** `vehicle` canonical over `rocket` (#20) · `simulation_events` canonical, no `mission_events` (#21) · learning schema reduced to `lessons` + `learning_progress` (#22) · `.rkt` is the versioning mechanism, no `project_versions` (#23) · telemetry flattened to `float8` + attitude (#24, ⚠ pending P3) · stage mass resolved via an explicit *structural remainder* field (#25, ⚠ pending P3+P1).

**Final MVP entity count: 17 tables** — 16 existing (14 unchanged, `projects` and 2 modified) + `learning_progress`. Nine requested entities were deferred or rejected with recorded reasons.

**Two new findings not in the audit brief:**
- **`RKT_SPEC.md`'s example vehicle is physically impossible** — declares 5000 N thrust while its own Isp/propellant/burn-time imply 12,258 N (2.45× off, verified numerically). `thrust_n`/`isp_s`/`burn_time_s`/`propellant_mass_kg` are four authored fields with three degrees of freedom (decision #26, blocked on P3).
- **`telemetry_points` has no attitude columns** despite `SIMULATION.md`'s state vector carrying `attitude[pitch,yaw,roll]` — P1's 3D replay could position the vehicle but not orient it.

**A correction to my own earlier work:** the Phase-2 telemetry volume estimate (~12,000 rows/run, ~1.2M per demo) was wrong by 20× — it used the integrator timestep instead of `SIMULATION.md`'s documented 1 Hz persistence rate. Real figures: ~600 rows/run, ~60,000 per 100 runs. The flatten-JSONB recommendation survives on other grounds, but volume is no longer a reason and is not presented as one.

**Phase 4 is authorized for 15 of 17 tables** (the entire auth and project spine). `vehicle_stages` and `telemetry_points` are blocked pending P3 sign-off — see `DATABASE_CONTRACT.md` §10.

## 14. Phase 4 — Database Foundation (2026-08-19)

First database code. Scope: SQLAlchemy configuration, ORM models for the approved entities, relationships, constraints, indexes, Alembic migrations, database initialization, test-database configuration, minimal seed structure, documentation. No auth endpoints, no domain APIs, no simulation, no AI — none were touched.

**Built:** `src/core/database/` (declarative base with naming convention, mixins, lazy async engine, session factory, `get_db` dependency) · `src/models/` (10 modules, 15 tables) · `database/alembic.ini` + `migrations/env.py` + 7 hand-written revisions · `database/seeds/` structure · `apps/api/tests/test_models.py` and `test_migrations.py` · `docs/backend/DATABASE_SETUP.md`.

**Blockers respected.** `vehicle_stages` and `telemetry_points` are **not** created — their contracts depend on unresolved P3 decisions (#24, #25, #26). A knock-on consequence had to be handled: **`vehicle_components.stage_id` is a foreign key into `vehicle_stages`**, so it defers with it. Components remain fully usable because `vehicle_id`, not `stage_id`, is their ownership link. All three land together in migration `0008`. Tests assert the deferred tables stay absent, so they cannot be added accidentally.

**Verified without a PostgreSQL server** (none is installed on this machine — see Known limitation below): 40 tests pass; ruff lint + format clean; mypy clean across 34 files; `alembic history`/`heads` show one linear chain with a single head; `alembic upgrade head --sql` emits valid DDL for all 7 revisions; generated DDL inspected for partial indexes, DESC indexes, GIN indexes, `GENERATED ALWAYS AS … STORED`, `ON DELETE RESTRICT`/`SET NULL`, and every CHECK; migration and model constraint names compared programmatically (14/14 exact match); the app boots and `/api/v1/health` returns 200 with no database running, confirming the engine is genuinely lazy.

**Two real defects found and fixed during the phase:**
- **Double-prefixed CHECK constraint names.** The `ck` naming convention is `ck_%(table_name)s_%(constraint_name)s`; migrations passing an already-prefixed name produced `ck_users_ck_users_role_valid`, which would not have matched the models. All 14 fixed, plus a regression test. FK/PK/UQ conventions have no `%(constraint_name)s` token, so only CHECKs were affected.
- **`failure_events` had no `created_at`**, which `DATABASE_CONTRACT.md` §6 requires of every table — `docs/architecture/DATABASE.md` omits it on that table alone. Added; `DATABASE.md` should be corrected to match.

A third issue was fixed in the baseline migration: its PostgreSQL version guard broke `alembic upgrade --sql`, since offline mode has no connection to query. It now skips when offline.

**Decision changed from the earlier plan:** migrations run on **asyncpg**, not psycopg2. `KNOWN_ISSUES.md` D-5 planned the conventional async-app/sync-Alembic split; Alembic's native async support removes the split entirely — one driver, no URL rewriting, and no chance of the two URLs being reconciled later and breaking one. D-5 is closed by elimination rather than documentation.

**Known limitation:** PostgreSQL is not installed on this machine, so **the migrations have not been run against a real database.** They are reviewed and internally consistent, not proven to apply. `docs/backend/DATABASE_SETUP.md` §Verification gives the exact commands to close this.

## 15. Phase 5 — Authentication (2026-08-19)

Scope: registration, login, `GET /auth/me`, `POST /auth/refresh`, `POST /auth/logout`, `get_current_user`, protected-route authorization, refresh-token rotation and revocation, standard error responses, input validation, secure secret handling. No project/vehicle/mission APIs, no frontend, no AI — none touched.

**Built:** `src/core/security/` (bcrypt password hashing, JWT access tokens via python-jose, opaque refresh tokens) · `src/auth/{service.py, dependencies.py, router.py}` · `src/schemas/auth.py` · `UnauthorizedError`/`ConflictError` added to the exception hierarchy · 5 routes wired into `api_router` under `/auth`. Uses the existing `refresh_tokens` table from Phase 4 — **no new session/token table created**, per instruction.

**Library deviation, verified before deciding:** `passlib[bcrypt]` (ARCHITECTURE.md's documented choice) is broken by the currently-resolved `bcrypt` 5.0.0 — reproduced directly (`AttributeError: module 'bcrypt' has no attribute '__about__'`) before switching to `bcrypt` directly. `python-jose` for JWT is unchanged. See `DECISION_LOG` #30.

**Security design, matching the stated requirements:**
- Access tokens: stateless JWT (`sub`, `type=access`, `iat`, `exp`), verified by signature + expiry + type claim only.
- Refresh tokens: opaque `secrets.token_urlsafe(32)`, SHA-256-hashed for storage — validity is decided entirely by the `refresh_tokens` row (Phase 4), never by anything encoded in the token (`DECISION_LOG` #31).
- **Rotation + reuse detection** (`DECISION_LOG` #32): `/auth/refresh` always issues a new token and revokes the old one (`replaced_by` chain). Presenting an already-revoked token is treated as a possible theft replay — **all** of that user's active refresh tokens are revoked defensively, and the response is identical to any other invalid-token error, so an attacker gets no signal reuse was specifically detected.
- Login returns one generic `INVALID_CREDENTIALS` error for wrong email, wrong password, and inactive accounts — never distinguishable. Registration *does* distinguish `EMAIL_ALREADY_EXISTS`/`USERNAME_ALREADY_EXISTS`, deliberately (`DECISION_LOG` #33).
- Ownership enforced on logout: revoking another user's refresh token returns 404, matching `DATABASE_CONTRACT.md` §5's "404, not 403" rule.
- `password_hash` never appears in any response; `UserResponse` is an explicit allow-list schema, not the ORM model serialized directly.
- `Settings.validate_production_safety()` (Phase 2) already refuses to boot in production with the default `SECRET_KEY`; nothing new needed there.

**One real, pre-existing bug found and fixed:** `validation_exception_handler` (Phase 2) passed Pydantic's `exc.errors()` straight to `json.dumps` via `JSONResponse`. A custom `field_validator` raising `ValueError` (both of `RegisterRequest`'s — password byte-length, username charset) causes Pydantic to embed the raw exception object under `ctx.error`, which isn't JSON-serializable — every such validation failure was a 500, not the intended 422. Not hypothetical: reproduced with a real request, full traceback captured. Fixed with `fastapi.encoders.jsonable_encoder`. This bug would have affected any future route with a custom validator, not just auth.

**Verified without PostgreSQL:** 100 tests pass (61 new), 18 correctly skip (need a live server); ruff lint + format clean; mypy clean across 38 files; live server boot-tested — `/api/v1/health` 200, `/api/v1/auth/me` with no token → clean 401 (not a hang/500, confirmed empirically that entering an unconnected `AsyncSession` context doesn't open a network connection), malformed registration → 422, all 5 auth routes present in the OpenAPI schema.

**Test strategy, three tiers by what's genuinely runnable without a database:**
1. `test_security.py` (21 tests) — pure, no mocking: real bcrypt/JWT round-trips, tampered signatures, wrong secrets, expired tokens, wrong-type tokens, password byte-length edge cases.
2. `test_auth_validation.py` (20) + `test_auth_service.py` (19) — no real DB connection: Pydantic rejects malformed bodies before any route code runs; service-layer decision logic (duplicate detection, credential checks, rotation, reuse lockout, logout ownership) tested against a mocked `AsyncSession`.
3. `test_auth_live.py` (18, all skipped) — full HTTP-level flows against a real database via a new `live_client` fixture (dependency-overrides `get_db` to `TEST_DATABASE_URL`, always rolls back). **Written and believed correct; not executed.** Explicitly marked PENDING in the file's own docstring.

**Known limitation, unchanged from Phase 4:** PostgreSQL is still not installed on this machine. Everything in tier 3 — the actual persistence, the actual UNIQUE-constraint-triggered 409s, the actual rotation against real rows — is unverified. `docs/backend/DATABASE_SETUP.md` has the commands; run `test_auth_live.py` specifically once a server exists.

**Not addressed, correctly out of scope:** rate limiting on `/auth/register`/`/auth/login` (`KNOWN_ISSUES` D-3, still open — Redis isn't wired up and wasn't in this phase's instructions) — flagged again here as a pre-launch gap, not fixed.

## 16. Phases 6–15 — Domain APIs, Integration & Verification (2026-08-19)

Ten queued phases, built on the pattern Phase 5 established. No architecture was redesigned and no completed table recreated.

**What was built.** 25 new endpoints across 6 domains, all following the same shape: Pydantic schema → service (ownership-checked) → router → standard envelope.

| Phase | Domain | Endpoints |
|---|---|---|
| 6 | Users | `GET/PATCH /users/me`, `GET/PATCH /users/me/preferences` |
| 7 | Projects | full CRUD + status filter + pagination |
| 8 | Vehicles | full CRUD + `/vehicles/{id}/components`, `/components/{id}` |
| 9 | Learning | `GET /lessons`, `/lessons/categories`, `/lessons/{id-or-slug}`, `GET/POST /learning/progress`, `PATCH /learning/progress/{lesson_id}` |
| 10 | Missions | full CRUD + project/status filters |
| 11 | Space objects | list/detail/categories + filtering, FTS search, sorting (public) |
| 12 | Conversations | full CRUD + `/conversations/{id}/messages` (also aliased under `/ai/conversations`) |
| 14 | Demo | `GET /health/ready`, `database/seeds/demo_data.py` |

**Contract decisions honoured rather than re-opened.** `favorites` stayed DEFER (Phase 6 asked for it "only if already supported" — SD-3 deferred it, so it was skipped). No `profiles` table: preferences became a JSONB column on `users` (migration `0008`). No `rockets`/`rocket_components`. No `mission_events`. `vehicle_stages` and `telemetry_points` remain blocked on P3, and `VehicleComponent.stage_id` with them.

**Security model, uniform across every owned resource.** Ownership is resolved in `core/authz.py` by walking FKs to `users.id` — never from the request body. Unowned rows return **404, not 403**, so ids can't be probed. Soft-deleted projects are invisible, and so is everything reachable through them. Every update schema uses `extra="forbid"`, which turns `{"role":"admin"}`, `{"user_id":…}`, `{"is_valid":true}` and similar into 422s instead of Pydantic's default silent drop — 13 such vectors are covered by parametrized tests.

**Verified without PostgreSQL:** 214 tests pass, 49 skip (DB-dependent); ruff + format clean; mypy clean across 61 files; live server boot-tested — 31 OpenAPI paths, health 200, readiness correctly **503** (not 500) with no database, protected routes 401, bad pagination 422; Alembic chain linear at `0008_user_preferences`, full schema still generates offline.

**Test tiers.** `test_domain_schemas.py` (36) — pure schema/security. `test_domain_endpoints.py` (78) — every one of the 33 protected endpoints rejects both anonymous *and* forged-token callers, plus public endpoints confirmed not to require auth. `test_integration_live.py` (31, skipped) — ownership **isolation** between two real users, CRUD round-trips, cascades, P3 vehicle save/load, P4 conversation persistence.

**Limitation, unchanged.** No PostgreSQL on this machine. The no-DB tests prove auth is *required* and that filters are *written*; only the live suite can prove user B actually cannot see user A's rows. That distinction is stated in the file's own docstring and must not be reported as verified until it runs.

**Deliberately not done:** rate limiting (`KNOWN_ISSUES` D-3, needs Redis, still open); simulation-run/telemetry persistence endpoints (Phase 13 mentions the boundary — the tables are contract-blocked on P3, so the API would be guessing); no physics, AI generation, search internals, or ingestion anywhere.

## 17. Checkpoint Log

| Checkpoint | Date | Summary |
|---|---|---|
| 0 | 2026-08-18 | Full repository audit. Confirmed zero code exists anywhere in the repo; only docs + directory scaffold. No files modified. Findings split into this file (state/architecture) and `KNOWN_ISSUES.md` (problems/risks). Waiting for direction on which build-order step to start. |
| 1 | 2026-08-18 | Pre-Phase-2 architecture correction (see §11 above). Fixed the auth/logout design gap, added conversation/message schema, resolved the `core/` doc mismatch, defined the seeds ownership boundary, and identified (not implemented) the minimum contract surface for Phase 2. Docs only — no application code. Phase 2 implementation not yet started. |
| 2 | 2026-08-19 | Phase 2 — Backend Foundation implemented and verified (see §12 above): FastAPI app, `/api/v1` routing, config, structured logging, centralized error handling, CORS, lint/format/type-check/test tooling, reproducible local startup. 9/9 tests passing, live server smoke-tested with real HTTP requests. No DB, auth, or domain logic — correctly out of scope. Ready for Phase 3 (first domain module) once directed. |
| 3 | 2026-08-19 | Phase 3 — Database Contract Finalization (see §13 above). Docs only. Six decisions closed (`DECISION_LOG` #20–#25), one blocked on P3 (#26). Final MVP schema: 17 tables; 9 requested entities deferred/rejected with reasons. Found that `RKT_SPEC.md`'s example vehicle is physically impossible and that telemetry has no attitude columns. Corrected my own 20× telemetry volume error from Phase 2. Phase 4 authorized for 15 of 17 tables; `vehicle_stages` + `telemetry_points` blocked pending P3. **No ORM models, migrations, or endpoints created — stop condition respected.** |
| 4 | 2026-08-19 | Phase 4 — Database Foundation (see §14 above). 15 ORM models, 7 Alembic revisions, session layer, test-DB config, seed structure, `DATABASE_SETUP.md`. 40 tests / lint / format / types all green. Blocked tables (`vehicle_stages`, `telemetry_points`) and the dependent `vehicle_components.stage_id` correctly deferred and test-guarded. Found and fixed double-prefixed CHECK names and a missing `created_at` on `failure_events`. **Migrations not yet run against a real PostgreSQL — none installed on this machine.** No auth, APIs, or domain logic. |
| 5 | 2026-08-19 | Phase 5 — Authentication (see §15 above). Full auth surface: register/login/me/refresh/logout, `get_current_user`, password hashing, JWT access tokens, opaque refresh tokens with rotation + reuse-detection lockout, ownership-checked logout. Deviated from `ARCHITECTURE.md` on one library (`passlib`→`bcrypt`, verified-broken, `DECISION_LOG` #30). Found and fixed a real pre-existing bug: custom Pydantic validators 500'd instead of 422'ing (unserializable `ValueError` in error details). 100 tests passing, 18 correctly skipped pending live PostgreSQL. Rate limiting (`KNOWN_ISSUES` D-3) remains open, out of scope for this phase. |
| 6-15 | 2026-08-19 | Phases 6-15 — Domain APIs, integration, verification (see §16 above). 25 new endpoints across users/projects/vehicles/missions/learning/space-objects/conversations, plus `/health/ready` and a deterministic demo seed. Shared ownership layer (`core/authz.py`) enforcing 404-not-403 and soft-delete invisibility; shared pagination. Migration `0008` adds `users.preferences` (a column, NOT the rejected `profiles` table). `favorites` correctly left deferred. 214 tests pass / 49 skip pending PostgreSQL; lint, format, mypy clean; live server verified. Rate limiting and P3-blocked tables (`vehicle_stages`, `telemetry_points`) remain open. |
