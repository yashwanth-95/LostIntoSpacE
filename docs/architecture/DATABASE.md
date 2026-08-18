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

## Migration Strategy
- Use Alembic for all migrations
- Never edit a released migration — create a new one
- Seed data lives in `database/seeds/`

## Indexing Strategy
- B-tree on all foreign keys and common filters
- GIN on tsvector columns for full-text search
- JSONB GIN indexes added only when query patterns emerge
]]>
