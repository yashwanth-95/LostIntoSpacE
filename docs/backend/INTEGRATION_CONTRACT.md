# Backend Integration Contract (Frozen)

**Owner:** Person 2 · **Date:** 2026-08-19 · **Status:** frozen for P1/P3/P4 integration

The machine-readable contract is the backend's own OpenAPI schema:

```
http://localhost:8000/openapi.json      # generate your client from this
http://localhost:8000/docs              # Swagger UI
```

Every response is now a **named schema** — no operation returns an untyped
object — and 401/404/409 are documented per operation, so a generated client
gets real types for both success and failure paths.

---

## Universal conventions

Everything below applies to every endpoint; the per-team sections only add specifics.

**Base path.** `/api/v1` — enforced by a test, nothing is served outside it.

**Success envelope.**
```json
{ "status": "success", "data": { ... } }
{ "status": "success", "data": [ ... ], "meta": { "page": 1, "per_page": 20, "total": 57 } }
```

**Error envelope.** Identical shape for every failure:
```json
{ "status": "error", "error": { "code": "NOT_FOUND", "message": "Project not found", "details": [] } }
```

`DELETE` returns **204 with no body** — the one deliberate exception.

**Auth.** `Authorization: Bearer <access_token>`. Access tokens are short-lived JWTs; refresh tokens are opaque strings sent in the request *body* (they are not JWTs, so there is nothing for the Bearer scheme to parse).

**Pagination.** `?page=` (≥1), `?per_page=` (1–100, default 20). Out-of-range values are 422 before any query runs.

**Ownership: 404, never 403.** A resource that exists but belongs to another user is indistinguishable from one that never existed. This is deliberate — a 403 would confirm the id is real and let an attacker enumerate other users' data. Do not treat a 404 as "definitely deleted".

**Updates are allow-lists.** Unknown fields in a PATCH body return **422**, they are not silently dropped. `role`, `is_active`, `user_id`, `password_hash`, and derived physics values cannot be set by any client.

**IDs.** UUIDv4 everywhere, as strings in JSON. A malformed UUID in a path is 422.

**Timestamps.** ISO-8601 with timezone (`TIMESTAMPTZ` throughout).

---

## P1 — Frontend contract

| Area | Endpoints |
|---|---|
| Auth | `POST /auth/register` · `POST /auth/login` · `POST /auth/refresh` · `POST /auth/logout` · `GET /auth/me` |
| Users | `GET/PATCH /users/me` · `GET/PATCH /users/me/preferences` |
| Projects | `GET/POST /projects` · `GET/PATCH/DELETE /projects/{id}` |
| Missions | `GET/POST /projects/{id}/missions` · `GET/POST /missions` · `GET/PATCH/DELETE /missions/{id}` |
| Vehicles | `GET/POST /vehicles` · `GET/PATCH/DELETE /vehicles/{id}` · `GET/POST /missions/{id}/vehicle` |
| Components | `GET/POST /vehicles/{id}/components` · `PATCH/DELETE /components/{id}` |
| Learning | `GET /lessons` · `GET /lessons/categories` · `GET /lessons/{id-or-slug}` · `GET/POST /learning/progress` · `PATCH /learning/progress/{lesson_id}` |
| Space objects | `GET /space-objects` · `GET /space-objects/categories` · `GET /space-objects/{id}` |
| Conversations | `GET/POST /conversations` · `GET/PATCH/DELETE /conversations/{id}` · `GET/POST /conversations/{id}/messages` |
| Health | `GET /health` (liveness) · `GET /health/ready` (503 if DB unreachable) |

**Auth flow.** `register` and `login` both return the identical `AuthResponse` (`access_token`, `refresh_token`, `token_type`, `expires_in`, `user`) — registration auto-logs-in, so there is no second round trip. On 401 from any endpoint, call `POST /auth/refresh` with the stored refresh token; it **rotates**, so replace the stored token with the new one every time.

**Refresh-token reuse is a lockout.** Presenting an already-rotated token revokes the entire session family and returns the same generic 401 as any other invalid token. Never retry a refresh with an old token, and never run two refreshes concurrently — store the new token before the next call.

