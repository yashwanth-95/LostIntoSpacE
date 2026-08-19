# Repository Audit — Phase 0

**Audit date:** 2026-08-20
**Baseline commit:** `075cfaa` (`Person 4 - recommit (#6)`)
**Integration branch:** `integration/first-prototype`
**Auditor:** Integration pass, first-prototype endgame

This document records the repository **as found**, before integration work. It
is deliberately blunt about what does not work. Statuses here are evidence-based:
every "works" claim below was produced by running the code, not by reading it.

---

## A. Repository structure

A polyglot monorepo. Four contributors worked in largely disjoint trees, which
is why there are few merge conflicts — and also why almost nothing is wired
together.

```
apps/web/                 P1  React + Vite frontend
apps/api/                 P2  FastAPI backend
database/                 P2  Alembic migrations + seeds
packages/simulation-engine/ P3 TypeScript physics + Three.js renderer
simulation/               P3  Python simulation (partial migration target)
scientific/               P3  empty scaffolding (.gitkeep only)
packages/contracts/       P4  Python Pydantic contracts
data/                     P4  space-data models, source adapters, provenance
search/                   P4  keyword + semantic + hybrid search
ai/                       P4  providers, RAG, grounding, assistant, safety
evaluation/               P4  retrieval/answer evaluation harness
packages/shared/          —   empty (.gitkeep only)
packages/ui/              —   empty (.gitkeep only)
assets/, scripts/, deployment/, .github/, tests/  — empty scaffolding
```

### Size of each area

Measured in lines of `.py`/`.ts`/`.tsx`, excluding `node_modules`:

| Area | Lines | Owner |
|---|---:|---|
| `data/` | 22,053 | P4 |
| `packages/simulation-engine/src` | 14,028 | P3 |
| `ai/` | 10,901 | P4 |
| `search/` | 6,808 | P4 |
| `apps/api/src` | 4,872 | P2 |
| `simulation/` (Python) | 2,119 | P3 |
| `evaluation/` | 1,936 | P4 |
| `database/` | 1,541 | P2 |
| **`apps/web/src`** | **1,421** | **P1** |
| `packages/contracts/src` | 1,229 | P4 |

The single most important number here is the last-but-one: **the frontend is the
smallest non-empty tree in the repository**, and it contains no pages.

---

## B. Current architecture

There is no current architecture in the integrated sense. There are five
well-built islands and no bridges:

```
apps/web  ──✗──  apps/api  ──✗──  data/ search/ ai/     (P4 engines)
   │                 │
   ✗                 ✗
   │                 │
packages/simulation-engine   simulation/  (two separate engines)
```

Verified by grep: **`apps/api/` does not import `data`, `search`, `ai`,
`contracts`, or `simulation` anywhere.** The backend is a pure persistence
layer that stores rows P4 is expected to insert out-of-band. The 40,000 lines
of P4 retrieval/AI/space-data engine and the P3 simulation engine are not
reachable from any HTTP endpoint.

---

## C. Frontend architecture

**Status: the application does not exist.** `apps/web/src` contains a shell,
a UI kit, and two stores — and no application.

What is present and good:

- `components/layout/AppShell.tsx` — sidebar + topbar + `<Outlet/>`, Ctrl+K wiring
- `components/layout/Sidebar.tsx` — 10 nav items with inline SVG icons
- `components/layout/TopBar.tsx` — search trigger, auth-aware account button
- `components/ui/` — Badge, Button, Card, EmptyState, ErrorPanel, Input, Modal, Select, Spinner, Tabs
- `lib/api-client.ts` — typed fetch wrapper, bearer token, 401→logout
- `stores/authStore.ts`, `stores/uiStore.ts` — Zustand
- `types/contracts/` — TS mirrors of P4 contracts (ai, analysis, provenance, search)
- `tailwind.config.ts` — a genuine space palette and type scale, not a default theme

What is missing:

- **`src/App.tsx` does not exist.** `main.tsx` imports `./App`; nothing provides it.
- **`src/pages/` contains only `.gitkeep`.** There are zero page components.
- No router configuration. No route table. Every `NavLink` in the sidebar points
  at a path that has no route.
- No auth pages, no landing page, no Explore, Catalog, Learn, Rocket Lab,
  Builder, Launch, Simulator, Missions, Search, AI, Help, Workspace.
- No data-fetching hooks or services (`services/` is `.gitkeep`).
- No tests. No `vitest.config.ts`, no test setup, despite `vitest` being a
  declared dependency and `npm test` being a declared script.
- `postcss.config.js` and `globals.css` exist, so styling would work once
  pages exist.

### The reported blocker, explained

```
Failed to resolve import "./App" from "src/main.tsx"
```

This is **not** a stale `main.tsx` and **not** a deleted file. Checked against
git history: `App.tsx` has never existed in any commit on `main`. `main.tsx`
was written against an application that was never implemented before the
frontend PR landed ("first frontend, incomplete (#3)" — the commit message is
accurate). The shell, the UI kit, and the design tokens are the finished part;
the application is the unfinished part.

Creating a stub `App.tsx` would suppress the error and leave the product empty.
The real repair is to build the application the shell was designed to host.

---

## D. Backend architecture

**Status: solid, well-documented, and genuinely working — but incomplete in
scope.** This is the strongest engineering in the repository per line.

- FastAPI app factory in `src/main.py` with lifespan, lazy engine creation
  (the app boots and answers `/health` with no database running — a deliberate,
  documented choice)
- `src/api_router.py` mounts everything under `/api/v1`
- Consistent response envelope (`src/core/envelope/`): `{status, data, meta}` /
  `{status, error:{code,message,details}}`
- Exception handlers, request-logging middleware, CORS from settings
- Settings via `pydantic-settings` reading the repo-root `.env`
- `validate_production_safety()` refuses to boot in production with the example
  secret key
- Liveness (`/health`) and readiness (`/health/ready`) correctly separated

### Endpoints that exist

| Prefix | Endpoints |
|---|---|
| `/auth` | register, login, me, refresh, logout |
| `/users` | me (get/patch), preferences (get/patch) |
| `/projects` | CRUD + versions list/create |
| `/missions` | CRUD + events list/create |
| `/vehicles` | CRUD + components list/create; `/components` patch/delete |
| `/lessons` | list, categories, detail |
| `/learning/progress` | get, create, patch |
| `/space-objects` | list, categories, detail |
| `/conversations`, `/ai/conversations` | CRUD + messages list/create |
| `/health`, `/health/ready` | liveness, readiness |

### Endpoints that do not exist

- **`/simulations` — nothing.** `src/simulation/` contains only `.gitkeep`.
  There is no way to run a simulation over HTTP. This is the single largest
  backend gap, because the simulation is the product's centrepiece.
- **`/search` — nothing.** `src/search/` contains only `.gitkeep`. The 6,808-line
  P4 search engine is unreachable.
- **AI is persistence-only.** `/conversations` stores messages. Nothing calls a
  model, retrieves context, or grounds an answer. `ai/service.py` says so
  explicitly in its docstring: P4 is expected to post finished assistant
  messages in. No endpoint does that.
- `/reports` — `.gitkeep` only.

So of the nine product surfaces the prototype needs, the backend fully serves
the CRUD half and none of the compute half.

---

## E. Database architecture

**Status: schema is complete and well-designed; not verifiable in this
environment (see §Q).**

- Alembic with **native async** (asyncpg for both app and migrations — a good
  call, documented in `migrations/env.py`, removes the usual psycopg2 split)
- Eight hand-numbered migrations, `0001_baseline` → `0008_user_preferences`
- Deterministic constraint naming convention on the metadata
- `UUIDPrimaryKeyMixin` using `gen_random_uuid()` (PG13+, no pgcrypto)
- `TimestampMixin` / `CreatedAtMixin`
- Models: user, project, vehicle, simulation, content, learning, conversation
- `SpaceObject.search_vector` is a **generated** tsvector column, so full-text
  search works on any row inserted by any path — a genuinely good decision
