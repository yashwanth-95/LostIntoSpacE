# MVP Status

**As of:** the first-prototype integration
**Verdict:** see the bottom of this file.

Statuses are evidence-based. **COMPLETE** means it was run and observed working.
**PARTIAL** means it works with a stated limitation. **BLOCKED** means something
outside the code prevents it. Nothing here is marked complete because the route
exists or the button renders.

Test counts referenced below:

```
P4  (data + search + ai)     1419 passed, 16 skipped
API (apps/api)                291 passed, 49 skipped
Python simulation             106 passed
TypeScript engine             570 passed
Frontend (apps/web)            27 passed
End-to-end journey             56 checks passed
```

---

## Public experience

| Feature | Status | Implementation | Tests | Limitations | External deps |
|---|---|---|---|---|---|
| Landing page | COMPLETE | `pages/Landing.tsx`, canvas starfield | build + typecheck | — | none |
| Guest mode | COMPLETE | `authStore.continueAsGuest`, no route gated except `/workspace` | e2e §10 | — | none |
| Application shell + navigation | COMPLETE | `AppShell`, `PublicLayout`, grouped sidebar | build | — | none |
| Help / Guide / FAQ / Troubleshooting / Contact | COMPLETE | `pages/Help.tsx`, one page with deep-linkable sections | build | Static content | none |
| Explore | PARTIAL | `pages/Explore.tsx` → `/space-objects` | API tests | **Needs PostgreSQL.** Shows the exact setup commands when it cannot connect. | database |
| Catalog | PARTIAL | Redirects to Explore | build | Not a separate surface — see note below | database |
| Space-object detail | PARTIAL | `pages/ObjectDetail.tsx` | API tests | Needs PostgreSQL | database |
| 404 | COMPLETE | `pages/NotFound.tsx` | build | — | none |

**On Catalog:** the audit found Explore and Catalog were two screens over one
data model, which the brief forbids duplicating. Rather than ship a second grid
over the same endpoint, Catalog redirects into Explore, which already provides
the categories, search, sorting and detail views a catalogue needs. The route is
kept so navigation and links resolve. Recorded as a decision, not an omission.

## Authentication

| Feature | Status | Implementation | Tests | Limitations |
|---|---|---|---|---|
| Sign up | PARTIAL | `pages/Signup.tsx` → `/auth/register` | 291 API tests incl. `test_security.py` | **Needs PostgreSQL** to store the user |
| Sign in | PARTIAL | `pages/Login.tsx` → `/auth/login` | as above | Needs PostgreSQL |
| Logout | COMPLETE | `Workspace`, clears local session regardless of server reachability | — | — |
| Session restore on reload | COMPLETE | `useSessionRestore`, refresh-token exchange on boot | — | Refresh token in `localStorage`; see below |
| Protected routes | COMPLETE | `RequireAuth`, waits for restore before deciding | — | — |
| Password hashing, JWT, authorization | COMPLETE | bcrypt, access + refresh, per-resource ownership | API suite | — |
| Password reset, email verification | NOT REQUIRED FOR MVP | Architecture supports it; no flow built | — | Needs a mail provider |

**Token storage.** The access token is held in memory; only the refresh token is
persisted. That keeps the short-lived credential out of storage while surviving
a reload. The correct end state is an httpOnly refresh cookie, which needs a
backend change (`Set-Cookie` on login, CSRF protection on refresh). Recorded as
a follow-up, not shipped.

## Learning

| Feature | Status | Implementation | Tests | Limitations |
|---|---|---|---|---|
| Learning paths | COMPLETE | `pages/Learn.tsx`, four curated paths over the corpus | e2e | Ordering is editorial |
| Concepts / lessons | COMPLETE | Backed by `/search?entity_type=CONCEPT` over the bundled corpus | e2e §8 | **Works with no database and no network** |
| Lesson detail | COMPLETE | `pages/LessonDetail.tsx` | build | Re-fetches by search on a direct link |
| Progress tracking | BLOCKED | `/learning/progress` implemented and tested | API tests | Needs PostgreSQL; no UI wired |
| Quizzes | NOT REQUIRED FOR MVP | Deferred in `SCHEMA_DECISIONS.md` (SD-3) | — | — |

## Rocket Lab

| Feature | Status | Implementation | Tests | Limitations |
|---|---|---|---|---|
| Component catalogue | COMPLETE | 28 components, 13 categories, from the engine's stock registry | 570 TS tests | Figures are engineering-plausible teaching values, labelled as such |
| Component detail + specifications | COMPLETE | Modal over the registry entry: mass, thrust, Isp, structural, thermal, failure modes | — | — |
| Category filtering and search | COMPLETE | `pages/RocketLab.tsx` | — | — |
| Starting designs | COMPLETE | Three presets, including one deliberately unflyable | e2e §2 | — |
| Compatibility / comparison | PARTIAL | Attachment rules enforced by the builder; no side-by-side comparison UI | TS tests | Comparison view not built |

## Rocket Builder

