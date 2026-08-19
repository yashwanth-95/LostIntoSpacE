<![CDATA[# Database Architecture

## Core Schema

### users
```sql
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(255) NOT NULL UNIQUE,
    username        VARCHAR(100) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    display_name    VARCHAR(200),
    avatar_url      TEXT,
    role            VARCHAR(20) DEFAULT 'student',  -- student | educator | admin
    is_active       BOOLEAN DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_users_email ON users(email);
```

### refresh_tokens

> Added in the pre-Phase-2 architecture correction (2026-08-18). Closes the gap where `POST /auth/logout` had no mechanism to actually revoke anything, since bare stateless JWTs cannot be individually invalidated before expiry. See `docs/decisions/DECISION_LOG.md` #16.
>
> **Only refresh tokens are persisted.** Access tokens remain stateless (short-lived, `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`, verified by signature only, never hit the DB). Refresh tokens are long-lived (`JWT_REFRESH_TOKEN_EXPIRE_DAYS`), so each issued refresh token gets a row here, letting logout/rotation/incident-response actually revoke access. Never store the raw token — only a hash of it (e.g. SHA-256), the same way `password_hash` never stores a raw password.

```sql
CREATE TABLE refresh_tokens (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash      VARCHAR(255) NOT NULL,          -- hash of the refresh token, never the raw value
    issued_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ NOT NULL,
    revoked_at      TIMESTAMPTZ,                    -- set on logout or manual revocation; NULL = still valid
    replaced_by     UUID REFERENCES refresh_tokens(id),  -- set on rotation, points at the token that superseded this one
    user_agent      TEXT,
    ip_address      VARCHAR(45),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_refresh_tokens_user ON refresh_tokens(user_id);
CREATE UNIQUE INDEX idx_refresh_tokens_hash ON refresh_tokens(token_hash);
```

A refresh token is valid only if `revoked_at IS NULL AND expires_at > now()`. `POST /auth/logout` sets `revoked_at`; `POST /auth/refresh` should rotate (issue a new row, set `replaced_by` on the old one, revoke the old one) rather than reuse the same token indefinitely.

### projects
```sql
CREATE TABLE projects (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            VARCHAR(200) NOT NULL,
    description     TEXT,
    status          VARCHAR(20) DEFAULT 'draft', -- draft | active | completed | archived
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_projects_user ON projects(user_id);
```

### missions
```sql
CREATE TABLE missions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name            VARCHAR(200) NOT NULL,
    objective        TEXT,
    target_orbit    JSONB,          -- {type, altitude_km, inclination_deg}
    launch_site     JSONB,          -- {name, lat, lon, altitude_m}
    environment     JSONB,          -- {wind, temperature, pressure, date}
    status          VARCHAR(20) DEFAULT 'planning', -- planning | ready | simulated | analyzed
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_missions_project ON missions(project_id);
```

### vehicles
```sql
CREATE TABLE vehicles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mission_id      UUID NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
    name            VARCHAR(200) NOT NULL,
    total_mass_kg   FLOAT,
    total_height_m  FLOAT,
    cg_position     JSONB,          -- {x, y, z}
    cp_position     JSONB,          -- {x, y, z}
    stability_margin FLOAT,
    is_valid        BOOLEAN DEFAULT false,
    validation_errors JSONB DEFAULT '[]',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_vehicles_mission ON vehicles(mission_id);
```

### vehicle_stages
```sql
CREATE TABLE vehicle_stages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vehicle_id      UUID NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    stage_number    INT NOT NULL,
    name            VARCHAR(100),
    dry_mass_kg     FLOAT NOT NULL,
    propellant_mass_kg FLOAT NOT NULL,
    thrust_n        FLOAT NOT NULL,
    isp_s           FLOAT NOT NULL,       -- Specific impulse
    burn_time_s     FLOAT NOT NULL,
    drag_coefficient FLOAT DEFAULT 0.5,
    reference_area_m2 FLOAT,
    separation_delay_s FLOAT DEFAULT 1.0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_stages_vehicle ON vehicle_stages(vehicle_id);
CREATE UNIQUE INDEX idx_stages_order ON vehicle_stages(vehicle_id, stage_number);
```

### vehicle_components
```sql
CREATE TABLE vehicle_components (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vehicle_id      UUID NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    stage_id        UUID REFERENCES vehicle_stages(id) ON DELETE SET NULL,
    component_type  VARCHAR(50) NOT NULL,  -- nose | body | fins | engine | payload | recovery | avionics
    name            VARCHAR(100),
    mass_kg         FLOAT NOT NULL,
    position        JSONB NOT NULL,        -- {x, y, z} relative to vehicle origin
    dimensions      JSONB NOT NULL,        -- type-specific: {length, diameter} or {span, chord}
    properties      JSONB DEFAULT '{}',    -- type-specific properties
    parent_id       UUID REFERENCES vehicle_components(id),
    sort_order      INT DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_components_vehicle ON vehicle_components(vehicle_id);
```

### simulation_runs
```sql
CREATE TABLE simulation_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mission_id      UUID NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
    vehicle_id      UUID NOT NULL REFERENCES vehicles(id),
    config          JSONB NOT NULL,        -- simulation parameters
    status          VARCHAR(20) DEFAULT 'pending', -- pending | running | completed | failed | cancelled
    result_summary  JSONB,                 -- max altitude, max velocity, outcome, etc.
    duration_s      FLOAT,                 -- wall-clock time
    sim_time_s      FLOAT,                 -- simulated time
    total_steps     INT,
    outcome         VARCHAR(30),           -- success | partial | failure
    error_message   TEXT,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_simruns_mission ON simulation_runs(mission_id);
```

### telemetry_points
```sql
CREATE TABLE telemetry_points (
    id              BIGSERIAL PRIMARY KEY,
    simulation_id   UUID NOT NULL REFERENCES simulation_runs(id) ON DELETE CASCADE,
    t               FLOAT NOT NULL,
    position        JSONB NOT NULL,        -- {x, y, z}
    velocity        JSONB NOT NULL,        -- {vx, vy, vz}
    acceleration    JSONB NOT NULL,
    altitude_m      FLOAT,
    speed_ms        FLOAT,
    mass_kg         FLOAT,
    thrust_n        FLOAT,
    drag_n          FLOAT,
    dynamic_pressure_pa FLOAT,
    mach_number     FLOAT,
    stage           INT,
    phase           VARCHAR(20)
);
CREATE INDEX idx_telemetry_sim ON telemetry_points(simulation_id, t);
```

### simulation_events
```sql
CREATE TABLE simulation_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    simulation_id   UUID NOT NULL REFERENCES simulation_runs(id) ON DELETE CASCADE,
    t               FLOAT NOT NULL,
    event_type      VARCHAR(50) NOT NULL,  -- ignition | max_q | staging | apogee | failure | landing | meco
    severity        VARCHAR(20),           -- info | warning | critical | fatal
    data            JSONB DEFAULT '{}',
    description     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_events_sim ON simulation_events(simulation_id, t);
```

### failure_events
```sql
CREATE TABLE failure_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id        UUID NOT NULL REFERENCES simulation_events(id) ON DELETE CASCADE,
    subsystem       VARCHAR(50),           -- propulsion | structure | aero | trajectory | thermal
    failure_mode    VARCHAR(100),
    trigger_condition TEXT,
    trigger_state   JSONB,
    contributing_factors JSONB DEFAULT '[]',
    consequence     TEXT,
    educational_explanation TEXT,
    recommended_fix TEXT,
    related_lessons JSONB DEFAULT '[]'
);
```

### space_objects
```sql
CREATE TABLE space_objects (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(300) NOT NULL,
    category        VARCHAR(50) NOT NULL,  -- planet | moon | asteroid | star | galaxy | nebula | exoplanet | spacecraft
    subcategory     VARCHAR(100),
    description     TEXT,
    physical_data   JSONB,                 -- mass, radius, temperature, etc.
    orbital_data    JSONB,                 -- semi_major_axis, eccentricity, period, etc.
    discovery       JSONB,                 -- date, discoverer, method
    images          JSONB DEFAULT '[]',
    source          VARCHAR(100),          -- nasa | esa | bundled
    source_id       VARCHAR(200),
    last_updated    TIMESTAMPTZ,
    search_vector   TSVECTOR,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_spaceobj_category ON space_objects(category);
CREATE INDEX idx_spaceobj_search ON space_objects USING GIN(search_vector);
CREATE UNIQUE INDEX idx_spaceobj_source ON space_objects(source, source_id) WHERE source_id IS NOT NULL;
```

### lessons
```sql
CREATE TABLE lessons (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           VARCHAR(300) NOT NULL,
    slug            VARCHAR(300) NOT NULL UNIQUE,
    category        VARCHAR(50),           -- orbital_mechanics | propulsion | atmosphere | stability | mission_design
    difficulty      VARCHAR(20),           -- beginner | intermediate | advanced
    summary         TEXT,
    content         TEXT NOT NULL,          -- Markdown
    equations       JSONB DEFAULT '[]',    -- [{latex, description}]
    related_objects JSONB DEFAULT '[]',
    related_lessons JSONB DEFAULT '[]',
    prerequisites   JSONB DEFAULT '[]',
    sort_order      INT DEFAULT 0,
    search_vector   TSVECTOR,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_lessons_category ON lessons(category);
CREATE INDEX idx_lessons_search ON lessons USING GIN(search_vector);
```

### search_history
```sql
CREATE TABLE search_history (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    query           TEXT NOT NULL,
    result_count    INT,
    filters         JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_searchhist_user ON search_history(user_id, created_at DESC);
```

### conversations

> Added in the pre-Phase-2 architecture correction (2026-08-18). P2 owns Conversation/message persistence per scope; this was previously undocumented despite being listed as an explicit backend responsibility. Backs `/ai/tutor`, `/ai/failure-analysis`, `/ai/recommend`. See `docs/decisions/DECISION_LOG.md` #17.

```sql
CREATE TABLE conversations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title           VARCHAR(200),
    context_type    VARCHAR(30) NOT NULL DEFAULT 'general',  -- general | tutor | failure_analysis | recommendation
    context_ref     JSONB,          -- soft link to what the conversation is about, e.g. {"type": "mission", "id": "..."} or {"type": "simulation_run", "id": "..."} or {"type": "lesson", "id": "..."}. Intentionally not a FK: conversation history should survive deletion of the thing it was about, and the referenced entity type varies.
    status          VARCHAR(20) NOT NULL DEFAULT 'active',   -- active | archived
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_conversations_user ON conversations(user_id, updated_at DESC);
```

### messages
```sql
CREATE TABLE messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            VARCHAR(20) NOT NULL,    -- user | assistant | system
    content         TEXT NOT NULL,
    grounding       JSONB DEFAULT '[]',      -- references to the deterministic data the response is grounded in (simulation_runs, failure_events, lessons, space_objects) — enforces "AI explains, models calculate" (ARCHITECTURE.md principle #2): every AI message should be traceable to a source, not asserted on its own authority
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_messages_conversation ON messages(conversation_id, created_at);
```

Fields specific to AI providers (tool-call payloads, token usage, model name) are deliberately left out of this design — that's AI implementation detail owned by P4, not something backend should pre-decide. If P4 needs to persist those, extend `messages` with agreement, not by backend unilaterally.

## Migration Strategy
- Use Alembic for all migrations
- Never edit a released migration — create a new one
- Seed data *content* (space objects, lessons, fallback datasets) is authored by P4 in `data/seeds/` and `data/fallback/`. Seed *loading* into Postgres — the idempotent scripts that read that content and insert/upsert it — is P2's responsibility and lives in `database/seeds/`. See `database/README.md` and `data/README.md` for the full boundary statement.

## Indexing Strategy
- B-tree on all foreign keys and common filters
- GIN on tsvector columns for full-text search
- JSONB GIN indexes added only when query patterns emerge
]]>