- `database/scripts/setup_local_db.sql` is idempotent and stores no password
  (passed as a psql variable at run time)
- Seeds exist: `database/seeds/{demo_data,seed_all}.py`

Table coverage matches the product: users, refresh tokens, projects +
versions, vehicles + components, missions + events, simulation results,
space objects, lessons, learning progress, conversations + messages,
user preferences.

**No duplicate models were found.** P2's schema is the single canonical
persistence layer, and nothing else in the repo defines competing tables.

---

## F. Authentication architecture

**Status: backend complete, frontend absent.**

Backend: bcrypt password hashing, JWT access + refresh tokens, `get_current_user`
dependency, ownership helpers in `core/authz.py` (`get_owned_project` etc.), and
262 passing tests including a dedicated `test_security.py`. Authorization is
enforced per-resource by owner, and conversations propagate ownership to
messages.

Frontend: `authStore` holds `user`/`token`/`isAuthenticated` and the API client
attaches the bearer token and logs out on 401. But there is **no login page, no
signup page, no protected-route wrapper, no session restore on reload, and no
guest mode**. The token is held in memory only, so any refresh loses the
session.

---

## G. Simulation architecture

**Status: two engines, and the wrong one is authoritative.**

### The TypeScript engine — `packages/simulation-engine/` — excellent

14,028 lines, **570 tests passing in 4.2 s**. Verified by running the suite.

Layering is enforced at build time (`tsconfig.headless.json` compiles
`physics`/`core`/`sim` without the DOM lib, and `tests/architecture.test.ts`
asserts the dependency direction):

```
physics → core → sim → renderer → adapters
                   ↘ integration
```

- `physics/`: vec3, constants, gravity, atmosphere (layered ISA), drag,
  thrust, **RK4 integrator**, orbital elements, frames (ENU↔ECI), stability
- `sim/`: config, state, forces, guidance (gravity turn), mission-state machine
  (601 lines), failures (842 lines, seeded RNG), telemetry sampler, runner (1,304 lines)
- `renderer/`: scene manager, planet, rocket mesh, trajectory, camera rig,
  effects, scale
- `core/`: component registry, catalog (981 lines), rocket design, builder,
  validation
- `adapters/`: `useSimulation`, `useRocketBuilder`, `RocketViewer`

It has determinism tests that assert identical telemetry across runs of a
long multi-stage ascent, and a performance test that completes a full orbital
ascent in ~317 ms. This is real, tested, credible physics.

### The Python engine — `simulation/` — a stub with a physics bug

2,119 lines, 46 tests passing. But the tests do not test physics.

`simulation/engine/runner.py::run_simulation` is the whole engine, and it:

```python
state.acceleration_ms2 = max(0.0, state.thrust_N / max(state.mass_kg, 1.0)) / max(state.mass_kg, 1.0)
```

**divides by mass twice** — the result is not an acceleration and the units are
wrong (m·s⁻²·kg⁻¹). Beyond that bug it has:

- **no gravity** — nothing decelerates the vehicle, so it can never fall back
- **no drag** — `drag_N` is hardcoded 0.0
- **no atmosphere** — `air_density_kgm3` hardcoded 0.0, `dynamic_pressure_Pa` 0.0
- **no staging** — only `stages[0]` is ever read, `stages_separated` always 0
- **no orbital mechanics** — all six orbital fields hardcoded 0.0, `in_orbit` always False
- **no failures** — the `failures` list is built and never appended to
- **no guidance** — `pitch_rad`/`yaw_rad`/`angle_of_attack_rad` hardcoded 0.0
- **fixed Isp of 280 s** hardcoded in the mass-flow term regardless of the engine
- Euler integration at the powered timestep, not RK4
- `fuel_fraction` hardcoded 1.0 while mass is being decremented — self-contradictory