**Terminology.** The API says `vehicle`; the UI may render "Rocket" freely. No backend field will ever be renamed to `rocket`.

**Public without a token:** `/health*`, `/lessons*`, `/space-objects*`, and the three auth entry points. Everything else is 401 without a Bearer token.

---

## P3 — Simulation / Rocket-builder contract

**What the backend gives you:** persistence and ownership. **What it never does:** physics.

### Vehicle loading (the builder's save/load path)

```
GET  /api/v1/missions/{mission_id}/vehicle    -> vehicle + all components
POST /api/v1/missions/{mission_id}/vehicle    -> create (mission_id from path)
GET  /api/v1/vehicles/{vehicle_id}            -> same payload, by vehicle id
PATCH/DELETE /api/v1/vehicles/{vehicle_id}
GET/POST /api/v1/vehicles/{vehicle_id}/components
PATCH/DELETE /api/v1/components/{component_id}
```

A vehicle belongs to exactly **one** mission (1:1, DB-enforced). `POST` to a mission that already has one returns **409** rather than silently destroying the existing design and its components.

**Component fields are your contract and are passed through verbatim:**

```json
{
  "component_type": "nose|body|fins|engine|payload|recovery|avionics",
  "name": "Ogive Nose",
  "mass_kg": 5.0,
  "position":   { "x": 0, "y": 0, "z": 2.5 },
  "dimensions": { "length_m": 0.5, "diameter_m": 0.3 },
  "properties": {},
  "parent_id": null,
  "sort_order": 0
}
```

`position`, `dimensions`, and `properties` are opaque JSONB — the backend stores and returns them unchanged and never interprets their interiors. `component_type` is validated against the list above; `mass_kg` must be ≥ 0 (matching the DB CHECK). Nothing else about a design is validated here.

**Read-only derived fields.** `total_mass_kg`, `cg_position`, `cp_position`, `stability_margin`, `is_valid`, `validation_errors` appear in responses but are **rejected in requests** (422). They are currently `null`/`false` because the backend does not compute physics — filling them with invented numbers would be fabricating results. When your engine computes them, we add a write path; the field names are already reserved.

### Mission loading

```
GET /api/v1/missions/{id}          -> name, objective, status,
                                      target_orbit / launch_site / environment (opaque JSONB)
GET /api/v1/projects/{id}/missions -> all missions in a project
```

The three JSONB config blobs are stored and returned verbatim, for the same reason as component geometry: their shape is yours to define, and fossilizing it into backend columns would make every change of yours a backend migration.

### ⚠ Blocked — not implemented, and deliberately so

| Blocked | Why |
|---|---|
| `vehicle_stages` + `/vehicles/{id}/stages`, `/stages/{id}` | Two unresolved questions: **SD-6** — is stage dry mass authored or derived from components? **SD-7** — `thrust_n`/`isp_s`/`burn_time_s`/`propellant_mass_kg` are four fields with only three degrees of freedom under `F = Isp·g₀·ṁ`. |
| `telemetry_points` + `/simulations/{id}/telemetry` | **SD-5** — flat `float8` columns vs JSONB, and whether attitude is persisted. |
| `/simulations/run`, `/simulations/{id}`, `/ws/simulation/{id}` | Depend on the above. |

**We are not guessing at these.** `RKT_SPEC.md`'s worked example is currently **physically impossible** — it declares 5000 N thrust while its own Isp/propellant/burn-time imply 12,258 N (2.45× off, verified numerically). Until you pick the authoritative fields, any schema we wrote would encode that contradiction.

**Three answers unblock all of it:** (1) which three propulsion fields are authoritative, (2) is stage dry mass authored or derived, (3) flat columns or JSONB for telemetry vectors. See `SCHEMA_DECISIONS.md` SD-5/SD-6/SD-7.

**Stable anchor.** When simulation results land, reference `simulation_runs.id` and nothing deeper. Telemetry and events are internal detail of a run and will change; the run id will not.

---

## P4 — AI / Space-data contract

### Space objects — you write, we read

You own ingestion and write rows through `database/seeds/` loaders. The API is **read-only** and works identically whether rows came from a live NASA fetch or bundled fallback data — which is what makes the offline demo mode work.

