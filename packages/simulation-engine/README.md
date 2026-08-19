<![CDATA[# @lostintospace/simulation-engine

> Physics simulation engine for LostIntoSpacE — rocket dynamics, 3D visualization, and React adapters.

**Owner: P3 (Simulation / Physics / 3D)**

## Architecture

```
┌─────────────────────────────────────────────────┐
│  Layer 4: ADAPTERS  (React hooks, R3F components)│
│  imports: react, @react-three/fiber              │
├─────────────────────────────────────────────────┤
│  Layer 3: RENDERER  (Three.js visualization)     │
│  imports: three                                  │
├─────────────────────────────────────────────────┤
│  Layer 2: SIM  (state machine, integrator, events)│
│  imports: nothing external                       │
├─────────────────────────────────────────────────┤
│  Layer 1: PHYSICS  (constants, vec3, models)     │
│  imports: nothing external                       │
├─────────────────────────────────────────────────┤
│  Layer 1.5: CORE  (domain types, validation)     │
│  imports: physics only                           │
└─────────────────────────────────────────────────┘
```

**Rules:**
- Each layer only depends on layers below it
- physics/ and sim/ have ZERO external dependencies
- physics/ and sim/ can run in Node, browser, or Web Worker
- renderer/ uses Three.js but NOT React
- adapters/ is the ONLY layer that imports React/R3F

## Usage

```typescript
// Physics + sim only (no browser deps)
import { G0, vec3, type SimConfig, type SimResult } from '@lostintospace/simulation-engine';

// 3D rendering (needs three)
import { ... } from '@lostintospace/simulation-engine/renderer';

// React integration (needs react + r3f)
import { useSimulation, RocketView } from '@lostintospace/simulation-engine/adapters';
```

## Development

```bash
cd packages/simulation-engine
npm install
npm run typecheck    # TypeScript strict check
npm test             # Run all tests
npm run test:watch   # Watch mode
```

## Integration Boundaries

| Team Member | Interface | What P3 Provides |
|-------------|-----------|-------------------|
| **P1 (Frontend)** | `adapters/` | React hooks + R3F components |
| **P2 (Backend)** | `sim/events.ts`, `core/types.ts` | Serializable types matching Pydantic schemas |
| **P4 (AI)** | `sim/events.ts` | SimEvent + FailureDetail for explanation pipeline |

## Scientific Fidelity

All models are **educational approximations**, NOT flight-certified:

| Model | Method | Source |
|-------|--------|--------|
| Gravity | g(h) = g₀·(R/(R+h))² | NIST CODATA 2018 |
| Atmosphere | US Std Atmosphere 1976 layers | USSA 1976 Table 4 |
| Drag | Fd = 0.5·ρ·v²·Cd·A | Standard aerodynamic drag |
| Thrust | F = Isp·g₀·ṁ | Tsiolkovsky rocket equation |
| Integration | RK4 fixed timestep | Classical numerical methods |
]]>
