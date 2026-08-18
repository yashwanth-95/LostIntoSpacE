<![CDATA[# Data Ingestion — `data/`

## Owner: P4 (AI / Search / Data / Integration)

## Purpose
Ingest, normalize, and cache data from external sources. Provide bundled fallback datasets for offline operation.

## Structure
- `ingestion/` — Fetchers for external APIs (NASA, etc.)
- `normalization/` — Schema validation, unit normalization
- `seeds/` — Initial seed data scripts
- `fallback/` — Bundled JSON datasets for offline mode
- `cache/` — Caching strategies
- `tests/` — Ingestion pipeline tests

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
