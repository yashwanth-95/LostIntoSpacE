# Database Contract — Person 2

**Phase:** 3 — Database Contract Finalization
**Date:** 2026-08-19
**Status:** Implementation-ready **except** where marked ⚠ PENDING. Phase 4 builds from this file.

## How to use this document

| Document | Role |
|---|---|
| **This file** | **Normative.** The contract Phase 4 implements: entities, fields, relationships, ownership, constraints. |
| [`SCHEMA_DECISIONS.md`](SCHEMA_DECISIONS.md) | Why each decision was made, alternatives rejected, sign-off status (SD-1 … SD-8). |
| [`DATABASE_DESIGN.md`](DATABASE_DESIGN.md) | Exploratory analysis that fed this contract. **Superseded** where the two disagree. |
| `docs/architecture/DATABASE.md` | Team-level schema doc. Still authoritative for tables this contract leaves unchanged; must be updated to match this file once the ⚠ items are signed off. |

**Rule for Phase 4: do not implement anything marked ⚠ PENDING until the named owner signs off.** Everything else is safe to build.

---

## 1. Canonical Terminology

| Concept | UI says | API/backend says | Table |
|---|---|---|---|
| The thing you build | Rocket | Vehicle | `vehicles` |
| Its parts | Parts / Components | Component | `vehicle_components` |
| Its stages | Stage | Stage | `vehicle_stages` |
| A flight attempt | Launch / Flight | Simulation run | `simulation_runs` |
| Things that happened in flight | Events | Simulation event | `simulation_events` |

No `rockets`, `rocket_components`, or `mission_events` tables exist (SD-1, SD-2).

---

## 2. Entity Decisions

