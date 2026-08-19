# Person 4 (AI / Search / Data / Integration) — Repository & Contract Audit

**Audit date:** 2026-08-18
**Branch:** `person/person4-ai-data`
**Auditor scope:** Read-only inspection. No features implemented. No Person 1/2/3-owned files modified.

---

## 0. Executive Summary

The repository contains **two commits** ("Initial commit" and "Initial Architecture Setup") and is **100% scaffolding**: every directory under `apps/`, `packages/`, `ai/`, `search/`, `data/`, `database/`, `deployment/`, `scientific/`, `simulation/`, `tests/`, `scripts/`, and `assets/` contains only empty `.gitkeep` placeholder files. There is **no source code** (`.py`, `.ts`, `.tsx`, `.js`) anywhere in the repository, and **no dependency manifests** (`package.json`, `requirements.txt`, `pyproject.toml`), **no Docker files**, **no Alembic config**, **no migrations**, **no tests**.

Everything that exists is either:
1. Per-directory `README.md` files declaring an owner and a *planned* structure, or
2. A set of design documents under `docs/` that describe the intended architecture, database schema, API surface, simulation physics, and file formats — all as prose/SQL/pseudocode, not as executable contracts.

Every one of the 15 contracts named in this audit is therefore **MISSING CONTRACT** as actual code. Some have a reasonably complete shape sketched in documentation (e.g. `Mission`, `Project`, `Telemetry`); others (`SourceReference`, `Recommendation`, `Conversation`, `AIResponse`, `SearchResult`/`SearchResponse`) have little or no prior specification anywhere and would need to be authored from scratch, with cross-team sign-off, before other teams build against them.

No integration code exists for any external data source. `data/README.md` records NASA (`api.nasa.gov`, `data.nasa.gov`), Open Notify (ISS position), and Solar System OpenData (`le-systeme-solaire.net`) as *researched/verified* sources — nothing more. **JPL, ESA, ISRO, MPC, CelesTrak, the Exoplanet Archive, NTRS, and EONET are not mentioned anywhere in the repository**, in code or in docs.

---

## 1. Inspection Findings by Area

### Frontend (`apps/web/`)
- Directory skeleton only: `components/{features/{auth,dashboard,explore,learn,reports,search,simulate},layout,ui}`, `hooks/`, `lib/`, `pages/`, `services/`, `stores/`, `styles/`, `types/`, `assets/` — every one is empty (`.gitkeep`).
- `apps/web/README.md` documents the intended stack (React 18 + TS + Vite, React Three Fiber + Drei, Tailwind CSS v3, Zustand + TanStack Query, React Router) and a 14-route page tree.
- Explicit import boundary rule: web may import only `packages/contracts` and `packages/ui`; never `apps/api/`, `simulation/`, or `scientific/`.
- No `package.json`, no `vite.config`, no `tsconfig.json`, no components exist.

### Backend (`apps/api/`)
- `src/` skeleton: `ai/`, `auth/`, `core/{config,database,exceptions,middleware,security}/`, `learning/`, `missions/`, `models/`, `projects/`, `reports/`, `schemas/`, `search/`, `simulation/`, `space_data/`, `users/`, `vehicles/` — every one is empty.
- `apps/api/README.md` documents the intended per-module layout (`router.py` + `service.py`), allowed imports (`packages/contracts/`, `simulation/`, `scientific/`, `ai/`, `search/`; **forbidden**: `apps/web/`).
- No `requirements.txt`, no `main.py`, no ORM models, no routers, no schemas exist.

### Database configuration
- No live config, no `alembic.ini`, no migration files (`database/migrations/` is empty), no ORM models.
- Full schema exists **only as documentation**: [`docs/architecture/DATABASE.md`](architecture/DATABASE.md) contains raw `CREATE TABLE` SQL for `users`, `projects`, `missions`, `vehicles`, `vehicle_stages`, `vehicle_components`, `simulation_runs`, `telemetry_points`, `simulation_events`, `failure_events`, `space_objects`, `lessons`, `search_history`.
- `.env.example` has `DATABASE_URL` (postgresql+asyncpg placeholder), `DATABASE_ECHO`, `REDIS_URL` — no connection code anywhere.