Meanwhile `simulation/models/{gravity,drag,atmosphere,thrust,constants}.py`
contain **805 lines of correct, usable physics that `run_simulation` never
imports**. The models were written; the engine was never connected to them.

This matters because the product brief forbids exactly this: "The simulation
must NOT be a fake animation pretending to be physics." Today the Python path
is that fake, and it is the path the architecture designates as authoritative.

### Contracts

`simulation/contracts/__init__.py` is good work: Pydantic models for
`SimConfig`, `TelemetryPoint`, `SimEvent`, `FailureDetail`, `SimResult`,
`MissionState` (all 19 states), `StageStatus`, mirroring the TS interfaces.
The contract is sound. Only the engine behind it is hollow.

---

## H. 3D architecture

**Status: renderer exists and is tested; nothing renders it.**

`packages/simulation-engine/src/renderer/` (1,584 lines) has a scene manager,
planet with atmosphere shell, rocket mesh, trajectory ribbon, camera rig with
follow modes, and exhaust/effects — with 58 passing tests. `RocketViewer.tsx`
is a React Three Fiber adapter over it.

Three.js and `@react-three/fiber` are **optional peer dependencies** of the
engine package and are **not dependencies of `apps/web`**. So the renderer
cannot currently be mounted by the web app: the packages are not installed
there. Nothing imports `RocketViewer` anywhere in the repository.

---

## I. AI architecture

**Status: engine excellent, entirely unreachable.**

`ai/` is 10,901 lines and the design is genuinely good:

- `providers/` — `AIProvider` base + registry + mock. Provider-agnostic, as
  the brief requires. No provider is hardcoded into callers.
- `grounding/` — RAG, citations, live sources, context assembly
- `safety/` — claim checking, sanitization, source validation
- `analysis/` — **failure analysis and a simulation view**: code that turns a
  simulation failure into a grounded explanation already exists
- `assistant/`, `missions/`, `recommendations/`, `context/`, `prompts/`

**Only a mock provider is implemented.** `providers/mock.py` is the sole
concrete provider; there is no OpenAI/Anthropic/local adapter. `.env.example`
has `AI_PROVIDER`/`AI_API_KEY`/`AI_MODEL` commented out. So the AI works
end-to-end in tests and would return mock text in production.

Nothing in `apps/api` imports `ai`. There is no `/ai/ask` endpoint.

---

## J. Search architecture

**Status: engine excellent, entirely unreachable.**

`search/` is 6,808 lines: keyword index + tokenizer, embeddings provider and
service, in-memory vector store, semantic retrieval, hybrid ranking with
reciprocal-rank fusion, a reranker, and intent classification. It ships its own
evaluation harness (`search/evaluation/`) with MRR and recall@5 metrics, and the
tests assert that hybrid **measurably beats** keyword-only and semantic-only
baselines. That is unusually disciplined for a prototype.

Not exposed by any endpoint. `apps/api/src/search/` is `.gitkeep`.

The frontend has a `SearchModal.tsx`, which is the only feature component that
exists — and it has no route, no page, and no backend to call.

---

## K. Space-data architecture

**Status: the most complete subsystem in the repository.**

`data/` is 22,053 lines:

- `models/` — canonical `SpaceObject`, orbit, physical, observation, mission,
  event, document, learning, units, enums
- `sources/` — NASA, JPL, ESA, ISRO, CelesTrak, MPC, Exoplanet Archive, plus
  a shared `base`/`http`/`ratelimit`/`errors`/`registry` framework
- `normalization/` — one normalizer per source
- `provenance/` — attribution, freshness, lineage
- `validation/` — authority ranking, range checks, issue reporting
- `cache/`, `offline/` — including an offline package for demo-without-network
- `entity_resolution/`, `ingestion/` — pipeline with plans and reports

