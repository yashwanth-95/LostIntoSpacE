# Canonical Architecture

**Status:** current as of the first-prototype integration
**Supersedes:** the per-person architecture notes in `docs/PERSON1_FRONTEND_MAP.md`,
`docs/PERSON4_DATA_ARCHITECTURE.md` and `docs/PERSON4_INTEGRATION_MAP.md`, which
remain as historical records of intent.

This describes what the repository *is*, not what it was planned to be. Where
the two differ, this file follows the code.

---

## The shape of the system

```
                          BROWSER  (apps/web)
                    React 18 · Vite · Tailwind · Zustand
                                  │
              ┌───────────────────┼───────────────────┐
              │                   │                   │
      TypeScript engine     lib/simConfig.ts     REST /api/v1
   packages/simulation-engine   (the bridge)          │
      · component catalogue                           │
      · rocket design + builder                       │
      · engineering analysis                          │
      · Three.js renderer                             │
                                                      │
                                              FastAPI (apps/api)
                                                      │
        ┌──────────────┬────────────────┬─────────────┴─────────┐
        │              │                │                       │
   PostgreSQL   simulation/        search/                    ai/
   (SQLAlchemy   Python physics    keyword + vector       providers · RAG
    + Alembic)   · RK4             · hybrid fusion        · grounding
                 · gravity/drag    · reranking            · failure analysis
                 · staging                                · safety
                 · failures                │                   │
                                           └────────┬──────────┘
                                                    │
                                                data/
                                        space-data models · adapters
                                        NASA/JPL/ESA/ISRO/CelesTrak/MPC
                                        normalisation · provenance
```

Everything the API reaches on the right-hand side goes through one module:
`apps/api/src/core/engines/`. That is the only place the backend imports a
sibling tree.

---

## Decisions that define this architecture

### 1. Python owns physics; TypeScript owns rendering and the builder

The brief requires it, and it is now true — but not by rewriting 14,000 lines
of working TypeScript.

| Concern | Owner | Why |
|---|---|---|
| Flight physics, integration, staging, failures | **Python** (`simulation/`) | Authoritative. Served over HTTP; every flight the product runs goes through it. |
| Component catalogue, rocket design, engineering analysis | **TypeScript** (`packages/simulation-engine/core/`) | Interactive: the builder recomputes mass and Δv on every keystroke, and a network round trip per edit would be unusable. |
| 3D rendering, camera, trajectory | **TypeScript** (`renderer/`, `apps/web`) | It is a browser concern. |
| TypeScript `sim/` layer | **Retained, not served** | 570 tests, used as a regression oracle for the Python engine. Not on the product's path. |

The two physics implementations are held in agreement by
`simulation/tests/test_cross_engine.py`, which flies the TypeScript engine's own
reference vehicles through the Python engine and compares. Every
trajectory-scale quantity agrees within 2%.

This is the answer to the audit's central architectural conflict: the working
physics was in TypeScript, and the engine designated as authoritative was a
stub. The stub was completed rather than the working code discarded.

### 2. Simulation is computed once, then replayed

`POST /api/v1/simulations/run` returns a complete flight — every telemetry
sample, every event — not a stream.

A reference orbital ascent computes in about 0.9 s server-side. Streaming it
back frame by frame would add a network round trip per frame for data the client
already holds, and would make a run non-deterministic. The client replays it
against its own clock, which is what makes playback speed independent of frame
rate and scrubbing instant.

WebSocket telemetry remains the right answer for a *long-running* or
*interactive* simulation. It is not needed for a flight that finishes faster
than the page can render it, and the endpoint contract does not change if that
later becomes true.

### 3. Two search systems, deliberately, with a clear boundary

| System | Scope | Backed by |
|---|---|---|
| `GET /api/v1/search` | Ranked retrieval across the whole knowledge corpus | P4 hybrid keyword + vector, fused and reranked |
| `GET /api/v1/space-objects?q=` | Filtering *within* one resource | PostgreSQL full-text over a generated `tsvector` |