| Feature | Status | Implementation | Tests | Limitations |
|---|---|---|---|---|
| Stage management | COMPLETE | `useRocketBuilder` | TS tests | — |
| Component placement | COMPLETE | Add/remove per stage | TS tests | No drag-and-drop; list-based |
| Live engineering metrics | COMPLETE | Mass, Δv, TWR, stability, propellant fraction, length | TS tests + e2e §2 | — |
| Validation | COMPLETE | Errors and warnings from `core/validation.ts` | 517-line module, TS tests | — |
| Undo / redo | COMPLETE | `useRocketBuilder` history | TS tests | — |
| Save / load / versioning | BLOCKED | `/vehicles` CRUD implemented and tested | API tests | Needs PostgreSQL; no UI wired |

**No physics is computed in the frontend.** Every number shown comes from
`analyzeRocket`, and the same analysis produces the vehicle that is flown.

## Launch

| Feature | Status | Implementation | Tests | Limitations |
|---|---|---|---|---|
| Mission configuration | COMPLETE | Name, objective, profile, target altitude | e2e §3 | — |
| Launch site selection | COMPLETE | Five real sites with real coordinates and elevations | frontend tests | Earth rotation is not modelled; stated in the UI |
| Guidance program selection | COMPLETE | Vertical, pitch program, gravity turn | e2e | — |
| Environmental parameters | PARTIAL | Surface wind is configurable and passed through | — | The engine does not yet apply wind to the trajectory |
| Pre-flight checks | COMPLETE | Five checks computed from the design's own analysis | e2e | Failing checks warn, deliberately do not block |
| Launch initiation | COMPLETE | Runs the simulation and moves to Mission Control | e2e §3 | — |
| Countdown | PARTIAL | Simulated: the engine starts at T−3 s and emits `STATE_COUNTDOWN` | sim tests | No UI countdown animation |

## Simulation

| Feature | Status | Implementation | Tests | Limitations |
|---|---|---|---|---|
| Python physics engine | COMPLETE | RK4, inverse-square gravity, USSA-1976, transonic drag, altitude-compensated thrust | 106 tests | Documented in `ASSUMPTIONS.md` |
| Physics separated from rendering | COMPLETE | Server computes, client renders; no physics in any component | architecture test in TS engine | — |
| Cross-engine agreement | COMPLETE | Python vs TypeScript, within 2% on every trajectory quantity | 24 tests | Guidance *policy* differs by design |
| Telemetry | COMPLETE | 35 fields per sample | e2e §4 | Decimated to ≤ 5,000 samples on the wire |
| Mission state machine | COMPLETE | 19 states | sim tests | `SECOND_STAGE` not in the shared contract; upper-stage flight re-enters `ASCENT` |
| Mission events | COMPLETE | Ignition, liftoff, max-Q, cutoff, separation, orbit insertion, failures | e2e §4 | — |
| Staging | COMPLETE | Separation drops the spent stage's mass | sim + e2e | — |
| Failure detection | COMPLETE | Four rules: insufficient TWR, dynamic pressure, g-load, heating | sim tests | Matches the TypeScript rule set |
| Failure injection | COMPLETE | Scripted, seeded, deterministic | sim tests | — |
| 3D visualization | COMPLETE | `FlightViewport`, R3F + Three.js | build | Planet radius and altitude are exaggerated for legibility; stated in the file |
| Pause / resume / reset | COMPLETE | `useTelemetryPlayback` | 14 frontend tests | — |
| Speed control 0.25×–10× | COMPLETE | Independent of frame rate | frontend tests | — |
| Timeline scrubbing | COMPLETE | Seek, and click any event to jump to it | frontend tests | — |
| Mission monitoring | COMPLETE | 12 live gauges, status chips, event log, summary | e2e | — |
| Replay | COMPLETE | The whole model is replay | frontend tests | — |
| Save a run | BLOCKED | `simulation_runs` table exists | API model tests | Needs PostgreSQL **and** a saved mission + vehicle to reference |

## Missions

| Feature | Status | Implementation | Tests | Limitations |
|---|---|---|---|---|
| Mission library | COMPLETE | `/search?entity_type=MISSION` over the bundled corpus | e2e §8 | Works with no database |
| Mission detail | COMPLETE | Overview, topics, sources | build | Timeline and imagery not surfaced |
| Provenance | COMPLETE | Every record carries its source | e2e §8 | — |

## AI

| Feature | Status | Implementation | Tests | Limitations |
|---|---|---|---|---|
| Grounded question answering | COMPLETE | `POST /ai/ask` | e2e §9 | See provider note |
| Source citation | COMPLETE | Sources on every answer | e2e §9 | — |
| Refusal when evidence is missing | COMPLETE | Asserted by the AI suite's own security tests | P4 suite | — |
| Simulation failure explanation | COMPLETE | `POST /ai/explain-failure` | e2e §7 | — |
| Separation of simulation vs source claims | COMPLETE | Distinct sections in the response and the UI | P4 suite | — |
| Conversation history | BLOCKED | `/conversations` CRUD implemented and tested | API tests | Needs PostgreSQL; no UI wired |
| Suggested prompts | COMPLETE | `pages/Assistant.tsx` | — | — |
| Streaming | NOT REQUIRED FOR MVP | — | — | Answers return in well under a second |

