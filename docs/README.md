# LostIntoSpacE Documentation

Start here.

## New to the project

| Read this | For |
|---|---|
| [`getting-started/LOCAL_SETUP.md`](getting-started/LOCAL_SETUP.md) | Getting it running. Every command has been executed against this repository. |
| [`getting-started/ENVIRONMENT.md`](getting-started/ENVIRONMENT.md) | Every environment variable, whether the prototype needs it, and where to get it. |
| [`integration/CANONICAL_ARCHITECTURE.md`](integration/CANONICAL_ARCHITECTURE.md) | How the pieces fit, and why the boundaries are where they are. |
| [`integration/MVP_STATUS.md`](integration/MVP_STATUS.md) | What actually works today, feature by feature, with honest statuses. |

**Shortest path to seeing it work:** steps 1–3 and 6–7 of the setup guide. The
rocket builder, the simulation, mission control, search and the AI assistant all
run with no database.

## Integration

The first-prototype integration pass, which turned five well-built but
disconnected trees into one product.

| File | Contents |
|---|---|
| [`integration/REPOSITORY_AUDIT.md`](integration/REPOSITORY_AUDIT.md) | The Phase 0 audit: what existed, what was broken, what was duplicated, what was missing. Written before any changes. |
| [`integration/CANONICAL_ARCHITECTURE.md`](integration/CANONICAL_ARCHITECTURE.md) | The architecture that resulted, and the decisions behind it. |
| [`integration/MVP_STATUS.md`](integration/MVP_STATUS.md) | Feature-by-feature status, limitations and blockers. |

## Simulation

| File | Contents |
|---|---|
| [`simulation/ASSUMPTIONS.md`](simulation/ASSUMPTIONS.md) | **Every approximation the physics makes, and what it costs.** Read before trusting any number the simulation produces. |
| [`simulation/ARCHITECTURE.md`](simulation/ARCHITECTURE.md) | Engine structure and the Python/TypeScript split. |
| [`simulation/MIGRATION_PLAN.md`](simulation/MIGRATION_PLAN.md) | The staged plan for moving physics to Python. Historical; the migration is done. |
| [`simulation/SIMULATION.md`](simulation/SIMULATION.md) | Simulation concepts and vocabulary. |

## Backend and data

| File | Contents |
|---|---|
| [`api/API.md`](api/API.md) | Endpoint reference. The generated OpenAPI schema at `/openapi.json` is authoritative. |
| [`backend/API_CONTRACT.md`](backend/API_CONTRACT.md) | The response envelope and error contract. |
| [`backend/DATABASE_CONTRACT.md`](backend/DATABASE_CONTRACT.md) | Table-by-table schema contract. |
| [`backend/DATABASE_SETUP.md`](backend/DATABASE_SETUP.md) | PostgreSQL specifics and version requirements. |
| [`backend/SCHEMA_DECISIONS.md`](backend/SCHEMA_DECISIONS.md) | Why the schema is shaped the way it is, including what was deferred. |
| [`backend/KNOWN_ISSUES.md`](backend/KNOWN_ISSUES.md) | Backend issue log. |
| [`architecture/DATABASE.md`](architecture/DATABASE.md) | Entity overview. |

## Space data, search and AI

| File | Contents |
|---|---|
| [`DATA_STRATEGY.md`](DATA_STRATEGY.md) | Which sources, and why. |
| [`DATA_ACCESS.md`](DATA_ACCESS.md) | How adapters fetch, normalise and cache. |
| [`PROVENANCE.md`](PROVENANCE.md) | How a record keeps its source. |
| [`PERSON4_DATA_ARCHITECTURE.md`](PERSON4_DATA_ARCHITECTURE.md) | The data/search/AI trees in depth. |

## Decisions and history

| File | Contents |
|---|---|
| [`decisions/DECISION_LOG.md`](decisions/DECISION_LOG.md) | Numbered decisions with rationale. |
| [`PERSON1_FRONTEND_MAP.md`](PERSON1_FRONTEND_MAP.md) | Original frontend plan. Historical — see the audit for what was actually built. |
| [`PERSON4_INTEGRATION_MAP.md`](PERSON4_INTEGRATION_MAP.md) | Original P4 integration plan. Historical. |
| [`rkt_spec/RKT_SPEC.md`](rkt_spec/RKT_SPEC.md) | The `.rkt` design file format. |
| [`scientific/MODELS.md`](scientific/MODELS.md) | Scientific model notes. |

---

## Conventions

**Documentation must match reality.** A file here describes what the code does,
not what it is meant to do. Where something is planned but not built, it says
so. Where a status is uncertain, it is marked uncertain rather than optimistic.

Files under `PERSON*` are kept as historical records of intent and are not
maintained against the current code. The audit and the canonical architecture
supersede them.

**Where the docs and the code disagree, the code is right and the doc is a
bug.** Fix it in the same change.