Cross-corpus ranking and "narrow this list" are different problems. What the
brief forbids — and what the audit flagged — is two *incompatible* systems doing
the same job. These do not.

### 4. Guest mode is the default, not a fallback

Every route except `/workspace` works without an account. Simulation, search and
AI answering take no token. Signing in adds persistence.

The cost controls that authentication would otherwise provide are explicit
instead: request limits in `apps/api/src/schemas/simulation.py`, a wall-clock
timeout in the service, telemetry decimation on the response.

### 5. One contract per shape, published through OpenAPI

The API publishes the engines' own Pydantic models as its response models —
`SimResult`, `TelemetryPoint`, `FailureDetail`, `SearchResponse`, `AIResponse`,
`FailureAnalysis` all appear in `/openapi.json` as themselves.

The frontend's `src/types/simulation.ts` currently transcribes those by hand and
says so. Generating them from the schema is the next step; the schema is already
the source of truth.

### 6. The Python/TypeScript dialect boundary is one file

`apps/web/src/lib/simConfig.ts`. The builder speaks camelCase, the API speaks
snake_case, and exactly one module translates. A field rename in either engine
breaks there — loudly, in one place — rather than in a dozen components.

---

## Request paths

### Running a flight

```
Builder (useRocketBuilder)
  → analyzeRocket()            engineering analysis, in the browser
  → vehicleFromAnalysis()      a flat Vehicle
  → toSimVehicle()             camelCase → snake_case
  → buildSimConfig()           + mission, guidance, termination
  → POST /api/v1/simulations/run
      → SimulationRunRequest   request limits enforced
      → SimConfig.model_validate()
      → anyio.to_thread        CPU-bound, off the event loop, 30 s cap
      → run_simulation()       the Python engine
      → decimate telemetry     ≤ 5,000 samples
  → SimResult + meta
  → Mission Control            replay, 3D, telemetry, events
```

### Explaining a failure

```
SimResult (with failures)
  → POST /api/v1/ai/explain-failure
      → parse_simulation_result()   duck-typed view over the payload
      → build_observations()        read off the run; no model involved
      → retrieve_references()       hybrid search over the corpus
      → provider.generate()         grounded, cited
  → FailureAnalysis
      · what the simulation measured
      · what the sources say
      · what the simulation cannot model
```

Those three are kept separate in the response and in the UI, so a modelled
outcome is never read as a statement about a real vehicle.

---

## What each tree owns

| Tree | Owns | Depends on |
|---|---|---|
| `apps/web` | Every user-facing surface | the API, `packages/simulation-engine` |
| `apps/api` | HTTP, auth, persistence, the engine seam | everything below |
| `packages/simulation-engine` | Catalogue, design, analysis, renderer, TS physics | nothing |
| `simulation/` | The authoritative flight simulation | `simulation/contracts` |
| `search/` | Keyword, vector and hybrid retrieval | `data/`, `packages/contracts` |
| `ai/` | Providers, RAG, grounding, safety, failure analysis | `search/`, `data/` |
| `data/` | Space-data models, source adapters, provenance | `packages/contracts` |
| `database/` | Migrations and seeds | `apps/api/src/models` |

Dependencies point one way. `data/` knows nothing about the API; the API knows
nothing about React.

---

## Deliberately not built

Recorded so their absence reads as a decision rather than an oversight.

- **A job queue for simulations.** Runs finish in about a second. The service
  layer is the seam where this becomes a queue when runs get longer.
- **WebSocket telemetry.** See decision 2.
- **A second 3D provider** (Cesium, Mapbox). Three.js with the existing
  scientific coordinate abstractions covers what the product needs.
- **A vector database.** The corpus is bundled and small; an in-memory store
  with hashed local embeddings is deterministic, offline-capable and fast
  enough. The `VectorStore` interface is where a real one would go.
- **An agent framework.** The AI does retrieval and grounded generation. Adding
  orchestration would add failure modes without adding capability.
- **Per-frame simulation requests.** Explicitly forbidden by the brief and
  unnecessary given decision 2.
