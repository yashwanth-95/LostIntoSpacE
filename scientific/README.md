<![CDATA[# Scientific Library — `scientific/`

## Owner: P3 (Simulation / Scientific Models)

## Purpose
Reusable scientific constants, unit conversions, atmosphere model, and propulsion utilities. Used by the simulation engine and backend.

## Structure
- `constants/` — Physical constants (g₀, R_earth, R_air, etc.)
- `units/` — Unit conversion helpers (km↔m, deg↔rad, etc.)
- `atmosphere/` — US Standard Atmosphere 1976 implementation
- `propulsion/` — Thrust, Isp, mass flow calculations
- `stability/` — Barrowman CP estimation, CG calculation
- `data/` — Tabulated reference data

## Rules
- Pure functions only — no side effects, no database, no API calls
- All functions document units in docstrings
- All constants cite their source
]]>
