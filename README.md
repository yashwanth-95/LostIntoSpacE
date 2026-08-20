# LostIntoSpacE

**Learn. Build. Simulate. Explore. Understand Space.**

A space laboratory in your browser. Study real objects and missions, learn the
engineering, build a rocket from real components, then fly it through a physics
simulation that tells you the truth about your design.

> You are not reading about space. You are exploring it.

---

## What the prototype does

One continuous loop, not six disconnected tools:

```
Explore  →  Learn  →  Build  →  Launch  →  Simulate  →  Understand
```

- **Explore** catalogued objects — planets, moons, asteroids, spacecraft — with
  the source of every figure attached.
- **Learn** propulsion, orbital mechanics, aerodynamics and mission design from
  a bundled, sourced corpus.
- **Build** a rocket from 28 real components across 13 categories. Mass, Δv,
  thrust-to-weight and static stability recompute on every change.
- **Launch** from one of five real sites, with a target orbit, a guidance
  program, and pre-flight checks that tell you what is wrong before you fly.
- **Simulate** in a Python physics engine: RK4 integration, inverse-square
  gravity, US Standard Atmosphere, transonic drag, staging, and the failures
  your design earns.
- **Understand** the result in Mission Control — 3D view, live telemetry, event
  timeline — and ask the AI why it failed, grounded in cited sources.

No account is needed. Signing in saves your work.

**It is an educational simulation with documented approximations. It is not
flight-certified engineering software.** Every approximation is listed in
[`docs/simulation/ASSUMPTIONS.md`](docs/simulation/ASSUMPTIONS.md).

---

## Quick start

```bash
git clone https://github.com/yashwanth-95/LostIntoSpacE.git
cd LostIntoSpacE
cp .env.example .env

# Backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e "apps/api[dev]"
pip install "httpx>=0.27" respx numpy pydantic
cd apps/api && PYTHONPATH=$PWD python -m uvicorn src.main:app --reload --port 8000

# Frontend, in another terminal
cd apps/web && npm install && npm run dev
```

Open <http://localhost:3000>.

The builder, the simulation, mission control, search and the AI assistant all
work **without a database**. PostgreSQL adds persistence and the object
catalogue — see
[`docs/getting-started/LOCAL_SETUP.md`](docs/getting-started/LOCAL_SETUP.md)
for those steps and for everything in more detail.

Verify a setup end to end:

```bash
cd apps/web && npx tsx e2e/journey.mjs   # 56 checks across the whole loop
```

---

## Architecture

```
   BROWSER  (apps/web · React · Vite · Tailwind)
      │
      ├── packages/simulation-engine   catalogue, design, analysis, Three.js
      │
      └── REST /api/v1 ──► FastAPI (apps/api)
                              │
              ┌───────────────┼───────────────┬──────────────┐
              │               │               │              │
         PostgreSQL      simulation/       search/          ai/
         persistence     Python physics    hybrid retrieval  RAG + grounding
                                                  └──────┬───┘
                                                       data/
                                            NASA · JPL · ESA · ISRO · CelesTrak
```

**Python owns physics. TypeScript owns rendering and the interactive builder.**
The two implementations are held in agreement by a cross-engine regression
suite: the same reference vehicles are flown through both, and every
trajectory-scale quantity agrees within 2%.

The full reasoning is in
[`docs/integration/CANONICAL_ARCHITECTURE.md`](docs/integration/CANONICAL_ARCHITECTURE.md).

### Repository layout

| Path | Contents |
|---|---|
| `apps/web/` | React frontend — every user-facing surface |
| `apps/api/` | FastAPI backend — HTTP, auth, persistence, the engine seam |
| `packages/simulation-engine/` | TypeScript: component catalogue, rocket design, engineering analysis, Three.js renderer |
| `packages/contracts/` | Shared Pydantic contracts |
| `simulation/` | The authoritative Python flight simulation |
| `search/` | Keyword, vector and hybrid retrieval |
| `ai/` | Providers, RAG, grounding, safety, failure analysis |
| `data/` | Space-data models, source adapters, normalisation, provenance |
| `database/` | Alembic migrations and seed data |
| `docs/` | [Documentation index](docs/README.md) |

### Stack

React 18 · Vite 7 · TypeScript 5 · Tailwind · Zustand · React Router 7 ·
Three.js / React Three Fiber · FastAPI · SQLAlchemy 2 (async) · Alembic ·
PostgreSQL · Pydantic 2 · NumPy · pytest · Vitest

---

## How the pieces connect

**Builder → simulation.** The TypeScript builder produces a `Vehicle`;
`apps/web/src/lib/simConfig.ts` translates it into the API's snake_case
`SimConfig`. That file is the entire Python/TypeScript dialect boundary, so a
field rename in either engine breaks in one place rather than a dozen.

**Simulation → client.** `POST /api/v1/simulations/run` returns a complete
flight — every sample, every event — not a stream. A reference orbital ascent
computes in about a second, and the client replays it against its own clock.
That is what makes playback speed independent of frame rate and scrubbing
instant.

**Simulation → AI.** `POST /api/v1/ai/explain-failure` takes a `SimResult`,
extracts the failure context, retrieves relevant engineering knowledge, and
returns an explanation that keeps *what the simulation computed* separate from
*what the sources say* — with the simulation's own limitations listed.

**Contracts.** The API publishes the engines' own Pydantic models in its OpenAPI
schema, so `SimResult`, `TelemetryPoint`, `FailureDetail`, `SearchResponse`,
`AIResponse` and `FailureAnalysis` all appear as themselves at `/openapi.json`.

**Space data.** Adapters for NASA, JPL, ESA, ISRO, CelesTrak, the Minor Planet
Center and the Exoplanet Archive normalise into one model and retain provenance
per record. A bundled offline corpus means search and learning work with no
network at all.

**AI provider.** Selected by a registry from the environment. With no
credentials it resolves to an extractive provider that composes answers from
retrieved passages rather than generating prose — and the interface says so
rather than implying more.

---

## Testing

```bash
pytest                                        # data, search, AI      1419
cd apps/api && PYTHONPATH=$PWD pytest         # backend                291
pytest simulation/tests                       # Python simulation      106
cd packages/simulation-engine && npx vitest run   # TypeScript engine  570
cd apps/web && npx vitest run                 # frontend                27
cd apps/web && npx tsx e2e/journey.mjs        # end-to-end          56 checks
```

Backend tests needing a live database skip unless `TEST_DATABASE_URL` is set.
It points at a separate database, so a test run can never touch development
data.

---

## Status

The complete product loop runs end to end today. **Persistence** — saving
rockets, missions, simulations and learning progress — is implemented and tested
but has not been run against a live database, so it is marked blocked rather
than complete.

Honest, feature-by-feature detail:
[`docs/integration/MVP_STATUS.md`](docs/integration/MVP_STATUS.md).

---

## Contributing

Read [`docs/README.md`](docs/README.md) first, then
[`docs/integration/CANONICAL_ARCHITECTURE.md`](docs/integration/CANONICAL_ARCHITECTURE.md).

House rules that matter more than style:

- **Documentation must match reality.** If a doc and the code disagree, the doc
  is a bug — fix it in the same change.
- **No physics in React.** Everything the builder shows comes from
  `analyzeRocket`; everything a flight shows comes from the Python engine.
- **Approximations are labelled.** A number that came from a simplified model
  says so, wherever a user can see it.
- **Provenance survives.** A scientific figure keeps its source through every
  transformation.
- **Never fabricate.** The assistant refuses rather than inventing; the
  simulation reports failure rather than pretending.

## Licence

MIT. See [LICENSE](LICENSE).
