# Contributor Guide

Setup is in [`../getting-started/LOCAL_SETUP.md`](../getting-started/LOCAL_SETUP.md).
This is about how to work in the codebase once it runs.

---

## Where does my change go?

| I want to change… | Go to | Do not touch |
|---|---|---|
| How a rocket flies | `simulation/` | `packages/simulation-engine/src/sim/` — that is the regression oracle |
| What components exist, or what a design's Δv is | `packages/simulation-engine/src/core/` | any duplicate catalogue (there is none; keep it that way) |
| What the 3D view looks like | `packages/simulation-engine/src/renderer/`, `apps/web/src/components/features/simulation/` | anything computing a position |
| An endpoint | `apps/api/src/<domain>/` | the engines directly — go through `core/engines/` |
| The schema | `apps/api/src/models/`, then a migration | the database by hand |
| Where space data comes from | `data/sources/`, `data/normalization/` | `apps/api` |
| How search ranks | `search/ranking/` | `apps/api/src/search/service.py`, which only wires it up |
| How the AI answers | `ai/grounding/`, `ai/providers/` | `apps/api/src/ai/assistant_service.py`, same reason |
| A page | `apps/web/src/pages/` | — |

---

## The rules that are not style

### No physics in React

Every number the builder shows comes from `analyzeRocket`. Every number a flight
shows comes from the Python engine. If a component computes a trajectory, a
mass or a Δv, it is in the wrong place.

The reason is not purity: it is that a second implementation of the same
calculation will disagree with the first, and the user will see two different
answers for the same rocket.

### The engines are reached through one door

`apps/api/src/core/engines/` is the only place the backend imports `simulation`,
`search`, `ai`, `data` or `contracts`. They are sibling trees, not installed
packages, and they may be absent from an install — so availability is probed,
never assumed, and `/health/engines` reports the truth.

### One dialect boundary

`apps/web/src/lib/simConfig.ts` translates the builder's camelCase into the
API's snake_case. Nothing else does. Add a field to a stage and it is changed
in exactly two places — the contract and that file — and
`simConfig.test.ts` fails loudly if you miss one.

### Approximations are labelled where a user can see them

The simulation is educational. If a figure came from a simplified model, the
interface says so. `docs/simulation/ASSUMPTIONS.md` is the complete list, and
changing the physics means changing that file in the same commit.

### Provenance survives every transformation

A scientific figure keeps its source. Ingestion, normalisation, indexing,
retrieval and display all carry it. A record that arrives without provenance is
a bug in the adapter.

### Never fabricate

The assistant refuses when the corpus has nothing, rather than inventing an
answer. The simulation reports a failure rather than producing a plausible
trajectory. Tests in `ai/tests/test_security_audit.py` assert the first; the
flight-physics tests assert the second.

---

## Testing expectations

A change to physics needs a test that would fail without it. The engine that
shipped with the prototype scaffolding passed all 46 of its tests while dividing
by mass twice, modelling no gravity and no drag — because every test asserted
plumbing rather than behaviour.

`simulation/tests/test_flight_physics.py` is the model to follow: each test
states a physical claim ("gravity brings vehicles back down", "doubling mass
halves the load factor") and fails against the broken engine.

If you change the Python physics, `test_cross_engine.py` will tell you whether
you have drifted from the TypeScript engine. If the drift is intentional, say so
in the test rather than widening the tolerance quietly.

### Running everything

```bash
pytest                                          # 1419
cd apps/api && PYTHONPATH=$PWD pytest           #  291
pytest simulation/tests                         #  106
cd packages/simulation-engine && npx vitest run #  570
cd apps/web && npx vitest run                   #   27
cd apps/web && npx tsx e2e/journey.mjs          #   56 checks, needs the API
```

---

## Commits

Small and logical. `feat(sim):`, `fix(api):`, `docs:`, `test(web):`.

The body should say *why*, not *what* — the diff already says what. When a
change fixes something subtle, describe the failure it prevents; that is the
part nobody can reconstruct later.

Never commit `.env`, credentials, `node_modules`, a virtualenv, or a build
artifact. `git check-ignore .env` should print a match before you push.

---

## Adding an endpoint

1. Schema in `apps/api/src/schemas/`.
2. Service in `apps/api/src/<domain>/service.py` — the logic, no FastAPI.
3. Router in `apps/api/src/<domain>/router.py` — thin, with a `response_model`.
4. Mount it in `api_router.py`.
5. Update `tests/test_openapi_contract.py`: if it is public, add it to
   `EXPECTED_PUBLIC`; add it to `CONTRACT_PATHS` either way.
6. Tests.

Step 5 is not bureaucracy. That file is a contract freeze — it is what catches a
protected route silently losing its auth dependency, and it will fail your build
until you have stated your intent.

Return a typed `response_model`. An untyped response documents as `{}` in
OpenAPI, and a generated client gets `any` for the whole payload.

---

## Adding a data source

1. Adapter in `data/sources/`, subclassing the shared base so it inherits
   timeouts, retries and rate limiting.
2. Normaliser in `data/normalization/`, mapping into the canonical model.
3. Provenance: every record gets a `SourceReference`. Not optional.
4. Tests with recorded fixtures. Live tests go behind
   `LOSTINTOSPACE_LIVE_TESTS=1` so a normal run never touches the network.
5. Register it in `data/sources/registry.py`.

---

## Common traps

**Adding a page but forgetting the route.** `App.tsx` holds the route table.
This is exactly how the original blocker happened: `main.tsx` imported an
`App.tsx` that was never written.

**Changing an engine's field name.** TypeScript will pass, the Python will pass,
and the request between them will fail validation at runtime. `simConfig.ts` and
its test are the seam that catches it.

**Adding a `.js` import inside the simulation engine.** Correct — the package is
spec-compliant ESM. But `apps/web/vite.config.ts` needs its resolver plugin for
Rollup to follow it; TypeScript resolves those specifiers itself and will not
warn you.

**Widening a test tolerance to make a failure go away.** If the physics changed,
the number should change and the test should be updated deliberately. If it did
not, something is wrong.