### API routes
- Fully specified only as a route table in [`docs/api/API.md`](api/API.md): auth, projects, missions, vehicles, `/space-objects`, `/search`, `/lessons`+`/learning`, `/simulations` (incl. a WebSocket), `/ai/*`, `/reports`, `/rkt/*`, plus a standard `{status, data, meta}` / `{status, error}` envelope.
- Zero FastAPI route implementations exist.

### API schemas / shared types
- `packages/contracts/src/` contains only `.gitkeep`. None of the files described in `packages/contracts/README.md` (`api.ts`, `simulation.py`, `ai.py`, `rkt.py`/`rkt.ts`, `websocket.ts`, `events.py`) exist.
- `packages/shared/src/` and `packages/ui/src/` are likewise empty, and `packages/shared/` has **no declared owner** anywhere (see Risks §5.3).

### Simulation
- `simulation/` tree is fully scaffolded (`engine/`, `models/{gravity,atmosphere,drag,thrust,trajectory}/`, `integrator/`, `telemetry/`, `events/`, `analysis/`, `validation/`, `tests/`) — every file is `.gitkeep`.
- Design fully documented in [`docs/simulation/SIMULATION.md`](simulation/SIMULATION.md) and [`docs/scientific/MODELS.md`](scientific/MODELS.md): gravity (inverse-square), US Standard Atmosphere 1976, simple drag, constant thrust, linear mass depletion, Barrowman stability, RK4 integration, plus a `SimConfig`/`SimState`/`SimResult` dataclass sketch and an event/failure taxonomy. None of it is implemented.
- `scientific/` (P3-owned reusable physics library) is likewise fully scaffolded with zero code.

### Telemetry
- No telemetry code exists. The concept is specified via the `telemetry_points` table (`DATABASE.md`) and a `TelemetryPoint` name referenced in `ARCHITECTURE.md §9` and `simulation/README.md` — but the type itself is never defined in any file, contracts or otherwise.

### Missions
- No mission code exists. Schema in `DATABASE.md`, routes in `API.md`, `apps/api/src/missions/` empty. No `Mission` type/dataclass/schema defined anywhere in code.

### Existing AI
- `ai/` tree scaffolded (`providers/`, `prompts/`, `tools/`, `grounding/`, `safety/`, `tests/`) — all empty.
- `ai/README.md` sketches an `AIProvider` `Protocol` (`async def complete(...) -> AIResponse`, `async def embed(...)`) — `AIResponse` is referenced but never defined anywhere.
- Explicit design rule already agreed: **"AI is the EXPLANATION layer. The simulation engine is the TRUTH layer. AI receives simulation results and explains them. AI never generates simulation results."** No code enforces this yet (`ai/safety/` is empty).
- No prompts, no provider implementation, no tool schemas, no grounding logic exist.
- `.env.example` has `AI_PROVIDER` / `AI_API_KEY` / `AI_MODEL` entirely commented out — provider choice is an open decision, not a default.

### Existing search
- `search/` tree scaffolded (`indexing/`, `ranking/`, `suggestions/`, `tests/`) — empty.
- `search/README.md` documents the MVP strategy: PostgreSQL `tsvector`/`tsquery` full-text search + prefix-match autocomplete; `pgvector` semantic search explicitly deferred post-MVP.
- `API.md` defines `/search`, `/search/suggestions`, `/search/history` — unimplemented.
- No `SearchResult`/`SearchResponse` type defined anywhere, including in docs.

### Existing space data
- `data/` tree scaffolded (`ingestion/`, `normalization/`, `seeds/`, `fallback/`, `cache/`, `tests/`) — empty.
- `data/README.md` lists a "Verified External Data Sources" **table** (research, not code): NASA `api.nasa.gov` (APOD, NEO, Mars Rovers), NASA `data.nasa.gov` (missions/spacecraft catalog), Open Notify (ISS position), Solar System OpenData (`api.le-systeme-solaire.net`, planet/moon data). Zero fetchers exist.
- `space_objects` table in `DATABASE.md` includes provenance fields (`source`, `source_id`, `last_updated`) — no ORM model, no seed data, no ingestion script.
- No `SpaceObject` type defined in code anywhere.

