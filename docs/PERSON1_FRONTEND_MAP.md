# Person 1 — Frontend Map

> Generated: 2026-08-19 | Status: Pre-implementation audit

---

## 1. Current Architecture

### Tech Stack (Specified, Not Yet Installed)

| Layer | Technology | Source |
|-------|-----------|--------|
| Framework | React 18 + TypeScript | `apps/web/README.md` |
| Build | Vite | `apps/web/README.md` |
| 3D | React Three Fiber + Drei + Three.js | `apps/web/README.md`, simulation-engine `package.json` |
| Styling | Tailwind CSS v3 | `apps/web/README.md` |
| Local state | Zustand | `apps/web/README.md` |
| Server state | TanStack Query | `apps/web/README.md` |
| Routing | React Router | `apps/web/README.md` |
| Realtime | WebSocket (native, via FastAPI WS) | `docs/api/API.md` |

### What Actually Exists

**`apps/web/`** — Empty scaffold. Only `.gitkeep` files and `README.md`. No source code, no `package.json`, no config files.

**`packages/ui/`** — Empty. Only `src/.gitkeep`. No shared components exist.

**`assets/`** — Empty. Only `.gitkeep` in `fonts/`, `icons/`, `images/`, `models3d/`, `textures/`.

### What Is Fully Built (By Other Persons)

| Package | Status | Owner |
|---------|--------|-------|
| `packages/simulation-engine/` | **Complete** — physics, core, sim, renderer, adapters, integration, tests | P3 |
| `packages/contracts/` | **Complete** — AI, search, provenance, analysis, time contracts (Python) | P4 |
| `ai/` | **Complete** — assistant, grounding, RAG, providers, safety, prompts, tests | P4 |
| `search/` | **Complete** — embeddings, keyword, ranking, retrieval, vector store, tests | P4 |
| `data/` | **Complete** — models, sources, ingestion, normalization, provenance, validation, tests | P4 |

---

## 2. Reusable Components Available to P1

### From `@lostintospace/simulation-engine/adapters`

| Export | Type | Purpose |
|--------|------|---------|
| `RocketViewer` | React component | Self-contained 3D canvas; shows rocket design and/or live simulation |
| `useRocketBuilder` | React hook | Edit a `RocketDesign` with undo/redo, live analysis, and validation |
| `useSimulation` | React hook | Drive a simulation from React with play/pause/reset/step/timeScale |

#### `RocketViewer` Props

| Prop | Type | Notes |
|------|------|-------|
| `layout` | `DesignLayout \| null` | From `analyzeRocket(...).layout` |
| `simulationRef` | `RefObject<Simulation \| null>` | Null = builder (static) view |
| `cameraMode` | `CameraMode` | Optional |
| `scaleBand` | `ScaleBand` | Optional |
| `sceneOptions` | `SceneManagerOptions` subset | Optional |
| `style`, `className` | CSS | Wrapper element styling |
| `onSceneReady` | `(manager: SceneManager) => void` | Callback for orbit controls |

#### `useSimulation` Returns

| Field | Type | Notes |
|-------|------|-------|
| `status` | `SimStatus` | `'ready' \| 'running' \| 'paused' \| 'finished'` |
| `time_s` | `number` | Simulated time, refreshed at UI rate (4 Hz default) |
| `missionState` | `MissionState` | Current mission phase |
| `telemetry` | `TelemetryPoint \| null` | Latest sample at UI rate |
| `events` | `readonly SimEvent[]` | All events so far |
| `result` | `SimResult \| null` | Non-null once flight ends |
| `simulationRef` | `RefObject<Simulation \| null>` | For `RocketViewer` and per-frame reads |
| `start`, `pause`, `reset`, `stepOnce`, `runToCompletion` | functions | Playback controls |
| `setTimeScale`, `timeScale` | function + number | 0.1–1000× speed |

#### `useRocketBuilder` Returns

