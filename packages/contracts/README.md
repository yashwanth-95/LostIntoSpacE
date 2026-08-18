<![CDATA[# Shared Contracts — `packages/contracts/`

## Owner: All team members (P4 maintains)

## Purpose
**Single source of truth** for all interfaces between frontend and backend, between backend and simulation, and between backend and AI. Team members develop against these contracts using mocks before integration.

## Files

- `api.ts` — All REST API request/response TypeScript types (used by frontend)
- `simulation.py` — SimConfig, SimResult, TelemetryPoint Python dataclasses (used by backend + simulation)
- `ai.py` — AI tool schemas, prompt interfaces
- `rkt.py` / `rkt.ts` — RKT file format schema (both languages)
- `websocket.ts` — WebSocket message types
- `events.py` — Simulation event type definitions

## Rules
1. **Any change to a contract requires agreement from all affected team members**
2. Contracts are versioned — breaking changes increment version
3. Both TypeScript and Python representations must stay in sync
4. Frontend mocks API responses using these types
5. Backend validates requests/responses against these schemas
]]>
