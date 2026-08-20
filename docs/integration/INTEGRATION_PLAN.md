# Integration Plan

The plan the first-prototype integration followed, and what each phase actually
did. Kept as a record: the reasoning behind an ordering is worth more later than
the ordering itself.

Starting commit: `075cfaa`. Branch: `integration/first-prototype`.

---

## The problem, in one line

Five well-built trees, none of them connected. `apps/api` imported nothing from
`simulation/`, `search/`, `ai/`, `data/` or `contracts/` — roughly 55,000 lines
of physics, retrieval and space-data code with no route in front of it — and the
frontend had no application at all.

The work was therefore **seams**, not features. Almost everything the product
needed already existed somewhere; it just could not be reached.

---

## Ordering principle

Work outward from what the product cannot exist without, and never build on
something unverified.

That put the simulation engine first, ahead of the more visibly broken frontend.
Building a Mission Control page over an engine that divided by mass twice would
have meant building it twice.

---

## Phase 0 — Audit

Read the whole repository, ran every test suite, and wrote
[`REPOSITORY_AUDIT.md`](REPOSITORY_AUDIT.md) before changing anything.

Two things came out of it that changed the plan:

- The reported blocker (`Failed to resolve import "./App"`) was not a deleted
  file. `App.tsx` had never existed in any commit. The frontend was not broken;
  it was unwritten.
- The Python simulation passed all 46 of its tests while being physically wrong.
  Test counts had been standing in for confidence.

Baseline recorded: P4 1419 (after fixes), API 262, TS 570, Python sim 46, web 0.

## Phase 1 — Unblock the test suites

Two one-line fixes took the P4 suite from 15 failures to green: a
`datetime.utcnow()` call that the project's own `filterwarnings` escalated to an
error on Python 3.12, and a test using `asyncio.get_event_loop()` that passed
alone and failed in suite.

Done first because an unreliable suite is worthless as a safety net for
everything after it.

## Phase 2 — Make the simulation real

The centrepiece, and the phase with the most risk.

The brief says Python owns physics. The working physics was 14,000 lines of
tested TypeScript, and the Python engine designated as authoritative was a stub
with no gravity, no drag, no staging and a units error. The brief also forbids a
big-bang rewrite.

Resolution: **complete the Python engine using the physics models already in
`simulation/models/`** — 805 lines of correct, unused code — and port the
*approach* proven by the TypeScript engine rather than the code. Then hold the
two in agreement with a cross-engine regression suite.

Found while doing it: `simulation/models/drag.py` claimed to be ported from the
TypeScript drag model and implemented a different curve. Correcting it moved
orbital drag loss from −32% to −0.1% against the reference.

Result: 46 tests → 106, every trajectory quantity within 2% of the independent
implementation.

## Phase 3 — Open the seams

`apps/api/src/core/engines/` — one module, the only place the backend crosses
into a sibling tree. Then three endpoints:

- `POST /simulations/run`
- `GET /search`
- `POST /ai/ask`, `POST /ai/explain-failure`

Each publishes the engine's own Pydantic contract as its response model, so
OpenAPI describes the real shape rather than a mirrored copy.

`test_openapi_contract.py` listed `/simulations/run` under `MUST_NOT_EXIST`,
blocked on P3. Its own docstring anticipated the case; the blocker was resolved,
so the path moved to `CONTRACT_PATHS` with the reasoning recorded.

Found while doing it: the simulation engine and the AI analyser named the same
failure differently (`INSUFFICIENT_THRUST` vs `insufficient_twr`). Reconciled
with an explicit alias table rather than bending either naming.

## Phase 4 — Build the application

App shell, route table, and the pages the loop needs. Two layouts, because a
first-time visitor should meet the product rather than a dashboard.

The one architectural decision here: `lib/simConfig.ts` is the entire
Python/TypeScript dialect boundary. The builder speaks camelCase, the API speaks
snake_case, and exactly one module translates.

Missions and Learn were pointed at the search API over the bundled corpus rather
than at the database — which turned out to matter, because it is why those
surfaces work today despite the database being blocked.

## Phase 5 — Verify end to end

`apps/web/e2e/journey.mjs` drives the whole loop through the real API and the
real builder. 56 checks.

It found two things:

- Its own first test rocket had a liftoff TWR above 3 and was destroyed at
  max-Q for exceeding its airframe's 65 kPa limit. The engine was right; the
  fixture was unrealistic. Real launchers fly 1.2–1.5 for exactly this reason.
- Database-backed endpoints returned 500 when PostgreSQL was unreachable, while
  `/health/ready` correctly called the same condition 503. The raw asyncpg
  error escapes before SQLAlchemy wraps it, so it reached the catch-all handler.
  Translated at the dependency boundary.

## Phase 6 — Close the quality gaps

Frontend tests (there were none), the dependency audit (7 vulnerabilities → 0),
and the small config errors the audit had listed: `CORS_ORIGINS` naming the
wrong port, an unused `VITE_API_URL` acting as a second source of truth, a
committed build artifact.

## Phase 7 — Documentation

Rewritten against the code. `ASSUMPTIONS.md` in particular now names the file
that makes each approximation, so every claim can be checked.

---

## What was preserved

Nothing was deleted. The TypeScript physics engine, the P4 data/search/AI trees,
the P2 backend and migrations, the UI kit and design tokens, and the existing
`docs/backend/` documentation were all good work and all remain.

The TypeScript `sim/` layer is no longer on the product's path but is retained
deliberately: it is the regression oracle that keeps the Python engine honest.

## What was changed rather than replaced

| Thing | Change |
|---|---|
| `simulation/engine/runner.py` | Rewritten — it was a stub |
| `simulation/models/drag.py` | Corrected to match its stated source |
| `apps/web/src/stores/authStore.ts` | Session restore added |
| `apps/web/src/lib/api-client.ts` | Error typing, network-failure distinction, `meta` support |
| `apps/api/src/core/database/__init__.py` | Connection failures become 503 |
| `ai/analysis/simulation_view.py` | Alias table for the engine's failure vocabulary |
| `apps/web/src/components/layout/Sidebar.tsx` | Nav regrouped to match the real routes |

## Sequencing that would have gone wrong

- **Frontend first.** Mission Control would have been built against a broken
  engine and then rebuilt.
- **Rewriting the TypeScript physics into Python.** Weeks of work, high risk,
  and it would have discarded the only implementation that was known to work.
- **Fixing the docs early.** They would have described an architecture that had
  not settled yet.
- **`npm audit fix --force` at the start.** It wanted a major vite upgrade. Done
  before any frontend code existed, that was free; done later, it would have
  broken a working build.