```
GET /api/v1/space-objects?category=&source=&q=&sort=&order=&page=&per_page=
GET /api/v1/space-objects/categories
GET /api/v1/space-objects/{id}
```

`q` runs PostgreSQL full-text search over the `search_vector` **generated column**, which the database maintains itself — you never populate an index. `sort` is restricted to `name|category|created_at|last_updated`; anything else is 422, so no caller input reaches SQL. `physical_data`, `orbital_data`, and `discovery` are opaque JSONB.

**Re-ingestion is safe:** the partial-unique index on `(source, source_id)` makes loaders upsert rather than duplicate.

### Conversation persistence — you generate, we store

```
POST /api/v1/conversations                        -> create
GET  /api/v1/conversations                        -> list (paginated)
GET  /api/v1/conversations/{id}                   -> conversation + full transcript, oldest first
PATCH/DELETE /api/v1/conversations/{id}
GET/POST /api/v1/conversations/{id}/messages
```

Also mounted at `/api/v1/ai/conversations` (the path `API.md` publishes) — same implementation, both work.

**The persistence flow:** your model produces a reply → `POST /conversations/{id}/messages` with `{"role": "assistant", "content": "...", "grounding": [...]}`. The backend **never calls a model**, builds a prompt, embeds text, or retrieves context.

**`grounding` is the provenance field** and exists to enforce "AI explains, models calculate": references to the deterministic data an answer rests on (`simulation_runs`, `failure_events`, `lessons`, `space_objects`). Stored verbatim, never interpreted. Please populate it — it is what makes an answer auditable rather than merely asserted.

**`context_ref`** is a soft link (`{"type": "simulation_run", "id": "..."}`), intentionally not a foreign key: a conversation should survive deletion of whatever it was about. Handle a dangling reference gracefully.

**Messages carry no `user_id`** — ownership is inherited from the conversation. Deleting a conversation cascades its messages.

---

## Contract issues found during this freeze

| # | Issue | Resolution |
|---|---|---|
| 1 | **Every response documented as an untyped `object`.** Request schemas were in OpenAPI but no response was — a generated client got `any` for every payload, so the schema was not actually a contract. | **Fixed.** Generic `SuccessResponse[T]`/`PaginatedResponse[T]` envelopes; 51/51 operations now reference named schemas. Locked by `test_no_operation_returns_an_untyped_object`. |
| 2 | Error shapes undocumented per operation. | **Fixed.** 401/404/409/503 registered with `ErrorResponse`; 82 documented error responses. |
| 3 | `GET/POST /projects/{pid}/missions` published in `API.md`, not implemented. | **Fixed.** Thin aliases over the existing mission service. |
| 4 | `GET/POST /missions/{mid}/vehicle` published, not implemented — the natural path for P3's "load the vehicle for this mission". | **Fixed.** Aliases over the vehicle service; `POST` returns 409 rather than destroying an existing design. |
| 5 | `API.md` had drifted — 26 live endpoints undocumented, 29 documented paths unbuilt with no indication which was which. | **Fixed.** Implementation-status table added to `API.md`. |
| 6 | `GET /search/history` is published and its `search_history` table exists, but no endpoint. | **Not fixed** — a new feature, out of scope for a freeze. Flagged for the team. |

**No finalized decision was reversed:** `vehicle` remains canonical, `simulation_events` remains canonical, no `mission_events`, no `rockets` tables, deferred entities stayed deferred, P3-blocked tables stayed blocked. A test asserts each of these absences.

---

## Remaining blockers

1. **No live PostgreSQL run** (`KNOWN_ISSUES` P-10, P-14). 49 integration tests — including every ownership-isolation assertion — are written and skip. The no-DB suite proves auth is *required* on all protected routes and that filters are *written*; only the live run proves user B cannot read user A's rows. **Highest priority.**
2. **P3's three answers** (SD-5/6/7) block stages, telemetry, and all simulation endpoints.
3. **No rate limiting** on `/auth/register` and `/auth/login` (`KNOWN_ISSUES` D-3) — needs Redis, and these endpoints are now live.
4. **`packages/contracts/`** is still empty. The OpenAPI schema is the de-facto contract; whether P1 generates a client from it or the team hand-writes shared types is unresolved.
