<![CDATA[# LostIntoSpacE — System Architecture

## 1. Architectural Philosophy

| # | Principle | Why |
|---|-----------|-----|
| 1 | **Deterministic Scientific Computation** | Physics models produce repeatable results; no randomness in core sim |
| 2 | **AI Explains, Models Calculate** | AI never invents physics results — it explains deterministic outputs |
| 3 | **Modular Simulation** | Each physics model is independent, testable, replaceable |
| 4 | **Data Provenance** | Every data point traces to its source (API, seed, calculated) |
| 5 | **Graceful Degradation** | External API down → cache → bundled fallback → still works |
| 6 | **API Isolation** | Frontend and backend develop against contracts, not implementations |
| 7 | **Testability First** | Every model has reference test cases before integration |
| 8 | **Explicit Contracts** | JSON schemas define all interfaces between team members |
| 9 | **Offline-First Demo** | SIH demo runs fully offline with bundled data |
| 10 | **Incremental Complexity** | Start simple, add fidelity in layers |
| 11 | **Demo Reliability > Feature Count** | A reliable demo of 5 features beats a broken demo of 15 |
| 12 | **Security by Default** | Input validation, parameterized queries, JWT auth from day 1 |

---

## 2. System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                         USER / BROWSER                       │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                    FRONTEND (React + TS)                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────┐  │
│  │  Explore  │ │  Learn   │ │  Build   │ │Mission Control │  │
│  └──────────┘ └──────────┘ └──────────┘ └────────────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────┐  │
│  │  Search   │ │Dashboard │ │ Reports  │ │  3D Viewport   │  │
│  └──────────┘ └──────────┘ └──────────┘ └────────────────┘  │
└──────────────────────────────┬──────────────────────────────┘
                               │ REST + WebSocket
┌──────────────────────────────▼──────────────────────────────┐
│                 API LAYER (FastAPI Python)                    │
│  ┌──────┐ ┌────────┐ ┌─────────┐ ┌────────┐ ┌───────────┐  │
│  │ Auth │ │Projects│ │Missions │ │Vehicles│ │Space Data │  │
│  └──────┘ └────────┘ └─────────┘ └────────┘ └───────────┘  │
│  ┌──────┐ ┌────────┐ ┌─────────┐ ┌────────┐ ┌───────────┐  │
│  │Search│ │Learning│ │   AI    │ │Reports │ │Simulation │  │
│  └──────┘ └────────┘ └─────────┘ └────────┘ └───────────┘  │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                      DOMAIN SERVICES                         │
│  ┌────────────┐ ┌──────────────┐ ┌───────────────────────┐  │
│  │ Space Data │ │Mission Engine│ │  Simulation Engine    │  │
│  │  Service   │ │              │ │  (Physics + Solver)   │  │
│  └────────────┘ └──────────────┘ └───────────────────────┘  │
│  ┌────────────┐ ┌──────────────┐ ┌───────────────────────┐  │
│  │  Vehicle   │ │  Analysis    │ │  Failure Engine       │  │
│  │  Engine    │ │  Engine      │ │                       │  │
│  └────────────┘ └──────────────┘ └───────────────────────┘  │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                        DATA LAYER                            │
│  ┌────────────┐ ┌──────────┐ ┌──────────┐ ┌─────────────┐  │
│  │ PostgreSQL │ │  Redis   │ │  Object  │ │  Bundled    │  │
│  │            │ │ (Cache)  │ │ Storage  │ │  Fallback   │  │
│  └────────────┘ └──────────┘ └──────────┘ └─────────────┘  │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                     EXTERNAL SOURCES                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │ NASA API │ │ Weather  │ │  Geo     │ │  AI Provider  │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Technology Stack

### Recommended Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| **Frontend** | React 18 + TypeScript + Vite | Fast dev, strong typing, great ecosystem |
| **3D** | Three.js + React Three Fiber + Drei | Best browser 3D; R3F integrates with React |
| **Styling** | Tailwind CSS v3 | Rapid prototyping, consistent design tokens |
| **State** | Zustand (local) + TanStack Query (server) | Simple, performant, no boilerplate |
| **Backend** | Python 3.11+ + FastAPI | Async, auto-docs, Pydantic validation |
| **ORM** | SQLAlchemy 2.0 (async) + Alembic | Mature, async support, migrations |
| **Database** | PostgreSQL 15+ | Full-text search, JSONB, pgvector ready |
| **Cache** | Redis (optional for MVP) | Session cache, rate limiting |
| **Auth** | JWT (python-jose + passlib[bcrypt]) | Stateless, simple, well-documented |
| **Simulation** | NumPy + SciPy | Industry-standard scientific Python |
| **AI** | LLM provider abstraction (OpenAI-compatible) | Swappable providers |
| **Realtime** | FastAPI WebSockets | Built-in, no extra infra |
| **Deployment** | Docker Compose | Single-command local + deploy |

---

## 4. Service Boundaries (Modular Monolith)

All backend modules live in ONE FastAPI process. No microservices for MVP.

| Module | Type | Location | Dependencies |
|--------|------|----------|-------------|
| auth | Backend module | `apps/api/src/auth/` | database |
| users | Backend module | `apps/api/src/users/` | auth, database |
| projects | Backend module | `apps/api/src/projects/` | auth, users |
| missions | Backend module | `apps/api/src/missions/` | projects, vehicles |
| vehicles | Backend module | `apps/api/src/vehicles/` | projects |
| simulation | Backend module + Domain service | `apps/api/src/simulation/` + `simulation/` | missions, vehicles |
| space_data | Backend module | `apps/api/src/space_data/` | database, data/ |
| search | Backend module | `apps/api/src/search/` + `search/` | space_data, learning |
| learning | Backend module | `apps/api/src/learning/` | database |
| ai | Backend module + Service | `apps/api/src/ai/` + `ai/` | search, simulation |
| reports | Backend module | `apps/api/src/reports/` | simulation, missions |

---

## 5. Database Schema (Core Entities)

See `docs/architecture/DATABASE.md` for full schema.

### Entity Relationship Summary

```
users ──1:N──> projects ──1:N──> missions ──1:1──> vehicles
                                     │                  │
                                     │              1:N stages
                                     │                  │
                                     │              N:1 components
                                     │
                                 1:N simulation_runs
                                     │
                                 1:N telemetry_points
                                     │
                                 1:N simulation_events
                                     │
                                 0:N failure_events

space_objects (standalone catalog)
lessons (standalone catalog)
search_history (per user)
```

---

## 6. Simulation Engine Architecture

```
SimulationConfig
       │
       ▼
 Initial State ◄── Vehicle Model + Mission Config
       │
       ▼
┌─────────────── INTEGRATION LOOP ───────────────┐
│                                                  │
│  Environment ──► Forces ──► Acceleration         │
│       │              │            │              │
│  atmosphere      gravity      thrust             │
│  wind            drag         mass_flow          │
│                                                  │
│  Integrator (RK4) ──► State Update               │
│       │                                          │
│  Event Detection ──► Telemetry Emission          │
│       │                                          │
│  Termination Check                               │
└──────────────────────────────────────────────────┘
       │
       ▼
 Analysis + Failure Classification
```

### State Vector

```python
@dataclass
class SimulationState:
    t: float              # Time (s)
    position: Vec3        # [x, y, z] meters (ENU or ECEF)
    velocity: Vec3        # [vx, vy, vz] m/s
    acceleration: Vec3    # [ax, ay, az] m/s²
    mass: float           # kg (decreasing with burn)
    attitude: Vec3        # [pitch, yaw, roll] radians
    stage: int            # Current active stage
    phase: MissionPhase   # PRELAUNCH | POWERED | COAST | DESCENT
    events: list          # Accumulated events
```

### Model Fidelity Classification

| Model | Fidelity | Method |
|-------|----------|--------|
| Gravity | Analytical approx | g(h) = g₀·(R/(R+h))² |
| Atmosphere | Educational sim | US Std Atmosphere 1976 (layers) |
| Drag | Educational sim | Fd = 0.5·ρ·v²·Cd·A |
| Thrust | Analytical approx | F = Isp·g₀·ṁ (constant or profiled) |
| Trajectory | Numerical sim | RK4 integration, 3-DOF |
| Stability | Analytical approx | Barrowman equations (CP), CG calc |

---

## 7. Dependency Graph (Implementation Order)

```
                    ┌─────────────┐
                    │ Architecture │
                    │ & Contracts  │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ Database │ │ Frontend │ │Scientific│
        │  Schema  │ │  Setup   │ │ Models   │
        └────┬─────┘ └────┬─────┘ └────┬─────┘
             │            │            │
             ▼            │            ▼
        ┌──────────┐      │     ┌──────────────┐
        │   Auth   │      │     │  Simulation  │
        │   API    │      │     │    Engine     │
        └────┬─────┘      │     └──────┬───────┘
             │            │            │
             ▼            ▼            │
        ┌──────────┐ ┌──────────┐     │
        │Space Data│ │  Core UI │     │
        │  + Seeds │ │  Layout  │     │
        └────┬─────┘ └────┬─────┘     │
             │            │            │
             ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │  Search  │ │  Build   │ │Telemetry │
        │   API    │ │   UI     │ │ + Events │
        └────┬─────┘ └────┬─────┘ └────┬─────┘
             │            │            │
             └────────────┼────────────┘
                          ▼
                   ┌─────────────┐
                   │ Integration │
                   │  + AI + RKT │
                   └──────┬──────┘
                          ▼
                   ┌─────────────┐
                   │Demo Harden  │
                   │  + Polish   │
                   └─────────────┘
```

---

## 8. Development Phases

| Phase | Name | Duration | Key Deliverables |
|-------|------|----------|-----------------|
| 0 | Research & Contracts | 3-4 days | API contracts, DB schema, model specs |
| 1 | Foundation | 4-5 days | Repo, DB, Auth, CI, Core UI shell |
| 2 | Core Platform | 5-7 days | Projects, Dashboard, Space Data, Search |
| 3 | Build & Simulate | 7-10 days | Vehicle builder, Sim engine, Telemetry |
| 4 | Analyze & Explain | 4-5 days | Failure engine, AI explanations, Reports |
| 5 | Polish & Demo | 3-5 days | RKT, offline mode, demo hardening |

---

## 9. Team Interface Contracts

### P1 (Frontend) ↔ P2 (Backend)
- **Contract**: `packages/contracts/src/api.ts` — all API request/response types
- **Mock Server**: P1 works against mock API until P2 is ready
- **Integration checkpoint**: End of Phase 1

### P2 (Backend) ↔ P3 (Simulation)
- **Contract**: `packages/contracts/src/simulation.ts` — SimulationConfig, SimulationResult, TelemetryPoint
- **Interface**: P2 calls simulation as a Python library import
- **Integration checkpoint**: End of Phase 2

### P3 (Simulation) ↔ P1 (Frontend)
- **Contract**: WebSocket telemetry message format in `packages/contracts/`
- **Integration checkpoint**: Phase 3

### P4 (AI/Search) ↔ P2 (Backend)
- **Contract**: AI tool schemas, search query/response in `packages/contracts/`
- **Integration checkpoint**: Phase 4
]]>