Provenance is preserved per record, source authority is ranked, and there is a
deliberate offline fallback path. This directly satisfies the brief's data
requirements — it just needs to be connected to the API.

---

## L. External APIs

| Service | Adapter | Credential | Reachable from app? |
|---|---|---|---|
| NASA | `data/sources/nasa.py` | `NASA_API_KEY` (user has set one) | No endpoint |
| JPL | `data/sources/jpl.py` | none | No endpoint |
| ESA | `data/sources/esa.py` | none | No endpoint |
| ISRO | `data/sources/isro.py` | none | No endpoint |
| CelesTrak | `data/sources/celestrak.py` | none | No endpoint |
| Minor Planet Center | `data/sources/mpc.py` | none | No endpoint |
| Exoplanet Archive | `data/sources/exoplanet_archive.py` | none | No endpoint |
| AI provider | `ai/providers/` | `AI_API_KEY` (unset) | Mock only |

All adapters share timeout/retry/rate-limit handling through
`data/sources/http.py` and `ratelimit.py`. Live tests are gated behind
`LOSTINTOSPACE_LIVE_TESTS=1` and skip by default — correct behaviour.

---

## M. Environment variables

`.env.example` is complete and well-commented; `.env` exists locally and is
correctly git-ignored. Full table in
[`docs/getting-started/ENVIRONMENT.md`](../getting-started/ENVIRONMENT.md).

Issues found:

1. **`DATABASE_URL` in the local `.env` still carries the example default
   password** (`postgresql+asyncpg://lostintospace:password@...`). PostgreSQL 16
   is running and accepting connections, but authentication as `lostintospace`
   fails. This blocks all live-database verification. **User action required.**
2. `CORS_ORIGINS` defaults to `http://localhost:5173`, but Vite is configured to
   serve on **port 3000**. Direct cross-origin calls would be blocked. Currently
   masked because Vite proxies `/api` same-origin, but the value is wrong.
3. `VITE_API_URL` is `http://localhost:8000/api/v1` while `api-client.ts`
   hardcodes the relative `/api/v1`. The variable is unused — two sources of
   truth, one of them dead.

No secrets are committed. No credentials appear in any tracked file.

---

## N. Existing tests

Baseline, all measured by running them on this machine:

| Suite | Command | Result |
|---|---|---|
| P4 (`data`+`search`+`ai`) | `pytest` (repo root) | **1419 passed, 16 skipped** ✅ |
| Backend | `pytest` (in `apps/api`) | **262 passed, 49 skipped** ✅ |
| TS simulation engine | `vitest run` | **570 passed** ✅ |
| Python simulation | `pytest simulation/tests` | 46 passed ⚠️ (see below) |
| **Frontend** | `npm test` | **no tests exist** ❌ |
| `tests/` (root e2e/integration) | — | **empty scaffolding** ❌ |

The P4 suite did **not** pass as found — 15 tests failed/errored. Two root
causes, both fixed during this audit:

- `search/ranking/intent.py` called `datetime.utcnow()`, deprecated in
  Python 3.12; the project's own `filterwarnings = ["error::DeprecationWarning:search.*"]`
  escalated it to a hard error, taking down 11 search tests and 4 AI tests.
- `ai/tests/test_live_sources.py` used `asyncio.get_event_loop().run_until_complete()`,
  which raises on 3.12 once an earlier test has closed the loop. Passed alone,
  failed in suite.

The 46 Python simulation tests pass while the engine is physically wrong, which
means they assert plumbing (shapes, enums, serialization) rather than physics.
No test asserts that a vehicle falls under gravity, that drag opposes motion, or
that mass decreases at the right rate — so none of them caught the double
mass division.

The 49 skipped backend tests are the live-database ones; they skip because
`TEST_DATABASE_URL` is unset. That is correct design, but it means **the
database layer has never actually been executed** in this environment.

---

## O. Existing documentation

