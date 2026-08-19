<![CDATA# 🚀 LostIntoSpacE

> A Space Exploration & Rocket Engineering Education Platform

**Explore → Learn → Build → Simulate → Fail → Understand → Improve → Repeat**

LostIntoSpacE is an integrated platform that combines space exploration, rocket engineering education, and physics-based simulation. Users explore celestial objects, learn aerospace concepts, design rockets, and run simulations to understand why missions succeed or fail.

---

## 🏗 Architecture Overview

```
USER
 ↓
FRONTEND (React + TypeScript + Three.js)
 ↓
API LAYER (Python FastAPI)
 ├── Auth, Projects, Missions, Vehicles
 ├── Search, Learning, AI, Reports
 ↓
DOMAIN SERVICES
 ├── Space Data, Mission Engine, Vehicle Engine
 ├── Simulation Engine, Analysis, Recommendations
 ↓
DATA LAYER
 ├── PostgreSQL, Cache, Object Storage
 ↓
EXTERNAL SOURCES
 ├── NASA APIs, Weather, Scientific Data
```

## 📁 Repository Structure

| Directory | Purpose | Owner |
|-----------|---------|-------|
| `apps/web/` | React frontend application | Frontend |
| `apps/api/` | FastAPI backend application | Backend |
| `packages/` | Shared contracts, types, UI components | All |
| `simulation/` | Physics simulation engine (Python) | Simulation |
| `scientific/` | Scientific models, constants, atmosphere | Simulation |
| `ai/` | AI provider abstraction, prompts, grounding | AI/Search |
| `search/` | Search indexing, ranking, suggestions | AI/Search |
| `data/` | Data ingestion, seeds, fallback datasets | AI/Search |
| `database/` | Migrations, seeds, scripts | Backend |
| `tests/` | Cross-cutting test suites | All |
| `docs/` | Architecture, API, scientific documentation | All |
| `deployment/` | Docker, nginx, deploy scripts | Backend |

## 🧑‍🤝‍🧑 Team Allocation

| Person | Role | Owns |
|--------|------|------|
| **P1** | Frontend / UX / 3D | `apps/web/`, `assets/`, `packages/ui/` |
| **P2** | Backend / Database / APIs | `apps/api/`, `database/`, `deployment/` |
| **P3** | Simulation / Scientific Models | `simulation/`, `scientific/` |
| **P4** | AI / Search / Data / Integration | `ai/`, `search/`, `data/`, `packages/contracts/` |

## 🚀 Quick Start

```bash
# 1. Clone
git clone <repo-url> && cd LostIntoSpacE

# 2. Copy environment
cp .env.example .env

# 3. Frontend setup
cd apps/web && npm install && npm run dev

# 4. Backend setup (in another terminal)
cd apps/api && pip install -r requirements.txt && uvicorn src.main:app --reload

# 5. Database
createdb lostintospace
cd database && alembic upgrade head
```

## 📚 Documentation

- [Architecture](docs/architecture/ARCHITECTURE.md)
- [API Reference](docs/api/API.md)
- [Simulation Engine](docs/simulation/SIMULATION.md)
- [Scientific Models](docs/scientific/MODELS.md)
- [Setup Guide](docs/setup/SETUP.md)
- [Demo Runbook](docs/demo/DEMO_RUNBOOK.md)
- [RKT Specification](docs/rkt_spec/RKT_SPEC.md)
- [Decision Log](docs/decisions/DECISION_LOG.md)

## 📄 License

MIT License — see [LICENSE](LICENSE)
]]>