| Entity | Decision | Reason | Dependencies | MVP? |
|---|---|---|---|---|
| `users` | **KEEP** | Auth root, ownership anchor | — | ✅ |
| `refresh_tokens` | **KEEP** | Makes logout/revocation real (`DECISION_LOG` #16) | users | ✅ |
| `projects` | **MODIFY** | Add `deleted_at` — delete cascades 4 levels (SD-8) | users | ✅ |
| `missions` | **KEEP** | Container for runs; per `API.md` | projects | ✅ |
| `vehicles` | **KEEP** | Canonical name confirmed (SD-1); add UNIQUE on `mission_id` | missions | ✅ |
| `vehicle_stages` | **MODIFY** ⚠ | Mass semantics (SD-6) + propulsion over-determination (SD-7) | vehicles, P3 | ✅ |
| `vehicle_components` | **KEEP** | Authoritative mass + geometry for CG/CP | vehicles, stages | ✅ |
| `simulation_runs` | **KEEP** | Stable anchor for all external references | missions, vehicles | ✅ |
| `telemetry_points` | **MODIFY** ⚠ | Flatten vectors + add attitude (SD-5) | simulation_runs, P3 | ✅ |
| `simulation_events` | **MODIFY** | `event_type` vocabulary incomplete vs `SIMULATION.md` (C-4) | simulation_runs | ✅ |
| `failure_events` | **KEEP** | Drives the demo's "why did it fail" act | simulation_events | ✅ |
| `space_objects` | **KEEP** | P4 ingestion target; `(source, source_id)` keeps loads idempotent | P4 seeds | ✅ |
| `lessons` | **KEEP** | Content catalog; category + sort_order + prerequisites already sequence it | P4 seeds | ✅ |
| `learning_progress` | **ADD** | `POST /learning/progress` exists with no table behind it (SD-3) | users, lessons | ✅ |
| `search_history` | **KEEP** | `GET /search/history`; `user_id` nullable (anonymous search allowed) | users | ✅ |
| `conversations` | **KEEP** | AI tutor persistence, P2-owned scope | users | ✅ |
| `messages` | **KEEP** | Ownership inherited via conversation | conversations | ✅ |
| `favorites` | **DEFER** | No endpoint, no demo act (SD-3) | — | ❌ |
| `learning_paths` | **DEFER** | `lessons.category`+`sort_order`+`prerequisites` already do this (SD-3) | — | ❌ |
| `quizzes`, `quiz_attempts` | **DEFER** | Absent from all 8 demo acts and from `API.md` (SD-3) | — | ❌ |
| `project_versions` | **DEFER** | `.rkt` is the versioning mechanism (SD-4) | — | ❌ |
| `rocket_instances` | **DEFER** | Needs the 1:1 mission↔vehicle question answered first | P1/P3 | ❌ |
| `reports` | **DEFER** | `POST /reports` exists in `API.md` but is Phase 4–5 work; will reference `simulation_runs.id` | simulation_runs | ❌ |
| `profiles` | **REJECT** | `users` already carries the fields; split adds a join for nothing (SD-3) | — | ❌ |
| `courses` | **REJECT** | Redundant with `learning_paths`; never build both (SD-3) | — | ❌ |
| `rockets` | **REJECT** | Is `vehicles` (SD-1) | — | ❌ |
| `rocket_components` | **REJECT** | Is `vehicle_components` (SD-1) | — | ❌ |
| `mission_events` | **REJECT** | Is `simulation_events` (SD-2) | — | ❌ |

**MVP total: 17 tables.** 16 existing (14 unchanged, `projects` and the two ⚠ modified) + 1 new (`learning_progress`).

---

## 3. Relationships

```
users ─┬─1:N─ refresh_tokens
       ├─1:N─ projects ─1:N─ missions ─1:1─ vehicles ─┬─1:N─ vehicle_stages
       │                          │                    └─1:N─ vehicle_components
       │                          └─1:N─ simulation_runs ─┬─1:N─ telemetry_points
       │                                                  └─1:N─ simulation_events ─0:1─ failure_events
       ├─1:N─ conversations ─1:N─ messages
       ├─1:N─ learning_progress ─N:1─ lessons
       └─0:N─ search_history          (user_id nullable — anonymous search)

space_objects   standalone catalog (P4-ingested)
lessons         standalone catalog (P4-authored)
```

### Cardinality contract

| Relationship | Cardinality | Enforcement |
|---|---|---|
| users → projects | 1:N | `projects.user_id` NOT NULL |
| projects → missions | 1:N | `missions.project_id` NOT NULL |
| **missions → vehicles** | **1:1** | `vehicles.mission_id` NOT NULL **+ UNIQUE** ← *currently only a non-unique index; must be upgraded, or nothing stops two vehicles per mission while `GET /missions/{mid}/vehicle` assumes one* |
| vehicles → vehicle_stages | 1:N | `vehicle_stages.vehicle_id` NOT NULL; UNIQUE `(vehicle_id, stage_number)` |
| vehicles → vehicle_components | 1:N | `vehicle_components.vehicle_id` NOT NULL |
| stages → components | 0:N | `vehicle_components.stage_id` **nullable** — a nose cone or payload belongs to no stage |
| components → components | 0:N | `parent_id` self-FK, nullable; **must be acyclic** (service-enforced) |
| missions → simulation_runs | 1:N | many runs per mission — this is the demo's retry loop |
| simulation_runs → telemetry/events | 1:N | CASCADE; internal detail of a run |
| simulation_events → failure_events | 1:0..1 | diagnosis of one event |
| users → conversations → messages | 1:N:N | messages carry **no** `user_id` (§5) |
| users × lessons → learning_progress | N:M with state | UNIQUE `(user_id, lesson_id)` |

**No direct `projects → vehicles` FK.** The path is `projects → missions → vehicles`. A second path to the same ownership answer would eventually disagree with the first.

---

## 4. Entity Contracts

Unchanged tables are summarized; **⚠ modified and new tables are given in full.** Full DDL for unchanged tables stays in `docs/architecture/DATABASE.md`.

### 4.1–4.8 Unchanged tables

`users`, `refresh_tokens`, `missions`, `vehicles`, `vehicle_components`, `simulation_runs`, `failure_events`, `space_objects`, `lessons`, `search_history`, `conversations`, `messages` — per `docs/architecture/DATABASE.md`, with the constraint additions in §6.

Two notes that bind Phase 4:

- **`vehicles.mission_id` must become UNIQUE** (see cardinality table above).
- **`vehicles.is_valid`, `validation_errors`, `total_mass_kg`, `cg_position`, `cp_position`, `stability_margin` are derived caches.** They must be recomputed by a single service function on every mutation of stages or components. A route that writes a component without triggering recomputation leaves the UI showing a green checkmark on a broken rocket.

### 4.9 `telemetry_points` — ⚠ PENDING P3 (SD-5)

**Coordinate frame: ENU (East–North–Up), origin at the launch site**, per `SIMULATION.md`. (`ARCHITECTURE.md` says "ENU or ECEF" — that ambiguity is resolved in favour of `SIMULATION.md`; see C-6.)

**Sampling: 1 Hz persisted**, per `SIMULATION.md` ("Stored data: Every 1s for persistence, full resolution discarded"). The realtime WebSocket stream is ~0.5 s and is **not** persisted. Expected volume: ≤600 rows per run, ~60,000 per 100 runs.

| Column | Type | Unit | Null? | Notes |
|---|---|---|---|---|
| `id` | BIGSERIAL PK | — | no | Sequential deliberately — cheapest PK on the hottest write path. Do **not** "fix" to UUID for consistency. |
| `simulation_id` | UUID FK → simulation_runs | — | no | CASCADE |
| `t` | float8 | s | no | Since ignition |
| `pos_x_m`, `pos_y_m`, `pos_z_m` | float8 | m | no | ENU from launch site |
| `vel_x_ms`, `vel_y_ms`, `vel_z_ms` | float8 | m/s | no | |
| `acc_x_ms2`, `acc_y_ms2`, `acc_z_ms2` | float8 | m/s² | no | |
| `att_pitch_rad`, `att_yaw_rad`, `att_roll_rad` | float8 | rad | **yes** | **NEW** — `SIMULATION.md`'s state vector has attitude; the table had no home for it. Nullable so a run that doesn't model attitude is still valid. Without these, P1's 3D replay can position the vehicle but not orient it. |
| `altitude_m` | float8 | m | yes | Derived scalar, persisted for cheap querying |
| `speed_ms` | float8 | m/s | yes | |
| `mass_kg` | float8 | kg | yes | Current total mass |
| `thrust_n`, `drag_n` | float8 | N | yes | |
| `dynamic_pressure_pa` | float8 | Pa | yes | Drives `max_q` |
| `mach_number` | float8 | — | yes | Dimensionless |
| `stage` | int | — | yes | Active stage index |
| `phase` | varchar(20) | — | yes | `PRELAUNCH\|POWERED\|COAST\|DESCENT\|TERMINATED` — **5 values**; `ARCHITECTURE.md` lists only 4 (C-5) |

**Precision: `float8` (double), not `float4`.** Python floats are doubles natively, so `float8` is a lossless round-trip from the engine. `float4` would save 4 bytes/column on a table that will hold tens of thousands of rows — a saving of no consequence — while introducing a conversion step and a precision question nobody should have to think about.

**Index: exactly one** — `(simulation_id, t)`. It serves both "all points for this run" and time-ordered playback. Every extra index taxes the write path; add none without a measured query.

**Units are encoded in column names** (`_m`, `_ms`, `_ms2`, `_rad`, `_n`, `_pa`), matching the existing convention and `SIMULATION.md`'s SI table. No unit ambiguity is permitted to reach the database.

**Migration implication: none today.** The table has never been created and holds no data — this is a greenfield definition, not a migration. That is precisely why it should be settled now.

### 4.10 `vehicle_stages` — ⚠ PENDING P3 (SD-6, SD-7)

| Column | Type | Unit | Authority | Notes |
|---|---|---|---|---|
| `id` | UUID PK | — | — | |
| `vehicle_id` | UUID FK | — | — | NOT NULL, CASCADE |
| `stage_number` | int | — | authored | ≥ 1; UNIQUE per vehicle |
| `name` | varchar(100) | — | authored | nullable |
| **`structural_dry_mass_kg`** | float8 | kg | **AUTHORITATIVE** | ⚠ renamed from `dry_mass_kg`. **Definition: stage structure not modelled as any component** — tanks, plumbing, engine casing, skirt. Defined as *the remainder*, so it cannot double-count components. |
| `propellant_mass_kg` | float8 | kg | **AUTHORITATIVE** | Depletes during burn; not a positioned part |
| `thrust_n` | float8 | N | ⚠ see SD-7 | Over-determined with the next two |
| `isp_s` | float8 | s | ⚠ see SD-7 | |
| `burn_time_s` | float8 | s | ⚠ see SD-7 | Recommended: **derived** |
| `drag_coefficient` | float8 | — | authored | default 0.5 |
| `reference_area_m2` | float8 | m² | authored | |
| `separation_delay_s` | float8 | s | authored | default 1.0 |

**Derived values — computed, never client-writable:**

```
stage_dry_mass_kg     = structural_dry_mass_kg + Σ(components WHERE stage_id = this stage)
vehicle_dry_mass_kg   = Σ(stage_dry_mass_kg) + Σ(components WHERE stage_id IS NULL)
vehicle_total_mass_kg = vehicle_dry_mass_kg + Σ(propellant_mass_kg)
CG                    = Σ(mᵢ·xᵢ) / Σ(mᵢ)          [MODELS.md]
stability_margin      = (CP − CG) / d_ref          [calibers]
```

**CG position rule for unpositioned mass:** `structural_dry_mass_kg` and `propellant_mass_kg` have no `position`, so each is assumed to act at **its stage's geometric centroid**. This is a stated approximation, not an oversight; it must be surfaced in the UI and added to `MODELS.md`. Validation should warn when structural remainder dominates a stage's mass, because CG accuracy — and therefore the stability margin the demo displays — degrades in that regime.

**API representation.** `structural_dry_mass_kg`, `propellant_mass_kg` and the propulsion fields are writable. `stage_dry_mass_kg` and all vehicle-level aggregates are **read-only in responses**; a request body containing them returns `422`, never a silent ignore.

**Simulation representation.** P3 never sees this ambiguity. The backend resolves all derived values before constructing `SimConfig`, and hands the engine finished numbers.

### 4.11 `learning_progress` — NEW

```sql
CREATE TABLE learning_progress (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    lesson_id        UUID NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    status           VARCHAR(20) NOT NULL DEFAULT 'in_progress'
                     CHECK (status IN ('not_started','in_progress','completed')),
    progress_percent SMALLINT NOT NULL DEFAULT 0
                     CHECK (progress_percent BETWEEN 0 AND 100),
    last_viewed_at   TIMESTAMPTZ,
    completed_at     TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_progress_user_lesson UNIQUE (user_id, lesson_id),
    CONSTRAINT ck_progress_completed CHECK ((status = 'completed') = (completed_at IS NOT NULL))
);
CREATE INDEX idx_progress_user ON learning_progress(user_id, status);
```

**Absence of a row means "not started."** Do not pre-create rows for every user × lesson pair — that cross product grows with the catalog and carries no information. The UNIQUE constraint makes `POST /learning/progress` a natural idempotent upsert (`ON CONFLICT … DO UPDATE`).

**Completion** = `status='completed'` with `completed_at` set; the CHECK keeps the two from ever disagreeing.

**Prerequisites and ordering** are read from `lessons.prerequisites` (JSONB array) and `lessons.category` + `lessons.sort_order`. No extra table (SD-3).

### 4.12 `simulation_events` — MODIFY

Structure unchanged; the **`event_type` vocabulary must be widened** to match `SIMULATION.md`, which is the authoritative list (C-4):

`ignition` · `liftoff` · `max_q` · `meco` · `staging` · `apogee` · `supersonic` · `impact` · `failure_*`

`DATABASE.md` currently lists `landing`, which does not appear in `SIMULATION.md`; `SIMULATION.md` has `impact`. `liftoff` and `supersonic` are missing from `DATABASE.md` entirely. Because failure events are a `failure_*` family rather than a fixed set, the CHECK constraint should allow the enumerated values **plus** a `failure_%` pattern, or be omitted in favour of application-level validation — decide during Phase 4, but do not encode the stale list.

`severity`: `info | warning | critical | fatal`.

---

## 5. Ownership & Authorization

**Principle: the backend derives ownership from the database, never from the request.** No client-supplied `user_id` is ever trusted. Every protected resource resolves to an owner by walking to `users.id`.

| Entity | Ownership path | Check |
|---|---|---|
| `projects` | `projects.user_id` | direct |
| `missions` | → `projects.user_id` | 1 join |
| `vehicles` | → `missions` → `projects.user_id` | 2 joins |
| `vehicle_stages`, `vehicle_components` | → `vehicles` → `missions` → `projects.user_id` | 3 joins |
| `simulation_runs` | → `missions` → `projects.user_id` | 2 joins |
| `telemetry_points`, `simulation_events` | → `simulation_runs` → `missions` → `projects.user_id` | 3 joins |
| `failure_events` | → `simulation_events` → `simulation_runs` → … | 4 joins |
| `conversations` | `conversations.user_id` | direct |
| `messages` | → `conversations.user_id` | 1 join |
| `learning_progress` | `learning_progress.user_id` | direct |
| `refresh_tokens` | `refresh_tokens.user_id` | direct |
| `search_history` | `search_history.user_id` (nullable) | direct; anonymous rows are unreadable by anyone |
| `space_objects`, `lessons` | **unowned** — public catalogs | read: public; write: seed/admin only |

**Rules binding Phase 4:**

1. **Deep paths stay joins, not shortcuts.** If the 3–4 join hops become a measured bottleneck, the remedy is a denormalized `user_id` on `simulation_runs` — never a weaker check.
2. **`messages` carries no `user_id`.** Authorization is at the conversation. Messages are always fetched in conversation context, so the join is on a path already being taken; a denormalized owner column could contradict its parent.
3. **404, not 403,** when a resource exists but is owned by someone else — otherwise the API confirms the existence of other users' data.
4. **Soft-deleted projects are invisible.** Every project-scoped query filters `WHERE deleted_at IS NULL`; a soft-deleted project's children are unreachable through it.
5. **`users.role`** (`student | educator | admin`) exists but grants nothing yet. Educator/admin access to others' work is **not** designed — see Open Question O-3.

---

## 6. Constraints

**Enums: `VARCHAR` + `CHECK`, not PostgreSQL `ENUM` types.** Adding a value to a PG enum needs `ALTER TYPE` and is awkward to reverse in a migration; a CHECK is a one-line drop-and-recreate. The existing schema declares enums as SQL comments only — these become real CHECKs:

| Table | Constraint |
|---|---|
| `users` | `role IN ('student','educator','admin')` |
| `projects` | `status IN ('draft','active','completed','archived')` |
| `missions` | `status IN ('planning','ready','simulated','analyzed')` |
| `simulation_runs` | `status IN ('pending','running','completed','failed','cancelled')`; `outcome IN ('success','partial','failure')` |
| `simulation_events` | `severity IN ('info','warning','critical','fatal')`; `event_type` per §4.12 |
| `telemetry_points` | `phase IN ('PRELAUNCH','POWERED','COAST','DESCENT','TERMINATED')` |
| `messages` | `role IN ('user','assistant','system')` |
| `conversations` | `context_type IN ('general','tutor','failure_analysis','recommendation')`; `status IN ('active','archived')` |
| `learning_progress` | as in §4.11 |

**Physical-impossibility CHECKs** — these belong in the database because they can never legitimately be violated, and "never trust frontend validation" means the last line of defence is here:

```sql
ALTER TABLE vehicle_stages
  ADD CONSTRAINT ck_stage_structural_mass CHECK (structural_dry_mass_kg >= 0),
  ADD CONSTRAINT ck_stage_propellant      CHECK (propellant_mass_kg >= 0),
  ADD CONSTRAINT ck_stage_thrust          CHECK (thrust_n > 0),
  ADD CONSTRAINT ck_stage_burn            CHECK (burn_time_s > 0),
  ADD CONSTRAINT ck_stage_isp             CHECK (isp_s > 0),
  ADD CONSTRAINT ck_stage_number          CHECK (stage_number >= 1);
ALTER TABLE vehicle_components
  ADD CONSTRAINT ck_component_mass CHECK (mass_kg >= 0);
```

**Domain-range rules stay in Pydantic**, not the database. `isp_s BETWEEN 50 AND 500` (`RKT_SPEC.md` rule 5) is an educational plausibility bound, not a law of physics, and is likelier to be retuned — keeping it in the app keeps migrations out of that loop. The DB asserts `isp_s > 0` (impossible otherwise); the app asserts the plausible range.

**Uniqueness:** `users.email`, `users.username`, `lessons.slug`, `refresh_tokens.token_hash`, `vehicles.mission_id` *(new)*, `(vehicle_id, stage_number)`, `(user_id, lesson_id)`, `(source, source_id) WHERE source_id IS NOT NULL`.

**FK delete behaviour:**

| Relationship | Action | Why |
|---|---|---|
| users → refresh_tokens/projects/conversations/learning_progress/search_history | CASCADE | meaningless without the user |
| projects → missions → vehicles → stages/components | CASCADE | strict containment |
| simulation_runs → telemetry/events; events → failure_events | CASCADE | internal detail of a run |
| conversations → messages | CASCADE | transcript belongs to the conversation |
| stages → components (`stage_id`) | **SET NULL** | stage-less parts (nose, payload) must survive staging |
| components → `parent_id` | SET NULL | removing an assembly must not delete its children |
| **simulation_runs.vehicle_id → vehicles** | **RESTRICT** *(new)* | currently NO ACTION; deleting a vehicle with recorded runs would orphan or destroy flight history. Blocking the delete is safer. |

**Timestamps:** `created_at TIMESTAMPTZ NOT NULL DEFAULT now()` on every table; `updated_at` on mutable ones, maintained by SQLAlchemy `onupdate` rather than a DB trigger (one visible mechanism, no hidden behaviour). **`TIMESTAMPTZ` everywhere, never `TIMESTAMP`** — mixed timezone handling in a launch-time application is a real correctness hazard.

---

## 7. Contract Compatibility Check

Conflicts found between this contract and existing artifacts. **None has been silently changed.**

| # | Conflict | Current contract says | Recommended resolution | Affected | Migration impact |
|---|---|---|---|---|---|
| **C-1** | `RKT_SPEC.md`'s example stage is **physically impossible**: thrust 5000 N vs 12,258 N implied by its own Isp/propellant/burn-time (2.45× off) | `RKT_SPEC.md` §File Structure example | Correct the example; adopt SD-7's authority rule | **P3**, P1, RKT | Doc-only; no data exists |
| **C-2** | Telemetry vectors as JSONB | `DATABASE.md` `telemetry_points` | Flatten to `float8` (SD-5) | **P3** | **None** — table never created |
| **C-3** | Telemetry has no attitude columns, but `SIMULATION.md`'s state vector has `attitude[p,y,r]` | `DATABASE.md` vs `SIMULATION.md` | Add 3 nullable rad columns (SD-5) | **P3**, P1 (3D replay) | None |
| **C-4** | `event_type` vocabularies disagree: `DATABASE.md` has `landing`, lacks `liftoff`/`supersonic`; `SIMULATION.md` has `impact` | `DATABASE.md` vs `SIMULATION.md` | `SIMULATION.md` wins; widen the list (§4.12) | **P3** | None |
| **C-5** | `phase` enum: `ARCHITECTURE.md` lists 4 values, `SIMULATION.md` lists 5 (adds `TERMINATED`) | `ARCHITECTURE.md` §6 | Use `SIMULATION.md`'s 5 | **P3** | None |
| **C-6** | Coordinate frame: `ARCHITECTURE.md` says "ENU **or** ECEF"; `SIMULATION.md` says "ENU frame from launch site" | Two architecture docs | **ENU from launch site**; correct `ARCHITECTURE.md` | **P3** | None; but if left ambiguous every stored coordinate is meaningless |
| **C-7** | `dry_mass_kg` → `structural_dry_mass_kg` rename (SD-6) | `DATABASE.md`, `RKT_SPEC.md`, `API.md` | **Preferred:** rename — the name *is* what removes the ambiguity. **Fallback:** keep `dry_mass_kg`, document it as "structure not covered by components" (cheaper, contract-stable, but the name keeps inviting the wrong reading) | **P3**, **P1** | `.rkt` v1.0 → v1.1 field rename; importer must map the old key |
| **C-8** | If SD-7's preferred option is taken, `burn_time_s` becomes derived and read-only | `RKT_SPEC.md`, builder UI | Team decision (SD-7) | **P3**, **P1** | `.rkt` v1.1; builder input becomes an output |

**Compatibility confirmed (no conflict):**

- **P1 / frontend** — no API path, resource name, or field changes except C-7/C-8 above, both flagged. `Vehicle` → "Rocket" is presentation-only.
- **P4 / space data** — `space_objects` untouched; `(source, source_id)` partial-unique index keeps re-ingestion idempotent, and `data/seeds` → `database/seeds` ownership (`DECISION_LOG` #18) is unchanged.
- **P4 / AI** — `conversations` + `messages` untouched; `context_ref` still soft-links to `simulation_runs.id`, `messages.grounding` still carries provenance.
- **`.rkt`** — structure, `rkt_version`, and the export/import/validate endpoints are unchanged; only the two stage fields in C-7/C-8 are in question.

---

## 8. Future Simulation Result References

**`simulation_runs.id` is the stable public anchor.** Reports, AI failure analyses, conversation `context_ref`, shareable links, and `.rkt`'s `results_ref` all reference it and nothing deeper.

`telemetry_points`, `simulation_events`, and `failure_events` are **internal detail of a run** — high-volume and, as C-2 through C-5 show, still in flux. If features outside the simulation module FK directly into them, every future change to telemetry becomes a cross-team migration.

**Rule: outside the simulation module, reference the run — never its contents.** The single exception is `failure_events.event_id → simulation_events.id`, which is inside the boundary.

---

## 9. Open Questions

| # | Question | Owner | Blocks Phase 4? |
|---|---|---|---|
| **O-1** | SD-7: which three propulsion fields are authoritative? | **P3** | **Yes** — `vehicle_stages` DDL |
| **O-2** | C-7: rename `dry_mass_kg`? | **P3 + P1** | **Yes** — `vehicle_stages` DDL |
| **O-3** | Are projects ever shared/public? Does `educator` see student work? | P1 + team | No — but retrofitting after every query hardcodes `user_id =` is expensive |
| **O-4** | Telemetry retention: keep every run forever, or prune/downsample? | P2 + P3 | No — decide before the demo |
| **O-5** | Does P4 need `pgvector`? | **P4** | Marginally — enabling the extension in the baseline migration is nearly free now, a coordination event later |
| **O-6** | What does `reports` persist — a rendered artifact or parameters to re-render? | P1 + P4 | No — Phase 4–5 |

---

## 10. Phase 4 Authorization

**Safe to build now** (no pending sign-off):

`users` · `refresh_tokens` · `projects` (+ `deleted_at`) · `missions` · `vehicles` (+ UNIQUE `mission_id`) · `vehicle_components` · `simulation_runs` · `simulation_events` (widened vocabulary) · `failure_events` · `space_objects` · `lessons` · `learning_progress` · `search_history` · `conversations` · `messages`

— that is **15 of 17 tables**, plus the baseline extensions migration, all constraints in §6, and the index strategy.

**Blocked pending sign-off:**

- `vehicle_stages` — O-1 and O-2 both change its columns
- `telemetry_points` — C-2/C-3 change its columns (low risk; P3 is unlikely to object, but it is their contract)

**Recommended sequencing:** build the 15 unblocked tables first — they are the whole auth and project spine and are enough for Phase 4's auth work — and land the two ⚠ tables in a follow-up migration once P3 answers. This keeps Phase 4 moving without guessing at another person's contract.

**Migration order** (each revision must apply to a fresh database, so FK targets come first):

1. Baseline + extensions (`pgcrypto` for `gen_random_uuid()`; `pgvector` if O-5 says yes)
2. `users` + `refresh_tokens`
3. `projects` → `missions` → `vehicles` → `vehicle_components`
4. `simulation_runs` → `simulation_events` → `failure_events`
5. `space_objects`, `lessons`, `search_history`
6. `learning_progress`
7. `conversations` → `messages`
8. ⚠ `vehicle_stages`, `telemetry_points` — after sign-off

Alembic autogenerate does not reliably detect CHECK constraints, partial indexes, or server defaults; every generated revision is a draft to be hand-corrected. `tsvector` population for `space_objects`/`lessons` needs raw SQL (generated column or trigger) in its migration.
