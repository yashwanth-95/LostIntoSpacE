# Minimum Shared Contract Surface (Pre-Phase-2)

**Status:** Identification only — this is *not* an implementation of `packages/contracts/`. It names the smallest set of shared types that must be agreed before Phase 2 parallel development starts, and sketches their shape at a conceptual level so P1/P4 can review before anything is written as code. Actual contract files (`packages/contracts/src/api.ts` and its Python mirror) remain P4-maintained and require team agreement to change, per `packages/contracts/README.md` rule 1.

Produced as part of the 2026-08-18 pre-Phase-2 architecture correction (`docs/decisions/DECISION_LOG.md` #19).

---

## 1. Why these and not others

`docs/architecture/ARCHITECTURE.md` §7 (dependency graph) and §8 (phase table) establish the order work actually happens in:

- **Phase 1 (Foundation)** needs Auth working end-to-end (P1 builds login/register UI against it).
- **Phase 2 (Core Platform)** is explicitly "Projects, Dashboard, Space Data, Search" — this is the next phase per the current request, and the first point where P1 and P4 both build against real backend response shapes instead of mocks.
- **Phase 3 (Build & Simulate)** is where `SimConfig`/`SimResult`/telemetry WebSocket format become load-bearing — not yet.
- **Phase 4 (Analyze & Explain)** is where AI tool schemas matter — not yet.
- **Phase 5 (Polish & Demo)** is where the `.rkt` contract matters — not yet (though `docs/rkt_spec/RKT_SPEC.md` already fully specifies it independently).

So the minimum surface blocking Phase 2 is: the response envelope, auth, projects, mission summaries, space objects, and search. Everything else can be defined later without blocking anyone.

## 2. Standard envelope

Already specified in `docs/api/API.md`; repeated here because every other type nests inside it and it's the single highest-leverage contract to lock first.

```
Success: { status: "success", data: <T>, meta?: { page, per_page, total } }
Error:   { status: "error", error: { code: string, message: string, details?: any[] } }
```

## 3. Auth

```
User = {
  id: uuid, email: string, username: string,
  display_name: string | null, avatar_url: string | null,
  role: "student" | "educator" | "admin",
  created_at: datetime
}

RegisterRequest = { email: string, username: string, password: string, display_name?: string }
LoginRequest    = { email: string, password: string }

AuthResponse = {
  access_token: string, refresh_token: string,
  token_type: "bearer", expires_in: number,   // seconds
  user: User
}
```
`password_hash` never appears in any response — obvious, but stated explicitly since it's the one field on the `users` table that must never cross the API boundary. See `docs/architecture/DATABASE.md` `refresh_tokens` for what backs `refresh_token` server-side.

## 4. Projects

```
Project = {
  id: uuid, user_id: uuid, name: string, description: string | null,
  status: "draft" | "active" | "completed" | "archived",
  metadata: object, created_at: datetime, updated_at: datetime
}
```

## 5. Missions (summary only)

Phase 2 is Dashboard-level — list/overview, not the vehicle builder. Only the summary shape is needed now; full `Mission` + `Vehicle` + `vehicle_stages` + `vehicle_components` detail types can wait for Phase 3 without blocking Phase 2 work.

```
MissionSummary = {
  id: uuid, project_id: uuid, name: string, objective: string | null,
  status: "planning" | "ready" | "simulated" | "analyzed",
  created_at: datetime, updated_at: datetime
}
```

## 6. Space Objects

```
SpaceObject = {
  id: uuid, name: string, category: string, subcategory: string | null,
  description: string | null,
  physical_data: object | null, orbital_data: object | null,
  images: string[], source: string, last_updated: datetime | null
}
```

## 7. Search

```
SearchRequest  = { q: string, type?: string, category?: string, page?: number, per_page?: number }
SearchResult   = { type: "space_object" | "lesson", id: uuid, title: string, snippet: string, score: number }
SearchResponse = envelope<SearchResult[]>   // meta.total = result count
```

## 8. Explicitly deferred (not blocking Phase 2)

- `SimConfig` / `SimResult` / `TelemetryPoint` (P2↔P3) — needed before Phase 3, not before Phase 2. Interface sketch already exists in `simulation/README.md`.
- WebSocket telemetry message format (P3↔P1) — Phase 3.
- AI tool schemas / `AIProvider` request-response shapes (P4↔P2) — Phase 4. Interface sketch already exists in `ai/README.md`.
- `.rkt` file schema (P2↔P1) — Phase 5. Already fully specified independently in `docs/rkt_spec/RKT_SPEC.md`; nothing further needed from this doc.
- Full `Mission`/`Vehicle`/stage/component detail types — needed for the Build phase (Phase 3), not the Dashboard phase (Phase 2).
- `Lesson`, `learning_progress` shapes — needed when the Learning module is actually built; not on the Phase 2 critical path per the dependency graph, can follow shortly after using the same pattern as Space Objects.

## 9. Next step

This doc is input for a short P1/P2/P4 review, not a final contract. Once agreed, these shapes become the first content of `packages/contracts/src/api.ts` (TypeScript, for P1) with a Python mirror for backend's own Pydantic schemas to validate against — implemented in the "Project bootstrap" / "Auth module" steps of `docs/backend/BACKEND_STATE.md` §10, not in this pre-Phase-2 correction.