Substantial and, unusually, mostly accurate — 21 markdown files. `docs/backend/`
is the strongest (`API_CONTRACT`, `DATABASE_CONTRACT`, `SCHEMA_DECISIONS`,
`KNOWN_ISSUES`, `DATABASE_SETUP`, `INTEGRATION_CONTRACT`, `BACKEND_STATE`).
`docs/decisions/DECISION_LOG.md` and `docs/simulation/` are real.

Gaps: no `docs/README.md` index, no root-level getting-started that actually
works end-to-end, no contributor guide, and the root `README.md` describes an
architecture more integrated than what exists. `docs/simulation/ARCHITECTURE.md`
describes the Python engine as though it were implemented.

---

## P. Existing deployment configuration

**None.** `deployment/docker/`, `deployment/nginx/`, `deployment/scripts/`,
`.github/workflows/`, and `.github/ISSUE_TEMPLATE/` all contain only `.gitkeep`.
There is no CI, no Dockerfile, no compose file. Not required for the first
prototype, but worth stating plainly.

---

## Q. Broken functionality

Ordered by severity.

| # | Issue | Impact |
|---|---|---|
| Q-1 | **Frontend has no application** — no `App.tsx`, no router, zero pages | The product cannot be used at all. This is the reported blocker. |
| Q-2 | **Python simulation is physically wrong** — double mass division, no gravity/drag/staging/orbit/failures | The centrepiece feature is a fake, and the brief explicitly forbids it |
| Q-3 | **No `/simulations` endpoint** | Simulation cannot be run over HTTP by anything |
| Q-4 | **No `/search` endpoint** | 6,808-line search engine unreachable |
| Q-5 | **No AI inference endpoint** | 10,901-line AI engine unreachable; `/conversations` only stores text |
| Q-6 | **Backend imports no P3/P4 code at all** | The compute half of the product is orphaned |
| Q-7 | Database credentials invalid in `.env` | No live DB verification possible — **needs user action** |
| Q-8 | P4 suite failed on Python 3.12 (15 tests) | **Fixed in this pass** |
| Q-9 | `CORS_ORIGINS` names port 5173; Vite serves 3000 | Any non-proxied call fails |
| Q-10 | Three.js / R3F not installed in `apps/web` | Renderer cannot be mounted |
| Q-11 | Auth token in memory only, no session restore | Refresh silently logs the user out |
| Q-12 | No frontend tests, no e2e tests | No regression safety on the surface users touch |

---

## R. Duplicate functionality

Genuinely little duplication — the ownership split worked. Three real cases:

1. **Two simulation engines** (TS `packages/simulation-engine/src/sim/` vs
   Python `simulation/`). Not accidental: this is P3's planned migration,
   mid-flight. Resolution in §W.