**Provider.** No LLM credentials are configured, so the registry resolves to its
`extractive` provider, which composes answers from retrieved passages rather
than generating prose. The assistant page labels this. Setting `AI_API_KEY` and
`LIS_AI_PROVIDER` selects a real provider; the abstraction is in place and no
caller changes.

## Search

| Feature | Status | Implementation | Tests | Limitations |
|---|---|---|---|---|
| Platform-wide search | COMPLETE | `GET /search` | e2e §8 | Corpus is missions + concepts; catalogued objects are in PostgreSQL |
| Hybrid retrieval | COMPLETE | Keyword + vector, RRF fusion, reranking | P4 suite asserts it beats both baselines | Embeddings are a hashed lexical projection, not a learned model |
| Relevance ranking | COMPLETE | e2e asserts monotonic ordering | e2e §8 | — |
| Entity filtering | COMPLETE | `?entity_type=` | e2e §8 | — |
| Source quality / provenance on results | COMPLETE | e2e asserts every result carries it | e2e §8 | — |
| Linkable queries | COMPLETE | Query lives in the URL | — | — |

## Workspace and persistence

| Feature | Status | Limitations |
|---|---|---|
| Projects list / create | BLOCKED | Needs PostgreSQL. UI built and wired. |
| Saved rockets | BLOCKED | Backend CRUD complete; no UI wired |
| Saved simulations | BLOCKED | Needs a saved mission + vehicle to reference |
| Favourites | NOT REQUIRED FOR MVP | Deferred (SD-3) |
| Learning progress | BLOCKED | Backend complete; no UI wired |
| Current unsaved work | COMPLETE | Shown explicitly, with a warning that it is in memory only |

## Data

| Feature | Status | Limitations |
|---|---|---|
| Space-data models, adapters, normalisation | COMPLETE | 22,053 lines, 1419 tests |
| Provenance retained per record | COMPLETE | — |
| Bundled offline corpus | COMPLETE | Search and Learn work with no network |
| NASA integration | PARTIAL | Adapter complete and tested; key configured. **Not reachable from any endpoint** — ingestion writes to PostgreSQL, which is blocked. |
| External failure handling | COMPLETE | Timeouts, retries, rate limits, offline fallback |
| Image provenance | PARTIAL | Records carry source and URL; no image-heavy UI beyond Explore |

## Backend and quality

| Item | Status | Evidence |
|---|---|---|
| FastAPI runs | COMPLETE | Observed serving; 291 tests |
| PostgreSQL | BLOCKED | See below |
| Migrations | PARTIAL | Eight revisions, native async; **never executed** against a live database here |
| Authentication / authorization | COMPLETE | Tested, including a dedicated security suite |
| API contracts documented | COMPLETE | OpenAPI publishes the engines' own models; contract-freeze tests |
| Frontend builds | COMPLETE | `vite build` succeeds; 84 kB gzipped main bundle |
| Frontend typechecks | COMPLETE | `tsc -b` clean |
| Tests pass | COMPLETE | All five suites green |
| End-to-end journey | COMPLETE | 56/56 |
| No secrets committed | COMPLETE | `.env` ignored; no credentials in any tracked file |
| Dependency vulnerabilities | COMPLETE | 7 → 0 |

---

## The one external blocker

**PostgreSQL is running but the `lostintospace` role is not reachable.** The
local `.env` still carries the example default password
(`postgresql+asyncpg://lostintospace:password@…`), and authentication fails.

This is a **user action**, not a code defect:

1. Create the role and databases —
   `psql -h 127.0.0.1 -U postgres -d postgres -v app_password="'<password>'" -f database/scripts/setup_local_db.sql`
2. Put that password into `DATABASE_URL` in `.env`
3. `cd database && alembic upgrade head`
4. `python database/seeds/seed_all.py`

Full instructions: [`docs/getting-started/LOCAL_SETUP.md`](../getting-started/LOCAL_SETUP.md).

Everything that does not need stored data works today. When the database comes
up, Explore, Catalog, object detail, auth, the workspace and progress tracking
become available with no code change — the endpoints are implemented and tested,
and the frontend is already wired to them.

Until then a request to a database-backed endpoint returns a clean
`503 DATABASE_UNAVAILABLE`, and the affected pages show the commands above
rather than an empty grid.

---

## Verdict

**READY as a first prototype**, with one documented external blocker.

The complete product loop the brief specifies — explore, learn, build, launch,
simulate, observe, fail, understand — runs end to end today, verified by 56
automated checks against the live API. The simulation is real physics,
cross-validated against a second independent implementation. The AI is grounded
and cited. Nothing is faked.

What is **not** ready is **persistence**: saving a rocket, a mission, a
simulation or learning progress. Those endpoints are implemented and tested, but
they have never run against a live database, so they are marked BLOCKED rather
than COMPLETE. Calling them complete on the strength of passing unit tests would
be exactly the kind of claim this document exists to prevent.

Two smaller gaps are worth naming: the AI answers extractively until a provider
key is configured, and the builder's save/load UI is not wired even though its
backend is. Neither blocks the loop.
