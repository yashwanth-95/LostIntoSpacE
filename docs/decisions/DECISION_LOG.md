<![CDATA[# Decision Log

Track all significant architectural and technical decisions.

| # | Date | Decision | Choice | Rationale | Alternatives | Revisit? |
|---|------|----------|--------|-----------|-------------|----------|
| 1 | — | Backend framework | FastAPI (Python) | Async, auto-docs, scientific Python ecosystem | Django, Express.js | No |
| 2 | — | Frontend framework | React + TypeScript + Vite | Strong ecosystem, R3F integration, fast builds | Next.js, Svelte | If SSR needed |
| 3 | — | 3D library | React Three Fiber | Declarative Three.js with React integration | raw Three.js, Babylon.js | No |
| 4 | — | Database | PostgreSQL | Full-text search built-in, JSONB, mature | MongoDB, SQLite | No |
| 5 | — | ORM | SQLAlchemy 2.0 async | Type safety, Alembic migrations, async support | Tortoise, raw SQL | No |
| 6 | — | State management | Zustand + TanStack Query | Minimal boilerplate, excellent caching | Redux, Jotai, MobX | No |
| 7 | — | Auth | JWT (access + refresh) | Stateless, simple, well-documented | Session cookies, OAuth | If scale needed |
| 8 | — | Simulation fidelity | 3-DOF + RK4 | Sufficient for education, achievable by team | 6-DOF, adaptive solvers | Post-SIH |
| 9 | — | Search | PostgreSQL FTS + tsvector | No extra infra, good enough for MVP | Meilisearch, Elasticsearch | If perf needed |
| 10 | — | Architecture | Modular monolith | Simple deployment, shared types, student-friendly | Microservices | Post-SIH |
| 11 | — | Styling | Tailwind CSS v3 | Rapid prototyping, team knows it | Vanilla CSS, Styled Components | No |
| 12 | — | Deployment | Docker Compose | Single-command, portable, reproducible | K8s, bare metal | Post-SIH |
| 13 | — | AI integration | Provider abstraction | Swap OpenAI/Gemini/local without code changes | Direct API calls | No |
| 14 | — | File format | .rkt (JSON-based) | Human-readable, easy to validate, versionable | Binary, protobuf | If perf needed |
| 15 | — | Atmosphere model | US Std 1976 | Well-documented, public domain, educational | NRLMSISE-00 | Post-SIH |

## Unresolved Decisions

| Topic | Options | Blocker | Owner |
|-------|---------|---------|-------|
| Semantic search | pgvector vs external embeddings | Need to test query quality | P4 |
| Weather API | OpenWeatherMap vs Open-Meteo | Licensing verification needed | P4 |
| 3D model format | GLTF vs procedural geometry | Depends on asset complexity | P1 |
| CI/CD platform | GitHub Actions vs self-hosted | Depends on hosting decision | P2 |
]]>
