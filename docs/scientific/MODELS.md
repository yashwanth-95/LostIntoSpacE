<![CDATA[# Scientific Models Specification

## Gravity Model

**Type**: Analytical approximation
**Method**: Inverse-square law with altitude correction

```
g(h) = g₀ × (R_earth / (R_earth + h))²

Where:
  g₀ = 9.80665 m/s²  (standard gravity)
  R_earth = 6,371,000 m (mean Earth radius)
  h = geometric altitude (m)
```

**Assumptions**: Spherical Earth, no oblateness (J2), no lunar/solar perturbations
**Validation**: Compare against tabulated values at 0, 10, 50, 100, 400 km
**Limitations**: Not suitable for precision orbital mechanics

---

## Atmosphere Model (US Standard Atmosphere 1976)

**Type**: Educational simulation
**Method**: Layered temperature profile with hydrostatic integration

### Layers (0–86 km)

| Layer | Base Alt (km) | Base Temp (K) | Lapse Rate (K/km) |
|-------|--------------|---------------|-------------------|
| Troposphere | 0 | 288.15 | -6.5 |
| Tropopause | 11 | 216.65 | 0.0 |
| Stratosphere 1 | 20 | 216.65 | +1.0 |
| Stratosphere 2 | 32 | 228.65 | +2.8 |
| Stratopause | 47 | 270.65 | 0.0 |
| Mesosphere 1 | 51 | 270.65 | -2.8 |
| Mesosphere 2 | 71 | 214.65 | -2.0 |

### Equations

```
Temperature:  T(h) = T_base + L × (h - h_base)

If L ≠ 0:
  P(h) = P_base × (T(h) / T_base)^(-g₀ / (L × R_air))

If L = 0 (isothermal):
  P(h) = P_base × exp(-g₀ × (h - h_base) / (R_air × T_base))

Density:
  ρ(h) = P(h) / (R_air × T(h))

Where:
  R_air = 287.053 J/(kg·K)
  g₀ = 9.80665 m/s²
```

**Above 86 km**: Use exponential decay approximation (not std atm)
**Validation**: Compare against USSA76 published tables

---

## Drag Model

**Type**: Educational simulation
**Method**: Simplified aerodynamic drag

```
F_drag = 0.5 × ρ(h) × v² × Cd × A_ref

Where:
  ρ(h) = atmospheric density at altitude h
  v    = magnitude of velocity relative to air (no wind for MVP)
  Cd   = drag coefficient (user-configurable, default ~0.5)
  A_ref = reference cross-sectional area (m²)
```

**Direction**: Opposite to velocity vector
**Assumptions**: No Mach-dependent Cd curve (future enhancement), no wind, no base drag
**Limitations**: Significant simplification of real aerodynamics

---

## Thrust Model

**Type**: Analytical approximation
**Method**: Constant thrust per stage

```
F_thrust = Isp × g₀ × ṁ

Mass flow rate:
  ṁ = m_propellant / t_burn

Thrust direction: Along vehicle longitudinal axis
```

**Assumptions**: Constant Isp, constant mass flow, instantaneous ignition, no throttling
**Future**: Thrust curves, altitude-compensating nozzles

---

## Mass Model

**Type**: Analytical approximation

```
m(t) = m_total - ṁ × t_elapsed_in_stage

After stage burnout:
  m = m_total - m_propellant_stage - m_dry_stage (if jettisoned)
```

---

## Stability Model (Barrowman)

**Type**: Analytical approximation for Center of Pressure

```
CP_nose = 0.666 × L_nose  (for ogive/cone)
CP_fins estimated via Barrowman fin equations

CG = Σ(mi × xi) / Σ(mi)   (mass-weighted center)

Stability Margin = (CP - CG) / d_ref  (in calibers)

Stable if margin > 1.0 caliber (rule of thumb)
```

**Assumptions**: Low angle of attack, subsonic, axially symmetric
**Validation**: Compare against OpenRocket for simple geometries

---

## Numerical Integration (RK4)

**Type**: Numerical simulation

```
k1 = f(t, y)
k2 = f(t + dt/2, y + dt/2 × k1)
k3 = f(t + dt/2, y + dt/2 × k2)
k4 = f(t + dt, y + dt × k3)

y(t+dt) = y(t) + (dt/6)(k1 + 2k2 + 2k3 + k4)
```

**Validation**: Verify energy conservation in coast phase (no thrust, no drag)
**Timestep**: 0.05s powered, 0.1s coast
]]>