### Tests
- Every test directory (`tests/{unit,integration,e2e,scientific,performance,fixtures}`, `simulation/tests/`, `scientific/tests/`, `ai/tests/`, `search/tests/`, `data/tests/`) contains only `.gitkeep`. **Zero test files exist in the entire repository.** No test framework is configured (no `pytest.ini`, no `vitest`/`jest` config).

### Package dependencies
- Zero manifests anywhere: no root or `apps/web` `package.json`, no `apps/api` `requirements.txt`/`pyproject.toml`, no lockfiles.
- Intended stack is only inferable from README prose (frontend: React 18/TS/Vite/R3F/Tailwind/Zustand/TanStack Query; backend: FastAPI/SQLAlchemy 2.0 async/Alembic/Pydantic v2/python-jose/passlib/uvicorn/NumPy/SciPy).

### Docker
- `deployment/docker/` contains only `.gitkeep` — no `Dockerfile`, no `docker-compose.yml`, despite `deployment/README.md` referencing `docker-compose -f deployment/docker/docker-compose.dev.yml up`.
- `deployment/nginx/` and `deployment/scripts/` are likewise empty.

### Environment variables (names only — no values inspected or printed beyond documented placeholders)
`.env.example` defines: `APP_ENV`, `DEBUG`, `LOG_LEVEL`, `VITE_API_URL`, `VITE_WS_URL`, `API_HOST`, `API_PORT`, `SECRET_KEY` (placeholder literal `change-me-in-production`), `JWT_ALGORITHM`, `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`, `JWT_REFRESH_TOKEN_EXPIRE_DAYS`, `DATABASE_URL`, `DATABASE_ECHO`, `REDIS_URL`, `NASA_API_KEY` (placeholder value `DEMO_KEY`), `OPENWEATHER_API_KEY` (commented out), `AI_PROVIDER`/`AI_API_KEY`/`AI_MODEL` (all commented out), `UPLOAD_DIR`, `MAX_UPLOAD_SIZE_MB`. No real secret values are present anywhere in the repository.

