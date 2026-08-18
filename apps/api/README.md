<![CDATA[# Backend API — `apps/api/`

## Owner: P2 (Backend / Database / APIs)

## Tech Stack
- Python 3.11+ / FastAPI
- SQLAlchemy 2.0 (async) + Alembic
- Pydantic v2 (validation)
- python-jose + passlib (auth)
- uvicorn (server)

## Module Structure

```
src/
├── main.py                 # App entrypoint, router mounting
├── core/
│   ├── config.py           # Settings from environment
│   ├── security.py         # JWT, password hashing
│   ├── database.py         # AsyncSession factory
│   ├── middleware.py        # CORS, logging, error handling
│   └── exceptions.py       # Custom exception classes
├── models/                 # SQLAlchemy ORM models (all tables)
├── schemas/                # Pydantic request/response schemas
├── auth/
│   ├── router.py           # POST /auth/register, /login, etc.
│   ├── service.py          # Business logic
│   └── dependencies.py     # get_current_user dependency
├── projects/
│   ├── router.py
│   └── service.py
├── missions/
│   ├── router.py
│   └── service.py
├── vehicles/
│   ├── router.py
│   └── service.py
├── simulation/
│   ├── router.py           # POST /simulations/run
│   ├── service.py          # Orchestrates simulation engine
│   └── websocket.py        # WS /ws/simulation/{id}
├── space_data/
│   ├── router.py
│   └── service.py
├── search/
│   ├── router.py
│   └── service.py
├── learning/
│   ├── router.py
│   └── service.py
├── ai/
│   ├── router.py
│   └── service.py
└── reports/
    ├── router.py
    └── service.py
```

## Allowed Imports
- `packages/contracts/` — shared types
- `simulation/` — simulation engine (Python import)
- `scientific/` — scientific constants and models
- `ai/` — AI provider abstraction
- `search/` — search engine
- NO imports from `apps/web/`

## Key Rules
- Every router function validates input via Pydantic schema
- Every database query uses async session
- Every protected route uses `Depends(get_current_user)`
- All errors return structured JSON (see API.md)
]]>