2. **Two contract definitions** — `packages/contracts/src/contracts/*.py` (P4,
   Pydantic) and `apps/web/src/types/contracts/*.ts` (P4's TS mirror), plus
   `simulation/contracts/` mirroring the TS `sim/` types, plus `apps/api/src/schemas/`.
   Four places define overlapping shapes. They currently agree; nothing enforces
   that they keep agreeing.
3. **Conversations router mounted twice** (`/conversations` and
   `/ai/conversations`). Deliberate and documented — same router, two prefixes,
   no duplicated logic. Harmless; keep.

Empty duplicates to note: `packages/ui/` and `packages/shared/` are empty while
`apps/web/src/components/ui/` holds the real UI kit. `scientific/` is empty
while `simulation/models/` holds the real physics models.

---

## S. Architectural conflicts

1. **Which simulation engine is authoritative?** The brief says Python owns
   physics and TypeScript owns rendering. The repository's *working* physics is
   in TypeScript; the Python engine designated as authoritative is a stub. This
   is the central architectural conflict of the integration.
2. **Where does search live?** P2's `space_data/service.py` implements search as
   PostgreSQL full-text over a generated `tsvector`. P4 implements hybrid
   semantic search in `search/`. Both are reasonable; they are not reconciled,
   and the brief forbids "separate incompatible search systems".
3. **Who owns AI orchestration?** P2's docstrings say P4 posts finished messages
   into `/conversations`. P4 has no HTTP client and no endpoint to post to.
   Neither side owns the seam, so it does not exist.
4. **Python version floor split.** Root `pyproject.toml` targets **≥3.9** and
   forbids `X | Y` annotations; `apps/api/pyproject.toml` targets **≥3.11** and
   uses them freely. Running environment is 3.12. Two trees, two dialects, one
   interpreter.
5. **Frontend port vs CORS origin** (Q-9) — a config-level instance of the same
   "nobody owned the seam" pattern.

---

## T. Missing MVP functionality

Against the brief's definition of done:

| Surface | State |
|---|---|
| Landing page | Missing entirely |
| Explore | Missing (backend `/space-objects` exists) |
| Catalog | Missing (backend exists) |
| Space-object detail | Missing (backend exists) |
| Learning paths/courses/lessons/quizzes | Missing (backend `/lessons` + progress exist) |
| Rocket Lab / component catalog | Missing (TS `core/catalog.ts` has 981 lines of components) |
| Rocket Builder | Missing (TS `useRocketBuilder` + `builder.ts` exist) |
| Launch configuration | Missing entirely |
| Mission simulation | Backend missing; Python engine hollow |
| Telemetry / Mission Control | Missing entirely |
| 3D visualization | Renderer exists, unmounted |
| Missions library | Missing (backend `/missions` exists) |
| Search UI | `SearchModal` only, no route, no backend |
| AI assistant | Missing (engine exists, unreachable) |
| Help / FAQ / Guide / Contact | Missing entirely |
| Auth UI (sign in/up/logout/guest) | Missing (backend complete) |
| Workspace / projects / favorites | Missing (backend complete) |

The pattern is consistent: **the backend and the engines are far ahead of the
surface.** Most missing MVP functionality is a frontend and a seam, not a new
subsystem.

---

## U. Security risks

Reviewed `apps/api` auth, authz, config, error handling, and the data layer.

**Good:** bcrypt hashing; JWT with separate access/refresh lifetimes;
per-resource ownership checks in `core/authz.py`; `debug=False` pinned on the
FastAPI app so stack traces never reach clients; `validate_production_safety()`
blocking the default secret in production; `plainto_tsquery` (not `to_tsquery`)
so user input cannot be a tsquery injection; readiness endpoint deliberately not
echoing the connection string on failure; all SQL through SQLAlchemy constructs —
no string-built queries found; secrets read from env only; live tests gated.

**Risks carried into integration:**

| # | Risk | Severity |
|---|---|---|
| U-1 | `SECRET_KEY` is the example default in local `.env`; only production is guarded | Medium |
| U-2 | No rate limiting anywhere — auth endpoints included | Medium |
| U-3 | No security headers (CSP, X-Frame-Options, HSTS) | Low for MVP |
| U-4 | Simulation endpoint does not exist yet; when added it **must** accept structured config only, never arbitrary expressions | High if done wrong |
| U-5 | Token in memory on the client; localStorage persistence must not be added carelessly (XSS exposure) | Design decision needed |
| U-6 | `CORS_ORIGINS` misconfigured (Q-9) — wrong now, and tempting to "fix" with `*` | Medium |

No committed secrets. No `eval`/`exec` on user input found anywhere. No file
upload endpoints exist despite `UPLOAD_DIR` being configured.

---

## V. Dependency risks

**Frontend:** `apps/web/node_modules` is installed (340 packages).
`package-lock.json` is untracked — it should be committed. React 18.3, Vite 5.3,
Tailwind 3.4, React Router 6.26, TanStack Query 5.51, Zustand 4.5 — all current
enough and mutually compatible. `lucide-react` and `framer-motion` are declared
but unused (the sidebar hand-rolls its SVGs, with a comment saying lucide would
replace them). Three.js and R3F are **not** installed but are needed to mount
the renderer.

**Python:** the `.venv` as found contained only pydantic, numpy, and pytest —
so neither the backend nor the P4 data layer could run. Installing the declared
dependencies of both manifests was required to execute anything, and revealed
that `httpx` was missing for the entire `data/` tree. Two manifests
(`pyproject.toml`, `apps/api/pyproject.toml`) with different Python floors and
no lockfile on either side.

`packages/simulation-engine` correctly declares three/R3F/react as **optional
peer** dependencies, so physics consumers do not pull in Three.js. Good design.

A `tsconfig.tsbuildinfo` is committed in `packages/simulation-engine/` — build
artifact, should be ignored.

---

## W. Recommended changes

The audit's conclusion is that this repository does not need a rewrite. It needs
**seams**. Four islands of good work need bridges, one hollow engine needs
filling, and one missing application needs building.

### W-1. Build the frontend application (largest item)

Create `App.tsx` and a real route table, then implement the pages the shell was
designed to host. Reuse the existing UI kit, tokens, stores, and API client —
all of which are good. Split routes into a **public** layout (landing, help,
FAQ, guide, contact, auth) and the **app shell** layout for everything else, so
guest mode and the cinematic landing page are not forced through the sidebar
chrome.

### W-2. Make the Python simulation real

Do not rewrite 14,000 lines of tested TypeScript into Python — the brief itself
forbids a big-bang rewrite. Instead:

- Connect `run_simulation` to the physics models that already exist in
  `simulation/models/` (gravity, drag, atmosphere, thrust)
- Replace Euler with RK4, matching the TS integrator
- Implement staging, mass flow from actual Isp, guidance pitch program,
  orbital elements, mission-state transitions, and the failure system
- Port the *approach* proven by the TS engine, and use the TS engine as a
  **regression oracle**: the same vehicle and mission should produce
  trajectories that agree within a documented tolerance
- Write physics tests that would have caught the double mass division

### W-3. Add the missing endpoints and the P3/P4 seams

- `POST /api/v1/simulations` — structured config in, `SimResult` out; **no
  arbitrary code paths** (U-4)
- WebSocket telemetry for live runs; HTTP for config and saved results
- `GET /api/v1/search` — backed by P4 hybrid search
- `POST /api/v1/ai/ask` — backed by P4 grounded RAG, citations preserved
- Make `apps/api` import the P4/P3 trees through a thin, tested adapter layer
  rather than reaching into them from route handlers

### W-4. Reconcile search

Use P4 hybrid search as the platform-wide search, and keep P2's PostgreSQL
full-text as the per-resource filter it already is (`?q=` on `/space-objects`).
Document the split so it stays intentional rather than accidental.

### W-5. Unify the contracts

Pick one source of truth per shape and generate the rest. The strongest existing
asset is the Pydantic contracts; OpenAPI already falls out of FastAPI. Generate
the TypeScript types from the OpenAPI schema instead of hand-mirroring them.

### W-6. Fix the small correctness items

`CORS_ORIGINS` → 3000; commit the lockfile; ignore `tsbuildinfo`; either use
`VITE_API_URL` or delete it; install three/R3F in `apps/web`; add session
restore to the auth store.

### W-7. Close the test gaps

Frontend has none and the root `tests/` tree is empty scaffolding. Add frontend
component tests and one true end-to-end journey that exercises the full loop the
brief specifies.

### What to preserve untouched

The TS physics/renderer engine, the P4 data/search/AI trees, the P2 backend and
migrations, the UI kit and design tokens, and the existing documentation in
`docs/backend/`. All of it is good work. Nothing in this audit recommends
deleting any of it.

---

## Baseline for comparison

Recorded so later phases can prove they did not regress anything:

```
P4  (data + search + ai)   1419 passed, 16 skipped
API (apps/api)              262 passed, 49 skipped
TS  (simulation-engine)     570 passed
Py  (simulation)             46 passed
Web (apps/web)              no tests, application does not build
```
