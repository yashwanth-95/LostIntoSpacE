# Environment Variables

Every variable in `.env.example`, what it does, and whether the prototype needs
it. No real value appears in this file or in any tracked file.

`.env` is git-ignored. `.env.example` is the template and is committed.

---

## General

| Variable | Purpose | Required for MVP? | Example | Where to obtain | Safe to commit? |
|---|---|---|---|---|---|
| `APP_ENV` | Environment name. `production` triggers the startup safety check on `SECRET_KEY`. | No — defaults to `development` | `development` | Choose | Yes |
| `DEBUG` | Application debug flag. Note the FastAPI app pins `debug=False` regardless, so error responses keep the JSON envelope in every environment. | No | `true` | Choose | Yes |
| `LOG_LEVEL` | Logging verbosity. | No — defaults to `info` | `info` | Choose | Yes |

## Backend

| Variable | Purpose | Required for MVP? | Example | Where to obtain | Safe to commit? |
|---|---|---|---|---|---|
| `API_HOST` | Bind address. | No | `0.0.0.0` | Choose | Yes |
| `API_PORT` | Bind port. | No — defaults to 8000 | `8000` | Choose | Yes |
| `SECRET_KEY` | Signs JWTs. **Anyone with this can mint a valid token for any user.** | **Yes for anything but local dev** | `openssl rand -hex 32` | Generate | **No** |
| `JWT_ALGORITHM` | JWT signing algorithm. | No — defaults to `HS256` | `HS256` | — | Yes |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Access-token lifetime. | No — defaults to 30 | `30` | Choose | Yes |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | Refresh-token lifetime. | No — defaults to 7 | `7` | Choose | Yes |
| `CORS_ORIGINS` | Comma-separated origins allowed to call the API. | No in development | `http://localhost:3000` | Your frontend origin | Yes |

`validate_production_safety()` refuses to start when `APP_ENV=production` and
`SECRET_KEY` is still the example default. Development is deliberately not
guarded, so a fresh checkout runs without ceremony.

**On `CORS_ORIGINS`:** in development the Vite proxy makes API calls
same-origin, so CORS is never exercised. It matters when the frontend is served
from a different origin. It must never be `*` on a service that accepts
credentials.

## Database

| Variable | Purpose | Required for MVP? | Example | Where to obtain | Safe to commit? |
|---|---|---|---|---|---|
| `DATABASE_URL` | PostgreSQL connection, asyncpg driver. | **Yes** for persistence, Explore and auth | `postgresql+asyncpg://lostintospace:PASSWORD@localhost:5432/lostintospace` | You create it — `database/scripts/setup_local_db.sql` | **No** |
| `DATABASE_ECHO` | Log every SQL statement. Noisy; useful when debugging a query. | No | `false` | — | Yes |
| `TEST_DATABASE_URL` | Separate database for the test suite. Tests needing a live server **skip** when unset. | No | `postgresql+asyncpg://lostintospace:PASSWORD@localhost:5432/lostintospace_test` | Same script | **No** |

`TEST_DATABASE_URL` pointing at a *different* database is what stops a test run
from destroying development data. Do not point both at the same one.

## External data

| Variable | Purpose | Required for MVP? | Example | Where to obtain | Safe to commit? |
|---|---|---|---|---|---|
| `NASA_API_KEY` | Authenticates NASA API requests. | No — `DEMO_KEY` works, at a much lower rate limit | `DEMO_KEY` | <https://api.nasa.gov> | **No** |

JPL, ESA, ISRO, CelesTrak, the Minor Planet Center and the Exoplanet Archive
adapters need **no credentials**. Live tests against any external source are
gated behind `LOSTINTOSPACE_LIVE_TESTS=1` and skip by default, so a normal test
run never touches the network.

## AI provider

| Variable | Purpose | Required for MVP? | Example | Where to obtain | Safe to commit? |
|---|---|---|---|---|---|
| `LIS_AI_PROVIDER` | Selects the provider. Unset resolves to `extractive`. | No | `extractive` | — | Yes |
| `AI_API_KEY` | Credential for a hosted model provider. | No | — | Your provider | **No** |
| `AI_MODEL` | Model identifier. | No | — | Your provider | Yes |

With no key configured the registry resolves to `extractive`, which composes
answers out of retrieved passages rather than generating prose. The assistant
page displays which provider answered, so nothing is presented as more than it
is. `GET /api/v1/ai/provider` reports the same thing.

## Optional

| Variable | Purpose | Required for MVP? | Notes |
|---|---|---|---|
| `REDIS_URL` | Caching / rate limiting. | No | Nothing reads it yet. Present for when caching or rate limiting is added. |
| `UPLOAD_DIR` | Upload destination. | No | **No upload endpoint exists.** Configured ahead of a feature that is not built. |
| `MAX_UPLOAD_SIZE_MB` | Upload size cap. | No | As above. |

---

## Minimum to run the product loop

Nothing. With no `.env` at all, the backend starts on its defaults and the
rocket builder, simulation, mission control, search and the AI assistant all
work.

## Minimum to add persistence

`DATABASE_URL`, pointing at a database that exists and has had
`alembic upgrade head` applied.

## Before deploying anywhere real

- A generated `SECRET_KEY`
- `APP_ENV=production`
- `CORS_ORIGINS` listing only your real frontend origin
- A `DATABASE_URL` whose password is not the example default

---

## Handling rules

1. Secrets come from the environment. Never from a tracked file, a default, or
   a docstring.
2. `.env` stays git-ignored. `git check-ignore .env` should print a match.
3. A rotated `SECRET_KEY` invalidates every issued token — which is the point
   when rotating after an exposure.
4. Never log a connection string. The database error handler deliberately
   discards the driver's message, because asyncpg puts the user and host in it.