### Documentation
- Root `README.md`: architecture overview, repo structure, **team allocation table** (P1 Frontend/UX/3D, P2 Backend/DB/APIs, P3 Simulation/Scientific, **P4 AI/Search/Data/Integration** — confirms the current branch owner is P4), quick start.
- `docs/architecture/ARCHITECTURE.md`: 12 architecture principles, system diagram, tech stack table, module dependency table, ERD summary, simulation architecture, dependency graph/implementation order, 6 development phases, and an explicit **"Team Interface Contracts" (§9)** section naming contract files that do not yet exist.
- `docs/architecture/DATABASE.md`: full SQL schema for 11 tables + indexing/migration strategy.
- `docs/api/API.md`: full REST route table + response envelope.
- `docs/decisions/DECISION_LOG.md`: 15 locked decisions + **4 unresolved decisions**, two of which are owned by P4 (semantic search: pgvector vs. external embeddings; weather API: OpenWeatherMap vs. Open-Meteo).
- `docs/demo/DEMO_RUNBOOK.md`: SIH demo script with three fallback modes (Live / Guided / Offline).
- `docs/rkt_spec/RKT_SPEC.md`: `.rkt` JSON project file format v1.0 + validation rules.
- `docs/scientific/MODELS.md`: physics equations for every simulation model.
- `docs/setup/SETUP.md`: dev setup instructions (assumes tooling that doesn't exist yet).
- 11 per-directory `README.md` files, each declaring an owner (P1–P4) and a planned structure.

---

## 2. Contract Registry

All 15 contracts are **MISSING CONTRACT** in code. Status below reflects how much of each shape is at least documented.

| # | Contract | Status | Documented Location | Documented Fields (if any) | Owner | Consumers (planned) |
|---|----------|--------|---------------------|------------------------------|-------|----------------------|
| 1 | **SpaceObject** | MISSING CONTRACT — shape documented as SQL only | `space_objects` table, `docs/architecture/DATABASE.md` | id, name, category, subcategory, description, physical_data (JSONB), orbital_data (JSONB), discovery (JSONB), images (JSONB), source, source_id, last_updated, search_vector | Table: P2. Ingestion/search indexing: **P4** (`data/`, `search/`) | `/explore` pages (P1), search, AI grounding |
| 2 | **Mission** | MISSING CONTRACT — shape documented as SQL + route table | `missions` table (`DATABASE.md`), routes (`API.md`), `MissionConfig` sketch (`simulation/README.md`) | id, project_id, name, objective, target_orbit (JSONB), launch_site (JSONB), environment (JSONB), status | API: P2 (`apps/api/src/missions/`). Sim-side config: P3 | vehicles, simulation engine, `/build`,`/simulate` pages |
| 3 | **Rocket** | MISSING CONTRACT — **name does not exist anywhere**, including docs | N/A | N/A | N/A | N/A |
| 4 | **SimulationResult** | MISSING CONTRACT — sketched as Python dataclass in prose, named as a formal contract | `SimResult` sketch (`simulation/README.md`); `simulation_runs` table (`DATABASE.md`); named explicitly in `ARCHITECTURE.md §9` as `packages/contracts/src/simulation.ts` (file does not exist) | success, outcome, summary (dict), telemetry (list), events (list), errors (list) | Produced by P3; contract co-owned P2↔P3; **file maintenance by P4** per `packages/contracts/README.md` | backend simulation service, `/analysis` page, `/ai/failure-analysis` |
| 5 | **MissionEvent** | MISSING CONTRACT — closest analog is `SimEvent` / `simulation_events` | `simulation_events` table (`DATABASE.md`); Event Types table (`docs/simulation/SIMULATION.md`); `events.py` listed as a planned contracts file | t, event_type, severity, data (JSONB), description | P3 (detection), P2 (persistence) | frontend telemetry timeline, AI |
| 6 | **FailureEvent** | MISSING CONTRACT — shape documented as SQL | `failure_events` table (`DATABASE.md`); failure detection rules table (`SIMULATION.md`) | event_id (FK), subsystem, failure_mode, trigger_condition, trigger_state (JSONB), contributing_factors (JSONB), consequence, educational_explanation, recommended_fix, related_lessons (JSONB) | Detection: P3. Persistence: P2. **Consumed by P4** (`/ai/failure-analysis`) | AI explanation layer, reports |
| 7 | **Telemetry** (TelemetryPoint) | MISSING CONTRACT — shape documented as SQL + sampling rules | `telemetry_points` table (`DATABASE.md`); sampling rules (`SIMULATION.md`); named in `ARCHITECTURE.md §9` and `simulation/README.md` | t, position, velocity, acceleration (JSONB), altitude_m, speed_ms, mass_kg, thrust_n, drag_n, dynamic_pressure_pa, mach_number, stage, phase | P3 produces; `websocket.ts` message format planned but not created | frontend 3D viewport, telemetry graphs, AI |
| 8 | **SearchResult** | MISSING CONTRACT — **no shape specified anywhere**, not even in docs | Only pipeline prose in `search/README.md` | Undefined | **P4** | `/search` page |
| 9 | **SearchResponse** | MISSING CONTRACT — **no shape specified anywhere** | Only the generic `{status,data,meta}` envelope (`API.md`) applies | Undefined | **P4** | `/search` page |
| 10 | **AIResponse** | MISSING CONTRACT — name used once, never defined | Return type in `AIProvider.complete()` sketch, `ai/README.md` | Undefined | **P4** | ai router/service |
| 11 | **SourceReference** | MISSING CONTRACT — **not mentioned anywhere** in the repo | N/A | Undefined — recommend reusing existing `source`/`source_id` provenance vocabulary from `space_objects` | **P4** (net-new) | AI citations/grounding |
| 12 | **Recommendation** | MISSING CONTRACT — only referenced as a capability, never a type | `/ai/recommend` route (`API.md`); "Recommendations" mentioned once in root `README.md` diagram | Undefined | **P4** | `/ai/recommend`, reports |
| 13 | **Conversation** | MISSING CONTRACT — **not mentioned anywhere**; no DB table, no route for history | N/A | Undefined — net-new if multi-turn tutoring needs persisted history | **P4** (net-new) | `/ai/tutor` |
| 14 | **Project** | MISSING CONTRACT (code) but most fully documented | `projects` table (`DATABASE.md`); CRUD routes (`API.md`) | id, user_id, name, description, status, metadata (JSONB) | P2 (`apps/api/src/projects/`) | `/projects/:id` page, missions (1:N) |
| 15 | **Learning content** (Lesson) | MISSING CONTRACT (code), documented as SQL | `lessons` table (`DATABASE.md`); routes `/lessons`, `/lessons/{slug}`, `/lessons/categories`, `/learning/progress` (`API.md`) | title, slug, category, difficulty, summary, content (markdown), equations (JSONB), related_objects/related_lessons/prerequisites (JSONB), search_vector | P2 (API) / **P4** (search indexing — lessons are a searched entity per `search/README.md`) | `/learn` pages, search |

**Naming flag:** the domain model uses **"vehicle"** everywhere (`vehicles`, `vehicle_stages`, `vehicle_components`, `VehicleConfig`), never "Rocket." If a `Rocket` contract is needed, it should alias the existing `vehicle` model rather than being invented as a separate concept — raise with P2/P3 before creating one.

---

## 3. Live Data Integration Audit

Searched the full repository (code + docs) for: NASA, JPL, ESA, ISRO, MPC, CelesTrak, Exoplanet Archive, NTRS, EONET.

| Source | Found? | Where | Status |
|--------|--------|-------|--------|
| **NASA** | Yes (docs only) | `.env.example` (`NASA_API_KEY=DEMO_KEY` placeholder); `data/README.md` table (`api.nasa.gov` — APOD/NEO/Mars Rovers; `data.nasa.gov` — missions/spacecraft catalog); mentioned generically in `README.md`, `DEMO_RUNBOOK.md`, `ARCHITECTURE.md` | Researched/planned only — **zero fetcher code** |
| **JPL** | No | — | Not mentioned anywhere |
| **ESA** | Partial | `docs/architecture/DATABASE.md` line 200, only as an example enum value in a SQL comment (`source -- nasa \| esa \| bundled`) | Not a real integration — just a placeholder enum value |
| **ISRO** | No | (Satish Dhawan Space Centre appears only as an example launch-site name in `docs/rkt_spec/RKT_SPEC.md`, not as an ISRO data integration) | Not mentioned as a data source |
| **MPC** (Minor Planet Center) | No | — | Not mentioned anywhere |
| **CelesTrak** | No | — | Not mentioned anywhere |
| **Exoplanet Archive** | Partial | `docs/architecture/DATABASE.md` line 193, only as an example `category` enum value (`planet \| moon \| asteroid \| star \| galaxy \| nebula \| exoplanet \| spacecraft`) | Not a real integration — just a category label |
| **NTRS** (NASA Technical Reports Server) | No | — | Not mentioned anywhere |
| **EONET** | No | — | Not mentioned anywhere |

Additionally documented (not requested, but found alongside NASA): **Open Notify** (`open-notify.org` — ISS position) and **Solar System OpenData** (`api.le-systeme-solaire.net` — planet/moon data), both in `data/README.md`'s "Verified External Data Sources" table, both unimplemented.

**No implementation exists for any of the above.** No fetch/HTTP client code, no API-key wiring beyond the `.env.example` placeholder, no response parsing, no `data/ingestion/` files.

---

## 4. Existing AI / Search Functionality

- **AI**: A one-paragraph design rule ("AI explains, models calculate") plus a `Protocol` sketch with two method signatures (`complete`, `embed`). No provider implementation, no prompts, no tool schemas, no grounding, no safety/validation code. `AI_PROVIDER` is unset (commented out) — no default provider chosen yet.
- **Search**: A three-step MVP strategy (Postgres FTS → autocomplete → deferred pgvector) documented in prose. No indexing code, no query normalization, no ranking logic.

Both are pure documentation — there is nothing functional to build on top of yet, only a design to follow.

---

## 5. Risks

1. **Contract drift.** `DATABASE.md` and `API.md` describe overlapping shapes independently (e.g., JSONB field names for `target_orbit`, `launch_site`). Without `packages/contracts/src/*` actually existing, any two people coding from the docs in parallel will diverge on field names/casing/enum spellings. This is precisely the problem `packages/contracts/` was created to prevent, and it is currently empty.
2. **Naming collision risk (`Rocket` vs `Vehicle`).** Resolve before any contract file is written, or duplicate/parallel types will appear.
3. **Ownership ambiguity.**
   - `apps/api/src/ai/` and `apps/api/src/search/` are physically inside P2's `apps/api/` (per `apps/api/README.md`, wholly P2-owned) but functionally belong to P4 per the module dependency table in `ARCHITECTURE.md §4`. Who writes `router.py`/`service.py` in these two folders is not stated and should be clarified before either person starts.
   - `packages/shared/src/` has no assigned owner anywhere (the team table only names `packages/contracts` and, implicitly via P1, `packages/ui`).
4. **Contract governance risk.** `packages/contracts/README.md` rule #1 states any contract change "requires agreement from all affected team members." Since `packages/contracts/src/` is currently empty, P4 authoring the *first* versions of `api.ts`, `ai.py`, `events.py`, `websocket.ts` is greenfield authorship affecting the whole team, not just P4's slice — needs explicit sign-off before others build against it, not after.
5. **External-source scope gap.** Only NASA/Open Notify/Solar System OpenData are researched. If stakeholders expect JPL/ISRO/MPC/CelesTrak/Exoplanet Archive/NTRS/EONET specifically (all plausible for a space-exploration platform), that is an unscoped gap — none of these appear in any planning document, so there's no existing agreement to build against.
6. **AI groundedness is a stated rule with no enforcement.** "AI never invents physics" is policy only; `ai/safety/` is empty. This needs to become executable validation once AI work starts, not remain aspirational.
7. **Demo/offline dependency.** `DEMO_RUNBOOK.md` Mode C (fully offline) and `data/README.md`'s fallback strategy both require bundled JSON in `data/fallback/`, currently empty. Demo reliability depends on P4 delivering this ahead of the Phase 5 "Polish & Demo" milestone in `ARCHITECTURE.md`.
8. **Sequencing dependency.** Search needs `space_objects`/`lessons` rows to exist (P2's DB + P4's own ingestion/seeds) before it can do anything. AI grounding needs real `simulation_runs`/`telemetry_points`/`failure_events` (P3/P2) before it has anything true to explain. Building either prematurely produces untestable code.
9. **Zero test scaffolding.** No test framework is configured anywhere in the repo. Any P4 contract or integration needs its own testing setup from scratch — there's no existing convention to follow beyond the naming rule in `tests/README.md` (`test_<module>_<function>_<scenario>.py`).
10. **Two of four unresolved architectural decisions belong to P4** (semantic search approach; weather API choice) per `DECISION_LOG.md` — both are cheap to resolve now and expensive to unwind after code exists that assumes one answer.

---

## 6. Person 4 Integration Boundaries

**P4 owns (per root `README.md` team table):** `ai/`, `search/`, `data/`, `packages/contracts/`.

**P4 likely also authors (needs confirmation — see Risk §5.3):** business logic inside `apps/api/src/ai/` and `apps/api/src/search/` (router + service), even though those directories live inside P2's `apps/api/` tree.

**P4 must NOT modify:** `apps/web/` (P1), `packages/ui/` (P1), `apps/api/src/{auth,users,projects,missions,vehicles,simulation,core,models,schemas}/` (P2), `database/` (P2), `deployment/` (P2), `simulation/` (P3), `scientific/` (P3).

**Shared/contested territory requiring coordination before edits:**
- `packages/contracts/src/*` — P4 maintains per `packages/contracts/README.md`, but content requires sign-off from whichever team owns the other side of each contract (P2 for API types, P3 for simulation/telemetry types).
- `packages/shared/` — no declared owner; clarify before use.
- `database/seeds/` — P2-owned directory, but P4's ingestion pipeline needs to produce data that lands there; coordinate format/idempotency conventions rather than editing P2's scripts directly.

---

## 7. Recommended Architecture (P4 scope only)

- **Contracts first.** Author `packages/contracts/src/api.ts` (subset: space-objects, search, ai, learning endpoints), `ai.py`, `events.py` (if P4 needs event shapes for grounding), and `websocket.ts` (only if AI/search ever streams). Circulate for sign-off per governance rule before writing implementation against them.
- **Data pipeline**, matching the stages already named in `data/README.md`: `ingestion/` (one thin fetch client per source) → `normalization/` (schema validation + unit normalization, reusing `scientific/units` where applicable) → provenance tagging (`source`/`source_id`/`last_updated`, matching the `space_objects` columns already defined in `DATABASE.md`) → `seeds/` (idempotent, matching `database/seeds/` conventions) → `cache/` (simple TTL; Redis optional per `REDIS_URL`) → `fallback/` (bundled JSON mirrors for offline Mode C).
- **Search**: start with Postgres `tsvector`/`tsquery` only, as already decided in `search/README.md` and `DECISION_LOG.md` — no external search infra. `indexing/` maintains the `search_vector` columns; `ranking/` and `suggestions/` are thin layers on top. Defer `pgvector` until the open decision is closed.
- **AI**: implement the `AIProvider` protocol first (`providers/`); wire `prompts/`/`tools/`/`grounding/` to pull only from already-computed simulation output (`simulation_runs`, `telemetry_points`, `failure_events`) — never recompute physics; `safety/` validates AI output against the deterministic source before it reaches the user, turning the stated policy into an actual check.
- Respect **API isolation** (`ARCHITECTURE.md` principle #6): P4's `ai/` and `search/` logic should be plain importable Python modules that `apps/api/src/ai/router.py` / `apps/api/src/search/router.py` call into — not the reverse.

---

## 8. Recommended Implementation Order (P4)

1. **Resolve open questions first** (cheap now, expensive later): the two P4-owned unresolved decisions in `DECISION_LOG.md` (semantic search approach; weather API choice), the `apps/api/src/{ai,search}` ownership question, and the `Rocket` vs `Vehicle` naming question.
2. **Get contract sign-off** from P1/P2/P3 on the specific `packages/contracts/src/*` files P4 needs to create or co-own — this blocks everything downstream per the dependency graph in `ARCHITECTURE.md §7`.
3. **Build `data/fallback/` + `data/seeds/` first**, independent of any live API — this is required for offline Demo Mode C regardless of live-integration progress, and matches the Phase 2 "Space Data + Seeds" milestone.
4. **Build `data/ingestion/`** for the sources already verified in `data/README.md` (NASA APOD/NEO/Mars Rovers, Open Notify ISS, Solar System OpenData) behind the fallback layer (graceful-degradation principle). Do **not** add JPL/ESA/ISRO/MPC/CelesTrak/Exoplanet Archive/NTRS/EONET until a stakeholder explicitly adds them to the verified-sources table — none are currently scoped anywhere in the project.
5. **Implement `search/`** against `space_objects`/`lessons` once P2's ORM models exist — FTS only, per the locked decision.
6. **Implement `ai/`** provider abstraction + grounding once P3/P2 are actually producing `simulation_runs`/`telemetry_points`/`failure_events` — there is nothing true to explain before then.
7. **Draft the genuinely new contracts** (`SourceReference`, `Recommendation`, `Conversation`) as part of steps 5–6, since nothing in current docs specifies their shape — circulate for the same sign-off as step 2 before other teams build against them.
8. **Demo hardening**: verify the offline path (Mode C) end-to-end once ingestion, fallback, search, and AI are all in place, ahead of the final "Demo Harden + Polish" phase.

---

*This document is an audit only. No code was written or modified as part of this task, and no Person 1/2/3-owned files were touched.*
