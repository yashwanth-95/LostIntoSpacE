<![CDATA[# API Architecture

## Base URL
```
/api/v1
```

## Authentication

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| POST | `/auth/register` | Create account | Public |
| POST | `/auth/login` | Get tokens | Public |
| POST | `/auth/logout` | Revoke the current refresh token | Bearer |
| POST | `/auth/refresh` | Rotate refresh token, get new access token | Refresh token |
| GET | `/auth/me` | Current user profile | Bearer |

**Token semantics** (see `docs/architecture/DATABASE.md` `refresh_tokens`, `docs/decisions/DECISION_LOG.md` #16): access tokens are stateless JWTs, verified by signature only, never persisted. Refresh tokens are persisted (hashed) so they can actually be revoked — `/auth/logout` sets `revoked_at` on the caller's refresh token row; `/auth/refresh` rotates (issues a new row, revokes the old one via `replaced_by`) rather than reusing the same token indefinitely.

## Projects

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| GET | `/projects` | List user's projects | Bearer |
| POST | `/projects` | Create project | Bearer |
| GET | `/projects/{id}` | Get project details | Bearer (owner) |
| PATCH | `/projects/{id}` | Update project | Bearer (owner) |
| DELETE | `/projects/{id}` | Delete project | Bearer (owner) |

## Missions

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| GET | `/projects/{pid}/missions` | List missions in project | Bearer |
| POST | `/projects/{pid}/missions` | Create mission | Bearer |
| GET | `/missions/{id}` | Get mission | Bearer |
| PATCH | `/missions/{id}` | Update mission | Bearer |
| DELETE | `/missions/{id}` | Delete mission | Bearer |
| POST | `/missions/{id}/validate` | Validate mission config | Bearer |

## Vehicles

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| GET | `/missions/{mid}/vehicle` | Get vehicle for mission | Bearer |
| POST | `/missions/{mid}/vehicle` | Create/replace vehicle | Bearer |
| PATCH | `/vehicles/{id}` | Update vehicle | Bearer |
| POST | `/vehicles/{id}/validate` | Validate vehicle | Bearer |
| GET | `/vehicles/{id}/stages` | List stages | Bearer |
| POST | `/vehicles/{id}/stages` | Add stage | Bearer |
| PATCH | `/stages/{id}` | Update stage | Bearer |
| DELETE | `/stages/{id}` | Remove stage | Bearer |
| GET | `/vehicles/{id}/components` | List components | Bearer |
| POST | `/vehicles/{id}/components` | Add component | Bearer |
| PATCH | `/components/{id}` | Update component | Bearer |
| DELETE | `/components/{id}` | Remove component | Bearer |

## Space Data

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| GET | `/space-objects` | List/filter objects | Public |
| GET | `/space-objects/{id}` | Object detail | Public |
| GET | `/space-objects/categories` | Category list | Public |

## Search

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| GET | `/search?q={query}&type=&category=` | Unified search | Optional |
| GET | `/search/suggestions?q={prefix}` | Autocomplete | Optional |
| GET | `/search/history` | User search history | Bearer |

## Learning

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| GET | `/lessons` | List lessons | Public |
| GET | `/lessons/{slug}` | Get lesson | Public |
| GET | `/lessons/categories` | Lesson categories | Public |
| POST | `/learning/progress` | Track progress | Bearer |

## Simulation

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| POST | `/simulations/validate` | Pre-flight validation | Bearer |
| POST | `/simulations/run` | Start simulation | Bearer |
| GET | `/simulations/{id}` | Get run summary | Bearer |
| GET | `/simulations/{id}/telemetry` | Get telemetry data | Bearer |
| GET | `/simulations/{id}/events` | Get events | Bearer |
| GET | `/simulations/{id}/analysis` | Get analysis | Bearer |
| WS | `/ws/simulation/{id}` | Realtime telemetry stream | Bearer |

## AI

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| POST | `/ai/explain` | Explain concept/result | Bearer |
| POST | `/ai/failure-analysis` | Explain why simulation failed | Bearer |
| POST | `/ai/recommend` | Suggest improvements | Bearer |
| POST | `/ai/tutor` | Contextual tutoring Q&A — creates/continues a `conversations` row and appends `messages` | Bearer |
| GET | `/ai/conversations` | List current user's conversations | Bearer |
| GET | `/ai/conversations/{id}` | Get a conversation with its messages | Bearer (owner) |

Conversation/message persistence is backend-owned (P2); see `docs/architecture/DATABASE.md` `conversations`/`messages`. The AI module (`apps/api/src/ai/`) is responsible for writing to these tables. Whether the root `ai/` library (P4) touches the database directly or stays a pure completion-producing library like `simulation/` is not yet settled — see `docs/backend/KNOWN_ISSUES.md` §4 item D-3 for the open clarification needed with P4.

## Reports

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| POST | `/reports` | Generate report | Bearer |
| GET | `/reports/{id}` | Get report | Bearer |

## RKT Files

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| POST | `/rkt/export/{project_id}` | Export project as .rkt | Bearer |
| POST | `/rkt/import` | Import .rkt file | Bearer |
| POST | `/rkt/validate` | Validate .rkt file | Bearer |

---

## Standard Response Envelope

```json
{
  "status": "success",
  "data": { ... },
  "meta": {
    "page": 1,
    "per_page": 20,
    "total": 100
  }
}
```

## Error Response

```json
{
  "status": "error",
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Vehicle has no stages",
    "details": [...]
  }
}
```

---

## Implementation Status (2026-08-19, backend contract freeze)

This document is the *design* contract. The table below records what the
backend actually serves today, so P1/P3/P4 can tell a published-but-unbuilt
path from a live one. The generated OpenAPI at `/openapi.json` (Swagger UI at
`/docs`) is the machine-readable source of truth and is now fully typed -
every response references a named schema, and 401/404/409 are documented per
operation.

| Area | Status |
|---|---|
| Auth (register/login/logout/refresh/me) | **Live** |
| Users (`/users/me`, `/users/me/preferences`) | **Live** — added since this doc was written |
| Projects CRUD (+ `/projects/{id}/missions`) | **Live** |
| Missions CRUD (+ `/missions/{id}/vehicle`) | **Live** |
| Vehicles CRUD + components | **Live** |
| Lessons + learning progress | **Live** |
| Space objects (list/detail/categories) | **Live** — filtering, full-text `q`, sorting |
| Conversations + messages | **Live** — at `/conversations` and `/ai/conversations` |
| Health / readiness | **Live** — `/health`, `/health/ready` (not in the original design doc) |
| Vehicle **stages** (`/vehicles/{id}/stages`, `/stages/{id}`) | **Blocked on P3** — `vehicle_stages` schema unresolved (`DECISION_LOG` #25/#26) |
| Simulations (`/simulations/*`, `/ws/simulation/{id}`) | **Blocked on P3** — telemetry contract open (`DECISION_LOG` #24) |
| Validation (`/missions/{id}/validate`, `/vehicles/{id}/validate`) | **Not built** — physics validation is P3's engine, not backend |
| AI generation (`/ai/explain`, `/ai/tutor`, ...) | **Not built** — P4 owns generation; P2 provides the persistence endpoints |
| Search (`/search`, `/search/suggestions`, `/search/history`) | **Not built** — P4 owns search internals; `search_history` table exists |
| Reports, RKT import/export | **Deferred** |

### Endpoints live in the backend but not listed above

Added during Phases 6-12 and not present in the original design tables:

| Method | Path | Auth |
|--------|------|------|
| GET/PATCH | `/users/me` | Bearer |
| GET/PATCH | `/users/me/preferences` | Bearer |
| GET/POST | `/missions` | Bearer |
| DELETE | `/missions/{id}` | Bearer (owner) |
| GET/POST | `/vehicles` | Bearer |
| GET/DELETE | `/vehicles/{id}` | Bearer (owner) |
| GET | `/learning/progress` | Bearer |
| PATCH | `/learning/progress/{lesson_id}` | Bearer |
| GET/POST | `/conversations` | Bearer |
| GET/PATCH/DELETE | `/conversations/{id}` | Bearer (owner) |
| GET/POST | `/conversations/{id}/messages` | Bearer (owner) |
| GET | `/health`, `/health/ready` | Public |

### Conventions all live endpoints follow

- **Pagination** on every list endpoint: `?page=` (>=1), `?per_page=` (1-100, default 20). `meta` is always `{page, per_page, total}`.
- **Ownership**: a resource owned by another user returns **404, not 403** — a 403 would confirm the id exists and let an attacker enumerate other users' data.
- **Updates are allow-lists**: unknown fields in a PATCH body are rejected with 422, never silently ignored. `role`, `is_active`, `user_id`, and derived physics values cannot be set by a client.
- **DELETE returns 204** with no body — the one deliberate exception to the envelope.

]]>
