<![CDATA[# Data Ingestion — `data/`

## Owner: P4 (AI / Search / Data / Integration)

## Purpose
Ingest, normalize, and cache data from external sources. Provide bundled fallback datasets for offline operation.

## Structure
- `ingestion/` — Fetchers for external APIs (NASA, etc.)
- `normalization/` — Schema validation, unit normalization
- `seeds/` — **Content only.** Initial seed content — space object records, lesson text, demo data — as source files (JSON, etc.). P4 owns and authors this content.
- `fallback/` — Bundled JSON datasets for offline mode
- `cache/` — Caching strategies
- `tests/` — Ingestion pipeline tests

## Ownership Boundary: `data/seeds/` vs `database/seeds/`
This directory does not load anything into Postgres. `data/seeds/` (and `data/fallback/`) hold the source content; `database/seeds/` (P2-owned, see `database/README.md`) holds the idempotent scripts that read this content and upsert it into the database. If content shape changes here, the loader scripts in `database/seeds/` need to change too — coordinate rather than each side guessing the other's format. See `docs/decisions/DECISION_LOG.md` #18.

## Verified External Data Sources

| Source | API/Dataset | Data | Free? | Rate Limit |
|--------|-------------|------|-------|------------|
| NASA | api.nasa.gov | APOD, NEO, Mars Rovers | Yes (API key) | 1000/hr |
| NASA | data.nasa.gov | Missions, spacecraft catalog | Yes | — |
| Open Notify | open-notify.org | ISS position | Yes | Low |
| Solar System OpenData | api.le-systeme-solaire.net | Planet/moon data | Yes | — |

## Fallback Strategy
Every external data source has a bundled JSON fallback in `fallback/`.
The application works fully offline using these files.

## Pipeline
```
External API → Fetch → Validate Schema → Normalize Units → Tag Provenance → Store → Cache
```

## Data Provenance
Every data record stores:
- `source`: Where it came from (nasa, bundled, calculated)
- `source_id`: External identifier
- `last_updated`: When last refreshed
]]>
