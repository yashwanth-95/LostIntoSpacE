# Schema Decisions — Person 2

**Phase:** 3 — Database Contract Finalization
**Date:** 2026-08-19
**Companion:** [`DATABASE_CONTRACT.md`](DATABASE_CONTRACT.md) is the normative spec Phase 4 implements. This file records *why* each decision was made, what was rejected, and what still needs sign-off.

## Status legend

| Status | Meaning |
|---|---|
| **FINAL** | Decided. Phase 4 may implement against it. |
| **RECOMMENDED** | P2's proposal, technically sound, but changes a contract another person owns. Phase 4 may implement **only** the parts marked safe; the rest needs the named sign-off. |
| **BLOCKED** | Cannot be decided by P2 alone. Named owner must answer. |

> **Coordination caveat, stated plainly:** several decisions below were directed to be "coordinated with Person 3." At the time of writing, **P3's simulation contract does not exist as code** — `simulation/` is empty scaffold and `packages/contracts/` is empty. The only concrete P3 artifacts are `docs/simulation/SIMULATION.md`, `docs/scientific/MODELS.md`, and `simulation/README.md`. Every decision below is therefore derived from *those documents* and is marked RECOMMENDED, not FINAL, where it changes something P3 owns. I have not obtained P3's agreement and do not claim it.

---

## SD-1 — `vehicle` is the canonical entity name

**Status:** FINAL (directed)

**Decision.** `vehicle` is the canonical backend, API, and database entity. The UI is free to say "Rocket". No `rockets` or `rocket_components` tables will be created.

| Layer | Term |
|---|---|
| UI / product copy | Rocket |
| Backend / API / domain | Vehicle |
| Database table | `vehicles` |
| Components table | `vehicle_components` |
| Stages table | `vehicle_stages` |

**Rationale.** "Vehicle" is already the term in 8 `API.md` endpoints, the `.rkt` format (`vehicle.stages`), `simulation/README.md`'s `SimConfig.vehicle`, `ARCHITECTURE.md`'s module table, and the `apps/api/src/vehicles/` scaffold. "Rocket" appears only in prose (`DEMO_RUNBOOK.md`, `RKT_SPEC.md` example *values* such as `"name": "Rocket Alpha"` — which are data, not field names). Renaming would break P1's API calls and P3's config contract for zero functional gain.

**Consequences.** Frontend maps `Vehicle` → "Rocket" at the presentation layer only. No translation layer in the backend. Recorded as `DECISION_LOG.md` #20.

---

## SD-2 — `simulation_events` is the canonical event entity

**Status:** FINAL (directed)

**Decision.** Events belong to a simulation run. No `mission_events` table.

```
mission → simulation_run → simulation_events → failure_events
```

