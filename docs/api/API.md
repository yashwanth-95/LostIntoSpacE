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
| POST | `/auth/logout` | Invalidate session | Bearer |
| POST | `/auth/refresh` | Refresh access token | Refresh token |
| GET | `/auth/me` | Current user profile | Bearer |

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
| POST | `/ai/tutor` | Contextual tutoring Q&A | Bearer |

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
]]>
