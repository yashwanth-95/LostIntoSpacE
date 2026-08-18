<![CDATA[# RKT File Format Specification v1.0

## Overview

`.rkt` is LostIntoSpacE's project file format. It is a JSON file with the `.rkt` extension, containing a complete project snapshot: mission, vehicle, configuration, and optional simulation results.

## File Structure

```json
{
  "rkt_version": "1.0",
  "generator": "LostIntoSpacE v0.1.0",
  "created_at": "2026-08-18T12:00:00Z",
  "updated_at": "2026-08-18T12:30:00Z",

  "project": {
    "name": "My First Rocket",
    "description": "A simple single-stage sounding rocket",
    "author": "Student Name"
  },

  "mission": {
    "name": "Suborbital Test",
    "objective": "Reach 10km altitude",
    "target": { "type": "suborbital", "target_altitude_km": 10 },
    "launch_site": {
      "name": "Satish Dhawan Space Centre",
      "latitude": 13.7199,
      "longitude": 80.2304,
      "altitude_m": 4
    },
    "environment": {
      "temperature_k": 300,
      "pressure_pa": 101325,
      "wind_speed_ms": 0,
      "wind_direction_deg": 0
    }
  },

  "vehicle": {
    "name": "Rocket Alpha",
    "stages": [
      {
        "stage_number": 1,
        "name": "First Stage",
        "dry_mass_kg": 50,
        "propellant_mass_kg": 200,
        "thrust_n": 5000,
        "isp_s": 250,
        "burn_time_s": 40,
        "drag_coefficient": 0.5,
        "reference_area_m2": 0.07
      }
    ],
    "components": [
      {
        "type": "nose",
        "name": "Ogive Nose",
        "mass_kg": 5,
        "position": { "x": 0, "y": 0, "z": 2.5 },
        "dimensions": { "length_m": 0.5, "diameter_m": 0.3 }
      }
    ]
  },

  "simulation_config": {
    "max_time_s": 600,
    "dt_powered_s": 0.05,
    "dt_coast_s": 0.1,
    "gravity_model": "inverse_square",
    "atmosphere_model": "us_standard_1976"
  },

  "results_ref": null,

  "educational_metadata": {
    "difficulty": "beginner",
    "concepts_covered": ["thrust_to_weight", "drag", "staging"],
    "related_lessons": ["propulsion-basics", "atmospheric-drag"]
  }
}
```

## Validation Rules

1. `rkt_version` must be a supported version string
2. `vehicle.stages` must have at least 1 stage
3. All mass values must be > 0
4. `thrust_n` must be > 0
5. `isp_s` must be in range [50, 500]
6. `burn_time_s` must be > 0
7. `launch_site.latitude` must be in [-90, 90]
8. `launch_site.longitude` must be in [-180, 180]
9. Total vehicle mass must be computable
10. File size must not exceed 10MB

## Security

- Validate JSON structure before parsing content
- Reject files with unexpected keys (allowlist approach)
- Sanitize all string fields (no script injection)
- Reject files exceeding size limit
- Never execute any code from .rkt files
]]>