| Field | Type | Notes |
|-------|------|-------|
| `design` | `RocketDesign` | Current immutable design |
| `analysis` | `RocketAnalysis` | Memoised engineering analysis |
| `validation` | `ValidationResult` | Auto-refreshed validation |
| `vehicle` | `Vehicle` | Simulation-ready vehicle |
| `lastError` | `RocketDesignError \| null` | Surfaced for UI display |
| `canUndo`, `canRedo`, `undo`, `redo` | boolean + functions | History (50-deep) |
| `addStage`, `removeStage`, `setStageIgnitionDelay` | functions | Stage operations |
| `addComponent`, `removeComponent`, `configureComponent`, `moveComponent` | functions | Component operations |
| `connect`, `disconnect` | functions | Connection operations |
| `replaceDesign` | function | Full design swap (load from API) |

### From `@lostintospace/simulation-engine/core`

| Export | Purpose |
|--------|---------|
| `ComponentRegistry` | Component catalog for the builder |
| `builtinCatalog` | Pre-loaded component definitions |
| `RocketDesign`, `RocketAnalysis`, `ValidationResult` | Types the builder UI renders |
| `Vehicle`, `Stage` | Simulation-facing types |
| All component definition types | `EngineDef`, `FuelTankDef`, `AvionicsDef`, etc. |

### From `@lostintospace/simulation-engine/integration`

| Export | Purpose |
|--------|---------|
| `RocketDesignDTO`, `SimulationRunDTO` | Wire types for save/load through P2's API |
| `DesignSummaryDTO` | Card/list headline figures |
| `toDesignDTO`, `toSimulationRunDTO` | Serializers |
| `checkSchemaCompatibility` | Version check on loaded payloads |

### From `packages/contracts/` (Python — need TypeScript mirrors)

Contracts are defined in Python. **TypeScript equivalents do not exist yet.** P1 must create TS mirrors in `apps/web/src/types/contracts/`.

| Contract | Key Types |
|----------|-----------|
| `provenance.py` | `SourceReference`, `SourceType` (11 variants), `FreshnessClass` (5 variants) |
| `ai.py` | `AIResponse`, `Citation`, `ContextItem`, `ClaimType` (7 variants), `ConfidenceLevel` (4 variants), `DataOrigin` (6 variants), `AnswerLimitation`, `Conversation`, `ConversationTurn` |
| `search.py` | `SearchQuery`, `SearchResult`, `SearchResponse`, `SearchEntityType` (9 variants), `SearchFacet`, `MatchType` (5 variants), `SortOrder` (4 variants), `ResultProvenance`, `SearchStatus` (3 variants) |
| `analysis.py` | `FailureAnalysis`, `SimulationObservation`, `ScientificExplanation`, `Mitigation`, `MissionSummary`, `MissionTimelineEntry`, `SourceConflict`, `FailureSeverity`, `SubsystemKind` |

---

## 3. Missing Pages (All of Them)

Every page from the MVP route tree needs to be created:

| Route | Page | API Dependencies | P3 Components |
|-------|------|-----------------|---------------|
| `/` | Landing | None | Hero 3D placeholder |
| `/explore` | Space object catalog | `GET /space-objects`, `GET /search` | — |
| `/explore/:id` | Object detail | `GET /space-objects/{id}` | Optional 3D view |
| `/search` | Search results | `GET /search`, `GET /search/suggestions` | — |
| `/learn` | Learning dashboard | `GET /lessons`, `GET /lessons/categories` | — |
| `/learn/:slug` | Lesson detail | `GET /lessons/{slug}`, `POST /learning/progress` | — |
| `/dashboard` | User dashboard | `GET /projects`, `GET /auth/me` | — |
| `/projects/:id` | Project overview | `GET /projects/{id}`, missions CRUD | — |
| `/build/:missionId` | Vehicle builder | Vehicle CRUD, `POST /vehicles/{id}/validate` | `useRocketBuilder`, `RocketViewer` |
| `/simulate/:missionId` | Mission control | `POST /simulations/run`, `WS /ws/simulation/{id}` | `useSimulation`, `RocketViewer` |
| `/analysis/:simId` | Post-flight analysis | `GET /simulations/{id}/analysis`, `POST /ai/failure-analysis` | — |
| `/missions` | Mission library | `GET /projects/{pid}/missions` | — |
| `/assistant` | AI assistant | `POST /ai/explain`, `/ai/tutor`, `/ai/recommend` | — |
| `/login` | Login | `POST /auth/login` | — |
| `/register` | Register | `POST /auth/register` | — |
| `/settings` | User settings | `GET /auth/me`, user update | — |
| `/profile` | User profile | `GET /auth/me` | — |

