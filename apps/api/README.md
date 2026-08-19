<![CDATA[# Backend API — `apps/api/`

## Owner: P2 (Backend / Database / APIs)

## Tech Stack
- Python 3.11+ / FastAPI
- SQLAlchemy 2.0 (async) + Alembic
- Pydantic v2 (validation)
- python-jose + passlib (auth)
- uvicorn (server)

## Module Structure

Legend: ✅ implemented (Phase 2 — backend foundation) · ⬜ scaffolded only, not yet implemented (Phase 3+).

```
src/
├── main.py             ✅  App entrypoint: settings, logging, middleware, error handlers, router mounting
├── api_router.py       ✅  Top-level /api/v1 router (health check only so far; domain routers get
│                            included here in later phases)
├── core/
│   ├── config/         ✅  Settings (pydantic-settings), env loading, production-safety check
│   ├── logging/        ✅  Structured JSON logging setup (added Phase 2, not in the original module list)
│   ├── envelope/       ✅  success_envelope()/error_envelope() - the API.md response shape as code
│   ├── middleware/     ✅  CORS + per-request structured logging (X-Request-ID)
│   ├── exceptions/     ✅  AppError hierarchy + centralized exception handlers
│   ├── database/       ✅  Lazy async engine, session factory, get_db, DeclarativeBase, mixins
│   └── security/       ✅  bcrypt password hashing, JWT access tokens (python-jose),
│                            opaque refresh token generation/hashing
├── models/             ✅  SQLAlchemy ORM models — 15 of 17 tables (Phase 4)
├── schemas/            ✅  auth.py: RegisterRequest/LoginRequest/AuthResponse/etc. (Phase 5).
│                            Other domains' schemas are still Phase 6+.
├── auth/               ✅  register/login/me/refresh/logout, get_current_user (Phase 5)
│   ├── router.py           # POST /auth/register, /login, /refresh, /logout, GET /auth/me
│   ├── service.py          # Business logic - registration, credential checks, token rotation
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

`projects/`, `missions/`, `vehicles/`, `space_data/`, `search/`, `learning/`, `ai/`, `reports/`, and `users/` are still empty scaffold directories (`.gitkeep` only). `auth/`, `models/`, and `schemas/` are implemented as of Phase 5/4. See `docs/backend/BACKEND_STATE.md` §10 for the build order.

`core/` is a package of packages, not a package of flat files (each entry above is a directory containing its own `__init__.py`, and further files as a concern grows). This matches the scaffold already committed to the repo and has been the source of truth since the 2026-08-18 pre-Phase-2 correction — an earlier draft of this doc showed flat files (`core/config.py`, etc.); that draft is superseded.

Internal cross-module imports are rooted at the installed package name, e.g. `from src.core.config import get_settings` — not `from core.config import ...`. The package is installed in editable mode (`pip install -e .`), which is what makes this work from any working directory once the venv is active; a bare `from core...` import only happens to work by accident of `sys.path`, and breaks under `uvicorn`. See `## Local Development` below.

## Local Development

The `.env` file lives at the **repo root** (`LostIntoSpacE/.env`, copied from `.env.example`), not inside `apps/api/`. `core/config` finds it automatically by walking up from the current working directory, so it doesn't matter whether you run these commands from the repo root or from `apps/api/`.

```bash
# From the repo root, once:
cp .env.example .env

# Backend setup:
cd apps/api
python -m venv venv
source venv/Scripts/activate   # Windows Git Bash. Linux/Mac: source venv/bin/activate
                                # Windows cmd.exe: venv\Scripts\activate.bat
pip install -e ".[dev]"

# Run the dev server:
python -m uvicorn src.main:app --reload --port 8000
```

Verify it worked:
- `http://localhost:8000/api/v1/health` → `{"status":"success","data":{"state":"ok",...}}`
- `http://localhost:8000/docs` → Swagger UI

Quality checks (all configured in `pyproject.toml`):
```bash
python -m pytest                          # tests/
python -m ruff check src tests            # lint
python -m ruff format src tests           # format
python -m mypy                            # type check
```

The test suite needs **no database**: models are compiled to PostgreSQL DDL with a dialect object rather than a connection. Tests that do need a live server read `TEST_DATABASE_URL` (never `DATABASE_URL`) and skip when it is unset.

### Database

Models live in `src/models/`; ORM concerns and Pydantic API schemas never share a file. Migrations are in `database/migrations/` and run with the same virtualenv:

```bash
cd ../../database && alembic upgrade head
```

See **[`docs/backend/DATABASE_SETUP.md`](../../docs/backend/DATABASE_SETUP.md)** for PostgreSQL requirements (13+), the test-database setup, and the verification commands. `src/models/` is the only place Alembic looks for tables — a model not reachable from `src/models/__init__.py` is invisible to autogenerate.

Dependencies are declared in `apps/api/pyproject.toml`, not a `requirements.txt` — this is the single source of truth for both runtime and dev-tool (ruff/mypy/pytest) versions, avoiding two dependency lists drifting apart.

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
- All errors return structured JSON (see API.md) — enforced centrally by `core/exceptions`, not per-route
]]>