**Rationale.** One mission can be simulated many times (the demo's core loop is *fail → understand → improve → re-simulate*). Events like `max_q`, `staging`, and `apogee` are properties of one specific run's trajectory, not of the mission. Attaching them to `missions` would make it impossible to hold two runs' timelines side by side — which is exactly what the "improve and retry" comparison needs.

**Mission-level metadata**, where needed, lives on `missions` itself (`status`, `environment`, `target_orbit`) — not in a duplicated event table. A mission *audit log* (created/validated/simulated-at) is a separate, non-MVP concern; if it ever arrives it will be its own table with its own semantics, not a copy of simulation events.

**Consequences.** `simulation_events.event_type` must cover the full vocabulary in `SIMULATION.md` — see conflict **C-4**, which found the existing enum is incomplete. Recorded as `DECISION_LOG.md` #21.

---

## SD-3 — Minimum learning schema: `lessons` + `learning_progress` only

**Status:** FINAL for what's built; the deferrals are reversible.

**Decision.** Build `learning_progress`. Keep `lessons` unchanged. Defer `learning_paths`, `courses`, `quizzes`, `quiz_attempts`. Reject `profiles`. **Defer `favorites`** (revised — see below).

| Deferred/rejected | Why deferred | What replaces it now | What would require it |
|---|---|---|---|
| `learning_paths` | `lessons` already carries `category`, `sort_order`, and a `prerequisites` JSONB array — that *is* a path expressed in columns we already have | `GET /lessons?category=…` ordered by `sort_order`; prerequisites read from the JSONB array | A curated sequence that **crosses categories**, or the same lesson appearing in several orderings. That needs `learning_paths` **plus** a `learning_path_lessons` join table (position-carrying N:M) — two tables, no current demand |
| `courses` | Redundant with `learning_paths`; two names for one grouping level | Same as above | Only if a two-level hierarchy (course → module → lesson) is genuinely needed. Pick one grouping entity, never both |
| `quizzes`, `quiz_attempts` | **Absent from all 8 acts of `DEMO_RUNBOOK.md`.** Not referenced by any endpoint in `API.md` | Nothing — the feature does not exist | A graded-assessment feature. `quiz_attempts` would also need a scoring/attempt-limit policy, which is product design that hasn't happened |
| `profiles` | `users` already holds `display_name`, `avatar_url`, `role`. Splitting adds a join to every profile read for no gain | The `users` columns | Profile data growing large or optional (bio, institution, preferences blob), or a need to separate auth columns from publicly-readable ones for row-level security |
| `favorites` | **Revised from my Phase-2 recommendation.** Applying the stated test — "if required by existing contracts" — it is not: no endpoint in `API.md`, no moment in `DEMO_RUNBOOK.md` | Nothing | P1 asking for a save/bookmark affordance in Explore. One table, ~30 minutes; genuinely cheap to add later, so there is no cost to waiting |

**Note on my own reversal.** `docs/backend/DATABASE_DESIGN.md` §1 put `favorites` in "build now (confirm with P1)". Applying this phase's stricter contract test, that was too generous — nothing requires it, so it moves to DEFER. `DATABASE_DESIGN.md` is superseded on this point.

**`learning_progress` is required** because `API.md` already publishes `POST /learning/progress` with no table behind it, and "Learning progress persistence" is explicit P2 scope. Contract in [`DATABASE_CONTRACT.md`](DATABASE_CONTRACT.md) §4.11.

---

## SD-4 — `.rkt` is the project versioning mechanism; no `project_versions` table

**Status:** FINAL

**Decision.** MVP project versioning is satisfied by: the `projects` row (current state) + `projects.metadata` JSONB (open-ended extras) + `.rkt` export/import (`POST /rkt/export/{project_id}`, `/rkt/import`). No `project_versions` table.

**Rationale.** `RKT_SPEC.md` already defines a complete, human-readable, versioned (`rkt_version`) project snapshot with validation rules, and `API.md` already publishes the three endpoints. That *is* the versioning and sharing story, and it's the one the demo uses (Act 8: "Export .rkt"). An in-DB version table would additionally require snapshotting a five-level tree (project → mission → vehicle → stages → components) on every save.

**What would require it:** in-app version history/diff/restore without a file round-trip, or server-side autosave checkpoints. If that arrives, the design is a **JSONB snapshot in the `.rkt` shape** (sketched in `DATABASE_DESIGN.md` §4.15) — *not* normalized row copies, because duplicating rows across five tables means every future schema migration must also migrate historical versions.

---

## SD-5 — Telemetry: flat `float8` columns, plus attitude

**Status:** RECOMMENDED — needs **P3** sign-off (changes the persisted shape of their output)

**Decision.** Replace the three JSONB vector columns in `telemetry_points` with flat `float8` columns, and **add the attitude triple that is currently missing**. Full field list, units, and precision in [`DATABASE_CONTRACT.md`](DATABASE_CONTRACT.md) §4.9.

**I must correct an error in my own Phase-2 analysis.** I previously argued this change on volume grounds, estimating ~12,000 telemetry rows per run and ~1.2M across a demo. **That was wrong by 20×.** I used the *integrator* timestep (`dt_powered_s = 0.05`) when `SIMULATION.md` explicitly specifies a different *persistence* rate:

> **Stored data**: Every 1s for persistence, full resolution discarded

The real figures are **~600 rows per run maximum** (600s ÷ 1 Hz) and **~60,000 rows for 100 runs** — trivial for PostgreSQL. **Volume is not a reason to change anything.** The recommendation stands on different, weaker-but-still-valid grounds:

1. **Fixed shape.** `SIMULATION.md`'s state vector is a 3-DOF `[x,y,z]` triple, always present. JSONB buys flexibility that is definitionally unused.
2. **Type safety.** `float8` columns cannot hold a string or a missing key; JSONB can, and the failure surfaces at read time in the 3D viewer rather than at write time.
3. **Query ergonomics.** `WHERE altitude_m > 1000` works directly; `WHERE (position->>'z')::float > 1000` needs a cast on every access and cannot use a plain index.
4. **Free to do now.** The table is empty. There is zero migration cost today and a real one later.

**Also fixes a gap:** `SIMULATION.md`'s state vector includes `attitude [pitch, yaw, roll]`, but `telemetry_points` has no attitude columns at all. Without them, P1's 3D replay cannot orient the vehicle — it can only place it. Adding three `float8` radian columns now avoids a schema change once the 3D work starts.

**If P3 rejects:** keep JSONB. The cost is ergonomic, not existential, and at 600 rows/run it is not a performance problem. This is a preference backed by reasoning, not a blocking defect.

---

## SD-6 — Stage mass: components are authoritative; stage carries an explicit *structural remainder*

**Status:** RECOMMENDED — needs **P3** sign-off (touches the mass model) and **P1** awareness (builder UI)

**The ambiguity.** `vehicle_stages.dry_mass_kg` and `Σ vehicle_components.mass_kg` for that stage can describe the same physical mass, with nothing saying which wins. Worse, the existing `component_type` vocabulary includes `engine` and `body` — parts that are *also* naturally covered by a stage's dry mass. So the two values don't merely *risk* overlapping, they overlap by construction. Option B from the brief ("stage has its own structural dry mass, components separate") is therefore **not viable as-is** — it guarantees double-counting.

**Decision — Option C.** Redefine the stage field so the two quantities are disjoint *by definition*:

- **`vehicle_components.mass_kg` is authoritative** for every discrete, positioned part. Required anyway: `MODELS.md` computes `CG = Σ(mᵢ·xᵢ) / Σ(mᵢ)`, which is only possible from individual masses at positions.
- **`vehicle_stages.structural_dry_mass_kg` is authoritative** for stage structure *not modelled as any component* — tanks, plumbing, engine casing, skirt. Defined as **the remainder**, so it cannot double-count.
- **`vehicle_stages.propellant_mass_kg` stays authoritative.** Propellant is not a positioned discrete part and it depletes; `MODELS.md` needs it per stage for `ṁ = m_propellant / t_burn`.

**Derived, never client-writable:**

```
stage_dry_mass_kg   = structural_dry_mass_kg + Σ(components WHERE stage_id = stage)
vehicle_dry_mass_kg = Σ(stage_dry_mass_kg) + Σ(components WHERE stage_id IS NULL)
vehicle_total_mass_kg = vehicle_dry_mass_kg + Σ(propellant_mass_kg)
CG = Σ(mᵢ·xᵢ)/Σ(mᵢ)   over components, structural lumps, and propellant
```

**Why this works for both authoring styles.** A beginner who models nothing puts the whole stage mass in `structural_dry_mass_kg` with zero components — matching `DEMO_RUNBOOK.md` Act 4 ("set thrust/Isp/mass"). A detailed builder models parts and sets the remainder to the leftover structure. Both are the same rule, no modes, no ambiguity.

**Documented approximation.** A structural remainder has mass but no position, so it cannot enter the CG sum directly. **Rule: the structural remainder is assumed to act at the stage's geometric centroid**, as is the propellant. This is an approximation and must be stated in the UI and in `MODELS.md` — it is the price of allowing mass that isn't attached to a modelled part. Validation should warn when `structural_dry_mass_kg` dominates total stage mass, because CG accuracy (and therefore the stability margin the demo shows) degrades in that case.

**Contract impact.** The field rename `dry_mass_kg` → `structural_dry_mass_kg` is the mechanism that removes the ambiguity — the name *is* the contract. It touches `RKT_SPEC.md` and `API.md`. See conflict **C-7** for the migration path and the lower-disruption fallback (keep the name, document the semantics).

---

## SD-7 — Stage propulsion is over-determined (NEW FINDING)

**Status:** BLOCKED — needs **P3**

**Not in the audit brief; found while verifying SD-6.** `vehicle_stages` stores `thrust_n`, `isp_s`, `burn_time_s`, and `propellant_mass_kg` as four independent authored fields. `MODELS.md` binds them:

```
F = Isp · g₀ · ṁ        ṁ = m_propellant / t_burn        g₀ = 9.80665 m/s²
```

Only **three** are independent. The fourth is determined. **The example vehicle in `RKT_SPEC.md` is internally inconsistent** — verified numerically:

| From `RKT_SPEC.md` | Value |
|---|---|
| declared `thrust_n` | 5000 N |
| `isp_s`, `propellant_mass_kg`, `burn_time_s` | 250 s, 200 kg, 40 s |
| ṁ = 200/40 | 5.0 kg/s |
| F = Isp·g₀·ṁ | **12,258 N** — 2.45× the declared 5000 N |
| or, holding F=5000: implied burn time | **98.1 s**, not the declared 40 s |

So a simulation run from that file produces different physics depending on which fields the engine reads. This is the same class of defect as SD-6 and the same rule applies: **one authoritative source.**

**Recommendation (needs P3 to choose):**

- **Preferred — author `thrust_n`, `isp_s`, `propellant_mass_kg`; derive `burn_time_s`.** Thrust and Isp are the two real, look-up-able engine specs, and burn time is physically a *consequence* of how much propellant you loaded and how fast you burn it: `ṁ = F/(Isp·g₀)`, `t_burn = m_prop/ṁ`. This is the most physically honest arrangement and keeps the two numbers students actually reason about as inputs.
- **Fallback — keep all four authored, add a consistency validation** with a tolerance (say 1%), surfaced as a pre-flight validation error via `POST /vehicles/{id}/validate`. More disruptive to no one, and arguably *more* educational ("your numbers don't balance, here's why") — which fits the platform's fail-and-understand premise. But it leaves two values that can disagree at rest in the database, which the "one source of truth" rule was written to prevent.

**Either way `RKT_SPEC.md`'s example must be corrected**, because it currently teaches an impossible engine. Tracked as conflict **C-1**.

---

## SD-8 — Soft delete on `projects` only

**Status:** FINAL (P2-owned)

**Decision.** Add `projects.deleted_at TIMESTAMPTZ`. No other table gets soft delete.

**Rationale.** `DELETE /projects/{id}` cascades four levels: missions → vehicles → stages/components → simulation_runs → telemetry/events. One click irreversibly destroys a student's entire body of work. Every other user-owned entity is either shallow (`favorites`, `search_history`), already has a lifecycle field (`users.is_active`), or is regenerable (`simulation_runs`).

**Accepted cost.** Every project query must filter `WHERE deleted_at IS NULL` — permanent discipline, enforced by a partial index and a base query helper. This cost is exactly why it is not applied more widely.

**Distinct from `status = 'archived'`**, which already exists and stays: archived is a user-chosen shelf; `deleted_at` is removal with a recovery window.

---

## Decisions deferred to their owners

| # | Question | Owner | Blocks |
|---|---|---|---|
| SD-7 | Which three propulsion fields are authoritative? | P3 | Vehicle validation, `.rkt` example, builder UI |
| C-2 | Telemetry JSONB vs flat columns | P3 | `telemetry_points` DDL |
| C-3 | Does telemetry persist attitude? | P3 + P1 | 3D replay fidelity |
| C-7 | `dry_mass_kg` rename | P3 + P1 | `vehicle_stages` DDL, `.rkt` v1.1 |
| — | Telemetry retention policy | P2 + P3 | Nothing in Phase 4; decide before demo |
| — | Are projects ever shared/public? | P1 + team | Authorization model (currently strict single-owner) |
| — | `pgvector` for semantic search? | P4 | Baseline migration extensions |