---

## 4. API Dependencies (Full Map)

### Person 2 — Backend / Auth / Projects / Missions / Vehicles / Learning

| Endpoint | Frontend Consumer | Backend Status |
|----------|------------------|----------------|
| `POST /auth/register` | Register page | **Not implemented** |
| `POST /auth/login` | Login page | **Not implemented** |
| `POST /auth/logout` | Nav/settings | **Not implemented** |
| `POST /auth/refresh` | API client interceptor | **Not implemented** |
| `GET /auth/me` | Dashboard, settings, nav | **Not implemented** |
| `GET/POST/PATCH/DELETE /projects` | Dashboard, project page | **Not implemented** |
| `GET/POST/PATCH/DELETE /missions` | Project page, builder | **Not implemented** |
| `GET/POST/PATCH /vehicles`, stages, components | Builder page | **Not implemented** |
| `GET /space-objects` | Explore page | **Not implemented** |
| `GET /space-objects/{id}` | Object detail | **Not implemented** |
| `GET /space-objects/categories` | Explorer filters | **Not implemented** |
| `GET /lessons`, `GET /lessons/{slug}` | Learn pages | **Not implemented** |
| `GET /lessons/categories` | Learn filters | **Not implemented** |
| `POST /learning/progress` | Lesson detail | **Not implemented** |
| `POST /simulations/run` | Simulate page | **Not implemented** |
| `GET /simulations/{id}/*` | Analysis page | **Not implemented** |
| `WS /ws/simulation/{id}` | Simulate page | **Not implemented** |
| `POST /reports`, `GET /reports/{id}` | Report page | **Not implemented** |
| `POST /rkt/export`, `/import`, `/validate` | Builder/project page | **Not implemented** |

**API response envelope:** `{ status, data, meta: { page, per_page, total } }`
**Error envelope:** `{ status: "error", error: { code, message, details } }`

### Person 3 — Simulation Engine (TypeScript, client-side)

| Interface | Frontend Consumer | Status |
|-----------|------------------|--------|
| `RocketViewer` component | Builder + simulate pages | **Ready** |
| `useRocketBuilder` hook | Builder page | **Ready** |
| `useSimulation` hook | Simulate page | **Ready** |
| `RocketDesignDTO` / `SimulationRunDTO` | Save/load through API | **Ready** |
| Component catalog (`builtinCatalog`) | Builder component palette | **Ready** |

### Person 4 — Search / AI / Analysis

| Endpoint | Frontend Consumer | Status |
|----------|------------------|--------|
| `GET /search` | Search page, explore page | Backend **not implemented**; contracts **ready** (Python) |
| `GET /search/suggestions` | Search bar autocomplete | Same |
| `POST /ai/explain` | Object detail, lesson detail | Same |
| `POST /ai/failure-analysis` | Analysis page | Same |
| `POST /ai/recommend` | Analysis page | Same |
| `POST /ai/tutor` | Contextual help panel | Same |

---

## 5. Integration Points

| Integration | P1 Side | Other Side | Contract Location |
|-------------|---------|------------|-------------------|
| REST API calls | `services/` + TanStack Query | P2 FastAPI | `docs/api/API.md` |
| WebSocket telemetry | `lib/` WS client | P2 `simulation/websocket.py` | `docs/api/API.md` |
| 3D rocket render | `RocketViewer` in pages | P3 simulation-engine | `packages/simulation-engine/src/adapters/RocketViewer.tsx` |
| Rocket builder | `useRocketBuilder` in builder page | P3 core + validation | `packages/simulation-engine/src/adapters/useRocketBuilder.ts` |
| Simulation playback | `useSimulation` in simulate page | P3 sim runner | `packages/simulation-engine/src/adapters/useSimulation.ts` |
| Design save/load | DTOs ↔ API | P2 stores, P3 produces DTOs | `packages/simulation-engine/src/integration/dto.ts` |
| RKT file import/export | Upload/download UI | P2 API + P3 `rkt.ts` | `packages/simulation-engine/src/integration/rkt.ts` |
| Search rendering | Search result cards | P4 `SearchResponse` contract | `packages/contracts/src/contracts/search.py` |
| AI response rendering | Citation UI, confidence badges | P4 `AIResponse` contract | `packages/contracts/src/contracts/ai.py` |
| Failure analysis UI | Observation vs explanation split | P4 `FailureAnalysis` contract | `packages/contracts/src/contracts/analysis.py` |
| Provenance display | Source badges, freshness indicators | P4 `SourceReference` contract | `packages/contracts/src/contracts/provenance.py` |
| JWT auth flow | Auth header injection, token refresh | P2 `core/security` | `docs/api/API.md` |

---

## 6. Files Person 1 Owns

| Path | Purpose |
|------|---------|
| `apps/web/` (entire directory) | Frontend application |
| `packages/ui/` (entire directory) | Shared UI component library |
| `assets/` (entire directory) | Fonts, icons, images, 3D models, textures |

### P1 Must Create

| File/Directory | Purpose |
|----------------|---------|
| `apps/web/package.json` | Dependencies and scripts |
| `apps/web/vite.config.ts` | Vite config |
| `apps/web/tsconfig.json` | TypeScript config |
| `apps/web/tailwind.config.ts` | Tailwind config |
| `apps/web/postcss.config.js` | PostCSS for Tailwind |
| `apps/web/index.html` | Entry HTML |
| `apps/web/src/main.tsx` | App entry point |
| `apps/web/src/App.tsx` | Root component with router |
| `apps/web/src/components/ui/` | Button, Card, Input, Modal, Badge, Tooltip, etc. |
| `apps/web/src/components/layout/` | Shell, Nav, Sidebar, Footer |
| `apps/web/src/components/features/` | Feature-specific components |
| `apps/web/src/pages/` | All route-level pages |
| `apps/web/src/hooks/` | `useAuth`, `useDebounce`, `useMediaQuery`, etc. |
| `apps/web/src/lib/` | API client, WS client, utilities |
| `apps/web/src/stores/` | Zustand stores (auth, ui, builder) |
| `apps/web/src/services/` | API service functions per domain |
| `apps/web/src/types/` | Frontend-specific types |
| `apps/web/src/types/contracts/` | TypeScript mirrors of Python contracts |
| `apps/web/src/styles/` | Global CSS, Tailwind layers |

---

## 7. Files Person 1 Should NOT Modify

| Path | Owner | Reason |
|------|-------|--------|
| `apps/api/` | P2 | Backend application |
| `database/` | P2 | Migrations and seeds |
| `deployment/` | P2 | Docker, nginx, deploy scripts |
| `simulation/` | P3 | Python simulation engine |
| `scientific/` | P3 | Scientific models and constants |
| `packages/simulation-engine/src/core/` | P3 | Core rocket domain model |
| `packages/simulation-engine/src/physics/` | P3 | Physics calculations |
| `packages/simulation-engine/src/sim/` | P3 | Simulation runner |
| `packages/simulation-engine/src/renderer/` | P3 | 3D rendering internals |
| `packages/simulation-engine/src/integration/` | P3 | DTOs and serialization |
| `packages/simulation-engine/tests/` | P3 | Simulation engine tests |
| `ai/` | P4 | AI provider, grounding, RAG |
| `search/` | P4 | Search indexing and ranking |
| `data/` | P4 | Data models, sources, ingestion |
| `packages/contracts/` | P4 | Shared type contracts |
| `evaluation/` | P4 | RAG evaluation |
| `pyproject.toml` | P4 | Python tooling config |
| `conftest.py` | P4 | Root test config |

### Safe to Import (Read-Only)

| Path | What to import |
|------|---------------|
| `packages/simulation-engine/src/adapters/` | `RocketViewer`, `useRocketBuilder`, `useSimulation` |
| `packages/simulation-engine/src/core/types.ts` | All design/vehicle/mission types |
| `packages/simulation-engine/src/core/component-types.ts` | Component definitions, `RocketDesign` |
| `packages/simulation-engine/src/core/builder.ts` | `RocketAnalysis`, `DesignLayout`, `analyzeRocket` |
| `packages/simulation-engine/src/core/validation.ts` | `ValidationResult`, `ValidationIssue` |
| `packages/simulation-engine/src/core/component-registry.ts` | `ComponentRegistry`, `builtinCatalog` |
| `packages/simulation-engine/src/sim/config.ts` | `SimConfig` |
| `packages/simulation-engine/src/sim/events.ts` | `SimEvent`, `FailureDetail`, `SimSummary` |
| `packages/simulation-engine/src/sim/telemetry.ts` | `TelemetryPoint` |
| `packages/simulation-engine/src/sim/state.ts` | `SimulationState`, `SimStatus` |
| `packages/simulation-engine/src/sim/mission-state.ts` | `MissionState` |
| `packages/simulation-engine/src/integration/dto.ts` | `RocketDesignDTO`, `SimulationRunDTO`, serializers |
| `packages/contracts/` | Read Python contracts → create TS mirrors |

---

## 8. Key Observations

1. **The frontend is 100% empty.** Every file is a `.gitkeep`. There is no `package.json`, no config, no source code. Everything must be created from scratch.

2. **The simulation engine is the most mature package** — fully implemented with 20 test files, React adapters, and clean APIs. The `useRocketBuilder` and `useSimulation` hooks are designed for direct React integration with no glue code needed.

3. **Contracts exist only in Python.** P1 must create TypeScript equivalents. The `packages/contracts/` README mentions TS mirrors in `packages/contracts/src/*.ts` but none exist.

4. **The backend API is fully specified** in `docs/api/API.md` with 40+ endpoints — but **none are implemented**. All `apps/api/src/` modules are `.gitkeep` stubs. P1 must build against mocks.

5. **Provenance and citation rendering is non-trivial.** Every search result and AI response carries source metadata. The UI must render `DataOrigin`, `FreshnessClass`, `ClaimType`, `ConfidenceLevel`, and citation verification status visibly.

6. **The analysis page has a strict two-panel contract**: simulator observations (what happened) vs scientific explanations (why). The `FailureAnalysis` contract enforces this separation and P1's UI must preserve it.

7. **The `RocketViewer` supports two modes**: static (builder view, `simulationRef` null) and live (simulation view, `simulationRef` connected). Same component, different pages.

8. **Simulation UI updates are throttled to 4 Hz** by `useSimulation` to avoid over-rendering, while the 3D view reads at full frame rate through the ref. P1 does not need to implement throttling.

9. **Design DTOs carry `DesignSummaryDTO`** with pre-computed headline figures (mass, delta-v, TWR, stage count). Card and list views can use these without recomputing.

---

## 9. Frontend Implementation Sequence

### Phase 1: Foundation
1. Initialize `apps/web/` (package.json, Vite, TS, Tailwind, React Router)
2. Create design system / UI primitives (Button, Card, Input, Modal, Badge, etc.)
3. Create layout shell (nav, sidebar, page wrapper)
4. Create TypeScript mirrors of Python contracts
5. Create API client with mock adapter
6. Create Zustand stores (auth, ui)

### Phase 2: Core Pages
7. Landing/Home page
8. Authentication pages (login, register, forgot password)
9. Dashboard
10. Search UI (global search bar + results page)

### Phase 3: Explorer & Learning
11. Space Explorer (catalog + filters + detail)
12. Learning Dashboard + Course + Lesson pages

### Phase 4: Rocket Engineering
13. Rocket Lab (component catalog + comparison)
14. Rocket Builder (integrating `useRocketBuilder` + `RocketViewer`)
15. Mission Simulator (integrating `useSimulation` + `RocketViewer`)
16. Post-flight Analysis (failure analysis rendering)

### Phase 5: Intelligence & Projects
17. AI Assistant (chat + streaming + citations)
18. Mission Library
19. Project Workspace

### Phase 6: Polish
20. Loading/error/empty states across all pages
21. Responsive behavior
22. Accessibility audit
23. Performance optimization
24. Tests
